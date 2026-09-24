"""Materialize a complete physical scene registry offline; never create a release.

See docs/SCENE_MATERIALIZATION.md for inputs, output paths and runtime limits.
Only base-asset paths may change. Recorded evidence is read, never rewritten.
"""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import csv
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Mapping

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experiments.workshops.spatial_grounding_v1.build_asset_manifest import referenced_usd_assets
from experiments.workshops.spatial_grounding_v1.fixtures import FixtureCandidate
from experiments.workshops.spatial_grounding_v1.runtime import D1_ROBOLAB_CLIENT_COMMIT
from experiments.workshops.spatial_grounding_v1.scene_design import write_scene
from tools.build_scene_package import FAMILIES, _duplicate, _inspect, _require, _resolve

PINNED_ROBOLAB_COMMIT = D1_ROBOLAB_CLIENT_COMMIT
SOURCE = Path(__file__).resolve().parents[1]
SPEC = Path('experiments/workshops/spatial_grounding_v1/spec')
BASE_SCENE = Path('assets/scenes/rubiks_cube_banana_bowl.usda')
AUTHORING_SOURCES = (
    Path('tools/materialize_scene_handoff.py'), Path('tools/build_scene_package.py'),
    Path('experiments/workshops/spatial_grounding_v1/scene_design.py'),
    Path('experiments/workshops/spatial_grounding_v1/prospective_family_scene.py'),
)
STATUS = 'physical_qualified_runtime_pending'


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _json(path: Path) -> dict:
    return json.loads(path.read_text())


def _write(path: Path, value: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n')
    return _sha(path)


def _record(path: Path) -> dict:
    return {'path': str(path.resolve()), 'sha256': _sha(path), 'bytes': path.stat().st_size}


def _verify_checkout(root: Path, commit: str, *, untracked: bool, exclude_assets: bool = False) -> None:
    _require(not (untracked and exclude_assets), 'Full source verification cannot exclude assets')
    try:
        actual = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True, stderr=subprocess.PIPE).strip()
        _require(len(commit) == 40 and actual == commit, f'Source commit mismatch: {root}')
        # RoboLab payloads are checked against the exact used dependency manifest
        # below. Avoid refreshing/hashing its unrelated Git-LFS assets here.
        check = (['diff', '--name-only', 'HEAD', '--', '.', ':(exclude)assets/**'] if exclude_assets else
                 ['status', '--porcelain', '--untracked-files=' + ('normal' if untracked else 'no')])
        dirty = subprocess.check_output(['git', '-C', str(root), *check], text=True)
    except (OSError, subprocess.CalledProcessError) as error:
        raise ValueError(f'Missing committed source checkout: {root}') from error
    _require(not dirty, f'Source checkout is dirty: {root}')


def _relocated_assets(path: Path, robolab: Path) -> tuple[dict, dict]:
    original = _json(path)
    _require(original.get('schema_version') == 'sgw-01-robolab-asset-manifest-v1', 'Unsupported asset manifest')
    _require(original['robolab_commit'] == PINNED_ROBOLAB_COMMIT, 'Asset manifest RoboLab commit mismatch')
    old_root = Path(original['robolab_root'])
    _require(old_root.is_absolute() and '..' not in old_root.parts, 'Original RoboLab root must be absolute')
    _require(Path(original['scene']['path']) == old_root / BASE_SCENE, 'Asset manifest binds a different base scene')
    relocated = copy.deepcopy(original)
    relocated['robolab_root'] = str(robolab)
    files, changes = set(), []
    for old, new in zip((original['scene'], *original['assets']), (relocated['scene'], *relocated['assets']), strict=True):
        old_path = Path(old['path'])
        _require(old_path.is_relative_to(old_root) and '..' not in old_path.parts, 'Asset path escapes original root')
        local = (robolab / old_path.relative_to(old_root)).resolve()
        _require(local.is_relative_to(robolab) and local not in files, 'Duplicate or escaping asset path')
        _require(local.is_file() and local.stat().st_size == old['bytes'] and _sha(local) == old['sha256'],
                 f'Changed or missing asset payload: {local}')
        files.add(local)
        new['path'] = str(local)
        changes.append({'original': old['path'], 'relocated': str(local), 'sha256': old['sha256']})
    dependencies = set(referenced_usd_assets(robolab / BASE_SCENE, robolab))
    _require(files == dependencies, 'Asset manifest does not cover the exact base-scene dependencies')
    return relocated, {'original_manifest': _record(path), 'path_changes': changes,
                       'allowed_changes': ['robolab_root', 'scene.path', 'assets[*].path'],
                       'payload_bytes_unchanged': True}


