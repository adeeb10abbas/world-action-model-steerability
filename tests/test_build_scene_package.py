"""Compact synthetic receipts exercise packaging, never physical qualification."""
import copy
import hashlib
import importlib
import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path
import subprocess
import sys

import pytest

from experiments.workshops.spatial_grounding_v1.fixtures import FixtureCandidate


def api():
    spec = importlib.util.find_spec('tools.build_scene_package')
    assert spec is not None, 'Portable scene package builder is missing'
    return importlib.import_module(spec.name)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + '\n')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def receipt(tmp_path, family='LAT', side='left', index=0, *, name=None, shift=None):
    name = name or f'{family}-{side}-{index:02d}'
    dx = index * .01 if shift is None else shift
    sign = 1 if side == 'left' else -1
    cube = [.46 + dx, sign * .10, .12]
    bowl = [.68 + dx, cube[1], .12]
    centers = {'rubiks_cube': cube, 'bowl': bowl}
    if family == 'DIST':
        centers['bowl'] = [.68 + dx, cube[1] + sign * .20, .12]
        centers['plate'] = [.68 + dx, cube[1] - sign * .20, .12]
    if family == 'HEIGHT':
        centers['height_upper_support'] = [cube[0], sign * .25, .16]
        centers['height_lower_support'] = [cube[0], -sign * .25, .08]
    objects = {key: {'root_position_env_local_xyz_m': value, 'root_quaternion_world_wxyz': [1., 0., 0., 0.],
                     'geometric_center_env_local_xyz_m': value,
                     'geometric_center_offset_root_local_xyz_m': [0., 0., 0.]}
               for key, value in centers.items()}
    root = tmp_path / 'evidence' / name
    scene = {'path': '/original/workstation/scene.usda', 'sha256': 'b' * 64, 'object_names': list(objects)}
    capture_hash = write(root / 'capture.json', {'objects': objects, 'scene': scene, 'model_requests': 0})
    design = {'design_id': name, 'family': family, 'side': side, 'seed': 20260923, 'centers': centers}
    design_hash = write(tmp_path / 'designs' / f'{name}.json', design)
    launch = {'design': design, 'design_sha256': design_hash, 'scene': scene, 'model_requests': 0,
              'workspace_sha256': 'd' * 64, 'asset_manifest_sha256': 'a' * 64,
              'calibration_sha256': 'c' * 64, 'robolab_commit': 'e' * 40}
    write(root / 'input.json', launch)
    scored = ('rubiks_cube', 'bowl', 'plate') if family == 'DIST' else ('rubiks_cube', 'bowl')
    candidate = {'candidate_id': name, 'family': family, 'seed': 20260923,
                 'asset_manifest_sha256': 'a' * 64, 'task_asset': scene['path'],
                 'object_poses': {key: {'position_m': centers[key], 'quaternion_wxyz': [1., 0., 0., 0.]} for key in scored},
                 'metadata': {'candidate_capture_sha256': capture_hash,
                              'scoring_center_offsets_root_local_m': {key: [0., 0., 0.] for key in scored},
                              'native_scene': {'asset': scene['path'], 'asset_sha256': scene['sha256']}}}
    write(root / 'candidate.json', candidate)
    candidate_hash = hashlib.sha256(json.dumps(asdict(FixtureCandidate.from_json(candidate)), sort_keys=True).encode()).hexdigest()
    checks = [{'goal_sign': goal, 'reset_index': reset, 'passed': True, 'actions_executed': 450,
               'score': {'requested_success': True, 'status': 'valid_model'}} for goal in (1, -1) for reset in range(3)]
    qualification = {'candidate_id': name, 'family': family, 'seed': 20260923, 'candidate_sha256': candidate_hash,
                     'action_cap': 450, 'model_request_count': 0, 'behavioral_episode_count': 0,
                     'status': 'accepted_model_blind_fixture_candidate', 'checks': checks,
                     'controller_identity': {'calibration_sha256': 'c' * 64}}
    qualification_hash = write(root / 'qualification.json', qualification)
    verification = {'candidate_id': name, 'family': family, 'status': 'verified_all_six_pass', 'passed_checks': 6,
                    'checks': checks, 'qualification_sha256': qualification_hash,
                    'scene_sha256': scene['sha256'], 'model_requests': 0, 'behavioral_episodes': 0}
    write(root / 'verification.json', verification)
    return {'candidate_id': name, 'side': side,
            'design': {'source': 'local', 'path': f'designs/{name}.json', 'sha256': design_hash},
            'evidence': {'source': 'local', 'path': f'evidence/{name}'}}


def plan(rows, family='LAT'):
    return {'seed': 20260923, 'families': {family: rows}}


