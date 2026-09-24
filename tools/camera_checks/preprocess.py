"""Run pinned image-only preprocessing against captured observations, offline.

Extracts only named pure preprocessing functions/methods from hash-checked
source exports. No model construction, checkpoint loading, or network client.
"""
import ast
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
import uuid
import numpy as np
from PIL import Image
import torch
import torch.nn.functional as F
from experiments.workshops.spatial_grounding_v1.policy_observations import nano_observation, dreamzero_observation, CAMERAS


def main(root):
    pins = {'nano': '024a6d19048a6ac732ca0b23e741b5da6d38424223783b944bf539b2b6bd9a24',
            'dreamzero': '96de16927536f2b48427a6a2dcc3111d03204e1832e50e159cadf67b3fe956ac'}
    sources = {}
    for name, expected in pins.items():
        data = (root / (name+'-source.py')).read_bytes()
        assert hashlib.sha256(data).hexdigest() == expected
        sources[name] = ast.parse(data)
    names = {'_ensure_rgb_uint8_image', '_resize_rgb_uint8', '_compose_roboarena_views', '_extract_observation_image'}
    nodes = [n for n in sources['nano'].body if isinstance(n,ast.FunctionDef) and n.name in names]
    assert len(nodes) == len(names)
    ns = {'np': np, 'torch': torch, 'F': F, 'Any': Any}
    exec(compile(ast.Module(body=nodes,type_ignores=[]), 'pinned-nano-preprocessing', 'exec'), ns)
    cls = next(n for n in sources['dreamzero'].body if isinstance(n,ast.ClassDef) and n.name == 'DreamZeroClient')
    methods = [n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name in {'_extract_observation','_pack_request','_resize_image'}]
    assert len(methods) == 3
    dzns = {'np':np,'uuid':uuid}
    exec(compile(ast.Module(body=methods,type_ignores=[]), 'pinned-d1-preprocessing','exec'), dzns)
    client = SimpleNamespace(cam2_source='right',resize='pad',image_height=180,image_width=320,_env_session_id={})
    client._resize_image = lambda image,h,w: dzns['_resize_image'](client,image,h,w)
    rows = []
    inputs = []
    for receipt in sorted(root.glob('*/receipt.json')):
        with np.load(receipt.parent/'reset-1/observation.npz') as loaded:
            inputs.append((receipt.parent.name, {name: loaded[name] for name in loaded.files}))
    # Asymmetric coloured corners reveal channel swaps, flips, and view swaps.
    synthetic = {}
    for i,name in enumerate(CAMERAS):
        a=np.full((1,720,1280,3),30+i*60,dtype=np.uint8)
        for (y,x),rgb in zip([(0,0),(0,1152),(592,0),(592,1152)],[(255,0,0),(0,255,0),(0,0,255),(255,255,0)]):
            a[:,y:y+128,x:x+128]=rgb
        synthetic[name]=a
    synthetic.update(arm_joint_pos=np.zeros((1,7),np.float32),gripper_pos=np.zeros((1,1),np.float32))
    inputs.append(('synthetic-corner-check',synthetic))
    for label, arrays in inputs:
        raw={'image_obs': {name:arrays[name] for name in CAMERAS},
             'proprio_obs': {name:arrays[name] for name in ('arm_joint_pos','gripper_pos')}}
        wire=json.loads(json.dumps(nano_observation(raw),default=lambda a:a.tolist()))
        comp=ns['_extract_observation_image'](wire)
        assert comp.shape==(1080,1280,3)
        assert np.array_equal(comp[:720],arrays['wrist_cam'][0])
        for name,x in [('over_shoulder_left_camera',0),('over_shoulder_right_camera',640)]:
            assert np.array_equal(comp[720:,x:x+640],ns['_resize_rgb_uint8'](arrays[name][0],(360,640)))
        # Official default service resize; the later learned dataset transform is not exercised.
        resized=ns['_resize_rgb_uint8'](comp,(540,640))
        extracted=dzns['_extract_observation'](client,dreamzero_observation(raw))
        packed=dzns['_pack_request'](client,extracted,'camera diagnostic only')
        output=root/label/'preprocessing'
        output.mkdir(parents=True,exist_ok=False)
        Image.fromarray(resized).save(output/'nano-service-image.png')
        keymap={'over_shoulder_left_camera':'observation/exterior_image_0_left',
                'over_shoulder_right_camera':'observation/exterior_image_1_left',
                'wrist_cam':'observation/wrist_image_left'}
        for name,key in keymap.items():
            expected=np.asarray(Image.fromarray(arrays[name][0]).resize((320,180),Image.Resampling.BILINEAR))
            assert np.array_equal(packed[key],expected),key
            Image.fromarray(packed[key]).save(output/('d1-'+name+'.png'))
        if label=='synthetic-corner-check':
            # Interior of each resized patch must retain the four RGB colours.
            for key in keymap.values():
                assert packed[key][10,10].tolist()==[255,0,0]
                assert packed[key][10,310].tolist()==[0,255,0]
                assert packed[key][170,10].tolist()==[0,0,255]
                assert packed[key][170,310].tolist()==[255,255,0]
        rows.append({'input':label,'N3':{'shape':[540,640,3],'wrist_rows':[0,360],
                   'left_rectangle_xyxy':[0,360,320,540],'right_rectangle_xyxy':[320,360,640,540],
                   'composition_pixel_checks_passed':True},
                   'D1':{'shape_per_view':[180,320,3],'mapping':keymap,'pixel_checks_passed':True}})
    assert len(rows)==7, 'Expected six native layouts and one synthetic input'
    (root/'preprocessing.json').write_text(json.dumps({'status':'passed','source_sha256':pins,'checks':rows,
          'model_requests':0,'scope':'Pinned image extraction, composition and service input resize only; later learned transforms, server execution and decoded futures not checked'},indent=2)+'\n')
    print(json.dumps({'status':'passed','native_inputs':6,'synthetic_inputs':1,'model_requests':0}))

if __name__=='__main__':
    import sys
    main(Path(sys.argv[1]))
