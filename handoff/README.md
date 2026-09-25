# Start here: SGW-01 cluster handoff

**Current execution continuation:** the user has since authorized cluster
integration and launch subject to the runtime gates. See
[the current cluster record](cluster-execution-20260924/README.md) for deployed
source, destination materialization, actual owners and preserved failures.
Genuine A40 study execution is running on five policy/simulator pairs. All
three models have valid recorded episodes after the verified recovery; 288
unique episodes (54 pilot, 216 development and 18 confirmation) were complete
at 2026-09-25 12:12 UTC. The development barrier released at 11:28:27 UTC;
all five current pairs now have genuine completed confirmation episodes.
The five original
technical-invalid attempts remain unchanged. The
original preparation-only handoff below does not itself grant that authority.

## Original preparation-only handoff

**The scenes, camera configuration and experiment queue are ready to transfer.
Model integration and cluster runtime qualification remain. No learned-policy
episodes have started, and this handoff does not authorize a study launch.**

Use the latest committed `main` from this repository. Do not redesign the
scenes, rerun completed physical qualification, or reuse an old environment
binding. Record the exact commit used by each cluster checkout.

## Delivered study snapshot

| Item | Current value |
| --- | --- |
| Physical layouts | 87: 29 each for LAT, HEIGHT and flat-table DIST |
| Scene evidence | 522 selected scripted passes; eight rejected candidates retained |
| Cameras | `close-oblique-v3-full-objects-20260924`: two elevated scene views containing every tabletop object, plus unchanged wrist |
| Camera checks | 87-layout geometric coverage; six-layout native rendering/synchronization checks |
| Checkpoints | N3: Cosmos3 Nano; E3: Cosmos3 Edge; F3: FLUX 3 Action. D1 is retired. |
| Instructions | 18 exact prompts; D/C/I wording crossed with two physical goals |
| Planned episodes | 1,566: 54 pilot, 216 development, 1,296 confirmation |
| Execution units | 27 model/family/stage partitions; 261 intact six-condition blocks |
| Learned-policy episodes | 0 |

The [scene registry](../artifacts/workshops/spatial_grounding_v1/scene_package_20260924/scene-registry.json),
[camera configuration](../experiments/workshops/spatial_grounding_v1/close_cameras.json),
[planned partitions](cluster-planning/partitions.json), and
[status](../REPOSITORY_STATUS.json) are the current inputs.
[Delivery](delivery.json) identifies current receipts and their hashes.
Historical camera views and the former N3/D1 queue remain as evidence, not
execution inputs.

## Work to assign

1. **One shared scene-transfer owner.** Install the pinned RoboLab/assets,
   materialize all 87 layouts against the cluster's real paths and current
   1,566-cell queue, and give the same binding to all model owners. Follow
   [scene materialization](../docs/SCENE_MATERIALIZATION.md). Retain the camera
   revision/hash in the binding; older bindings must not be patched by hand.
2. **One integration owner per checkpoint.** Retain N3's pinned configuration.
   Implement and pin E3/F3 using their official interfaces; both deliberately
   reject inference while integration is missing. Do not substitute another
   model. Record camera order/resize, action units, gripper convention,
   reset/cache behavior, effective seeds, ownership and source/checkpoint hashes.
   See [runtime setup](../docs/STANDALONE_RUNTIME.md).
3. **One recording/forecast owner.** Verify that captured predictions belong
   to the same request as the executed actions, with documented camera and
   physical-time alignment. FLUX's released action-only API still needs
   same-request forecast export. Record unavailable predictions as unavailable;
   keep valid behavior outcomes. Historical D1 preprocessing checks do not
   qualify E3 or F3.
4. **One execution owner, after the separate launch instruction.** Supply the
   actual image digest, namespace, PVC, runtime endpoints, GPU/storage ownership
   and finite Job deadline. Use the existing partition/release/worker path and
   shared model locks. Proceed pilot → development → confirmation, preserving
   each six-condition block and all failures. See the
   [cluster runbook](../docs/CLUSTER_HANDOFF.md).
5. **One analysis owner.** Follow [the experiment specification](../experiments/workshops/spatial_grounding_v1/spec/EXPERIMENT_SPEC.md)
   and [analysis safeguard](../docs/EQUIVALENCE_ANALYSIS_NOTE.md). Report
   complete-layout counts, prediction availability and technical missingness.
   The independent sample is a layout, not a frame or repeated instruction.

## Quick repository check

```sh
uv sync --extra test
uv run python tools/validate_standalone_sgw.py --check-imports
uv run pytest -q
```

These are CPU software checks. They do not download models, allocate GPUs,
create a runtime release, apply Kubernetes Jobs or start episodes. The
checked-in partition export is a plan, not the worker's released queue.

Use the latest [camera preview](../artifacts/workshops/spatial_grounding_v1/camera_checks_20260924/close-v3-full-objects/all-three-families.jpg)
to recognize the intended setup. LAT and DIST remain flat; only HEIGHT has
raised supports. The wrist view is intentionally unchanged and has documented
reference-visibility limits. Do not change scenes or prompts after seeing
model outcomes.
