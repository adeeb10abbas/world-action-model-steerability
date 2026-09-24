# Current cluster continuation

The user separately authorized runtime integration, bounded checks, and the
committed study on 24 September 2026. This supersedes the preparation-only
permission recorded in the original delivery. **No behavioral release or study
episode has started.** Do not equate the implemented adapters, model loading,
or the destination check below with qualified model inference.

**All three actual pinned runtimes have now completed six fixed-input
requests each (18 total), with zero executed actions or study episodes.**
This is verified native inference, not merely a Running Pod. Closed-loop
execution and physical forecast mapping remain unqualified. These requests
are consumed; do not rerun them to finish downstream evidence.

**Subsequent live evidence:** Nano-B and Edge-B each consumed two additional
real requests and executed 64 acknowledged physical actions with two resets.
Edge's [final technical result](e3-live-result.json) is receiver-confirmed and
completed with clean owned HTTP shutdown. Nano's original missing post-close
marker/cleanup failure remains preserved and requires a separate external
lifecycle witness; no Nano replay is allowed. These are still **zero study
episodes**, and do not make forecasts physically scored evidence.

The [latest user instruction](completion-instruction.json) extends the
objective through all 1,566 unique study outcomes and verified video/raw
manifests, not merely launch. Keep every actual recording on the PVC and push
compact indexes, hashes, provenance and derived results. Do not add video
blobs to Git or Git LFS. Retain full-quality originals, including original
resolution, frame counts and timestamps. Create separate H.264 MP4 viewing
derivatives with their own hashes and master references. **Only after all
1,566 episodes and required outputs are finished/accounted**, download the
study viewport and exposed prediction derivatives to
`/Users/SZ5VJY/Downloads/world-action-model-steerability-videos`, with a
manifest-driven, checksum-verified local receipt. Preserve the PVC originals,
safe hierarchy and resumable partial files; do not overwrite unrelated files
or delete other user data for space. Check total derivative bytes against
fresh laptop headroom before transfer. If insufficient, report the exact
capacity needed for the user's external drive; do not start partial delivery
before full-study accounting.

Once the study is actually healthy and running, use one light receipt/scoped
Job-state check about every 15 minutes, with nonempty evidence commits about
hourly or at completed-partition milestones. No full raw-data rehashing or
inference for monitoring. Switch immediately to focused diagnosis on failure
or abnormal lack of progress, then return to sparse monitoring after recovery.
Do not arm that monitor before launch or make cluster progression depend on
the monitor, laptop, or app remaining open.

The sole resource/output coordinator is session
`5ed7dc81-68d8-493f-a8c4-81a4b6cb59f6`, acting on the user's instruction relayed
by `c230f3cd-3fe9-4f1f-9ee4-e8b857151a60`. The current instruction permits
verified-idle existing capacity as needed, not the historical four-GPU cap.
It does not permit paid capacity, preemption, stopping other workloads, or
changing the frozen scenes, cameras, prompts, splits or scoring.

## Persistent inputs and observed results

- Exact delivered source: `6dbdecc37b397b2ab7b9f064008da40e067a5ceb`.
  Cluster checkout: `/data/users/ali/sgw-01/current-20260924a/source`.
- [Materialization](materialization.json): all 87 layouts and 1,566 planned
  bindings regenerated at
  `/data/users/ali/sgw-01/current-20260924a/materialization`.
  This is still a physical-only binding, not a released queue.
- [Destination check](destination-check.json): LAT-P01, two resets, three
  current-position holds, 15 exact sensor/RGB matches, zero physical goal
  trials. The Job exited zero on an idle-checked, UUID-locked A40. Current
  camera configuration was unchanged. No broader camera campaign was run.
- Current-input Nano diagnostic source:
  `f6b3f17f4c0710167ac4455fe2a85edf9f3a08c8`, checked out separately at
  `/data/users/ali/sgw-01/current-20260924a/source-f6b3f17`.
  Registration:
  `/data/users/ali/sgw-01/current-20260924a/current-n3-registration.json`,
  SHA-256 `2ee4773e5b72023330c4e397f622069c363ad28de962e4347119ee59d8576ef8`.
  Frozen LAT-P01 effective seed: `2026092201`. Six requests maximum, no
  executed actions, no automatic retry.
