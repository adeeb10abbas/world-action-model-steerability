"""Check retained and live camera geometry, synchronization, and image inventory."""
import hashlib
import itertools
import json
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw

CAMERAS=('over_shoulder_left_camera','over_shoulder_right_camera','wrist_cam')

def rotation(q):
    w,x,y,z=np.asarray(q,dtype=float)/np.linalg.norm(q)
    return np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],
                     [2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],
                     [2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])

def project(points,camera):
    p=np.atleast_2d(points)-camera['position_world_m']
    if 'quaternion_ros_wxyz' in camera:
        r=rotation(camera['quaternion_ros_wxyz'])
    else:
        r=rotation(camera['quaternion_world_wxyz']) @ np.array([[0,0,1],[-1,0,0],[0,-1,0]])
    xyz=p@r
    uv=xyz@np.array(camera['K']).T
    return uv[:,:2]/uv[:,2:],xyz[:,2]

def geometry(objects,camera):
    result={}
    for name,ob in objects.items():
        corners=ob['bbox_world_m']; center=ob['center_world_m']
        uv,z=project(corners,camera); cuv,cz=project(center,camera)
        lo,hi=uv.min(axis=0),uv.max(axis=0)
        result[name]={'center_uv_px':cuv[0].tolist(),'depth_m':float(cz[0]),
            'bbox_uv_xyxy_px':[*lo.tolist(),*hi.tolist()],
            'bbox_inside_image': bool((z>0).all() and (lo>=0).all() and (hi<[1280,720]).all()),
            'center_inside_image':bool(cz[0]>0 and (cuv[0]>=0).all() and (cuv[0]<[1280,720]).all()),
            'projected_bbox_size_px':(hi-lo).tolist()}
    return result

