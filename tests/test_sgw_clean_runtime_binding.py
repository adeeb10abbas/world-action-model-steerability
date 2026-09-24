"""CPU regressions for the real frozen queue and qualified clean appearance."""
import copy
import csv
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from experiments.workshops.spatial_grounding_v1.adapters import (
    AdapterError, DreamZeroPolicyAdapter, NanoPolicyAdapter, ProductionAdapter,
)
from experiments.workshops.spatial_grounding_v1.contract import Cell
from experiments.workshops.spatial_grounding_v1.fixtures import FixtureCandidate
from experiments.workshops.spatial_grounding_v1 import robolab_jointpos_environment as jointpos
from tests.test_sgw_adapters import make_transport

QUEUE = Path(__file__).resolve().parents[1] / 'experiments/workshops/spatial_grounding_v1/spec/planned_cells.csv'


def queue_block(model):
    with QUEUE.open() as stream:
        return [r for r in csv.DictReader(stream) if r['model'] == model and r['layout_id'] == 'LAT-C01']


@pytest.mark.parametrize('model,policy,expected_seed', [
    ('N3', NanoPolicyAdapter, 2026092401), ('D1', DreamZeroPolicyAdapter, 1140),
])
def test_actual_queue_preserves_six_cell_policy_seed_and_fresh_reset_identity(model, policy, expected_seed, tmp_path):
    rows = queue_block(model)
    before = copy.deepcopy(rows)
    runtime_resets, environments, requests = [], [], []
    def environment_factory(*, cell, evidence_root):
        name = cell.row['cell_id']
        class Environment:
            closed = False
            def reset(self):
                return SimpleNamespace(snapshot={'sim_time': 0.0}, receipt={
                    'reset_id': name, 'camera_id': 'cam', 'camera_name': 'cam',
                    'fingerprint': 'a' * 64, 'temporal_cache_reset': True})
            def render_viewport(self):
                return np.zeros((8, 8, 3), dtype=np.uint8)
            def close(self):
                self.closed = True
        env = Environment()
        environments.append(env)
        return env
    original_transport = make_transport(model)
    def transport(request):
        requests.append(dict(request))
        return original_transport(request)
    adapter = ProductionAdapter(policy, transport=transport, transport_factory=lambda **_: transport,
        environment_factory=environment_factory,
        runtime_handle=SimpleNamespace(reset=lambda: runtime_resets.append(True), close=lambda: None))
    recorder = SimpleNamespace(path=tmp_path, record_reset=lambda *a, **kw: {'action_step': 0})
    for row in rows:
        adapter.reset(Cell(row), recorder)
        adapter.policy.predict({}, row['prompt'], action_step_start=0)
    adapter.close()
    assert rows == before
    assert len(rows) == len(runtime_resets) == len(requests) == 6
    assert {r['sampling_seed'] for r in requests} == {expected_seed}
    assert {r['reset_id'] for r in requests} == {r['cell_id'] for r in rows}
    assert {r['request_index'] for r in requests} == {0}
    assert all(env.closed for env in environments)


@pytest.mark.parametrize('change', [
    {'effective_policy_seed': None}, {'effective_policy_seed': True},
    {'effective_policy_seed': 1.5}, {'effective_policy_seed': '-1'},
    {'effective_policy_seed': '1141'}, {'sampling_seed': 19},
])
def test_invalid_or_conflicting_d1_seed_fails_before_reset(change):
    row = {**queue_block('D1')[0], **change}
    resets = []
    adapter = ProductionAdapter(DreamZeroPolicyAdapter, transport=lambda _: None,
        transport_factory=lambda **_: None,
        runtime_handle=SimpleNamespace(reset=lambda: resets.append(True)))
    with pytest.raises(AdapterError, match='seed'):
        adapter.reset(Cell(row), SimpleNamespace())
    assert not resets


def clean_candidate():
    return FixtureCandidate.from_json({
        'candidate_id': 'clean', 'family': 'LAT', 'seed': 77,
        'task_asset': '/relocated/scene.usda', 'asset_manifest_sha256': 'a' * 64,
        'object_poses': {name: {'position_m': [.46, .18, .08], 'quaternion_wxyz': [1, 0, 0, 0]}
                         for name in ('rubiks_cube', 'bowl')},
        'metadata': {'scoring_center_offsets_root_local_m': {'rubiks_cube': [0, 0, 0], 'bowl': [0, 0, 0]},
            'visual_style': 'clean-studio-v1', 'native_scene': {
            'asset': '/relocated/scene.usda', 'object_names': ['rubiks_cube', 'bowl', 'banana', 'table']}}})


def test_clean_appearance_is_applied_to_real_runtime_config_from_candidate_metadata():
    candidate = clean_candidate()
    spawn = SimpleNamespace(texture_file='office.hdr', color=(1, 1, 1), intensity=1000.0,
                            visible_in_primary_ray=False)
    config = SimpleNamespace(scene=SimpleNamespace(dome_light=SimpleNamespace(spawn=spawn)))
    assert hasattr(jointpos, 'configure_clean_appearance'), 'Clean runtime appearance binding is missing'
    result = jointpos.configure_clean_appearance(config, candidate)
    assert result is config
    assert vars(spawn) == {'texture_file': '', 'color': (.65, .67, .70), 'intensity': 500.0,
                           'visible_in_primary_ray': True}


@pytest.mark.parametrize('style', [None, 'original-office', 'unknown'])
def test_missing_or_unknown_appearance_cannot_silently_use_office_defaults(style):
    candidate = clean_candidate()
    candidate.metadata['visual_style'] = style
    assert hasattr(jointpos, 'configure_clean_appearance'), 'Clean runtime appearance binding is missing'
    with pytest.raises(AdapterError, match='appearance'):
        jointpos.configure_clean_appearance(SimpleNamespace(), candidate)


def test_missing_dome_configuration_is_a_runtime_error():
    assert hasattr(jointpos, 'configure_clean_appearance'), 'Clean runtime appearance binding is missing'
    with pytest.raises(AdapterError, match='dome'):
        jointpos.configure_clean_appearance(SimpleNamespace(), clean_candidate())


def test_environment_seed_must_match_queue_not_fixture_generation_seed(tmp_path):
    candidate = clean_candidate()
    path = tmp_path / 'candidate.json'
    from dataclasses import asdict
    path.write_text(json.dumps(asdict(candidate)))
    row = {**queue_block('N3')[0], 'status': 'RELEASED', 'fixture_sha256': 'f'}
    record = {key: row[key] for key in ('family', 'layout_id', 'fixture_sha256', 'prompt_sha256')}
    record.update(scene_seed=77, candidate_path=str(path), candidate_file_sha256=jointpos._sha256(path))
    binding = jointpos.JointPositionBinding(tmp_path, tmp_path, tmp_path / 'assets.json', 'a' * 64,
                                           {row['cell_id']: record})
    with pytest.raises(AdapterError, match='environment_seed'):
        binding.cell(row)