- Nano attempt A failed during guardrail startup with missing `libxcb.so.1`;
  [original failure](n3-check-a-failure.json) and
  [actual Job](jobs/n3-check-a.json) are retained. Attempt B used the repaired
  linker path, then found missing `uvx` on `PATH`;
  [original failure](n3-check-b-failure.json) and
  [actual Job](jobs/n3-check-b.json) are retained. **Both started zero model
  requests.** Neither is a behavioral failure or scored zero. Their raw
  evidence remains under `n3-check/` and `n3-check-b/` in the cohort root.
- E3/F3 adapter implementation, immutable file identities, official source
  references and CPU checks are recorded in
  [checkpoint_integrations.json](../../experiments/workshops/spatial_grounding_v1/checkpoint_integrations.json).
  Actual fixed-input results are retained below.

## Completed native fixed-input checks

The [terminal Job/Pod identities](fixed-input-job-outcomes.json) record all
three Jobs exiting zero with no container restarts. Submitted manifests are
in `jobs/n3-check-c.json`, `jobs/e3-check-a.json` and `jobs/f3-check-a.json`.
Nano ran source `4c39c450b1dace8470edc7d907fb4e86a88bd0e3`; Edge and FLUX ran
`1b45b1fedaa5377d2d3dd7717607b18f5266be54`. All used separately idle-checked,
UUID-locked A100-SXM4-80GB allocations on `dcwipphai0061.edc.nam.gm.com`.

- [Nano result](n3-fixed-input-result.json), with
  [loaded runtime](n3-loaded-runtime.json): six valid native responses;
  repeated actions and all three offline latent redecodes were bit-identical.
  Opposite-prompt action RMS difference was `0.08661260613195104`.
- [Edge result](e3-fixed-input-result.json): six valid native responses and
  six decoded same-request futures; repeated actions were identical.
  Opposite-prompt action RMS difference was `0.03079543058790927`.
- [FLUX result](f3-fixed-input-result.json): six valid native responses,
  three with same-request latent/video capture and three without capture.
  All three matched capture-on/off action arrays were exactly equal (maximum
  absolute differences `0.0`). Opposite-prompt RMS difference was
  `0.12912268060309118`.

These differences are descriptive model outputs, not physical success scores.
All use the frozen effective seed `2026092201`. A separate CPU read verified
45 retained action/future/latent/redecode artifact hashes (21 Nano, 12 Edge,
12 FLUX) without making more model requests. Raw bytes, native traces and
logs remain under `n3-check-c/`, `e3-check-a/` and `f3-check-a/` on the PVC.
FLUX's three no-capture outputs are deliberately `not_exposed`, not missing
scored zeros. Exposed forecasts remain physically unmapped.

## Reproducible startup repair

Use the checked-in
[`tools/cluster_policy_bootstrap.sh`](../../tools/cluster_policy_bootstrap.sh)
for subsequent policy commands, including native workers with the corresponding
model interpreter. It prepends that interpreter's `bin/` to `PATH` so the
pinned Cosmos checkpoint resolver finds its existing `uvx`, and prepends:

```text
/data/users/ali/vla_wam/envs/robolab-native-libs-ubuntu2204/usr/lib/x86_64-linux-gnu
/data/users/ali/glvnd/lib
/data/users/ali/vla_wam/envs/fastwam-native-libs/lib
/usr/lib/x86_64-linux-gnu
```

`SGW01_NATIVE_LIBRARY_DIRS` can explicitly bind a relocated colon-separated
directory list; nonexistent or relative entries are rejected. These are
native shared libraries, not alternate model packages. No guardrail is
disabled. No Python environment or upstream source was modified to fix these
two failures.

Also bind `UV_CACHE_DIR` to
`/data/users/ali/sgw-01/current-20260924a/cache/uv`. The subsequent CPU-only
resolver check found that a numeric-UID staging process otherwise selected
unwritable `/.cache/uv` and `/.local/share/uv/tools`. The bootstrap now requires
an explicit absolute, writable cache before a Cosmos command and places
`UV_TOOL_DIR` under that cache unless explicitly bound elsewhere; it never
relies on those root-home defaults.

With both paths bound, the pinned `GUARDRAIL1_CHECKPOINT.download()` resolver
passed on CPU against its existing offline snapshot
`d6d4bfa899a71454a700907664f3e88f503950cf`; no guardrail weights were downloaded,
no guardrail was disabled, and no model was constructed. `uvx` installed its
pinned `hf@1.16.4` helper into the writable tool cache.

