"""Finite, hash-bound SCRIPTED scene completion; never launches learned policies.

Run with --plan /absolute/plan.json --expected-sha256 SHA256. Candidate input
paths are relative to the plan directory; every execution root is explicit.
Existing complete pass/fail receipts are reused. Partial attempts are blockers.
"""
from __future__ import annotations

import argparse
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from contextlib import ExitStack
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import threading

from .recorder import atomic_json
from .scene_completion_contract import measured_side

SCHEMA = 'sgw-scene-completion-parallel-v1'
FAMILIES = ('LAT', 'HEIGHT', 'DIST')
LAUNCHER = 'docs/scene_design_rtx/run-completion-scene.sh'
SOURCE = 'experiments/workshops/spatial_grounding_v1/'
REQUIRED_SOURCES = {LAUNCHER,
    'artifacts/workshops/spatial_grounding_v1/infrastructure/a40-20260922z-workspace.json',
    'artifacts/workshops/spatial_grounding_v1/controller_calibrations/lat-closed-pad-20260923.json',
    *(SOURCE + name for name in (
    'scene_completion_parallel.py', 'scene_completion_runner.py', 'scene_completion_verify.py',
    'scene_completion_contract.py', 'scene_design.py', 'scene_design_task.py',
    'scene_design_archive.py', 'model_blind_qualification.py', 'grasp_calibration.py',
    'scoring.py', 'fixtures.py', 'robolab_lat_qualification.py',
    'robolab_height_dist_qualification.py', 'qualification_batch_verifier.py'))}


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def relative_file(root, value):
    path = Path(value)
    if path.is_absolute() or '..' in path.parts or not path.parts:
        raise ValueError(f'Expected a contained relative file: {value}')
    return Path(root) / path


def check_hashes(root, hashes):
    if not isinstance(hashes, dict) or not hashes:
        raise ValueError('Nonempty file hashes required')
    for name, expected in hashes.items():
        if sha(relative_file(root, name)) != expected:
            raise ValueError(f'Source/runtime hash changed: {name}')


def load_plan(path, expected_sha256):
    path = Path(path).resolve()
    if sha(path) != expected_sha256:
        raise ValueError('Plan hash mismatch')
    plan = json.loads(path.read_text())
    if plan.get('schema_version') != SCHEMA or not re.fullmatch(r'[A-Za-z0-9_.-]+', plan.get('id', '')):
        raise ValueError('Invalid plan schema/id')
    for key in ('code_root', 'runtime_root', 'output_root'):
        if not Path(plan[key]).is_absolute():
            raise ValueError(f'{key} must be absolute')
    if not REQUIRED_SOURCES.issubset(plan['source_sha256']):
        raise ValueError('Plan lacks required source hashes')
    check_hashes(plan['code_root'], plan['source_sha256'])
    check_hashes(plan['runtime_root'], plan['runtime_sha256'])
    if 'evidence/assets.json' not in plan['runtime_sha256']:
        raise ValueError('Runtime asset manifest hash required')
    if (len(plan['gpus']) != 2 or len(set(plan['gpus'])) != 2
            or any(type(gpu) is not int or gpu < 0 for gpu in plan['gpus'])):
        raise ValueError('Exactly two distinct physical GPU indices required')
    if type(plan['slots_per_gpu']) is not int or not 1 <= plan['slots_per_gpu'] <= 2:
        raise ValueError('At most two single-environment processes per GPU')
    if plan['target_sides'] != {'left': 14, 'right': 15}:
        raise ValueError('Expected declared 14-left/15-right targets per family')
    if set(plan['candidates']) != set(FAMILIES):
        raise ValueError('Explicit ordered LAT/HEIGHT/DIST candidate lists required')
    if not 1 <= plan.get('candidate_timeout_s', 3600) <= 86400:
        raise ValueError('Candidate timeout must be bounded within one day')
    rows, seen = [], set()
    for family in FAMILIES:
        for entry in plan['candidates'][family]:
            item = {**entry, 'family': family}
            if (not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', item['id'])
                    or item['id'] in seen or item['side'] not in ('left', 'right')):
                raise ValueError('Invalid/duplicate candidate id or side')
            seen.add(item['id'])
            source = relative_file(path.parent, item['input'])
            if sha(source) != item['input_sha256']:
                raise ValueError(f"Candidate input hash mismatch: {item['id']}")
            design = json.loads(source.read_text())
            if design['design_id'] != item['id'] or design['family'] != family:
                raise ValueError('Candidate input identity mismatch')
            item['input_path'] = str(source.resolve())
            evidence = Path(item.get('existing_evidence', Path(plan['output_root']) / family / item['id']))
            if not evidence.is_absolute():
                raise ValueError('Existing evidence path must be absolute')
            item['evidence_path'] = str(evidence)
            rows.append(item)
    return {**plan, 'candidates_flat': rows, 'plan_path': str(path), 'plan_sha256': expected_sha256}