def test_partial_pool_never_reports_ready_and_preserves_original_paths(tmp_path):
    row = receipt(tmp_path)
    before = (tmp_path / row['evidence']['path'] / 'candidate.json').read_bytes()
    result = api().build_package(plan([row]), {'local': tmp_path})
    assert result['status'] == 'partial'
    assert result['ready'] is False and result['learned_policy_launch_authorized'] is False
    assert result['families']['LAT']['qualified_counts'] == {'left': 1, 'right': 0}
    assert result['families']['LAT']['missing_counts'] == {'left': 13, 'right': 15}
    assert result['families']['DIST']['qualified_counts'] == {'left': 0, 'right': 0}
    saved = result['layouts']['LAT-D01']
    assert saved['files']['candidate']['path'] == row['evidence']['path'] + '/candidate.json'
    assert saved['files']['design']['sha256'] == row['design']['sha256']
    assert saved['regenerate_scene']['workspace_sha256'] == 'd' * 64
    assert (tmp_path / row['evidence']['path'] / 'candidate.json').read_bytes() == before


def test_ready_package_has_87_distinct_layouts_in_declared_order_and_balanced_stages(tmp_path):
    families = {}
    for family in ('LAT', 'HEIGHT', 'DIST'):
        families[family] = [receipt(tmp_path, family, 'left', i) for i in range(14)] + [receipt(tmp_path, family, 'right', i) for i in range(15)]
    result = api().build_package({'seed': 20260923, 'families': families}, {'local': tmp_path})
    assert result['ready'] is True and result['status'] == 'ready'
    assert len(result['layouts']) == 87
    assert len({entry['candidate_id'] for entry in result['layouts'].values()}) == 87
    for family in families:
        assert result['layouts'][family + '-P01']['candidate_id'] == f'{family}-right-00'
        assert result['layouts'][family + '-D01']['candidate_id'] == f'{family}-left-00'
        for stage, count in (('D', 2), ('C', 12)):
            assert Counter(row['side'] for key, row in result['layouts'].items() if key.startswith(f'{family}-{stage}')) == {'left': count, 'right': count}


@pytest.mark.parametrize('changed_file', ['design', 'capture', 'candidate', 'qualification'])
def test_hash_mismatch_rejects_candidate(tmp_path, changed_file):
    row = receipt(tmp_path)
    path = tmp_path / row['design']['path'] if changed_file == 'design' else tmp_path / row['evidence']['path'] / (changed_file + '.json')
    value = json.loads(path.read_text())
    if changed_file == 'candidate':
        value['metadata']['tamper'] = 'changed'
        write(path, value)
    else:
        path.write_text(path.read_text() + '\n')
    result = api().build_package(plan([row]), {'local': tmp_path})
    assert result['families']['LAT']['qualified_counts'] == {'left': 0, 'right': 0}
    assert len(result['rejections']) == 1
    assert 'hash' in result['rejections'][0]['reason'].lower()


@pytest.mark.parametrize('family', ['LAT', 'HEIGHT', 'DIST'])
def test_measured_side_disagreement_is_rejected(tmp_path, family):
    row = receipt(tmp_path, family)
    row['side'] = 'right'
    result = api().build_package(plan([row], family), {'local': tmp_path})
    assert 'side' in result['rejections'][0]['reason']
    assert not result['layouts']


def test_repeated_goal_or_failed_trial_cannot_be_counted_as_six_passes(tmp_path):
    row = receipt(tmp_path)
    root = tmp_path / row['evidence']['path']
    q = json.loads((root / 'qualification.json').read_text())
    q['checks'][-1] = copy.deepcopy(q['checks'][0])
    qhash = write(root / 'qualification.json', q)
    v = json.loads((root / 'verification.json').read_text())
    v['qualification_sha256'] = qhash
    write(root / 'verification.json', v)
    result = api().build_package(plan([row]), {'local': tmp_path})
    assert 'six' in result['rejections'][0]['reason']
    q['checks'][-1].update(goal_sign=-1, reset_index=2, passed=False)
    q['checks'][-1]['score']['requested_success'] = False
    q['status'] = 'rejected_model_blind_fixture_candidate'
    v.update(qualification_sha256=write(root / 'qualification.json', q), status='verified_physical_rejection', passed_checks=5)
    v['checks'] = q['checks']
    write(root / 'verification.json', v)
    result = api().build_package(plan([row]), {'local': tmp_path})
    assert result['rejections'][0]['status'] == 'physical_rejection'
    assert result['rejections'][0]['passed_checks'] == 5


