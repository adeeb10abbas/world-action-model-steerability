# Offline scene handoff

`tools/materialize_scene_handoff.py` turns a **ready, complete 87-layout scene
registry** into destination-specific scene overlays and 1,044 planned cell
bindings. It runs no simulator, model, network request or release operation.

The [complete registry](../artifacts/workshops/spatial_grounding_v1/scene_package_20260924/scene-registry.json)
has passed the full materializer against the workstation's pinned RoboLab
assets using study commit `b4ad6145423e98b3b5f7524b3294b2de27e2953c` and
Python 3.11.14. The [saved receipt](../handoff/workstation-materialization.json)
records 87 rebuilt layouts, 1,044 bound planned cells, zero native runs and
zero model requests. The output remains `physical_qualified_runtime_pending`.

The actual destination-bound output is at
`/home/ali/sgw-scene-design-20260923/evidence/SGW-FINAL-HANDOFF-20260924`
on the workstation. A copy for inspection is at
`/Users/ali-adeeb/Downloads/astra_creative_director/sgw_scene_handoff_20260924`
on this Mac; its embedded paths still refer to the workstation. Regenerate
the output at the cluster's actual paths using the instructions below.

Run it from the clean committed study checkout at the destination where the
pinned RoboLab checkout and asset payloads already exist. The output must be a
new directory outside both source checkouts. Supply every source alias used by
the registry and the exact measured workspace file(s) named by its hashes:

```sh
python tools/materialize_scene_handoff.py \
  --registry /evidence/scene-registry.json \
  --evidence-root repo=/study/world-action-model-steerability \
  --evidence-root evidence=/evidence/compact-receipts \
  --workspace /evidence/measured-workspace.json \
  --assets-manifest artifacts/workshops/spatial_grounding_v1/runtime_dependencies/workstation-assets.json \
  --robolab-root /opt/RoboLab \
  --source-root /study/world-action-model-steerability \
  --source-commit FULL_CLEAN_STUDY_COMMIT \
  --output /handoff/clean-scenes
```

Repeat `--workspace` when selected scenes bind different measured workspace
files. Alias names and paths above are examples; supply the actual registry's
aliases. The compact original workstation asset manifest is tracked, with
SHA-256 `eb5507f84044f7206f5822c7ef18595272f45022fcd166cfdb3a12ef88a09ec1`.
Its external asset payloads are not redistributed.

The study checkout must match its supplied commit and have no tracked changes
or untracked files. RoboLab must match its pinned commit and have no tracked
changes outside `assets/`, including staged code changes. The RoboLab code
check excludes `assets/**` before Git examines payloads, so unrelated Git-LFS
assets neither block the handoff nor incur a whole asset-checkout scan.

The materializer verifies the recorded six-trial receipts, distinct layouts,
side quotas, declared selection order, frozen prompts and intact six-condition
blocks. Every asset in the exact used base-scene dependency closure must retain
its recorded byte size and SHA-256; missing, changed or extra manifest entries
fail. Excluding assets from the Git code check does not relax these checks.
Manifest relocation changes only its root and asset paths. Each overlay is
regenerated from the exact design/workspace; substituting its old base-scene
path must recover the recorded overlay SHA-256. A geometry, material or other
appearance change therefore fails instead of inheriting old qualification.

Outputs:

- `layouts/<layout_id>/scene.usda`, one derived `candidate.json`, and a
  `physical-fixture.json` retaining the original evidence references. Only the
  derived candidate's task/native asset path, native asset hash and manifest
  hash change. Its measured poses, offsets, goal supports, appearance and
  generation seed remain intact. The original receipts are never edited.
- `physical-fixtures.json` maps all 87 layout IDs to candidate, overlay and
  physical fixture hashes. `fixture_sha256` hashes that layout's
  `physical-fixture.json` bytes.
- `environment-binding.json` has the fields consumed by `JointPositionBinding`,
  with 1,044 explicit cells. Each uses `scene_seed=int(environment_seed)` from
  the frozen queue, not the candidate-generation seed. Both models and all six
  conditions for a layout share its one candidate and overlay.
- `bound-cells.jsonl` retains `PLANNED_NOT_RELEASED`, empty runtime/time-map
  hashes and the original queue fields, adding the physical fixture hash.
  `handoff.json`, `asset-relocation.json`, and an unchanged registry copy record
  derivation and source identities.

These are **physical fixtures pending runtime qualification**. The fixture
export has `runtime_qualified=false`, `status=physical_qualified_runtime_pending`
and `time_maps={}`. `release.create_release` deliberately rejects it. A future
authorized integration must validate destination resets/rendering and N3/D1
runtimes, provide real time/camera-map evidence, and create a separate qualified
fixture receipt that preserves these physical layout hashes. Use the original
frozen `planned_cells.csv` as the eventual release source. Put future clean
releases under a fresh cohort parent to keep attempt/completion namespaces
separate. This tool supplies no launch authorization or runtime receipt.

Paths are bound to the actual destination. Moving the output or RoboLab assets
requires a new materialization; do not rewrite existing handoff receipts.

CPU check: `python -m pytest -q tests/test_materialize_scene_handoff.py`.