def read_completed(item):
    """Reuse verified outcomes without re-running physics or re-reading arrays."""
    root = Path(item['evidence_path'])
    if not root.exists():
        if item.get('existing_evidence'):
            raise ValueError(f"Declared existing evidence is absent: {root}")
        return None
    required = ('input.json', 'qualification.json', 'verification.json', 'capture.json', 'candidate.json')
    if not all((root / name).is_file() for name in required) or (root / 'raw-arrays.tar.zst.partial').exists():
        raise ValueError(f'Preserved partial attempt requires investigation: {root}')
    launch = json.loads((root / 'input.json').read_text())
    report = json.loads((root / 'verification.json').read_text())
    if report.get('qualification_sha256') != sha(root / 'qualification.json'):
        raise ValueError(f'Completed qualification hash mismatch: {root}')
    if (launch.get('design_sha256') != item['input_sha256']
            or sha(item['input_path']) != item['input_sha256']
            or launch['design'] != json.loads(Path(item['input_path']).read_text())):
        raise ValueError(f'Completed input hash/content mismatch: {root}')
    qualification = json.loads((root / 'qualification.json').read_text())
    candidate = json.loads((root / 'candidate.json').read_text())
    if qualification.get('candidate_sha256') != hashlib.sha256(json.dumps(candidate, sort_keys=True).encode()).hexdigest():
        raise ValueError(f'Qualified candidate hash mismatch: {root}')
    if candidate.get('metadata', {}).get('candidate_capture_sha256') != sha(root / 'capture.json'):
        raise ValueError(f'Qualified capture hash mismatch: {root}')
    passed = report.get('status') == 'verified_all_six_pass'
    expected_status = 'accepted_model_blind_fixture_candidate' if passed else 'rejected_model_blind_fixture_candidate'
    if (report.get('status') not in ('verified_all_six_pass', 'verified_physical_rejection')
            or qualification.get('status') != expected_status
            or report.get('candidate_id') != item['id'] or qualification.get('candidate_id') != item['id']
            or report.get('family') != item['family'] or qualification.get('family') != item['family']
            or qualification.get('action_cap') != 450
            or any(value != 0 for value in (report.get('model_requests'), report.get('behavioral_episodes'),
                                            qualification.get('model_request_count'), qualification.get('behavioral_episode_count'),
                                            launch.get('model_requests')))):
        raise ValueError(f'Invalid completed scripted receipt: {root}')
    checks = qualification.get('checks', [])
    if ([(c['goal_sign'], c['reset_index']) for c in checks] != [(s, r) for s in (1, -1) for r in range(3)]
            or any(type(c.get('passed')) is not bool for c in checks)
            or sum(c['passed'] for c in checks) != report.get('passed_checks')
            or passed != (report.get('passed_checks') == 6)):
        raise ValueError(f'Incomplete/inconsistent six-trial receipt: {root}')
    capture = json.loads((root / 'capture.json').read_text())
    if measured_side(item['family'], capture['objects']) != item['side']:
        raise ValueError(f'Measured side differs from declared side: {root}')
    return {'id': item['id'], 'family': item['family'], 'side': item['side'], 'passed': passed,
            'status': report['status'], 'passed_checks': report['passed_checks'],
            'evidence_path': str(root), 'verification_sha256': sha(root / 'verification.json'),
            'qualification_sha256': report['qualification_sha256']}