The new Edge source `cf5d68c00d97ccd2480a2320ed652b92dec63102` and checkpoint
`a7c7288f9b6ac1684e993007b0f9703dd26e58ef` are staged separately under this
cohort's `external/cosmos-cf5d68c` and `checkpoints/cosmos3-edge-a7c7288`.
`verify_identity("E3")` passed for these fresh files; the older
`vla_wam/checkpoints/cosmos3_edge_policy_droid` did not match the new
`transformer/config.json` identity and was not changed. The FLUX policy and
base snapshots in `checkpoint_integrations.json` also passed full registered
file verification. Its isolated `envs/flux-e2dd1d8` environment has Python
3.12.13, Torch 2.10.0+cu128, NATTEN 0.21.6+torch2100cu128, and the study's
recording dependencies. These are CPU staging results, not runtime qualification.

The corrected Nano Job is retained as `jobs/n3-check-c.json`, using source
`4c39c450b1dace8470edc7d907fb4e86a88bd0e3` and new output `n3-check-c`.
It passed the fresh idle allocation check on
`GPU-9b784824-3fad-dcf1-8e3e-abee22db4a8e` (A100-SXM4-80GB), completed all
six requests and the three offline redecodes, then exited zero.

For Edge/FLUX, use the new bounded `checkpoint_fixed_input.py` entrypoint
documented in `docs/STANDALONE_RUNTIME.md`. Its CPU tests exercise fake
backends only. Neither those tests, imports, weight hashing nor a Running Pod
qualifies a model or starts a behavioral episode.

The following **CPU-only** startup check passed in the approved container:

```sh
UV_CACHE_DIR=/data/users/ali/sgw-01/current-20260924a/cache/uv \
bash tools/cluster_policy_bootstrap.sh --check-only N3 \
  /data/users/ali/vla_wam/envs/cosmos-nano-411d25b-v3-exact/bin/python
```

It verifies `uvx 0.10.8` and imports OpenCV/RetinaFace without model construction.
OpenCV is `4.13.0`. A normal invocation runs that same startup check and then
executes the supplied command:

```sh
UV_CACHE_DIR=/data/users/ali/sgw-01/current-20260924a/cache/uv \
bash tools/cluster_policy_bootstrap.sh N3 \
  /data/users/ali/vla_wam/envs/cosmos-nano-411d25b-v3-exact/bin/python \
  -m experiments.workshops.spatial_grounding_v1.nano_fixed_input \
  --registration /data/users/ali/sgw-01/current-20260924a/current-n3-registration.json \
  --output /data/users/ali/sgw-01/current-20260924a/NEW-DIAGNOSTIC-OUTPUT
```

This is a **diagnostic**, not a study command. Use only in a newly registered,
finite, owned Job after its idle/UUID/model-lock checks. The literal
`NEW-DIAGNOSTIC-OUTPUT` above must not be used as a shared default. Never rerun
the completed physical campaign or clear failed output/claim paths.

## Actual environment and ownership

Context `prod-dcwi-warrenq1-vmkub007`, namespace `211247-prod`, PVC
`211247-prod-pvc` mounted at `/data`; UID/GID `816149040/2518800`.
All current Jobs use approved image
`artifactory-ci.gm.com/docker-approved/devcontainers/base@sha256:03f5ce7d090fbd378070a8216d0aedfc6e473c52da99b40b0cf53918612a297c`.
The exact submitted diagnostic Jobs are retained in [jobs/](jobs/).
They have exact nodes, finite deadlines, `backoffLimit: 0`, no service-account
token, exclusive output creation, and shared physical-GPU locks.

RoboLab remains `0aef241fb088ca21bb4ebd24448940ed56620d17` at
`/data/users/ali/vla_wam/external/RoboLab-pi05-v3-0aef241`,
with Python 3.11.13 at
`/data/users/ali/vla_wam/envs/robolab-v2-isaac50/bin/python`.
N3 remains source `411d25b2e35bc441126f48c44a4b93e1c0564274` at
`/data/users/ali/vla_wam/external/cosmos-framework-411d25b`,
checkpoint `6706d7680581c255ff61e0f3bb49d90eac55c79e` at
`/data/users/ali/vla_wam/checkpoints/cosmos3_nano_policy_droid`,
and Python 3.13.6 at
`/data/users/ali/vla_wam/envs/cosmos-nano-411d25b-v3-exact/bin/python`.
`HF_HOME=/data/users/ali/vla_wam/cache/huggingface-cosmos`; credentials are
not stored here.