def _selected(registry: Mapping, roots: Mapping[str, Path]) -> dict:
    _require(registry.get('schema_version') == 'sgw-portable-scene-package-v1' and
             registry.get('ready') is True and registry.get('status') == 'ready',
             'A ready complete physical scene registry is required')
    labels = [f'{family}-{stage}{i:02d}' for family in FAMILIES
              for stage, n in (('P', 1), ('D', 4), ('C', 24)) for i in range(1, n + 1)]
    _require(set(registry['layouts']) == set(labels), 'Registry must contain exactly the 87 frozen layout IDs')
    pilot = ('left', 'right')[registry['seed'] % 2]
    _require(registry['pilot_side'] == pilot, 'Registry pilot side disagrees with seed')
    selected, seen = {}, set()
    for family in FAMILIES:
        state = registry['families'][family]
        _require(state['ready'] is True and state['selection_order_resolved'] is True and state['selected_count'] == 29,
                 'Registry family is incomplete or selection order unresolved')
        geometry = []
        for label in (label for label in labels if label.startswith(family + '-')):
            entry = registry['layouts'][label]
            _require(entry['family'] == family and entry['candidate_id'] not in seen, 'Duplicate or cross-family layout candidate')
            seen.add(entry['candidate_id'])
            for ref in entry['files'].values():
                path = _resolve(ref, roots)
                _require(_sha(path) == ref['sha256'], f'Registry file hash mismatch for {label}: {path}')
            candidate_ref = entry['files']['candidate']
            evidence = {'source': candidate_ref['source'], 'path': str(Path(candidate_ref['path']).parent)}
            inspected, measured = _inspect({'candidate_id': entry['candidate_id'], 'side': entry['side'],
                                            'design': entry['files']['design'], 'evidence': evidence}, family, roots)
            _require(inspected['status'] == 'qualified' and inspected['passed_checks'] == 6,
                     f'Layout lacks six passing physical checks: {label}')
            for key in ('candidate_id', 'family', 'side', 'status', 'passed_checks', 'files', 'regenerate_scene'):
                _require(entry[key] == inspected[key], f'Registry layout binding mismatch: {label}/{key}')
            _require(not any(_duplicate(measured, old) for old in geometry), 'Duplicate measured layout geometry')
            geometry.append(measured)
            selected[label] = {'entry': entry, 'design': _json(_resolve(entry['files']['design'], roots)),
                               'input': _json(_resolve(entry['files']['input'], roots)),
                               'candidate': _json(_resolve(candidate_ref, roots))}
        _require(selected[family+'-P01']['entry']['side'] == pilot, 'Layout pilot side mismatch')
        for stage, per_side in (('D', 2), ('C', 12)):
            for i in range(1, per_side * 2 + 1):
                _require(selected[f'{family}-{stage}{i:02d}']['entry']['side'] == ('left' if i <= per_side else 'right'),
                         'Layout side quota mismatch')
        for side in ('left', 'right'):
            ordered = [selected[label]['entry']['declared_ordinal'] for label in labels
                       if label.startswith(family+'-') and selected[label]['entry']['side'] == side]
            _require(all(type(i) is int for i in ordered) and ordered == sorted(set(ordered)),
                     'Layout assignment differs from declared candidate order')
    return selected