def main(repo,root):
    registry_path=repo/'artifacts/workshops/spatial_grounding_v1/scene_package_20260924/scene-registry.json'
    registry=json.loads(registry_path.read_text())
    receipts={p.parent.name:json.loads(p.read_text()) for p in root.glob('*/receipt.json')}
    assert len(receipts)==6
    base=receipts['LAT-P01']['snapshots'][0]['camera']
    native=[]
    contact=Image.new('RGB',(1440,6*294),'white')
    for row,(layout,receipt) in enumerate(sorted(receipts.items())):
        assert receipt['status']=='captured' and receipt['model_requests']==0
        snapshots=receipt['snapshots']; assert len(snapshots)==5
        for s in snapshots:
            cams=list(s['camera'].values())
            assert len({c['frame'] for c in cams})==1
            assert np.ptp([c['sensor_timestamp_s'] for c in cams])<1e-8
            for name,c in s['camera'].items():
                assert c['observation_equals_sensor_rgb']
                assert np.allclose(c['K'],base[name]['K'],atol=1e-6)
        for a,b in zip(snapshots[:3],snapshots[1:4]):
            for name in CAMERAS:
                assert b['camera'][name]['frame']-a['camera'][name]['frame']==1
                assert abs(b['camera'][name]['sensor_timestamp_s']-a['camera'][name]['sensor_timestamp_s']-1/15)<1e-6
        reset1,reset2=snapshots[0],snapshots[-1]
        for name in CAMERAS:
            a,b=reset1['camera'][name],reset2['camera'][name]
            assert a['sensor_timestamp_s']==b['sensor_timestamp_s']==0
            assert np.allclose(a['position_world_m'],b['position_world_m'],atol=1e-6)
            assert np.allclose(rotation(a['quaternion_world_wxyz']),rotation(b['quaternion_world_wxyz']),atol=1e-6)
        # The wrist sensor is attached to the gripper base, not a fixed exterior view.
        wrist_offsets=[]
        for s in snapshots:
            g=s['gripper_base']; w=s['camera']['wrist_cam']
            offset=rotation(g['quaternion_wxyz']).T@(np.asarray(w['position_world_m'])-g['position_world_m'])
            # Report native transform rounding at a practical 0.1 mm diagnostic tolerance.
            assert np.linalg.norm(offset-[.011,-.031,-.074]) < 1e-4
            wrist_offsets.append(offset.tolist())
        projections={name:geometry(reset1['objects'],reset1['camera'][name]) for name in CAMERAS}
        for col,name in enumerate(CAMERAS):
            image=Image.open(root/layout/'reset-1'/(name+'.png')).convert('RGB')
            draw=ImageDraw.Draw(image)
            for obj,proj in projections[name].items():
                box=proj['bbox_uv_xyxy_px']; center=proj['center_uv_px']
                color=(255,70,70) if obj=='rubiks_cube' else (30,220,250)
                draw.rectangle(box,outline=color,width=3)
                draw.ellipse((center[0]-4,center[1]-4,center[0]+4,center[1]+4),fill=color)
                draw.text((box[0],box[1]-14),obj,fill=color,stroke_width=1,stroke_fill='black')
            out=root/layout/('projected-'+name+'.png');image.save(out)
            contact.paste(image.resize((480,270)),(col*480,row*294+24))
            ImageDraw.Draw(contact).text((col*480+5,row*294+5),layout+' | '+name,fill='black')
        native.append({'layout_id':layout,'status':'passed','camera_streams':3,'reset_count':2,
                       'hold_steps':3,'synchronized_sensor_updates':True,'exact_observation_sensor_rgb':True,
                       'wrist_mount_position_tolerance_m':1e-4,
                       'wrist_mount_position_max_error_m':max(float(np.linalg.norm(np.asarray(v)-[.011,-.031,-.074])) for v in wrist_offsets),
                       'projections':projections,
                       'reset_image_byte_identical':{n:reset1['camera'][n]['image_sha256']==reset2['camera'][n]['image_sha256'] for n in CAMERAS}})
    contact.save(root/'camera-projection-contact-sheet.jpg',quality=92)
    archived=[]
    for layout,item in registry['layouts'].items():
        ref=item['files']['capture']; path=(repo/'artifacts/workshops/spatial_grounding_v1/workstation_receipts_20260924')/ref['path']
        payload=path.read_bytes(); assert hashlib.sha256(payload).hexdigest()==ref['sha256']
        capture=json.loads(payload); objects={}
        for name,ob in capture['objects'].items():
            if name in ('table','banana'):continue
            corners=list(itertools.product(*zip(ob['bbox_env_local_min_xyz_m'],ob['bbox_env_local_max_xyz_m'])))
            objects[name]={'bbox_world_m':corners,'center_world_m':ob['geometric_center_env_local_xyz_m']}
        views={}
        for name,c in capture['cameras'].items():
            assert np.allclose(c['position_world_m'],base[name]['position_world_m'],atol=1e-7)
            assert np.allclose(rotation(c['quaternion_world_wxyz']),rotation(base[name]['quaternion_world_wxyz']),atol=1e-7)
            image=Image.open(path.parent/(name+'.png'))
            assert image.mode=='RGB' and image.size==(1280,720)
            array=np.asarray(image);assert np.ptp(array)
            views[name]={'geometry':geometry(objects,{**c,'K':base[name]['K']}),'image_sha256':hashlib.sha256((path.parent/(name+'.png')).read_bytes()).hexdigest()}
        archived.append({'layout_id':layout,'side':item['side'],'views':views,'capture_sha256':ref['sha256']})
    warnings=[]
    for layout in archived:
        for name,view in layout['views'].items():
            for obj,p in view['geometry'].items():
                if not p['bbox_inside_image']:
                    warnings.append({'layout':layout['layout_id'],'camera':name,'object':obj,'center_inside':p['center_inside_image']})
    report={'schema':'sgw-camera-alignment-check-v1','status':'mapping_and_sync_passed_with_wrist_visibility_limits',
        'registry_sha256':hashlib.sha256(registry_path.read_bytes()).hexdigest(),'native_layouts':native,
        'retained_layouts':archived,'retained_layout_count':len(archived),'retained_image_count':len(archived)*3,
        'intrinsics':{name:base[name]['K'] for name in CAMERAS},'projection_boundary_warnings':warnings,
        'model_requests':0,'learned_policy_episodes':0,'full_model_runtime_qualified':False,
        'limitations':['Geometric field of view does not prove absence of occlusion.',
                       'Native checks cover six selected layouts, not 87 fresh runs.',
                       'Sensor timestamps are reset-relative; simulator clock continues across resets.',
                       'Sensor updates do not independently measure render exposure latency.',
                       'Decoded model futures and later model transforms are not exercised.']}
    (root/'geometry-report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'native_layouts':6,'retained_images':261,'boundary_warning_count':len(warnings)}))

if __name__=='__main__':
    import sys
    main(Path(sys.argv[1]),Path(sys.argv[2]))