The protected training Pod `211247-ali-b200-1gpu`, UID
`b58e8416-9412-4db5-921b-110420433480`, was observed Running and was not touched.
Never use its node `dcwipphhgc225.edc.nam.gm.com` or GPU
`GPU-60b3065c-79cb-61e6-b92a-32d0ae3750f3` for this study.

Physical locks remain `/data/users/ali/sgw-01/locks/gpu-<UUID>.lock`.
Model locks are
`/data/users/ali/sgw-01/current-20260924a/locks/<N3|E3|F3>.lock`.
Future releases must remain sibling directories in this same new cohort
parent. Do not import old cohort completion pointers or evade model locks
with different parents.

## Hardware selection, not advertised availability

The user's requested [bounded hardware inventory](hardware-inventory.json)
was read at 19:44:49 UTC. Kubernetes advertises 95 A100 80GB, 64 A100 40GB,
42 A40, 40 B200, 16 V100 32GB and eight RTX PRO 6000 Blackwell GPUs.
These are capacity counts, **not idle counts**. Only this namespace's
reservations are visible; the inventory cannot establish current physical
availability across other namespaces.

Use **A100-SXM4-80GB (SM80) for N3/E3/F3 inference** and **A40 (SM86) for the
separate RoboLab headless/RTX renderer**. Those roles have current successful
native evidence, on two distinct A100 devices and one A40 device. Their prior
idle snapshots are not fresh admission receipts. A100 lacks RT cores and is
not an Isaac renderer substitute. The installed policy builds are Torch
2.10/CUDA 12.8 for Nano/FLUX and Torch 2.10/CUDA 13.0 for Edge, with exact
NATTEN builds recorded in the inventory. Driver 580.95.05 was demonstrated.
Torch architecture flags alone do not qualify all NATTEN/native kernel paths.
No peak VRAM was recorded, so no lower-memory fit or minimum VRAM is claimed.

The initial bounded placement used up to three policy lanes on node0061 and
separate A40 simulator lanes on nodes191/192/193. The snapshot showed no
namespace-visible GPU reservations on those candidate nodes, but each new
useful Job must still pass fresh actual-device checks. Invoke
`gpu_idle_probe --expected-name "NVIDIA A100-SXM4-80GB"` for policy lanes and
`--expected-name "NVIDIA A40"` for simulator lanes, in addition to count,
idle-process and physical-UUID locks. New release bindings should also set
`model_gpu_names` per model; the worker checks those exact device names before
construction. Preserve actual blocked receipts rather than trying other
placements in a loop. Extra hardware does not waive one worker per model,
whole partitions, P -> D -> C, or the protected node exclusion.

## Live admission and owned-terminal reconciliation

The six submitted `jobs/live-*-a.json` Jobs used exact deployed source
`8ac48581eec62143dbd8be7d4cd77cce6de10887` and
[fresh source/path materialization](live-materialization.json). That CPU
materialization preserves all 87 layouts, 1,566 bindings and the unchanged
camera hash; it is not another native scene campaign.

[Actual admission evidence](live-admission-a.json) records all three simulator
Pods and the F3 policy Pod rejected before container startup:
`UnexpectedAdmissionError`, requested `nvidia.com/gpu: 1`, available `0`.
N3/E3 obtained two idle A10080 devices, but their 180-second identity waits
expired with exit 1 and zero restarts. The
[PVC pre-execution snapshot](live-pre-execution-state-a.json) confirms no
simulator identity, mailbox or model-evidence directory for any model.
**This batch produced zero live model requests, physical actions, or study
episodes.** It is an infrastructure failure, not a model score.

The user then authorized one bounded owned-terminal allocation reconciliation.
[Eight exact terminal Jobs](terminal-reconciliation-before.json) were checked:
the six failed live-A Jobs, the completed current destination check, and
the completed historical simulator
`sgw01-ali-main-p-20260923dn-simulator-02`, Job UID
`3c020853-eca6-4fa4-a96b-510e4ea7b9ef`, Pod UID
`4062ded0-056f-4673-9858-7ee2ed30e1a7`. Their complete pre-cleanup Kubernetes
snapshots and output-owner/log hashes were
[preserved on PVC](terminal-reconciliation-preservation.json) before deleting
only these terminal Kubernetes objects. All matching Pods were then absent.
No PVC claim, raw output, old result, unrelated workload or protected training
allocation was changed. Historical results were not reanalyzed or imported.

