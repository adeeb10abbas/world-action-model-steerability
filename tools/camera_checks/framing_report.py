"""Verify every registered close view covers objects, both goals and lift envelope."""
import hashlib,itertools,json
from pathlib import Path
import numpy as np
from tools.camera_checks.analyze import project
from experiments.workshops.spatial_grounding_v1.camera_configuration import CONFIG_PATH,camera_views


def main(repo,output):
    rp=repo/'artifacts/workshops/spatial_grounding_v1/scene_package_20260924/scene-registry.json'
    registry=json.loads(rp.read_text());results=[]
    for layout,item in registry['layouts'].items():
        capture=json.loads((repo/'artifacts/workshops/spatial_grounding_v1/workstation_receipts_20260924'/item['files']['capture']['path']).read_text())
        design=json.loads((repo/item['files']['design']['path']).read_text())
        objs={name:np.array(list(itertools.product(*zip(v['bbox_env_local_min_xyz_m'],v['bbox_env_local_max_xyz_m']))))
              for name,v in capture['objects'].items() if name not in ('table','banana')}
        cube=objs['rubiks_cube'];origin=capture['objects']['rubiks_cube']['geometric_center_env_local_xyz_m']
        for goal,target in {'initial':origin,**design['targets']}.items():
            for lift in [0,.12]:objs[f'cube_at_{goal}_lift_{lift}']=cube-origin+target+[0,0,lift]
        views={}
        for name,view in camera_views(item['candidate_id']).items():
            f=view['focal_px'];camera={'K':[[f,0,640],[0,f,360],[0,0,1]],'position_world_m':view['position_env_m'],
                                      'quaternion_opengl_wxyz':view['quaternion_opengl_wxyz']}
            margins=[]
            for obj,points in objs.items():
                uv,z=project(points,camera)
                margin=float(np.min(np.concatenate([uv,np.array([1280,720])-uv])))
                assert (z>0).all() and margin>=35.99,(layout,name,obj,margin)
                margins.append(margin)
            uv,_=project(cube,camera);size=np.ptp(uv,axis=0)/4
            old={**capture['cameras'][name],'K':[[500,0,640],[0,500,360],[0,0,1]]}
            olduv,_=project(cube,old);oldsize=np.ptp(olduv,axis=0)/4
            views[name]={'minimum_margin_native_px':min(margins),'cube_bbox_at_320x180_px':size.tolist(),
                         'original_cube_bbox_at_320x180_px':oldsize.tolist(),
                         'width_gain':float(size[0]/oldsize[0]),'area_gain':float(np.prod(size/oldsize))}
        results.append({'layout_id':layout,'family':item['family'],'views':views})
    summary={}
    for family in ['LAT','HEIGHT','DIST']:
        vals=[v for r in results if r['family']==family for v in r['views'].values()]
        summary[family]={'layouts':29,'cube_width_px_range':[min(v['cube_bbox_at_320x180_px'][0] for v in vals),max(v['cube_bbox_at_320x180_px'][0] for v in vals)],
                         'width_gain_range':[min(v['width_gain'] for v in vals),max(v['width_gain'] for v in vals)],
                         'minimum_margin_native_px':min(v['minimum_margin_native_px'] for v in vals)}
    report={'status':'passed','layouts':87,'exterior_views':174,'scope':'Project measured initial object/support bounds and both scripted cube destinations, including 0.12 m lift; this is geometric coverage, not occlusion or model-performance evidence.',
            'config_sha256':hashlib.sha256(CONFIG_PATH.read_bytes()).hexdigest(),'summary':summary,'details':results,'model_requests':0}
    output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(summary))

if __name__=='__main__':
    import sys
    main(Path(sys.argv[1]),Path(sys.argv[2]))