def test_geometry_duplicates_and_repeated_candidate_ids_stay_out_of_registry(tmp_path):
    first = receipt(tmp_path)
    duplicate = receipt(tmp_path, name='same-geometry', shift=.002)
    result = api().build_package(plan([first, duplicate, first]), {'local': tmp_path})
    assert len(result['layouts']) == 1
    assert len(result['rejections']) == 2
    assert any('geometry' in row['reason'] for row in result['rejections'])
    assert any('candidate ID' in row['reason'] for row in result['rejections'])


def test_missing_evidence_is_pending_and_archive_receipt_does_not_require_raw_decompression(tmp_path):
    complete = receipt(tmp_path)
    pending = copy.deepcopy(complete)
    pending['candidate_id'] = 'pending'
    pending['evidence']['path'] = 'evidence/pending'
    root = tmp_path / complete['evidence']['path']
    write(root / 'archive.json', {'status': 'verified_lossless_archive', 'archive_sha256': 'f' * 64,
                                'archive_bytes': 123, 'verified_files': 100, 'verified_bytes': 456})
    result = api().build_package(plan([complete, pending]), {'local': tmp_path})
    assert result['families']['LAT']['pending_count'] == 1
    assert len(result['rejections']) == 0
    archive = result['layouts']['LAT-D01']['raw_archive']
    assert archive['sha256'] == 'f' * 64 and archive['contents_reverified'] is False


def test_cli_writes_partial_registry_with_nonzero_readiness_exit(tmp_path):
    api()
    source = tmp_path / 'plan.json'
    write(source, plan([receipt(tmp_path)]))
    output = tmp_path / 'package.json'
    result = subprocess.run([sys.executable, '-m', 'tools.build_scene_package', '--plan', str(source),
                             '--source-root', 'local=' + str(tmp_path), '--output', str(output)],
                            text=True, capture_output=True)
    assert result.returncode == 2, result.stderr
    assert json.loads(output.read_text())['status'] == 'partial'
    assert 'partial' in result.stdout


def test_reset_rejection_is_retained_when_physical_goal_succeeded(tmp_path):
    row = receipt(tmp_path)
    root = tmp_path / row['evidence']['path']
    q = json.loads((root / 'qualification.json').read_text())
    q['checks'][-1].update(passed=False, reset_error='reset exceeded tolerance')
    q['status'] = 'rejected_model_blind_fixture_candidate'
    v = json.loads((root / 'verification.json').read_text())
    v.update(qualification_sha256=write(root / 'qualification.json', q),
             status='verified_physical_rejection', passed_checks=5, checks=q['checks'])
    write(root / 'verification.json', v)
    result = api().build_package(plan([row]), {'local': tmp_path})
    assert result['rejections'][0]['status'] == 'physical_rejection'
    assert result['rejections'][0]['passed_checks'] == 5


def test_unresolved_earlier_candidate_keeps_selection_provisional(tmp_path):
    rows = [receipt(tmp_path, 'LAT', 'left', i) for i in range(14)] + [receipt(tmp_path, 'LAT', 'right', i) for i in range(15)]
    pending = copy.deepcopy(rows[0])
    pending['candidate_id'] = 'earlier-pending'
    pending['evidence']['path'] = 'missing-earlier-receipts'
    result = api().build_package(plan([pending, *rows]), {'local': tmp_path})
    assert result['families']['LAT']['missing_counts'] == {'left': 0, 'right': 0}
    assert result['families']['LAT']['ready'] is False
    assert result['families']['LAT']['selection_order_resolved'] is False


def test_identical_captured_float_quaternions_do_not_create_artificial_pose_error(tmp_path):
    row = receipt(tmp_path)
    root = tmp_path / row['evidence']['path']
    capture = json.loads((root / 'capture.json').read_text())
    capture['objects']['rubiks_cube']['root_quaternion_world_wxyz'] = [.9999999, 0., 0., 0.]
    candidate = json.loads((root / 'candidate.json').read_text())
    candidate['object_poses']['rubiks_cube']['quaternion_wxyz'] = [.9999999, 0., 0., 0.]
    candidate['metadata']['candidate_capture_sha256'] = write(root / 'capture.json', capture)
    write(root / 'candidate.json', candidate)
    qualification = json.loads((root / 'qualification.json').read_text())
    qualification['candidate_sha256'] = hashlib.sha256(json.dumps(asdict(FixtureCandidate.from_json(candidate)), sort_keys=True).encode()).hexdigest()
    verification = json.loads((root / 'verification.json').read_text())
    verification['qualification_sha256'] = write(root / 'qualification.json', qualification)
    write(root / 'verification.json', verification)
    result = api().build_package(plan([row]), {'local': tmp_path})
    assert result['families']['LAT']['qualified_counts']['left'] == 1
