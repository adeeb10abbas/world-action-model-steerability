"""Frozen close camera views for SGW-01, selected before learned-policy runs."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from typing import Any
from .adapters import AdapterError

CONFIG_PATH = Path(__file__).with_name('close_cameras.json')


def camera_configuration_identity() -> dict[str, str]:
    raw = CONFIG_PATH.read_bytes()
    return {'revision': json.loads(raw)['revision'], 'sha256': hashlib.sha256(raw).hexdigest()}


def camera_views(candidate_id: str) -> dict[str, Any]:
    config = json.loads(CONFIG_PATH.read_bytes())
    if config.get('schema') != 'sgw-close-cameras-v1' or candidate_id not in config['configurations']:
        raise AdapterError('Candidate has no registered close camera configuration')
    return config['configurations'][candidate_id]['views']


def configure_study_cameras(scene_config: Any, candidate: Any) -> Any:
    """Keep sensor names/resolution and wrist unchanged; bind both exterior views."""
    for name, view in camera_views(candidate.candidate_id).items():
        camera = getattr(scene_config.scene, name, None)
        if camera is None or (camera.height, camera.width) != (720, 1280):
            raise AdapterError('Study camera is missing or its image resolution changed')
        camera.offset.pos = tuple(view['position_env_m'])
        camera.offset.rot = tuple(view['quaternion_opengl_wxyz'])
        camera.offset.convention = 'opengl'
        camera.spawn.focal_length = view['focal_length_mm']
        camera.spawn.horizontal_aperture = view['horizontal_aperture_mm']
        camera.spawn.vertical_aperture = view['vertical_aperture_mm']
    return scene_config
