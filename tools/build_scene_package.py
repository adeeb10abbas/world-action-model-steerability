"""Package compact, independently verified scenes without running a simulator.

Usage::

    python tools/build_scene_package.py --plan selection.json \
        --source-root repo=/path/to/repo --source-root evidence=/path/to/receipts \
        --output scene-registry.json

Plan format (list order is the caller's prospectively declared selection order)::

    {"seed": 20260923, "families": {"LAT": [{
      "candidate_id": "example", "side": "left",
      "design": {"source": "repo", "path": "designs/example.json", "sha256": "..."},
      "evidence": {"source": "evidence", "path": "example"}
    }], "HEIGHT": [], "DIST": []}}

Optional ``registration`` metadata is copied into the registry for provenance.
This tool preserves supplied order; it cannot establish when it was declared.
Exit 0 means scene quotas are complete; exit 2 writes a truthful partial package.
Neither status authorizes learned-policy execution. Raw archives are not opened.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any, Mapping

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experiments.workshops.spatial_grounding_v1.fixtures import FixtureCandidate, Pose, pose_error
from experiments.workshops.spatial_grounding_v1.scene_completion_contract import measured_side


FAMILIES = ('LAT', 'HEIGHT', 'DIST')
PAIRS = {(goal, reset) for goal in (1, -1) for reset in range(3)}
FILES = ('candidate', 'input', 'capture', 'qualification', 'verification')


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve(ref: Mapping[str, Any], roots: Mapping[str, Path]) -> Path:
    _require(ref['source'] in roots, f"Unknown source root: {ref['source']}")
    relative = Path(ref['path'])
    _require(not relative.is_absolute() and '..' not in relative.parts, 'References must stay relative to their explicit source root')
    base = roots[ref['source']].resolve()
    resolved = (base / relative).resolve()
    _require(resolved.is_relative_to(base), 'Reference escapes its explicit source root')
    return resolved


def _file_ref(base: Mapping[str, Any], name: str, path: Path) -> dict[str, Any]:
    return {'source': base['source'], 'path': (Path(base['path']) / name).as_posix(),
            'sha256': _sha(path), 'bytes': path.stat().st_size}


def _six_checks(checks: list[Mapping[str, Any]], label: str) -> None:
    _require(len(checks) == 6 and {(c['goal_sign'], c['reset_index']) for c in checks} == PAIRS,
             f'{label} requires six unique goal/reset checks')


def _inspect(row: Mapping[str, Any], family: str, roots: Mapping[str, Path]) -> tuple[dict[str, Any], dict[str, Pose]]:
    directory = _resolve(row['evidence'], roots)
    data = {name: json.loads((directory / (name + '.json')).read_text()) for name in FILES}
    candidate_data, launch, capture, qualification, verification = [data[name] for name in FILES]
    candidate = FixtureCandidate.from_json(candidate_data)
    design_path = _resolve(row['design'], roots)
    design = json.loads(design_path.read_text())
    _require(_sha(design_path) == row['design']['sha256'] == launch['design_sha256'], 'Design hash mismatch')
    _require(design == launch['design'], 'Recorded design differs from declared input')
    _require(candidate.candidate_id == row['candidate_id'] == design['design_id'] == qualification['candidate_id'] == verification['candidate_id'], 'Candidate identity mismatch')
    _require(candidate.family == family == design['family'] == qualification['family'] == verification['family'], 'Family mismatch')
    _require(candidate.seed == qualification['seed'] == design['seed'], 'Candidate seed mismatch')
    candidate_hash = hashlib.sha256(json.dumps(asdict(candidate), sort_keys=True).encode()).hexdigest()
    _require(candidate_hash == qualification['candidate_sha256'], 'Candidate content hash mismatch')
    _require(_sha(directory / 'capture.json') == candidate.metadata['candidate_capture_sha256'], 'Capture hash mismatch')
    _require(_sha(directory / 'qualification.json') == verification['qualification_sha256'], 'Qualification hash mismatch')
    scene_hash = launch['scene']['sha256']
    _require(scene_hash == verification['scene_sha256'] == capture['scene']['sha256'], 'Scene hash binding mismatch')
    native_scene = candidate.metadata.get('native_scene', {})
    if 'asset_sha256' in native_scene:
        _require(native_scene['asset_sha256'] == scene_hash, 'Candidate scene hash mismatch')
    _require(candidate.asset_manifest_sha256 == launch['asset_manifest_sha256'], 'Asset manifest hash mismatch')
    _require(qualification['controller_identity']['calibration_sha256'] == launch['calibration_sha256'], 'Controller calibration hash mismatch')
    _require(qualification['action_cap'] == 450, 'Qualification action cap differs from 450')
    _require(qualification['model_request_count'] == qualification['behavioral_episode_count'] == 0
             and verification['model_requests'] == verification['behavioral_episodes'] == 0
             and launch['model_requests'] == capture['model_requests'] == 0, 'Evidence is not model blind')
    objects = capture['objects']
    side = measured_side(family, objects)
    _require(side == row['side'], 'Declared side disagrees with measured side')
    if family != 'LAT':
        _require(design['side'] == side, 'Design side disagrees with measured side')
    for name, pose in candidate.object_poses.items():
        observed = objects[name]
        measured = Pose.from_json({'position_m': observed['root_position_env_local_xyz_m'],
                                   'quaternion_wxyz': observed['root_quaternion_world_wxyz']})
        error = max(abs(a - b) for a, b in zip(pose.position_m, measured.position_m))
        # Compare the captured components directly: a float quaternion's norm
        # can be slightly below one even when these two receipts are identical.
        quaternion_error = min(max(abs(a - sign * b) for a, b in zip(pose.quaternion_wxyz, measured.quaternion_wxyz))
                               for sign in (1, -1))
        _require(error <= 1e-6 and quaternion_error <= 1e-6, 'Candidate pose differs from bound capture')
        _require(math.dist(candidate.scoring_poses()[name].position_m, observed['geometric_center_env_local_xyz_m']) <= 1e-6,
                 'Candidate scoring center differs from bound capture')
    _six_checks(qualification['checks'], 'Qualification')
    _six_checks(verification['checks'], 'Independent verification')
    passed = sum(check['passed'] is True for check in verification['checks'])
    _require(passed == verification['passed_checks'], 'Independent verification pass count differs')
    qchecks = {(c['goal_sign'], c['reset_index']): c for c in qualification['checks']}
    for check in verification['checks']:
        original = qchecks[(check['goal_sign'], check['reset_index'])]
        _require(original['passed'] is check['passed'], 'Qualification and independent verification disagree')
        _require(original['actions_executed'] == 450, 'Qualification trial is missing its 450-action endpoint')
        for result in (check, original):
            expected_pass = result['score']['requested_success'] is True and result.get('reset_error') is None
            _require(expected_pass is result['passed'], 'Recorded physical/reset success and pass flag disagree')
    accepted = passed == 6
    _require(verification['status'] == ('verified_all_six_pass' if accepted else 'verified_physical_rejection'), 'Verification status differs from six checks')
    _require(qualification['status'] == ('accepted_model_blind_fixture_candidate' if accepted else 'rejected_model_blind_fixture_candidate'), 'Qualification status differs from six checks')
    entry = {
        'candidate_id': candidate.candidate_id, 'family': family, 'side': side,
        'status': 'qualified' if accepted else 'physical_rejection', 'passed_checks': passed,
        'files': {name: _file_ref(row['evidence'], name + '.json', directory / (name + '.json')) for name in FILES},
        'regenerate_scene': {
            'writer': 'experiments.workshops.spatial_grounding_v1.scene_design.write_scene',
            'workspace_sha256': launch['workspace_sha256'], 'robolab_commit': launch['robolab_commit'],
            'asset_manifest_sha256': launch['asset_manifest_sha256'], 'calibration_sha256': launch['calibration_sha256'],
            'recorded_scene_sha256': scene_hash,
            'instructions': 'Load the exact design and matching measured workspace; call write_scene(design, workspace, pinned_robolab_root, new_output_path). Preserve original receipts. The USD embeds the external base-scene path, so relocation may change its byte hash; validate regenerated geometry before use.',
        },
    }
    entry['files']['design'] = {**row['design'], 'bytes': design_path.stat().st_size}
    archive_path = directory / 'archive.json'
    if archive_path.is_file():
        archive = json.loads(archive_path.read_text())
        _require(archive['status'] == 'verified_lossless_archive', 'Archive receipt is not independently verified')
        entry['files']['archive'] = _file_ref(row['evidence'], 'archive.json', archive_path)
        entry['raw_archive'] = {'source': row['evidence']['source'], 'path': (Path(row['evidence']['path']) / 'raw-arrays.tar.zst').as_posix(),
                                'sha256': archive['archive_sha256'], 'bytes': archive['archive_bytes'],
                                'file_present': (directory / 'raw-arrays.tar.zst').is_file(),
                                'contents_reverified': False, 'basis': 'Recorded verified_lossless_archive receipt'}
    geometry = {name: Pose(tuple(obj['geometric_center_env_local_xyz_m']), tuple(obj['root_quaternion_world_wxyz']))
                for name, obj in objects.items() if name not in ('banana', 'table')}
    return entry, geometry


def _duplicate(first: Mapping[str, Pose], second: Mapping[str, Pose]) -> bool:
    return set(first) == set(second) and all(pose_error(first[name], second[name])[0] <= .003
                                           and pose_error(first[name], second[name])[1] <= 2 for name in first)


def build_package(plan: Mapping[str, Any], source_roots: Mapping[str, Path | str]) -> dict[str, Any]:
    """Return a partial or complete registry; missing evidence never earns a slot."""
    seed = plan['seed']
    _require(isinstance(seed, int) and not isinstance(seed, bool), 'Plan seed must be an integer')
    _require(isinstance(plan['families'], dict) and set(plan['families']).issubset(FAMILIES), 'Unknown plan family')
    roots = {key: Path(value).resolve() for key, value in source_roots.items()}
    pilot_side = ('left', 'right')[seed % 2]
    required = {side: 14 + int(side == pilot_side) for side in ('left', 'right')}
    families, layouts, inventory, rejections = {}, {}, [], []
    seen_ids = set()
    for family in FAMILIES:
        rows = plan['families'].get(family, [])
        _require(isinstance(rows, list), 'Each family must supply an ordered candidate list')
        groups = {'left': [], 'right': []}
        geometries = []
        pending_rows = []
        for ordinal, row in enumerate(rows):
            record = {'candidate_id': row.get('candidate_id'), 'family': family, 'ordinal': ordinal,
                      'declared_side': row.get('side'), 'evidence': row.get('evidence')}
            try:
                _require(row['candidate_id'] not in seen_ids, 'Duplicate candidate ID in declared plan')
                seen_ids.add(row['candidate_id'])
                _require(row['side'] in ('left', 'right'), 'Declared side must be left or right')
                entry, geometry = _inspect(row, family, roots)
                entry['declared_ordinal'] = ordinal
                record.update(status=entry['status'], passed_checks=entry['passed_checks'])
                if entry['status'] == 'physical_rejection':
                    record['reason'] = 'Independent verification retained a physical/reset failure'
                    record['files'] = entry['files']
                    rejections.append(record)
                else:
                    _require(not any(_duplicate(geometry, prior) for prior in geometries), 'Duplicate measured geometry within 3 mm / 2 degrees')
                    geometries.append(geometry)
                    groups[entry['side']].append(entry)
            except FileNotFoundError as error:
                record.update(status='pending_evidence', reason=str(error))
                pending_rows.append(record)
            except (ValueError, KeyError, TypeError) as error:
                record.update(status='invalid_evidence', reason=str(error))
                rejections.append(record)
            inventory.append(record)
        counts = {side: len(group) for side, group in groups.items()}
        missing = {side: max(0, required[side] - counts[side]) for side in required}
        if groups[pilot_side]:
            layouts[family + '-P01'] = groups[pilot_side].pop(0)
        for stage, per_side in (('D', 2), ('C', 12)):
            for offset, side in enumerate(('left', 'right')):
                selected, groups[side] = groups[side][:per_side], groups[side][per_side:]
                for index, entry in enumerate(selected, start=1 + offset * per_side):
                    layouts[f'{family}-{stage}{index:02d}'] = entry
        selected_entries = [entry for label, entry in layouts.items() if label.startswith(family + '-')]
        order_resolved = not any(pending['ordinal'] < max(
            (entry['declared_ordinal'] for entry in selected_entries if entry['side'] == pending['declared_side']), default=-1)
            for pending in pending_rows)
        families[family] = {'ready': not any(missing.values()) and order_resolved, 'declared_count': len(rows),
                            'qualified_counts': counts, 'required_counts': required.copy(), 'missing_counts': missing,
                            'pending_count': len(pending_rows), 'selection_order_resolved': order_resolved,
                            'selected_count': len(selected_entries)}
    ready = all(value['ready'] for value in families.values())
    return {'schema_version': 'sgw-portable-scene-package-v1', 'status': 'ready' if ready else 'partial', 'ready': ready,
            'readiness_scope': 'Qualified physical scene quotas only; regenerated runtime and learned-policy release are separate.',
            'learned_policy_launch_authorized': False, 'seed': seed, 'pilot_side': pilot_side,
            'selection_rule': 'First eligible distinct candidates in each supplied family list; seeded pilot, D 2/side, C 12/side.',
            'registration': plan.get('registration'),
            'source_roots': {key: str(value) for key, value in roots.items()},
            'portability': 'Resolve each source alias against a local root; never rewrite embedded historical evidence paths.',
            'families': families, 'layouts': layouts, 'inventory': inventory, 'rejections': rejections}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--source-root', action='append', default=[], metavar='NAME=PATH', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    roots = {}
    for item in args.source_root:
        name, separator, value = item.partition('=')
        if not name or not separator or not value or name in roots:
            parser.error('Source roots require unique NAME=PATH values')
        roots[name] = Path(value)
    if args.output.exists():
        parser.error('Output exists; write a new registry snapshot')
    result = build_package(json.loads(args.plan.read_text()), roots)
    result['plan_sha256'] = _sha(args.plan)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as stream:
        stream.write(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + '\n')
    print(json.dumps({'status': result['status'], 'selected_layouts': len(result['layouts']), 'families': result['families']}))
    return 0 if result['ready'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
