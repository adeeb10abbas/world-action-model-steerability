"""Offline synthetic handoff evidence; none of these are physical trials."""
import copy
import hashlib
import importlib
import json
from dataclasses import asdict
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

import pytest

from experiments.workshops.spatial_grounding_v1.fixtures import FixtureCandidate
from experiments.workshops.spatial_grounding_v1.scene_design import write_scene
from tests.test_build_scene_package import receipt, write
from tools.build_scene_package import build_package


ROOT = Path(__file__).resolve().parents[1]
SPEC = Path('experiments/workshops/spatial_grounding_v1/spec')


def api():
    spec = importlib.util.find_spec('tools.materialize_scene_handoff')
    assert spec is not None, 'Offline scene handoff materializer is missing'
    return importlib.import_module(spec.name)


def git_snapshot(path):
    # A disposable test checkout, never the user's working repository.
    for args in (['init', '-q'], ['add', '.'],
                 ['-c', 'user.name=Synthetic Test', '-c', 'user.email=test@example.invalid',
                  'commit', '-qm', 'Synthetic offline fixture']):
        subprocess.run(['git', '-C', str(path), *args], check=True, capture_output=True)
    return subprocess.check_output(['git', '-C', str(path), 'rev-parse', 'HEAD'], text=True).strip()


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    found = importlib.util.find_spec('tools.materialize_scene_handoff')
    module = importlib.import_module(found.name) if found else None
    source = tmp_path / 'source'
    authoring = module.AUTHORING_SOURCES if module else [Path('experiments/workshops/spatial_grounding_v1/scene_design.py')]
    for relative in (*authoring, SPEC/'protocol.json', SPEC/'prompts.json', SPEC/'planned_cells.csv'):
        destination = source / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, destination)
    source_commit = git_snapshot(source)
    robolab = tmp_path / 'robolab'
    scene = robolab / 'assets/scenes/rubiks_cube_banana_bowl.usda'
    payload = robolab / 'assets/objects/cube.usda'
    payload.parent.mkdir(parents=True)
    payload.write_text('#usda 1.0\ndef Xform "cube" {}\n')
    scene.parent.mkdir(parents=True)
    scene.write_text('#usda 1.0\n(subLayers = [@../objects/cube.usda@])\n')
    (robolab/'assets/unused.bin').write_bytes(b'unused asset')
    (robolab/'controller.py').write_text('speed = 1\n')
    robolab_commit = git_snapshot(robolab)
    if module:
        monkeypatch.setattr(module, 'PINNED_ROBOLAB_COMMIT', robolab_commit)
    old_root = Path('/recorded/RoboLab')
    def asset(path):
        return {'path': str(old_root / path.relative_to(robolab)),
                'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'bytes': path.stat().st_size}
    manifest = tmp_path / 'original-assets.json'
    manifest_hash = write(manifest, {'schema_version': 'sgw-01-robolab-asset-manifest-v1',
        'status': 'measured_asset_files_not_fixture_qualified', 'robolab_root': str(old_root),
        'robolab_commit': robolab_commit, 'scene': asset(scene), 'assets': [asset(payload)]})
    workspace = tmp_path / 'workspace.json'
    workspace_hash = write(workspace, {'synthetic_offline_workspace': True})
    evidence = tmp_path / 'evidence-root'
    families = {}
    for family in ('LAT', 'HEIGHT', 'DIST'):
        families[family] = []
        for side, count in (('left', 14), ('right', 15)):
            for i in range(count):
                row = receipt(evidence, family, side, i)
                folder = evidence / row['evidence']['path']
                design_path = evidence / row['design']['path']
                design = json.loads(design_path.read_text())
                centers = design['centers']
                supports = []
                if family == 'DIST':
                    supports = [{'name': 'plate', 'center_m': centers['plate'], 'shape': 'cylinder',
                        'radius_m': .11, 'thickness_m': .012, 'display_color_rgb': [.94, .94, .9], 'rigid_body': True}]
                design.update(visual_style='clean-studio-v1', supports=supports,
                    roots={name: p for name, p in centers.items() if name != 'plate'},
                    orientations={name: [1., 0., 0., 0.] for name in centers if name != 'plate'})
                row['design']['sha256'] = write(design_path, design)
                generated = write_scene(json.loads(design_path.read_text()), {}, old_root, folder/'scene.usda')
                generated['path'] = f'/recorded/evidence/{design["design_id"]}/scene.usda'
                capture = json.loads((folder/'capture.json').read_text())
                capture['scene'] = generated
                capture_hash = write(folder/'capture.json', capture)
                candidate = json.loads((folder/'candidate.json').read_text())
                candidate.update(task_asset=generated['path'], asset_manifest_sha256=manifest_hash)
                candidate['metadata'].update(visual_style='clean-studio-v1', candidate_capture_sha256=capture_hash,
                    native_scene={'asset': generated['path'], 'asset_sha256': generated['sha256'],
                                  'object_names': generated['object_names']})
                write(folder/'candidate.json', candidate)
                launch = json.loads((folder/'input.json').read_text())
                launch.update(design=design, design_sha256=row['design']['sha256'], scene=generated,
                    workspace_sha256=workspace_hash, asset_manifest_sha256=manifest_hash, robolab_commit=robolab_commit)
                write(folder/'input.json', launch)
                qualification = json.loads((folder/'qualification.json').read_text())
                qualification['candidate_sha256'] = hashlib.sha256(json.dumps(asdict(FixtureCandidate.from_json(candidate)), sort_keys=True).encode()).hexdigest()
                qhash = write(folder/'qualification.json', qualification)
                verification = json.loads((folder/'verification.json').read_text())
                verification.update(qualification_sha256=qhash, scene_sha256=generated['sha256'])
                write(folder/'verification.json', verification)
                families[family].append(row)
    registry = tmp_path/'registry.json'
    package = build_package({'seed': 20260923, 'families': families}, {'evidence': evidence, 'local': evidence})
    assert package['ready']
    write(registry, package)
    return dict(registry=registry, source_roots={'local': evidence}, workspaces=[workspace],
                assets_manifest=manifest, robolab_root=robolab, source_root=source,
                source_commit=source_commit, output=tmp_path/'handoff')


def test_materializes_one_candidate_per_layout_and_consumable_cell_bindings(inputs):
    module = api()
    registry = json.loads(inputs['registry'].read_text())
    original = inputs['source_roots']['local']/registry['layouts']['LAT-P01']['files']['candidate']['path']
    original_bytes = original.read_bytes()
    result = module.materialize(**inputs)
    root = inputs['output']
    assert result['status'] == 'physical_qualified_runtime_pending'
    assert result['learned_policy_launch_authorized'] is False
    assert result['layout_count'] == 87 and result['cell_count'] == 1566
    assert len(list((root/'layouts').glob('*/candidate.json'))) == 87
    assert len(list((root/'layouts').glob('*/scene.usda'))) == 87
    assert original.read_bytes() == original_bytes
    fixtures = json.loads((root/'physical-fixtures.json').read_text())
    binding = json.loads((root/'environment-binding.json').read_text())
    assert fixtures['status'] == 'physical_qualified_runtime_pending' and fixtures['time_maps'] == {}
    assert fixtures['runtime_qualified'] is False
    assert len(binding['cells']) == 1566
    rows = [json.loads(line) for line in (root/'bound-cells.jsonl').read_text().splitlines()]
    assert {row['status'] for row in rows} == {'PLANNED_NOT_RELEASED'}
    assert all(row['time_map_sha256'] == row['runtime_sha256'] == '' for row in rows)
    row = next(row for row in rows if row['cell_id'] == 'DIST-C24-F3-I-NEG')
    record = binding['cells'][row['cell_id']]
    assert record['scene_seed'] == 20282946  # frozen queue, not candidate generation seed
    assert record['candidate_id'] == registry['layouts']['DIST-C24']['candidate_id']
    from experiments.workshops.spatial_grounding_v1.robolab_jointpos_environment import JointPositionBinding
    bridge = JointPositionBinding(inputs['source_root'], inputs['robolab_root'], Path(binding['assets_manifest']),
                                  binding['assets_manifest_sha256'], binding['cells'])
    _, candidate = bridge.cell({**row, 'status': 'RELEASED'})
    assert candidate.candidate_id == record['candidate_id'] and candidate.seed == 20260923
    assert candidate.metadata['visual_style'] == 'clean-studio-v1'
    assert candidate.object_poses == FixtureCandidate.from_json(json.loads((inputs['source_roots']['local']/registry['layouts']['DIST-C24']['files']['candidate']['path']).read_text())).object_poses
    assert record['fixture_sha256'] == fixtures['layouts']['DIST-C24']['fixture_sha256']
    assert len({layout['fixture_sha256'] for layout in fixtures['layouts'].values()}) == 87
    assert f'@{inputs["robolab_root"]}/assets/scenes/' in Path(candidate.task_asset).read_text()


@pytest.mark.parametrize('change', ['partial', 'missing_layout', 'swapped_layouts'])
def test_rejects_incomplete_or_cross_layout_registry_before_writing(inputs, change):
    registry = json.loads(inputs['registry'].read_text())
    if change == 'partial':
        registry.update(status='partial', ready=False)
    elif change == 'missing_layout':
        del registry['layouts']['LAT-C24']
    else:
        registry['layouts']['LAT-D01'], registry['layouts']['LAT-D02'] = registry['layouts']['LAT-D02'], registry['layouts']['LAT-D01']
    write(inputs['registry'], registry)
    with pytest.raises(ValueError, match='complete|layout|order'):
        api().materialize(**inputs)
    assert not inputs['output'].exists()


def test_changed_asset_payload_is_rejected_even_with_same_file_size(inputs):
    path = inputs['robolab_root']/'assets/objects/cube.usda'
    path.write_text(path.read_text().replace('cube', 'oops'))
    with pytest.raises(ValueError, match='asset payload'):
        api().materialize(**inputs)
    assert not inputs['output'].exists()


def test_unused_robolab_asset_change_is_not_read_or_blocking(inputs, tmp_path):
    robolab = inputs['robolab_root']
    marker = tmp_path/'asset-filter-ran'
    probe = tmp_path/'asset-filter.py'
    probe.write_text('from pathlib import Path\nimport sys\n'
                     f'Path({str(marker)!r}).write_text("asset bytes scanned")\n'
                     'sys.stdout.buffer.write(sys.stdin.buffer.read())\n')
    (robolab/'.git/info/attributes').write_text('assets/** filter=assetprobe\n')
    subprocess.run(['git', '-C', str(robolab), 'config', 'filter.assetprobe.clean',
                    shlex.join([sys.executable, str(probe)])], check=True)
    (robolab/'assets/unused.bin').write_bytes(b'edited asset')
    result = api().materialize(**inputs)
    assert result['layout_count'] == 87
    assert not marker.exists(), 'Git must not read/filter unused asset payloads'


@pytest.mark.parametrize('staged', [False, True])
def test_robolab_tracked_code_change_is_rejected(inputs, staged):
    robolab = inputs['robolab_root']
    (robolab/'controller.py').write_text('speed = 2\n')
    if staged:
        subprocess.run(['git', '-C', str(robolab), 'add', 'controller.py'], check=True)
    with pytest.raises(ValueError, match='dirty'):
        api().materialize(**inputs)
    assert not inputs['output'].exists()


@pytest.mark.parametrize('change', ['tracked_asset', 'untracked'])
def test_study_checkout_still_requires_all_files_clean(tmp_path, change):
    source = tmp_path/'study'
    (source/'assets').mkdir(parents=True)
    (source/'assets/tracked.txt').write_text('original')
    commit = git_snapshot(source)
    changed = source/('assets/tracked.txt' if change == 'tracked_asset' else 'untracked.txt')
    changed.write_text('changed')
    with pytest.raises(ValueError, match='dirty'):
        api()._verify_checkout(source, commit, untracked=True)


def test_changed_workspace_or_design_does_not_reuse_qualification(inputs):
    inputs['workspaces'][0].write_text('{"changed": true}')
    with pytest.raises(ValueError, match='workspace'):
        api().materialize(**inputs)
    assert not inputs['output'].exists()


def test_different_writer_cannot_silently_change_geometry_or_appearance(inputs, monkeypatch):
    original_writer = api().write_scene
    def changed_writer(row, workspace, robolab_root, output):
        row = copy.deepcopy(row)
        row['roots']['rubiks_cube'][0] += .05
        return original_writer(row, workspace, robolab_root, output)
    monkeypatch.setattr(api(), 'write_scene', changed_writer)
    with pytest.raises(ValueError, match='geometry|appearance|recorded scene'):
        api().materialize(**inputs)
    assert not inputs['output'].exists()


def test_physical_export_cannot_be_used_as_a_runtime_qualified_release(inputs, tmp_path):
    api().materialize(**inputs)
    from experiments.workshops.spatial_grounding_v1.contract import ContractError
    from experiments.workshops.spatial_grounding_v1.release import create_release
    from tests.test_sgw_contract import make_release
    (tmp_path/'release-test').mkdir()
    binding = json.loads((make_release(tmp_path/'release-test')/'runtime_binding.json').read_text())
    binding.update(cpu_memory_limits={'cpu_request':'2'}, model_code_commits={'N3':'a'}, checkpoint_hashes={'N3':'b'},
                   policy_ports={'N3':1}, frame_time_mapping_hashes={'N3':'c'})
    binding_path = tmp_path/'runtime.json'
    write(binding_path, binding)
    with pytest.raises(ContractError, match='qualified per-layout'):
        create_release(output=tmp_path/'forbidden-release', release_id='unqualified',
            protocol=ROOT/SPEC/'protocol.json', prompts=ROOT/SPEC/'prompts.json',
            planned_queue=ROOT/SPEC/'planned_cells.csv', fixtures=inputs['output']/'physical-fixtures.json',
            runtime_binding=binding_path, resource_owner='ali', stage='P', model='N3', family='LAT')
