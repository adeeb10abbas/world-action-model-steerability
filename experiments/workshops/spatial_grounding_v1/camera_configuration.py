"""Explicitly selected frozen camera revisions; legacy releases stay unchanged."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
from typing import Any
import numpy as np
from .adapters import AdapterError

CONFIG_PATH = Path(__file__).with_name('close_cameras.json')
STOCK_CONFIG_PATH = Path(__file__).with_name('stock_cameras.json')
LEGACY_REVISION = 'close-oblique-v3-full-objects-20260924'
STOCK_REVISION = 'stock-over-shoulder-official-input-v1-20260925'


def selected_configuration_path() -> Path:
    revision = os.environ.get('SGW01_CAMERA_REVISION', LEGACY_REVISION)
    if revision == LEGACY_REVISION:
        return CONFIG_PATH
    if revision == STOCK_REVISION:
        return STOCK_CONFIG_PATH
    raise AdapterError(f'Unregistered camera revision: {revision}')


def camera_configuration_identity() -> dict[str, str]:
    raw = selected_configuration_path().read_bytes()
    return {'revision': json.loads(raw)['revision'], 'sha256': hashlib.sha256(raw).hexdigest()}


def camera_views(candidate_id: str) -> dict[str, Any]:
    config = json.loads(selected_configuration_path().read_bytes())
    if config.get('schema') == 'sgw-fixed-stock-cameras-v1':
        if candidate_id not in config['candidate_ids']:
            raise AdapterError('Candidate has no registered stock camera configuration')
        return config['views']
    if config.get('schema') == 'sgw-close-cameras-v1' and candidate_id in config['configurations']:
        return config['configurations'][candidate_id]['views']
    raise AdapterError('Candidate has no registered close camera configuration')


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
        if 'focus_distance' in view:
            camera.spawn.focus_distance = view['focus_distance']
    return scene_config


def verify_captured_camera_configuration(capture: dict[str, Any]) -> None:
    """Bind retained reset facts to a selected revision without rewriting receipts."""
    if capture.get('status') != 'captured' or capture.get('model_requests') != 0:
        raise AdapterError('Camera binding requires successful model-free reset capture')
    views = camera_views(capture['candidate_id'])
    snapshot = capture['snapshots'][0]
    for name, view in views.items():
        actual = snapshot['camera'][name]
        width, height = 1280, 720
        k = [[view['focal_length_mm'] / view['horizontal_aperture_mm'] * width, 0, width / 2],
             [0, view['focal_length_mm'] / view['vertical_aperture_mm'] * height, height / 2],
             [0, 0, 1]]
        q = np.asarray(actual['quaternion_opengl_wxyz'], dtype=float)
        expected = np.asarray(view['quaternion_opengl_wxyz'], dtype=float)
        # USD Gf.Rotation preserves the real part and normalizes the axis of
        # the stock three-decimal quaternion, rather than normalizing all four.
        expected[1:] *= np.sqrt(1 - expected[0] ** 2) / np.linalg.norm(expected[1:])
        q /= np.linalg.norm(q)
        position = np.asarray(actual['position_world_m']) - snapshot['world_origin_m']
        if (actual['shape'] != [height, width, 3]
                or not actual['observation_equals_sensor_rgb']
                or not np.allclose(position, view['position_env_m'], atol=1e-6, rtol=0)
                or not (np.allclose(q, expected, atol=1e-6, rtol=0)
                        or np.allclose(q, -expected, atol=1e-6, rtol=0))
                or not np.allclose(actual['K'], k, atol=1e-4, rtol=0)):
            raise AdapterError(f'Captured {name} differs from the selected camera revision')
