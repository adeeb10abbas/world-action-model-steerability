"""Register deterministic close exterior views using both goals, before model runs."""
import hashlib,itertools,json
from pathlib import Path
import numpy as np


def quaternion(r):
    # Rotation matrix to scalar-first quaternion; stable eigenvector construction.
    x,y,z=r[0]; a,b,c=r[1]; d,e,f=r[2]
    k=np.array([[x-b-f,y+a,z+d,e-c],[y+a,b-x-f,c+e,z-d],
                [z+d,c+e,f-x-b,a-y],[e-c,z-d,a-y,x+b+f]])/3
    _,v=np.linalg.eigh(k);q=v[:, -1][[3,0,1,2]]
    return (q if q[0]>=0 else -q).tolist()


def build(repo):
    regpath=repo/'artifacts/workshops/spatial_grounding_v1/scene_package_20260924/scene-registry.json'
    reg=json.loads(regpath.read_text());result={}
    for key,item in reg['layouts'].items():
        cap=json.loads((repo/'artifacts/workshops/spatial_grounding_v1/workstation_receipts_20260924'/item['files']['capture']['path']).read_text())
        design=json.loads((repo/item['files']['design']['path']).read_text())
        pts=[];cube=None
        for name,ob in cap['objects'].items():
            if name in ['table','banana']:continue
            corners=np.array(list(itertools.product(*zip(ob['bbox_env_local_min_xyz_m'],ob['bbox_env_local_max_xyz_m']))))
            pts.extend(corners)
            if name=='rubiks_cube':cube=corners;origin=np.array(ob['geometric_center_env_local_xyz_m'])
        for target in [origin,*design['targets'].values()]:
            pts.extend(cube-origin+target)
            pts.extend(cube-origin+target+[0,0,.12])
        pts=np.array(pts);focus=(pts.min(0)+pts.max(0))/2
        views={};limit=[]
        for name,sign in [('over_shoulder_left_camera',1),('over_shoulder_right_camera',-1)]:
            pos=focus+[.25,sign*.18,.50]
            forward=focus-pos;forward/=np.linalg.norm(forward)
            right=np.cross(forward,[0,0,1]);right/=np.linalg.norm(right)
            down=np.cross(forward,right);ros=np.stack([right,down,forward],axis=1)
            xyz=(pts-pos)@ros;xy=xyz[:,:2]/xyz[:,2:]
            limit.append(min(604/abs(xy[:,0]).max(),324/abs(xy[:,1]).max()))
            views[name]={'position_env_m':pos.tolist(),'quaternion_opengl_wxyz':quaternion(ros@np.diag([1,-1,-1])),
                         'look_at_env_m':focus.tolist()}
        focal_px=float(np.floor(min(limit)/25)*25)
        for v in views.values():v.update(focal_length_mm=focal_px*5.376/1280,focal_px=focal_px,
                                         horizontal_aperture_mm=5.376,vertical_aperture_mm=3.024,
                                         resolution_hw=[720,1280])
        result[item['candidate_id']]={'layout_id':key,'family':item['family'],'side':item['side'],'views':views,
            'framing_bounds_min_m':pts.min(0).tolist(),'framing_bounds_max_m':pts.max(0).tolist()}
    return {'schema':'sgw-close-cameras-v1','revision':'close-oblique-v2-20260924',
        'basis_registry_sha256':hashlib.sha256(regpath.read_bytes()).hexdigest(),
        'method':'Layout-centered symmetric elevated oblique views; include scored objects, supports, both cube destinations, and 0.12 m lift envelope. Fit shared focal length for both exterior views with >=36 px boundary margin. Wrist unchanged.',
        'requested_by_user':'Move scene cameras closer, from the side or top, before learned-policy study.',
        'model_requests_used_for_design':0,'configurations':result}

if __name__=='__main__':
    import sys
    path=Path(sys.argv[2]);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(build(Path(sys.argv[1])),indent=2,sort_keys=True)+'\n')