def _planned_cells(source: Path) -> tuple[list, dict]:
    prompts = _json(source / SPEC / 'prompts.json')['prompts']
    lookup = {p['prompt_id']: p for p in prompts}
    _require(len(prompts) == len(lookup) == 18, 'Expected frozen 18-prompt registry')
    with (source / SPEC / 'planned_cells.csv').open(newline='') as stream:
        rows = list(csv.DictReader(stream))
    _require(len(rows) == 1044 and len({row['cell_id'] for row in rows}) == 1044, 'Expected 1044 unique frozen cells')
    groups, seeds = {}, {}
    for row in rows:
        p = lookup[row['prompt_id']]
        _require(row['status'] == 'PLANNED_NOT_RELEASED' and row['action_cap'] == '450' and
                 not any(row[key] for key in ('fixture_sha256', 'runtime_sha256', 'time_map_sha256')),
                 'Source queue must remain frozen and unreleased')
        _require(row['model'] in ('N3', 'D1') and row['family'] in FAMILIES and
                 row['layout_id'].startswith(row['family']+'-'+row['stage']), 'Cell layout/family mismatch')
        goal = int(row['physical_goal_sign'])
        _require((row['family'], row['form'], goal, row['prompt'], row['prompt_sha256']) ==
                 (p['family'], p['form'], p['physical_goal_sign'], p['text'], p['sha256']) and
                 hashlib.sha256(p['text'].encode()).hexdigest() == p['sha256'], 'Cell prompt binding mismatch')
        _require(row['cell_id'] == f'{row["layout_id"]}-{row["model"]}-{row["form"]}-' + ('POS' if goal == 1 else 'NEG'),
                 'Cell ID differs from layout/form/goal')
        seed = int(row['environment_seed'])
        _require(str(seed) == row['environment_seed'] and seed >= 0, 'Invalid frozen environment seed')
        seeds.setdefault(row['layout_id'], set()).add(seed)
        groups.setdefault((row['layout_id'], row['model']), []).append((row['form'], goal))
    conditions = Counter((form, goal) for form in ('D', 'C', 'I') for goal in (1, -1))
    _require(len(groups) == 174 and all(Counter(group) == conditions for group in groups.values()) and
             all(len(values) == 1 for values in seeds.values()), 'Cells lack intact matched six-condition blocks')
    return rows, {name: _record(source / SPEC / name) for name in ('protocol.json', 'prompts.json', 'planned_cells.csv')}


