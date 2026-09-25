import json
import itertools
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from experiments.workshops.spatial_grounding_v1.adapters import AdapterError
from experiments.workshops.spatial_grounding_v1.camera_configuration import (
    CONFIG_PATH, camera_views, configure_study_cameras,
)
from experiments.workshops.spatial_grounding_v1 import camera_configuration as camera_config
from tools.camera_checks.analyze import rotation, project


def test_every_tabletop_object_including_banana_fits_both_exterior_views():
    root=Path(__file__).resolve().parents[1]
    registry=json.loads((root/'artifacts/workshops/spatial_grounding_v1/scene_package_20260924/scene-registry.json').read_text())
    for layout,item in registry['layouts'].items():
        capture=json.loads((root/'artifacts/workshops/spatial_grounding_v1/workstation_receipts_20260924'/item['files']['capture']['path']).read_text())
        assert 'banana' in capture['objects']
        for name,view in camera_views(item['candidate_id']).items():
            f=view['focal_px']
            camera={'K':[[f,0,640],[0,f,360],[0,0,1]],'position_world_m':view['position_env_m'],
                    'quaternion_opengl_wxyz':view['quaternion_opengl_wxyz']}
            for obj,bounds in capture['objects'].items():
                if obj=='table':continue
                points=np.array(list(itertools.product(*zip(bounds['bbox_env_local_min_xyz_m'],bounds['bbox_env_local_max_xyz_m']))))
                uv,z=project(points,camera)
                assert (z>0).all() and (uv>=36-1e-6).all() and (uv<=[1244+1e-6,684+1e-6]).all(),(layout,name,obj)


def test_every_selected_layout_has_fixed_symmetric_views_and_valid_look_direction():
    root=Path(__file__).resolve().parents[1]
    registry=json.loads((root/'artifacts/workshops/spatial_grounding_v1/scene_package_20260924/scene-registry.json').read_text())
    configs=json.loads(CONFIG_PATH.read_text())['configurations']
    assert set(configs)=={v['candidate_id'] for v in registry['layouts'].values()}
    for candidate in configs.values():
        left,right=list(candidate['views'].values())
        assert left['focal_px']==right['focal_px']
        for view in candidate['views'].values():
            vector=np.array(view['look_at_env_m'])-view['position_env_m'];vector/=np.linalg.norm(vector)
            np.testing.assert_allclose(-rotation(view['quaternion_opengl_wxyz'])[:,2],vector,atol=1e-12)
            assert view['resolution_hw']==[720,1280]


def test_config_changes_only_exterior_camera_parameters():
    key=next(iter(json.loads(CONFIG_PATH.read_text())['configurations']))
    def cam():return SimpleNamespace(height=720,width=1280,offset=SimpleNamespace(),spawn=SimpleNamespace())
    wrist=object();robot=object()
    cfg=SimpleNamespace(scene=SimpleNamespace(over_shoulder_left_camera=cam(),over_shoulder_right_camera=cam(),wrist_cam=wrist,robot=robot))
    configure_study_cameras(cfg,SimpleNamespace(candidate_id=key))
    assert cfg.scene.wrist_cam is wrist and cfg.scene.robot is robot
    assert cfg.scene.over_shoulder_left_camera.offset.convention=='opengl'
    with pytest.raises(AdapterError,match='registered'):
        camera_views('unregistered-layout')


def test_old_binding_is_rejected_before_any_native_import(tmp_path, monkeypatch):
    from experiments.workshops.spatial_grounding_v1 import robolab_jointpos_environment as jointpos
    path=tmp_path/'binding.json';path.write_text('{}')
    monkeypatch.setenv('SGW01_ENV_BINDING',str(path))
    monkeypatch.setenv('SGW01_ENV_BINDING_SHA256',jointpos._sha256(path))
    with pytest.raises(AdapterError,match='selected camera revision'):
        jointpos.JointPositionBinding.load()


def test_unknown_camera_revision_fails_closed(monkeypatch):
    monkeypatch.setenv('SGW01_CAMERA_REVISION', 'unregistered')
    with pytest.raises(AdapterError, match='Unregistered camera revision'):
        camera_config.camera_configuration_identity()


def test_stock_revision_is_explicit_and_preserves_wrist(tmp_path, monkeypatch):
    import hashlib

    path = tmp_path / 'stock_cameras.json'
    view = {
        'position_env_m': [0.9, 0, 1],
        'quaternion_opengl_wxyz': [0.653, 0.271, 0.271, 0.653],
        'focal_length_mm': 2.1, 'horizontal_aperture_mm': 5.376,
        'vertical_aperture_mm': 3.024, 'focus_distance': 28,
    }
    path.write_text(json.dumps({
        'schema': 'sgw-fixed-stock-cameras-v1',
        'revision': camera_config.STOCK_REVISION,
        'candidate_ids': ['selected'],
        'views': {'over_shoulder_left_camera': view},
    }))
    monkeypatch.setattr(camera_config, 'STOCK_CONFIG_PATH', path)
    legacy = camera_config.camera_configuration_identity()
    monkeypatch.setenv('SGW01_CAMERA_REVISION', camera_config.STOCK_REVISION)
    identity = camera_config.camera_configuration_identity()
    assert identity != legacy
    assert identity['sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()
    camera = SimpleNamespace(height=720, width=1280, offset=SimpleNamespace(), spawn=SimpleNamespace())
    wrist = object()
    cfg = SimpleNamespace(scene=SimpleNamespace(over_shoulder_left_camera=camera, wrist_cam=wrist))
    configure_study_cameras(cfg, SimpleNamespace(candidate_id='selected'))
    assert cfg.scene.wrist_cam is wrist
    assert camera.offset.pos == (0.9, 0, 1)
    assert camera.spawn.focus_distance == 28
    with pytest.raises(AdapterError, match='registered stock'):
        camera_views('unselected')


def test_retained_literal_stock_reset_matches_new_selection_without_relabeling(monkeypatch):
    import copy

    root = Path(__file__).resolve().parents[1]
    capture = json.loads((root / 'artifacts/workshops/spatial_grounding_v1/camera_checks_20260925/front-side-candidates/receipt.json').read_text())
    original = copy.deepcopy(capture)
    monkeypatch.setenv('SGW01_CAMERA_REVISION', camera_config.STOCK_REVISION)
    camera_config.verify_captured_camera_configuration(capture)
    assert capture == original
    capture['snapshots'][0]['camera']['over_shoulder_left_camera']['position_world_m'][0] += .001
    with pytest.raises(AdapterError, match='differs from the selected camera'):
        camera_config.verify_captured_camera_configuration(capture)