def selected_ids(rows, outcomes, target_sides):
    selected = {family: {'left': [], 'right': []} for family in dict.fromkeys(r['family'] for r in rows)}
    for row in rows:
        group = selected[row['family']][row['side']]
        if outcomes.get(row['id'], {}).get('passed') and len(group) < target_sides[row['side']]:
            group.append(row['id'])
    return selected


def next_candidate(rows, outcomes, inflight, target_sides):
    counts = {}
    for row in rows:
        key = (row['family'], row['side'])
        counts[key] = counts.get(key, 0) + bool(outcomes.get(row['id'], {}).get('passed') or row['id'] in inflight)
    for row in rows:
        if (row['id'] not in outcomes and row['id'] not in inflight
                and counts[(row['family'], row['side'])] < target_sides[row['side']]):
            return row
    return None


def check_dispatch(plan, item):
    if sha(plan['plan_path']) != plan['plan_sha256']:
        raise ValueError('Plan changed during execution')
    check_hashes(plan['code_root'], plan['source_sha256'])
    check_hashes(plan['runtime_root'], plan['runtime_sha256'])
    if sha(item['input_path']) != item['input_sha256']:
        raise ValueError('Candidate input changed before dispatch')
    if shutil.disk_usage(plan['output_root']).free < 40 * 1024 ** 3:
        raise RuntimeError('Free space below the 40 GiB floor')
    if Path(item['evidence_path']).exists():
        raise ValueError('Refusing to rerun an existing/partial attempt')


def execute_candidate(plan, item, gpu):
    from .scene_completion_verify import verify
    from .scene_design_archive import archive_arrays
    root = Path(item['evidence_path'])
    root.parent.mkdir(parents=True, exist_ok=True)
    # Intent/log survives even if the child fails before creating evidence.
    log_path = root.parent / f"{item['id']}.log"
    with log_path.open('x') as log:
        command = ['bash', str(Path(plan['code_root']) / LAUNCHER), item['input_path'], str(gpu), str(root)]
        env = {**os.environ, 'SGW_SCENE_ROOT': plan['runtime_root'], 'SGW_SCENE_CODE_ROOT': plan['code_root']}
        proc = subprocess.Popen(command, cwd=plan['code_root'], env=env, stdout=log,
                                stderr=subprocess.STDOUT, start_new_session=True)
        try:
            code = proc.wait(timeout=plan.get('candidate_timeout_s', 3600))
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
            raise
        if code:
            raise RuntimeError(f"Native candidate {item['id']} exited {code}; evidence retained")
    atomic_json(root / 'verification.json', verify(root))
    result = read_completed(item)
    archive_arrays(root)
    return result


def schedule(plan, outcomes, stop_event=None):
    """Dispatch native work only while unfilled quota exceeds in-flight work."""
    stop = stop_event or threading.Event()
    root = Path(plan['output_root'])
    root.mkdir(parents=True, exist_ok=True)
    rows, active, errors = plan['candidates_flat'], {}, []

    def status(phase):
        value = {'id': plan['id'], 'plan_sha256': plan['plan_sha256'], 'phase': phase,
                 'updated_at_utc': datetime.now(timezone.utc).isoformat(),
                 'selected_ids': selected_ids(rows, outcomes, plan['target_sides']),
                 'inflight': [{'id': item['id'], 'gpu': gpu} for item, gpu in active.values()],
                 'outcomes': [outcomes[r['id']] for r in rows if r['id'] in outcomes],
                 'errors': errors, 'model_requests': 0, 'behavioral_episodes': 0}
        atomic_json(root / 'status.json', value)
        print(json.dumps({'phase': phase, 'finished': len(outcomes), 'inflight': len(active), 'errors': len(errors)}), flush=True)
        return value

    def guarded(item, gpu):
        try:
            return execute_candidate(plan, item, gpu)
        except BaseException:
            stop.set()
            raise

    with ThreadPoolExecutor(max_workers=len(plan['gpus']) * plan['slots_per_gpu']) as executor:
        while True:
            for future in [future for future in active if future.done()]:
                item, gpu = active.pop(future)
                try:
                    outcomes[item['id']] = future.result()
                except BaseException as error:
                    errors.append({'id': item['id'], 'gpu': gpu, 'error': str(error)})
                    stop.set()
                status('draining' if stop.is_set() else 'running')
            for gpu in plan['gpus']:
                while (not stop.is_set()
                       and sum(owner == gpu for _, owner in active.values()) < plan['slots_per_gpu']):
                    item = next_candidate(rows, outcomes, {r['id'] for r, _ in active.values()}, plan['target_sides'])
                    if item is None:
                        break
                    try:
                        check_dispatch(plan, item)
                    except Exception as error:
                        errors.append({'id': item['id'], 'error': str(error)})
                        stop.set()
                        break
                    active[executor.submit(guarded, item, gpu)] = (item, gpu)
                    status('running')
            if not active:
                break
            wait(active, timeout=1, return_when=FIRST_COMPLETED)
    selected = selected_ids(rows, outcomes, plan['target_sides'])
    families = plan.get('candidates', selected)
    complete = all(len(selected.get(family, {}).get(side, [])) == count
                   for family in families for side, count in plan['target_sides'].items())
    phase = 'stopped_infrastructure_error' if errors else 'stopped_by_signal' if stop.is_set() else 'completed' if complete else 'pool_exhausted'
    return status(phase)


