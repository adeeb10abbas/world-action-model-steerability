import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from experiments.workshops.spatial_grounding_v1.adapters import AdapterError
from experiments.workshops.spatial_grounding_v1.camera_configuration import (
    CONFIG_PATH, camera_views, configure_study_cameras,
)
from tools.camera_checks.analyze import rotation


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
    with pytest.raises(AdapterError,match='close camera revision'):
        jointpos.JointPositionBinding.load()
