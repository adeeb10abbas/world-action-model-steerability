"""Execute the two prospectively recorded flat-table scripted checks once."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import fcntl
import json
import os
from pathlib import Path

from experiments.workshops.spatial_grounding_v1.scene_completion_parallel import (
    check_gpu_allocation, check_hashes, execute_candidate, sha,
)
from experiments.workshops.spatial_grounding_v1.recorder import atomic_json


def main():
    code = Path(__file__).resolve().parents[1]
    runtime = Path('/home/ali/sgw-scene-design-20260923')
    folder = code / 'artifacts/workshops/spatial_grounding_v1/flat_dist_prototypes_20260924'
    path = folder / 'plan.json'
    expected = '1a8ce121f99e507b794568aab55defd254f1c030550898f752a10a99775f004c'
    if sha(path) != expected:
        raise ValueError('Prototype plan changed')
    plan = json.loads(path.read_text())
    check_hashes(code, plan['source_sha256'])
    # Initial attempt failed in GLX startup under SSH's forwarded DISPLAY,
    # before simulation initialization. Preserve it and record this attempt apart.
    output = runtime / 'evidence' / (plan['id'] + '-HEADLESS-A2')
    for key in ('DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY'):
        os.environ.pop(key, None)
    output.mkdir(exist_ok=False)
    execution = {'code_root': str(code), 'runtime_root': str(runtime), 'candidate_timeout_s': 3600}
    items = []
    for name, info in plan['inputs'].items():
        source = folder / info['file']
        if sha(source) != info['sha256']:
            raise ValueError('Prototype input changed')
        design = json.loads(source.read_text())
        items.append({'id': name, 'family': 'DIST', 'side': design['side'],
                      'input_path': str(source), 'input_sha256': info['sha256'],
                      'evidence_path': str(output / name)})
    with (runtime / '.scene-completion-gpu-1.lock').open('a') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        check_gpu_allocation(1, 2)
        atomic_json(output / 'execution.json', {'plan_sha256': expected, 'gpu': 1,
                    'previous_attempt': str(runtime / 'evidence' / plan['id']),
                    'reason': 'GLX startup failed before simulation initialization or physical trials; disable inherited display forwarding.',
                    'environment': {'DISPLAY': None, 'WAYLAND_DISPLAY': None, 'XAUTHORITY': None},
                    'model_requests': 0, 'behavioral_episodes': 0})
        outcomes, errors = [], []
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = {pool.submit(execute_candidate, execution, item, 1): item for item in items}
            for future in as_completed(futures):
                item = futures[future]
                try:
                    outcomes.append(future.result())
                except Exception as error:
                    errors.append({'id': item['id'], 'error': str(error)})
                atomic_json(output / 'status.json', {'outcomes': outcomes, 'errors': errors,
                            'model_requests': 0, 'behavioral_episodes': 0})
                print(json.dumps({'completed': len(outcomes), 'errors': errors}), flush=True)
        if errors:
            raise RuntimeError(errors)


if __name__ == '__main__':
    main()