def check_gpu_allocation(gpu, slots):
    processes = subprocess.check_output(['nvidia-smi', f'--id={gpu}', '--query-compute-apps=pid', '--format=csv,noheader'], text=True).strip()
    if processes:
        raise RuntimeError(f'GPU {gpu} has unknown compute processes: {processes}')
    values = subprocess.check_output(['nvidia-smi', f'--id={gpu}', '--query-gpu=memory.total,memory.free',
                                      '--format=csv,noheader,nounits'], text=True).strip()
    total, free = [int(value.strip()) for value in values.split(',')]
    if total < 23000:
        raise RuntimeError(f'GPU {gpu} is smaller than the declared 24 GB allocation')
    minimum = 20000 if slots == 2 else 10000
    if free <= minimum:
        raise RuntimeError(f'GPU {gpu} free memory must exceed {minimum} MiB for {slots} slots; observed {free}')


def run(plan):
    output = Path(plan['output_root'])
    output.mkdir(parents=True, exist_ok=True)
    if Path(__file__).resolve() != (Path(plan['code_root']) / SOURCE / 'scene_completion_parallel.py').resolve():
        raise ValueError('Coordinator must run from the declared code snapshot')
    stop = threading.Event()
    with ExitStack() as stack:
        for gpu in sorted(plan['gpus']):
            lock = stack.enter_context((Path(plan['runtime_root']) / f'.scene-completion-gpu-{gpu}.lock').open('a'))
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            check_gpu_allocation(gpu, plan['slots_per_gpu'])
        for sig in (signal.SIGINT, signal.SIGTERM):
            previous = signal.signal(sig, lambda *_: stop.set())
            stack.callback(signal.signal, sig, previous)
        previous_status = output / 'status.json'
        if previous_status.exists() and json.loads(previous_status.read_text()).get('plan_sha256') != plan['plan_sha256']:
            raise ValueError('Output root belongs to a different plan')
        outcomes = {}
        for item in plan['candidates_flat']:
            completed = read_completed(item)
            if completed:
                outcomes[item['id']] = completed
            elif Path(item['evidence_path']).with_name(item['id'] + '.log').exists():
                raise ValueError(f"Preserved partial attempt log: {item['id']}")
        return schedule(plan, outcomes, stop)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--expected-sha256', required=True)
    args = parser.parse_args()
    plan = load_plan(args.plan, args.expected_sha256)
    try:
        result = run(plan)
    except Exception as error:
        # Preserve any prior progress file; this separate receipt explains why
        # preflight/resume refused to dispatch a new native attempt.
        Path(plan['output_root']).mkdir(parents=True, exist_ok=True)
        atomic_json(Path(plan['output_root']) / 'preflight_failure.json',
                    {'plan_sha256': plan['plan_sha256'], 'error': str(error), 'model_requests': 0})
        raise
    return 0 if result['phase'] == 'completed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
