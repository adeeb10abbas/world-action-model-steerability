# Local Nano across two RTX 3090 GPUs

This wrapper retains the pinned native Nano service, BF16 weights, sampling
settings, observation transforms, action postprocessing and same-request video
decoding. It exposes the official OpenPI websocket on rank zero. Each request
is broadcast over Gloo; both FSDP ranks execute the native call and acknowledge
retention before the response is returned. Native failures terminate that rank
immediately; torchrun owns and terminates its peer. A watchdog bounds native
requests and total process lifetime. There are no retries.

The pinned source defaults to full FSDP across `WORLD_SIZE`. It does not expose
core-model CPU offload or `device_map`. The wrapper's opt-in `--offload-fsdp`
uses PyTorch `CPUOffloadPolicy(pin_memory=True)` at the two native FSDP call
sites. It materializes FSDP DTensor shards in pinned CPU memory while retaining
the native CUDA placement of buffers and unsharded parameters. The unchanged
native DCP safetensors reader loads directly into those CPU-backed shards.
PyTorch transfers shards to CUDA before each all-gather; explicit
`reshard_after_forward=True` also releases the root network's gathered weights
after its forward. This trades host RAM and transfer time for GPU memory.
The pinned Cosmos files, BF16 precision, complete checkpoint, sampling settings,
and cameras are unchanged. The hooks are removed after model construction.

The server defaults to no core offload; the workstation launcher below explicitly
passes `--offload-fsdp`. Both rank runtime records and websocket metadata include
`fsdp_placement`, with policy, materialization count, and verified CPU/pinned/BF16
shard placement after checkpoint loading. Auxiliary guardrails remain enabled
and use the official `offload_guardrail_models=True` setup option.

A tiny two-GPU test passed on installed PyTorch 2.10.0+cu128 using the pinned
Cosmos safetensors reader/planner, native-style initialization, and this same
placement hook. Three forwards matched the unsharded BF16 reference exactly;
shards returned to pinned CPU memory and ordinary buffers stayed on CUDA.
Evidence is under `/home/ali/wam-nano-stock-20260926/offload-qualification-003/`
with the adjacent `.log`. This qualifies the placement mechanism, not full Nano
memory use, inference latency, or policy quality. The small CPU tests below
qualify transport only.

Use a separate clean pinned Cosmos checkout with the existing Cosmos Python
environment. The downloaded checkpoint must have the exact registered file
sizes, config hash, and Hugging Face revision metadata. Full weight SHA256s are
not recomputed on every launch; the receipt states that limit explicitly.

The workstation launcher runs the server, waits for readiness, starts the six
episodes, and stops its server when the client finishes. After deploying the
code and the dependencies recorded in `docs/WORKSTATION_NANO_20260926.md`, use
a new attempt name:

```sh
bash /home/ali/wam-nano-stock-20260926/code/tools/run_workstation_nano.sh \
  /home/ali/wam-nano-stock-20260926 attempt-NEW
```

The receipt and websocket metadata are identical and include the resolved
native config, pins, FSDP/CFG/context degrees and resource bounds. The ready
receipt means both ranks loaded and are ready to bind; verify `/healthz` or
the websocket handshake to confirm actual socket readiness. Existing output
directories with rank records are rejected. Both GPUs are occupied by the
policy; shared simulator memory must be assessed after loading.

`policy.infer({"_workstation_control": "reset"})` performs an acknowledged
two-rank reset boundary without consuming inference budget. With native
`history_length=1` and deterministic seed, every sample is constructed fresh;
there is no persistent observation history to erase. Reset does not reset the
simulator. The client owns its physical reset separately.

Each rank retains runtime and request records. Rank zero additionally retains
input arrays, actions and decoded futures. Futures remain `decoded_unmapped`:
successful capture does not establish physical time or camera correspondence.
Terminate the owned torchrun process group after the finite client finishes;
do not signal unrelated GPU processes.

CPU verification:

```sh
python tools/workstation_nano_server/test_server.py
CUDA_VISIBLE_DEVICES='' /home/ali/cosmos-framework/.venv/bin/python \
  -m torch.distributed.run --standalone --nproc-per-node=2 \
  tools/workstation_nano_server/cpu_gloo_check.py
```

The optional toy GPU qualification uses no Nano weights or simulator. Run it
only when both GPUs are available, with a fresh output path:

```sh
PYTHONPATH=/home/ali/wam-nano-stock-20260926/cosmos-framework \
  HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 CUDA_VISIBLE_DEVICES=0,1 \
  /home/ali/cosmos-framework/.venv/bin/torchrun --standalone --nproc_per_node=2 \
  tools/workstation_nano_server/offload_gloo_nccl_check.py \
  --output /home/ali/wam-nano-stock-20260926/offload-qualification-NEW
```
