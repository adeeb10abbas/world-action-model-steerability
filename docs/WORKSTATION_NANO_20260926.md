# Nano on stock RoboLab tasks: first workstation run

The user explicitly requested Cosmos Nano experiments on the local workstation
on 26 September 2026. This is a separate exploratory run using existing RoboLab
tasks, not a continuation or replacement of the registered 1,566-cell cohort.
Existing cluster records, queues and outcomes remain unchanged.

## First batch

Run six episodes on the unmodified `rubiks_cube_banana_bowl.usda` scene:
left/right goals crossed with direct, syntax-matched and reference-inverted
instructions. Always move the cube. Use the stock left-task scene for every
condition; upstream's right task otherwise adds a mug and bin. Keep the original
RoboLab DROID cameras, robot, object geometry and initial configuration. Do not
rebuild scenes or reuse the close camera override.

Each episode uses environment seed 6100 and deterministic policy seed 6100,
32-action chunks and at most 450 executed actions. Disable goal-triggered early
termination. Save the exact prompt, actual initial state and sensor images,
returned and executed actions, object/robot trajectories, viewport video and
same-request decoded futures. Compare actual reset states before describing
conditions as matched. Preserve errors and partial attempts; no automatic
episode retries or replacement of behavioral failures.

This is one scene with six conditions, not six independent scene samples.
The stock initial scene may already satisfy one relation. Record that fact and
movement/grasp/release evidence; initial relation satisfaction alone is not
successful instruction following. The first batch checks basic manipulation,
wording response and recording. It cannot establish generalization or support
paper-wide success-rate claims. Forecast timing must be checked before scoring
prediction accuracy.

## Model and hardware

- Checkpoint: `nvidia/Cosmos3-Nano-Policy-DROID`, revision
  `6706d7680581c255ff61e0f3bb49d90eac55c79e`.
- Cosmos source: `411d25b2e35bc441126f48c44a4b93e1c0564274`.
- RoboLab: `0aef241fb088ca21bb4ebd24448940ed56620d17`.
- BF16 weights, guidance 3, four denoising steps, shift 5, history 1,
  conditioning FPS 15, resolution 480, joint-position actions, video decoding.
- Workstation: `ssh workstation`, two RTX 3090 GPUs with 24 GiB each.
- Working directory: `/home/ali/wam-nano-stock-20260926`.

The approximately 33 GB checkpoint does not fit on a single GPU. The planned
server uses the framework's distributed sharding and broadcasts each request
to both ranks, with only rank zero serving the WebSocket. This is a hardware
adaptation requiring an actual successful model request before being called
operational. No quantization or substitute checkpoint is authorized by this
plan. Runtime memory, latency, request counts and exact source identities will
be recorded from execution.

## Current state

Workstation connectivity restored after the user's intervention. Both GPUs
were idle at inspection. All 43 checkpoint files have the registered byte sizes.
The first transfer stalled; its partial files and logs were retained, and a
standard HTTP transfer completed the download. Full weight hashes were not
recomputed. The separate Cosmos checkout is pinned to the revision above.

Startup attempts 001 and 002 failed before any inference requests or robot
actions because auxiliary dependencies were missing. Their original logs and
terminal records remain under the working directory. Attempt 003 loaded Nano
on both GPUs but failed to initialize the simulator because Vulkan enumerated
each GPU twice. Selecting one existing NVIDIA ICD per simulator process and
using physical GPU 1 resolved that issue in attempt 004. No host driver changes
were made.

Attempt 004 created the stock scene and captured its first observations, but
the first model request exhausted GPU 1 memory: approximately 15.94 GiB for the
model process plus 7.66 GiB for the simulator. No actions were returned or
executed.

Attempt 005 enables PyTorch FSDP2 CPU offloading of BF16 parameter shards;
the checkpoint, sampling settings and scene cameras stay fixed. The separate
two-GPU toy qualification matched its unsharded BF16 reference exactly over
three forwards using the native checkpoint reader. The full Nano load then
validated 809 pinned CPU parameter shards per rank (15,173,136,576 local bytes),
with other parameters and buffers retaining native CUDA placement. Idle GPU
residency after loading was approximately 2.3 GB per GPU. First inference began
at 06:40 UTC on 26 September; no completed episodes are claimed yet.

The native loader uses these external assets even though the Nano checkpoint
also bundles tokenizer and VAE files:

| Dependency | Revision | Use |
| --- | --- | --- |
| `nvidia/Cosmos-Guardrail1` | `d6d4bfa899a71454a700907664f3e88f503950cf` | Original blocklist and face filter |
| `Qwen/Qwen3Guard-Gen-0.6B` | `fada3b2f655b89601929198343c94cd2f64d93cc` | Original text guardrail |
| `Qwen/Qwen3-VL-8B-Instruct` | `0c351dd01ed87e9c1b53cbc748cba10e6187ff3b` | Tokenizer and processor only |
| `Wan-AI/Wan2.2-TI2V-5B` | `921dbaf3f1674a56f47e83fb80a34bac8a8f203e` | `Wan2.2_VAE.pth` |

The Qwen cached `main` references resolve to the recorded revisions, and the
run uses offline mode. Dependency download receipts are in `logs/`. Guardrails
remain enabled, using the official option to place them on CPU.

No changes to Overleaf or numerical paper results are implied by this note.
