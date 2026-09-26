# Local Nano across two RTX 3090 GPUs

This wrapper retains the pinned native Nano service, BF16 weights, sampling
settings, observation transforms, action postprocessing and same-request video
decoding. It exposes the official OpenPI websocket on rank zero. Each request
is broadcast over Gloo; both FSDP ranks execute the native call and acknowledge
retention before the response is returned. Native failures terminate that rank
immediately; torchrun owns and terminates its peer. A watchdog bounds native
requests and total process lifetime. There are no retries.

The pinned source defaults to full FSDP across `WORLD_SIZE`. It does not expose
core-model CPU offload or `device_map`. Auxiliary guardrails remain enabled and
use the official `offload_guardrail_models=True` setup option. This placement
change is recorded. Two-rank GPU fit and numerical behavior require native
qualification; the small CPU tests are transport checks only.

Use a separate clean pinned Cosmos checkout with the existing Cosmos Python
environment. The downloaded checkpoint must have the exact registered file
sizes, config hash, and Hugging Face revision metadata. Full weight SHA256s are
not recomputed on every launch; the receipt states that limit explicitly.

Example after copying this directory and the manifest to the workstation:

```sh
CUDA_VISIBLE_DEVICES=0,1 \
HF_HOME=/home/ali/cosmos-framework/.cache/huggingface \
HF_HUB_OFFLINE=1 PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
/home/ali/cosmos-framework/.venv/bin/python -m torch.distributed.run \
  --standalone --nnodes=1 --nproc-per-node=2 \
  /home/ali/wam-nano-stock-20260926/study/tools/workstation_nano_server/server.py \
  --source-root /home/ali/wam-nano-stock-20260926/cosmos-framework \
  --checkpoint-path /home/ali/wam-nano-stock-20260926/checkpoints/nano \
  --checkpoint-manifest /home/ali/wam-nano-stock-20260926/study/artifacts/vla_wam_shared_v2/pilot/expansion/cosmos3_nano_policy_droid_v2a011_registry.json \
  --output /home/ali/wam-nano-stock-20260926/server-attempt-01 \
  --receipt /home/ali/wam-nano-stock-20260926/server-attempt-01/ready.json \
  --port 18026 --seed 6100 --max-requests 96 --wall-seconds 10800 \
  --request-timeout 900 --offload-guardrails
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
