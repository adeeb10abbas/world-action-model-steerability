# Current cluster continuation

The user separately authorized runtime integration, bounded checks, and the
committed study on 24 September 2026. This supersedes the preparation-only
permission recorded in the original delivery. **No behavioral release or study
episode has started.** Do not equate the implemented adapters, model loading,
or the destination check below with qualified model inference.

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
  Their actual runtimes and capture parity remain unqualified.

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

The following **CPU-only** startup check passed in the approved container:

```sh
bash tools/cluster_policy_bootstrap.sh --check-only N3 \
  /data/users/ali/vla_wam/envs/cosmos-nano-411d25b-v3-exact/bin/python
```

It verifies `uvx 0.10.8` and imports OpenCV/RetinaFace without model construction.
OpenCV is `4.13.0`. A normal invocation runs that same startup check and then
executes the supplied command:

```sh
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

## Remaining gates and resume

Finish actual N3/E3/F3 construction/inference checks and same-request capture
parity, then establish the physical action-prefix/camera/time correspondence.
Preserve unavailable forecasts explicitly. Complete guarded runtime/fixture
receipts before creating any full model/family/stage release.

There is currently **no release to resume**. Once released, the existing
`native_worker_entrypoint --release <immutable-release> --model <model>
--family <family> --stage <stage> --resume --max-valid-episodes <6|24|144>`
is the resume interface, using the same runtime binding and shared cohort
completion pointers. Keep P -> D -> C and all six conditions in each block.
Never substitute a diagnostic registration or `bound-cells.jsonl` for its
released `queue.jsonl`. Retain all raw arrays/videos/request traces on the
PVC and commit only compact evidence and hashes.