A single new useful Nano simulator-B admission on the **same node191**
subsequently succeeded. Its actual Job UID is
`52fc58f5-9c87-48a3-9ae6-0dd6c0f158d8`, Pod UID
`91ff3894-b12a-4820-831f-2f906e976bce`; the identity was bound before creating
its policy counterpart. Attempt B uses the distinct
`/data/users/ali/sgw-01/current-20260924a/closed-loop-N3-b` output, not cleared
or reused attempt-A paths. Admission alone does not establish live inference.
Prefer sequential documented model checks on this one compatible
A10080/A40 pair, not a speculative multi-node placement loop.

The [renderer](../../tools/render_runtime_closed_loop_jobs.py) reproduces the
submitted A manifests exactly. An explicit `--attempt-suffix` gives a distinct
Job/output identity, and `--simulator-node` can select one of the three
registered A40 candidate nodes for sequential use; type/idle/UUID/model locks,
finite deadlines and no automatic retries remain unchanged. Registration and
actual UID binding are still separate required steps. Do not resubmit any
recorded attempt or treat an old idle snapshot as current admission.

The successful Edge check uses source
`a68a0bc4aef413f400dede291cbd83f139b996bf` and
[its source-only materialization](lifecycle-materialization.json), including
the outer Isaac shutdown witness. The initial source bundle import exposed
the delivered depth-one history boundary; the new checkout explicitly retains
the real `6dbdecc` shallow boundary. No commit or historical checkout was
rewritten. The incomplete import remains separate on the PVC.

The user's newer resource direction requests
[three independent model lanes](three-lane-plan.json): three A10080 policy
GPUs plus three A40 simulator GPUs, not one unsuitable physical GPU per model.
The supplied node inventory establishes compatible advertised capacity only.
One useful distinct FLUX pair was attempted: node0063 allocated an
[actually idle A10080](f3-live-b-pre-execution.json), but node190's A40
[admission was rejected](f3-live-b-admission.json) with requested 1/available 0.
No simulator identity was published and no FLUX live request or action ran.
This is not three running lanes. The user clarified that protection applies
to Edge's evidence/claims, not indefinite retention of terminal allocation
objects. After [full Edge preservation](e3-live-b-preservation.json) and
[failed FLUX preservation](f3-live-b-terminal-preservation.json), only their
four verified terminal Jobs/Pods were recycled. FLUX's prior policy exited
1 at 21:21:07 UTC, and its shared model lock was independently available.
Fresh FLUX-C is separately registered and admitted on the proven0061/191
pair; its actual simulator UID was bound before proceeding. Its live requests
have not previously been consumed. No Nano/Edge requests are replayed.
The separate protected training workload remains untouched. No paid resources,
new cluster, speculative placement sweep, or lower hardware guard is allowed.

## Remaining gates and resume

Do not repeat the completed fixed-input construction/inference checks or
capture parity. Establish the live physical action-prefix/camera/time
correspondence with the separately bounded closed-loop technical check.
Its implementation and CPU contracts are present; the first native admission
failed before execution and the reconciled Nano attempt is separately bound.
Native check success is not yet claimed. Follow the
[two-phase registration instructions](../../docs/STANDALONE_RUNTIME.md#bounded-live-model-to-simulator-check)
to preserve planned-cell status and actual simulator Job/Pod identity.
Preserve unavailable forecasts explicitly. Complete guarded runtime/fixture
receipts before creating any full model/family/stage release.

There is currently **no release to resume**. Once released, the existing
`native_worker_entrypoint --release <immutable-release> --model <model>
--family <family> --stage <stage> --resume --max-valid-episodes <6|24|144>`
is the resume interface, using the same runtime binding and shared cohort
completion pointers. Keep P -> D -> C and all six conditions in each block.
This per-release command is not itself a durable 27-partition supervisor.
Full-study progression must run on Kubernetes independently of the app,
retain real finite deadlines/resumption, and honor shared locks and stage gates.
Never substitute a diagnostic registration or `bound-cells.jsonl` for its
released `queue.jsonl`. Retain all raw arrays/videos/request traces on the
PVC and commit only compact evidence and hashes.

The worker now supports an explicitly opted-in, hash-bound
[replacement-Job admission](../../docs/STANDALONE_RUNTIME.md#resuming-under-a-replacement-job).
This fixes the otherwise unavoidable stale Job/Pod UID in an immutable
allocation receipt without rewriting scientific release hashes or replaying
completed cells. Its regression check stops after one synthetic completion,
rejects the replacement Job's old allocation, then resumes only the remaining
five cells with fresh operational authority. This is CPU engineering evidence,
not a native study-resume claim.
