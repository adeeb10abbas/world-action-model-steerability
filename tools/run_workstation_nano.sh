#!/usr/bin/env bash
# One finite, separately recorded stock-scene Nano diagnostic on the workstation.
set -euo pipefail
run_root=${1:-/home/ali/wam-nano-stock-20260926}
attempt=${2:-attempt-001}
attempt_root="$run_root/$attempt"
mkdir "$attempt_root"
exec > >(tee -a "$attempt_root/launch.log") 2>&1
date -u
printf 'Run directory: %s\n' "$attempt_root"

# Wait for the already-started exact-revision download, with a finite deadline.
/home/ali/cosmos-framework/.venv/bin/python - "$run_root" <<'PY'
import json, pathlib, sys, time
root = pathlib.Path(sys.argv[1])
files = json.loads((root / 'checkpoint-manifest.json').read_text())['checkpoint']['files']
deadline = time.monotonic() + 1800
previous = None
while True:
    present = sum((root / 'checkpoints/nano' / p).is_file()
                  and (root / 'checkpoints/nano' / p).stat().st_size == spec['bytes']
                  for p, spec in files.items())
    if present != previous:
        print(f'Checkpoint files complete: {present}/{len(files)}', flush=True)
        previous = present
    if present == len(files):
        break
    if time.monotonic() >= deadline:
        raise SystemExit('Checkpoint download did not finish within 30 minutes; no model launched.')
    time.sleep(5)
PY

export PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1
export CUDA_VISIBLE_DEVICES=0,1
export PYTHONPATH="$run_root/cosmos-framework"
export TOKENIZERS_PARALLELISM=false
export OMP_NUM_THREADS=4
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
/home/ali/cosmos-framework/.venv/bin/torchrun --standalone --nproc_per_node=2 \
  "$run_root/code/tools/workstation_nano_server/server.py" \
  --source-root "$run_root/cosmos-framework" \
  --checkpoint-path "$run_root/checkpoints/nano" \
  --checkpoint-manifest "$run_root/checkpoint-manifest.json" \
  --output "$attempt_root/server" --port 18026 --seed 6100 \
  --max-requests 90 --wall-seconds 10800 --request-timeout 900 \
  > "$attempt_root/server.log" 2>&1 &
server_pid=$!
printf '%s\n' "$server_pid" > "$attempt_root/server.pid"
trap 'kill "$server_pid" 2>/dev/null || true; wait "$server_pid" 2>/dev/null || true' EXIT

/home/ali/cosmos-framework/.venv/bin/python - "$attempt_root" "$server_pid" <<'PY'
import os, pathlib, socket, sys, time
root, pid = pathlib.Path(sys.argv[1]), int(sys.argv[2])
deadline = time.monotonic() + 1800
while True:
    os.kill(pid, 0)
    if (root / 'server/ready.json').exists():
        try:
            with socket.create_connection(('127.0.0.1', 18026), timeout=1):
                break
        except OSError:
            pass
    if time.monotonic() >= deadline:
        raise SystemExit('Model startup exceeded 30 minutes; no episodes launched.')
    time.sleep(2)
print('Nano server is ready; starting the six stock-scene cells.', flush=True)
PY

# Vulkan enumerates physical devices independently of CUDA masking. This host
# also has duplicate NVIDIA ICD registrations; select one for this process.
unset CUDA_VISIBLE_DEVICES
export VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/nvidia_icd.json
export PYTHONPATH="$run_root/code:/home/ali/sgw-scene-design-20260923/RoboLab:/home/ali/openpi-robolab/packages/openpi-client/src"
export OMNI_KIT_ACCEPT_EULA=YES ACCEPT_EULA=Y
export XDG_CACHE_HOME=/home/ali/sgw-scene-design-20260923/cache/xdg
export WARP_CACHE_PATH=/home/ali/sgw-scene-design-20260923/cache/warp
export MPLCONFIGDIR=/home/ali/sgw-scene-design-20260923/cache/matplotlib
env -u DISPLAY -u WAYLAND_DISPLAY timeout --signal=TERM --kill-after=30s 10800 \
  /home/ali/sgw-scene-design-20260923/venv/bin/python \
  "$run_root/code/tools/workstation_nano/run.py" \
  --robolab-root /home/ali/sgw-scene-design-20260923/RoboLab \
  --output-root "$attempt_root/episodes" \
  --server-receipt "$attempt_root/server/ready.json" \
  --remote-host 127.0.0.1 --remote-port 18026 --device cuda:1 --headless \
  "--kit_args=--portable-root=$attempt_root/kit --/rtx/verifyDriverVersion/enabled=false --/renderer/multiGpu/enabled=false --/renderer/activeGpu=1" \
  > "$attempt_root/episodes.log" 2>&1
date -u
printf 'Six-cell runner finished. Results: %s\n' "$attempt_root/episodes"
