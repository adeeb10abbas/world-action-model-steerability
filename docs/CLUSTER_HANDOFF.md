# Cluster handoff: completed scenes, runtime integration

**The current user instruction authorizes runtime integration and subsequent
gated study launch.** See the
[current continuation](../handoff/cluster-execution-20260924/README.md) for its
hash-bound instruction, actual cluster paths and zero-request failures. No
behavioral release exists yet. The original scene-planning handoff below is
resource-neutral; its historical absence of launch authority does not revoke
the new instruction. Scene qualification is not model-runtime readiness.

The [final scene registry](../artifacts/workshops/spatial_grounding_v1/scene_package_20260924/scene-registry.json) is ready: 87 layouts, 29 per family, and 522 passing scripted trials. The [completion receipt](../handoff/physical-scene-completion.json) records the checks. Use these selected designs and assignments; no further scene search is needed. [Recording locations](SCENE_RECORDS.md) include the eight rejected candidates. The model interfaces and physical time/camera mappings still need cluster qualification.

The revised N3/E3/F3 1,566-cell queue is a **template for a separately named clean-scene
release**, as proposed in [CLEAN_SCENE_COHORT.md](CLEAN_SCENE_COHORT.md).
The former N3/D1 registry is archived under `provenance/retired-n3-d1-registry-v1.1/`. Preserve the revised cell IDs inside that new release namespace, with selected
clean fixtures and the same model/family/stage/condition counts. No clean
release is created here. This repository and paper include only the clean
cohort. Its output namespace and completion pointers must be independent of
prior experiments, which remain outside this package.

## Queue and supported partitioning

| Stage | Layouts per family | Cells per model/family partition | Partitions | Total cells |
| --- | ---: | ---: | ---: | ---: |
| Pilot P | 1 | 6 | 9 | 54 |
| Development D | 4 | 24 | 9 | 216 |
| Confirmation C | 24 | 144 | 9 | 1,296 |
| Total | 29 | 174 across stages | 27 across stages | 1,566 |

Each family (LAT, HEIGHT, DIST) uses the same selected layouts for all three checkpoints
(N3, E3, F3). Each layout/model block contains all six conditions: D/C/I wording
forms crossed with positive/negative goals. There are **87 distinct layout
slots, 261 matched six-cell blocks, and 18 unique prompts**. Preserve the
frozen queue order and each block's `within_block_order`.

The current `Release.partition` and `native_worker_entrypoint` accept one
complete **model × family × stage** selection. They require exactly 6, 24, or
144 cells. They do not support arbitrary layout ranges, cell-index shards,
or one Job per confirmation block. Split across the nine model/family branches
at each stage without splitting their matched blocks. Follow P → D → C using
the existing technical readiness receipts; model failures remain results and
must not be retried away.

Partition count is not a concurrency allocation. The existing worker takes a
shared-parent `locks/N3.lock`, `locks/E3.lock`, or `locks/F3.lock` before constructing a model.
With releases under one shared study parent, it permits one worker per model
at a time. Keep that locking intact; do not create separate parents to evade
ownership. Use actual available resources when a launch is later authorized.

## Prepare the offline handoff

From the repository root:

```sh
python tools/prepare_cluster_handoff.py --output handoff/cluster-planning-review
```

This standard-library-only command checks frozen hashes and writes
`partitions.json` (every original queue row grouped into supported partitions)
and `preparation.json`. Existing output directories are never overwritten.
The checked-in [partition export](../handoff/cluster-planning/partitions.json)
contains planned rows only; it is not the released `queue.jsonl` consumed by
the worker.

No Kubernetes Job is emitted by default because the new study does not yet
have a concrete reviewed native Job with image, namespace, PVC and runtime
paths. Inventing those values would produce an unusable launch document.
Once such a manifest exists, the same tool can take `--reviewed-job-json`
and a fresh output directory. It accepts only a concrete, digest-pinned Job
that directly invokes the existing `native_worker_entrypoint`, selects a full
registered partition, mounts its actual PVC and has a finite deadline. It
preserves those supplied runtime/resource values and writes a Kubernetes JSON
manifest with **`suspend: true` and `parallelism: 0`**. It never applies it.
Those two controls prevent pod creation; changing them is a later launch step,
not part of preparation or permission granted here.

The generic specification template is not a complete native Job: a concrete
target environment must supply AppLauncher and runtime wiring. This handoff
contains no dated cluster launch manifests and invokes no V2/V3 validators.

## Reuse the selected scenes on the cluster

Use [the offline materializer](SCENE_MATERIALIZATION.md) with the final ready
scene registry. It regenerates path-bound overlays, preserves the qualified
geometry and appearance, and writes the 87-layout and 1,566-cell mappings.
Its physical-only output intentionally lacks model/runtime qualification.

Use camera revision `close-oblique-v3-full-objects-20260924`, documented in
[CAMERA_ALIGNMENT.md](CAMERA_ALIGNMENT.md). The current input set is the
1,566-cell N3/E3/F3 queue and all 87 selected geometries. The
[delivery index](../handoff/delivery.json) identifies the latest checked
materialization. Regenerate it at cluster paths; do not copy a workstation
binding or patch an old binding by hand. Earlier 1,044-cell and v2-camera
receipts remain historical evidence. Original geometry, assignments and all
522 scripted physical passes remain unchanged.

Transfer the selected **input JSON, family assignments, calibration, asset
manifests, source hashes and qualification receipts** together. Preserve each
selected layout ID, its appearance, support orientation, and measured object
geometry. Use the same physical scene for all six conditions and all three model
branches. Keep P/D/C layout assignments distinct; multiple prompts or resets
of one layout are not new independent layouts.