def materialize(*, registry: Path, source_roots: Mapping[str, Path | str], workspaces: list[Path],
                assets_manifest: Path, robolab_root: Path, source_root: Path,
                source_commit: str, output: Path) -> dict:
    """Write a destination-specific physical handoff, with no runtime qualification."""
    registry, assets_manifest, output = Path(registry).resolve(), Path(assets_manifest).resolve(), Path(output).resolve()
    source, robolab = Path(source_root).resolve(), Path(robolab_root).resolve()
    roots = {key: Path(value).resolve() for key, value in source_roots.items()}
    _require(not output.exists(), 'Handoff output must be a new directory')
    _require(not output.is_relative_to(source) and not output.is_relative_to(robolab), 'Output must be outside clean source checkouts')
    package = _json(registry)
    selected = _selected(package, roots)
    _verify_checkout(source, source_commit, untracked=True)
    _verify_checkout(robolab, PINNED_ROBOLAB_COMMIT, untracked=False, exclude_assets=True)
    for relative in AUTHORING_SOURCES:
        _require(_sha(source / relative) == _sha(SOURCE / relative), f'Executing authoring source differs from pinned checkout: {relative}')
    assets, relocation = _relocated_assets(assets_manifest, robolab)
    workspace_files = {_sha(Path(path)): Path(path).resolve() for path in workspaces}
    rows, frozen = _planned_cells(source)
    _require({row['layout_id'] for row in rows} == set(selected), 'Queue and registry layout sets differ')
    for label, data in selected.items():
        original, launch, design = data['candidate'], data['input'], data['design']
        _require(launch['workspace_sha256'] in workspace_files, f'Matching measured workspace absent: {label}')
        _require(launch['asset_manifest_sha256'] == _sha(assets_manifest) and launch['robolab_commit'] == PINNED_ROBOLAB_COMMIT,
                 'Qualification differs from original asset manifest or RoboLab pin')
        _require(design.get('visual_style') == original['metadata'].get('visual_style') == 'clean-studio-v1',
                 'Geometry/appearance input is not the qualified clean scene')
        _require(original['task_asset'] == original['metadata']['native_scene']['asset'] == launch['scene']['path'],
                 'Candidate task/native scene path mismatch')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.'+output.name+'-', dir=output.parent) as temp:
        staging = Path(temp)
        assets_hash = _write(staging/'assets.json', assets)
        relocation['relocated_manifest'] = {'path': str(output/'assets.json'), 'sha256': assets_hash}
        _write(staging/'asset-relocation.json', relocation)
        layouts = {}
        for label, data in selected.items():
            original, launch, design, entry = data['candidate'], data['input'], data['design'], data['entry']
            workspace_path = workspace_files[launch['workspace_sha256']]
            prefix = Path('layouts')/label
            scene = write_scene(design, _json(workspace_path), robolab, staging/prefix/'scene.usda')
            authored = (staging/prefix/'scene.usda').read_bytes()
            new_reference = ('@'+str(robolab/BASE_SCENE).replace('\\', '\\\\')+'@').encode()
            old_reference = ('@'+str(Path(_json(assets_manifest)['robolab_root'])/BASE_SCENE).replace('\\', '\\\\')+'@').encode()
            _require(authored.count(new_reference) == 1, 'Overlay must have one exact base-asset reference')
            restored = authored.replace(new_reference, old_reference, 1)
            _require(hashlib.sha256(restored).hexdigest() == launch['scene']['sha256'],
                     f'Regenerated geometry/appearance differs from recorded scene: {label}')
            _require(scene['object_names'] == original['metadata']['native_scene']['object_names'],
                     'Regenerated native object inventory changed')
            scene_ref = {'path': str(output/prefix/'scene.usda'), 'sha256': scene['sha256']}
            derived = copy.deepcopy(original)
            derived['asset_manifest_sha256'] = assets_hash
            derived['task_asset'] = scene_ref['path']
            derived['metadata']['native_scene'].update(asset=scene_ref['path'], asset_sha256=scene_ref['sha256'])
            FixtureCandidate.from_json(derived)
            candidate_hash = _write(staging/prefix/'candidate.json', derived)
            candidate_ref = {'path': str(output/prefix/'candidate.json'), 'sha256': candidate_hash}
            physical = {'schema_version': 'sgw-physical-layout-handoff-v1', 'status': STATUS,
                'layout_id': label, 'family': entry['family'], 'side': entry['side'], 'candidate_id': entry['candidate_id'],
                'candidate': candidate_ref, 'native_scene': scene_ref, 'assets_manifest_sha256': assets_hash,
                'original_evidence': entry['files'], 'original_candidate_sha256': entry['files']['candidate']['sha256'],
                'original_scene_sha256': launch['scene']['sha256'], 'workspace': _record(workspace_path),
                'derivation': {'allowed_candidate_changes': ['asset_manifest_sha256', 'task_asset',
                    'metadata.native_scene.asset', 'metadata.native_scene.asset_sha256'],
                    'recorded_scene_restored_by_base_path_substitution': True,
                    'original_receipts_modified': False},
                'runtime_qualified': False, 'learned_policy_launch_authorized': False}
            fixture_hash = _write(staging/prefix/'physical-fixture.json', physical)
            layouts[label] = {'candidate_id': entry['candidate_id'], 'family': entry['family'], 'side': entry['side'],
                'fixture_sha256': fixture_hash, 'physical_fixture_path': str(output/prefix/'physical-fixture.json'),
                'candidate': candidate_ref, 'native_scene': scene_ref}
        fixtures = {'schema_version': 'sgw-physical-fixtures-pending-runtime-v1', 'status': STATUS,
                    'runtime_qualified': False, 'time_maps': {}, 'layouts': layouts,
                    'learned_policy_launch_authorized': False}
        _write(staging/'physical-fixtures.json', fixtures)
        cells = {}
        with (staging/'bound-cells.jsonl').open('w') as stream:
            for row in rows:
                layout = layouts[row['layout_id']]
                cells[row['cell_id']] = {'family': row['family'], 'layout_id': row['layout_id'],
                    'candidate_id': layout['candidate_id'], 'fixture_sha256': layout['fixture_sha256'],
                    'prompt_sha256': row['prompt_sha256'], 'scene_seed': int(row['environment_seed']),
                    'candidate_path': layout['candidate']['path'], 'candidate_file_sha256': layout['candidate']['sha256'],
                    'native_scene_files': [layout['native_scene']]}
                stream.write(json.dumps({**row, 'fixture_sha256': layout['fixture_sha256']}, sort_keys=True)+'\n')
        binding = {'schema_version': 'sgw-jointpos-environment-binding-v1', 'status': STATUS,
            'source_root': str(source), 'source_commit': source_commit, 'robolab_root': str(robolab),
            'robolab_commit': PINNED_ROBOLAB_COMMIT, 'assets_manifest': str(output/'assets.json'),
            'assets_manifest_sha256': assets_hash, 'cells': cells, 'runtime_qualified': False,
            'learned_policy_launch_authorized': False}
        _write(staging/'environment-binding.json', binding)
        shutil.copyfile(registry, staging/'selection-registry.json')
        result = {'schema_version': 'sgw-offline-scene-handoff-v1', 'status': STATUS,
            'layout_count': len(layouts), 'cell_count': len(cells), 'runtime_qualified': False,
            'learned_policy_launch_authorized': False, 'model_requests': 0, 'native_runs': 0,
            'selection_registry': _record(registry), 'source_roots': {k: str(v) for k,v in roots.items()},
            'source_root': str(source), 'source_commit': source_commit, 'frozen_sources': frozen,
            'authoring_source_sha256': {str(p): _sha(source/p) for p in AUTHORING_SOURCES},
            'files': {name: {'path': str(output/name), 'sha256': _sha(staging/name)} for name in
                ('assets.json', 'asset-relocation.json', 'physical-fixtures.json', 'environment-binding.json',
                 'bound-cells.jsonl', 'selection-registry.json')},
            'remaining_gates': ['destination native reset and rendering checks', 'N3/D1 runtime qualification',
                                'verified physical time and camera maps', 'explicit learned-study release authorization']}
        _write(staging/'handoff.json', result)
        _require(not output.exists(), 'Handoff output appeared during materialization')
        staging.rename(output)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('registry', 'assets-manifest', 'robolab-root', 'source-root', 'output'):
        parser.add_argument('--'+name, required=True, type=Path)
    parser.add_argument('--source-commit', required=True)
    parser.add_argument('--evidence-root', action='append', required=True, metavar='ALIAS=PATH')
    parser.add_argument('--workspace', type=Path, action='append', required=True)
    args = parser.parse_args()
    roots = {}
    for item in args.evidence_root:
        key, separator, value = item.partition('=')
        if not key or not separator or not value or key in roots:
            parser.error('Evidence roots require unique ALIAS=PATH values')
        roots[key] = Path(value)
    result = materialize(registry=args.registry, source_roots=roots, workspaces=args.workspace,
        assets_manifest=args.assets_manifest, robolab_root=args.robolab_root, source_root=args.source_root,
        source_commit=args.source_commit, output=args.output)
    print(json.dumps({key: result[key] for key in ('status', 'layout_count', 'cell_count', 'runtime_qualified')}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
