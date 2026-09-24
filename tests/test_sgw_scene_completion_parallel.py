"""CPU scheduling tests; native process execution is replaced at its boundary."""
import hashlib
import importlib
import json
import copy
from pathlib import Path
import threading

import pytest


def api():
    name = 'experiments.workshops.spatial_grounding_v1.scene_completion_parallel'
    assert importlib.util.find_spec(name), 'Bounded scripted scene coordinator is missing'
    return importlib.import_module(name)


def candidate(tmp_path, name, side='left', family='LAT'):
    path = tmp_path / f'{name}.json'
    design = {'design_id': name, 'family': family,
              'centers': {'rubiks_cube': [.46, .18 if side == 'left' else -.18, .08]}}
    path.write_text(json.dumps(design))
    return {'id': name, 'family': family, 'side': side, 'input_path': str(path),
            'input_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'evidence_path': str(tmp_path / 'output' / family / name)}


def completed(item, passed=True):
    root = Path(item['evidence_path'])
    root.mkdir(parents=True)
    design = json.loads(Path(item['input_path']).read_text())
    (root / 'input.json').write_text(json.dumps({'design': design, 'design_sha256': item['input_sha256'], 'model_requests': 0}))
    (root / 'capture.json').write_text(json.dumps({'objects': {
        'rubiks_cube': {'geometric_center_env_local_xyz_m': design['centers']['rubiks_cube']}}}))
    fixture = {'candidate_id': item['id'], 'family': item['family'], 'metadata': {
        'candidate_capture_sha256': hashlib.sha256((root / 'capture.json').read_bytes()).hexdigest()}}
    (root / 'candidate.json').write_text(json.dumps(fixture))
    qualification = {'candidate_id': item['id'], 'family': item['family'], 'action_cap': 450,
                     'candidate_sha256': hashlib.sha256(json.dumps(fixture, sort_keys=True).encode()).hexdigest(),
                     'model_request_count': 0, 'behavioral_episode_count': 0,
                     'status': 'accepted_model_blind_fixture_candidate' if passed else 'rejected_model_blind_fixture_candidate',
                     'checks': [{'goal_sign': sign, 'reset_index': index, 'passed': passed}
                                for sign in (1, -1) for index in range(3)]}
    (root / 'qualification.json').write_text(json.dumps(qualification))
    (root / 'verification.json').write_text(json.dumps({
        'candidate_id': item['id'], 'family': item['family'], 'model_requests': 0, 'behavioral_episodes': 0,
        'status': 'verified_all_six_pass' if passed else 'verified_physical_rejection',
        'passed_checks': 6 if passed else 0,
        'qualification_sha256': hashlib.sha256((root / 'qualification.json').read_bytes()).hexdigest()}))


def test_inflight_reserves_quota_and_valid_failures_are_not_retried(tmp_path):
    m = api()
    rows = [candidate(tmp_path, name, side) for name, side in
            [('L0', 'left'), ('L1', 'left'), ('R0', 'right'), ('R1', 'right'), ('R2', 'right')]]
    outcomes = {'L0': {'passed': False}, 'R0': {'passed': True}}
    assert m.next_candidate(rows, outcomes, {'L1'}, {'left': 1, 'right': 2})['id'] == 'R1'
    assert m.next_candidate(rows, outcomes, {'L1', 'R1'}, {'left': 1, 'right': 2}) is None
    outcomes['L1'] = {'passed': True}
    outcomes['R1'] = {'passed': True}
    assert m.next_candidate(rows, outcomes, set(), {'left': 1, 'right': 2}) is None


def test_selection_uses_declared_order_not_completion_order(tmp_path):
    m = api()
    rows = [candidate(tmp_path, name) for name in ('first', 'second', 'third')]
    outcomes = {name: {'passed': True} for name in ('third', 'first', 'second')}
    assert m.selected_ids(rows, outcomes, {'left': 2, 'right': 0}) == {'LAT': {'left': ['first', 'second'], 'right': []}}


@pytest.mark.parametrize('passed', [True, False])
def test_resume_accepts_both_valid_outcomes_and_checks_bindings(tmp_path, passed):
    m = api()
    item = candidate(tmp_path, 'old')
    completed(item, passed)
    result = m.read_completed(item)
    assert result['passed'] is passed
    assert result['id'] == 'old'
    (Path(item['evidence_path']) / 'qualification.json').write_text('{}')
    with pytest.raises(ValueError, match='qualification hash'):
        m.read_completed(item)


def test_partial_attempt_cannot_be_restarted(tmp_path):
    m = api()
    item = candidate(tmp_path, 'partial')
    assert m.read_completed(item) is None
    Path(item['evidence_path']).mkdir(parents=True)
    with pytest.raises(ValueError, match='partial'):
        m.read_completed(item)


def test_input_drift_or_wrong_measured_side_cannot_be_reused(tmp_path):
    m = api()
    item = candidate(tmp_path, 'changed')
    completed(item)
    item['input_sha256'] = '0' * 64
    with pytest.raises(ValueError, match='input'):
        m.read_completed(item)
    item['input_sha256'] = hashlib.sha256(Path(item['input_path']).read_bytes()).hexdigest()
    item['side'] = 'right'
    with pytest.raises(ValueError, match='side'):
        m.read_completed(item)


def test_measured_side_capture_must_remain_bound_to_qualified_candidate(tmp_path):
    m = api()
    item = candidate(tmp_path, 'capture-drift')
    completed(item)
    capture = Path(item['evidence_path']) / 'capture.json'
    value = json.loads(capture.read_text())
    value['objects']['rubiks_cube']['geometric_center_env_local_xyz_m'][1] = .181
    capture.write_text(json.dumps(value))
    with pytest.raises(ValueError, match='capture hash'):
        m.read_completed(item)


def test_plan_binds_files_roots_and_gpu_slot_limit(tmp_path):
    m = api()
    code_root = Path(__file__).resolve().parents[1]
    runtime = tmp_path / 'runtime'
    (runtime / 'evidence').mkdir(parents=True)
    (runtime / 'evidence/assets.json').write_text('{}')
    row = candidate(tmp_path, 'planned')
    plan = {'schema_version': 'sgw-scene-completion-parallel-v1', 'id': 'test-plan',
            'code_root': str(code_root), 'runtime_root': str(runtime), 'output_root': str(tmp_path / 'out'),
            'source_sha256': {name: m.sha(code_root / name) for name in m.REQUIRED_SOURCES},
            'runtime_sha256': {'evidence/assets.json': m.sha(runtime / 'evidence/assets.json')},
            'gpus': [0, 1], 'slots_per_gpu': 2, 'target_sides': {'left': 14, 'right': 15},
            'candidates': {'LAT': [{'id': row['id'], 'side': 'left',
                                   'input': Path(row['input_path']).name, 'input_sha256': row['input_sha256']}],
                           'HEIGHT': [], 'DIST': []}}
    path = tmp_path / 'plan.json'
    def write(value):
        path.write_text(json.dumps(value))
        return m.sha(path)
    expected = write(plan)
    loaded = m.load_plan(path, expected)
    assert loaded['candidates_flat'][0]['input_path'] == row['input_path']
    with pytest.raises(ValueError, match='Plan hash'):
        m.load_plan(path, '0' * 64)
    bad = copy.deepcopy(plan)
    bad['slots_per_gpu'] = 3
    with pytest.raises(ValueError, match='At most two'):
        m.load_plan(path, write(bad))
    bad = copy.deepcopy(plan)
    bad['candidates']['LAT'][0]['input_sha256'] = '0' * 64
    with pytest.raises(ValueError, match='input hash'):
        m.load_plan(path, write(bad))


def test_initial_gpu_allocation_requires_idle_device_and_free_memory(monkeypatch):
    m = api()
    assert hasattr(m, 'check_gpu_allocation'), 'GPU allocation must check actual free memory'
    answers = {'processes': '', 'free': 20000}
    def query(command, **kwargs):
        if '--query-compute-apps=pid' in command:
            return answers['processes']
        assert '--query-gpu=memory.total,memory.free' in command
        return f"24576, {answers['free']}\n"
    monkeypatch.setattr(m.subprocess, 'check_output', query)
    with pytest.raises(RuntimeError, match='free memory'):
        m.check_gpu_allocation(0, 2)
    answers['free'] = 20001
    m.check_gpu_allocation(0, 2)
    answers['processes'] = '1234\n'
    with pytest.raises(RuntimeError, match='unknown compute'):
        m.check_gpu_allocation(0, 2)


def test_scheduler_runs_at_most_two_per_gpu_and_drains_after_error(tmp_path, monkeypatch):
    m = api()
    rows = [candidate(tmp_path, f'c{i}', 'left' if i % 2 == 0 else 'right') for i in range(10)]
    plan = {'id': 'test', 'output_root': str(tmp_path / 'campaign'), 'gpus': [0, 1],
            'slots_per_gpu': 2, 'target_sides': {'left': 3, 'right': 3},
            'candidates_flat': rows, 'plan_sha256': 'test'}
    started, finished, counts = [], [], {0: 0, 1: 0}
    lock, four_started = threading.Lock(), threading.Event()

    def native(plan, item, gpu):
        with lock:
            started.append(item['id'])
            counts[gpu] += 1
            assert counts[gpu] <= 2
            if len(started) == 4:
                four_started.set()
        assert four_started.wait(2)
        if item['id'] == 'c0':
            raise RuntimeError('synthetic infrastructure error')
        # Let the coordinator observe the infrastructure event while the other
        # already-owned attempts finish; no native/simulator processes are used.
        import time
        time.sleep(.03)
        with lock:
            finished.append(item['id'])
            counts[gpu] -= 1
        return {'id': item['id'], 'passed': True, 'status': 'verified_all_six_pass'}

    monkeypatch.setattr(m, 'execute_candidate', native)
    monkeypatch.setattr(m, 'check_dispatch', lambda plan, item: None)
    result = m.schedule(plan, {})
    assert result['phase'] == 'stopped_infrastructure_error'
    assert len(started) == 4
    assert set(finished) == set(started) - {'c0'}
    assert result['model_requests'] == result['behavioral_episodes'] == 0


def test_scheduler_reuses_pass_fail_and_fills_only_remaining_quota(tmp_path, monkeypatch):
    m = api()
    rows = [candidate(tmp_path, name, side) for name, side in
            [('old-pass', 'left'), ('old-fail', 'right'), ('new-right', 'right'), ('unused', 'left')]]
    plan = {'id': 'test', 'output_root': str(tmp_path / 'campaign'), 'gpus': [0, 1],
            'slots_per_gpu': 2, 'target_sides': {'left': 1, 'right': 1},
            'candidates_flat': rows, 'plan_sha256': 'test'}
    calls = []
    def native(plan, item, gpu):
        calls.append(item['id'])
        return {'id': item['id'], 'passed': True, 'status': 'verified_all_six_pass'}
    monkeypatch.setattr(m, 'execute_candidate', native)
    monkeypatch.setattr(m, 'check_dispatch', lambda plan, item: None)
    result = m.schedule(plan, {'old-pass': {'passed': True}, 'old-fail': {'passed': False}})
    assert calls == ['new-right']
    assert result['phase'] == 'completed'
    assert result['selected_ids']['LAT'] == {'left': ['old-pass'], 'right': ['new-right']}