The existing clean candidate pools are under
`artifacts/workshops/spatial_grounding_v1/clean_campaign_20260924/`; prototypes
are under `scene_design_rtx_20260923/`. Complementary LAT and DIST inputs are
under `completion_prototypes_20260924/` (LAT) and `flat_dist_prototypes_20260924/`
(DIST); the active balanced candidates are under
`balanced_flat_scene_candidates_20260924/`. Its bounded plans retain the first
100 authored candidates per family. Earlier pedestal DIST inputs are superseded
and excluded. Use the matching clean native
receipts and final selected assignments. A planned/authored row does not
establish a qualified layout or a complete family pool.

Keep raw scene records on persistent storage. Reuse existing compatible
qualification evidence instead of rerunning scenes just for this handoff.
Resolve paths against the cluster's pinned RoboLab checkout and actual asset
bytes. Generated USDA overlays contain absolute base-scene references, so
regenerate the same selected design on the cluster rather than copying an
overlay that points to a workstation directory. Record the new overlay/path
binding and verify unchanged geometry/appearance; a path update is not a new
layout. The original hashed scene registrations remain unchanged.

## Preserve inputs, observations and scoring

- **Seeds and prompts:** use each exported row's original `environment_seed`,
  `effective_policy_seed`, prompt text and SHA-256. N3's sampling seed varies
  by registered layout; E3/F3 effective seed handling remains to be qualified. Never replace
  seeds with worker IDs. Prompts remain static for the full episode.
- **Cameras and state:** retain the unchanged wrist and registered close
  exterior cameras. The historical sensor names remain for slot compatibility;
  their exterior positions now look down from the far side of the table.
  `policy_observations.py` uses
  `wrist_cam`, `over_shoulder_left_camera`, and `over_shoulder_right_camera`.
  N3 maps exterior cameras to official one-based slots. E3/F3 camera packing
  and image transforms must be qualified independently. Policy input contains RGB and arm/gripper proprioception.
  Object coordinates and scoring state are for measurement only.
  Both goal destinations and a 0.12 m lift envelope determine framing before
  any model outcomes; the view stays fixed across all six conditions.
  Offline slot/resize checks and six native camera diagnostics passed. These
  do not establish server execution or generated-future timing. Wrist-only
  predictions can lack a visible reference object; retain that missingness.
- **Resets and actions:** perform a full physical reset and clear model
  session/cache for every cell. Verify reset positions within 3 mm and
  orientations within 2 degrees. Use the official absolute joint-position
  action interface; N3 executes up to 32 actions per returned chunk. Pin
  E3/F3 returned and executed horizons during integration. Stop at 450 actions, with no success-based
  early termination; preserve explicit physical safety truncation separately.
- **Physical outcomes:** keep the frozen 30 mm relation margin, 5 mm initial
  neutrality/reference-motion limits, 30 mm pickup held for three samples,
  and final 0.5 s stability window at ≤0.02 m/s and ≤0.2 rad/s. Score measured
  geometric centers, actual support contacts and detached release; actor
  roots alone are not geometric centers. Use the existing scorer unchanged.
- **Recording:** retain timestamped actions and raw state/camera records,
  reset/warmup evidence, viewport videos, model request traces, decoded
  futures/latents with hashes, timing maps and completion pointers. Determine
  video cadence from physical timestamps. Missing/undecodable/unmapped futures
  remain explicitly unavailable, never prediction failures or zeros.

## What still needs native qualification

The pinned dependency identities are in [STANDALONE_RUNTIME.md](STANDALONE_RUNTIME.md).
Before any later model release, the cluster agent must establish the actual
image/environment, RoboLab/assets, policy source/checkpoint bytes, cameras,
controller and process ownership. Reuse retained model checks only when their
exact identity and inputs still match the new scene/runtime condition.

The production path needs qualified per-layout fixtures, the native
`SGW01_ENV_BINDING` and hash, `SGW01_SIMULATOR_DEVICE`, and a valid
`SGW01_ENV_FACTORY` such as the existing joint-position factory after
AppLauncher startup. The owned runtime also needs its real model endpoint,
`SGW01_SERVER_ARGV`, runtime receipt and the concrete trace reader. These
values come from the working native environment; this tool does not guess
them. E3/F3 adapters and immutable source/checkpoint pins are now implemented;
their actual runtime, reset and image-processing qualification remains
pending. D1 is retired. FLUX same-request latent/video capture is implemented
but not yet natively qualified. Prove physical timing and action prefix
alignment for each model before scoring predictions.

`release.create_release` already combines the full frozen source queue with
qualified fixture/time-map records and the actual runtime binding, selecting
one model/family/stage. It preserves only that full partition in an immutable
release directory. It requires the direct-command readiness receipt and the
stage's technical receipt (and the pilot receipt for D/C). Use those existing
records when ready; do not manufacture passing receipts or add another
parallel release system.

Store releases as sibling directories under one persistent study parent so
status, attempts and model locks remain shared. Keep raw arrays, videos,
checkpoints and simulator caches outside ordinary Git. Before later D/C
execution, measure pilot bytes and runtime using retained records: the current
worker requires a 100 GiB free-space floor and at least 1.5 × measured pilot
P95 episode bytes × the storage receipt's global episode count. Its current
implementation conservatively requires that count to cover at least all
1,566 cells; do not call it a shrinking remaining-count estimate. Bind actual
GPU ownership, finite Job deadlines and storage estimates to the runtime.

Resume through existing completion pointers. Preserve valid failures, safety
censoring, interrupted evidence and technical attempt numbers; do not replay
completed cells within the same release. The future clean release must have
its own completion namespace and must not import another cohort's completion
pointers. Nothing in this document authorizes a new inference request,
GPU allocation, Job application, or study launch.
