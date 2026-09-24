#!/usr/bin/env bash
set -euo pipefail

check_only=false
if [[ "${1:-}" == "--check-only" ]]; then
    check_only=true
    shift
fi
if [[ $# -lt 2 ]]; then
    echo "usage: cluster_policy_bootstrap.sh [--check-only] N3|E3|F3 PYTHON [ARGS...]" >&2
    exit 64
fi
model=$1
shift
case "$model" in
    N3|E3|F3) ;;
    *) echo "unsupported active checkpoint: $model" >&2; exit 64 ;;
esac
if [[ "$1" != /* || ! -x "$1" ]]; then
    echo "an absolute executable model interpreter is required: $1" >&2
    exit 66
fi
python_bin=$(dirname "$1")
export PATH="$python_bin:$PATH"

native_dirs=${SGW01_NATIVE_LIBRARY_DIRS:-/data/users/ali/vla_wam/envs/robolab-native-libs-ubuntu2204/usr/lib/x86_64-linux-gnu:/data/users/ali/glvnd/lib:/data/users/ali/vla_wam/envs/fastwam-native-libs/lib:/usr/lib/x86_64-linux-gnu}
IFS=: read -r -a directories <<< "$native_dirs"
for directory in "${directories[@]}"; do
    if [[ "$directory" != /* || ! -d "$directory" ]]; then
        echo "required native library directory is unavailable: $directory" >&2
        exit 66
    fi
done
export LD_LIBRARY_PATH="$native_dirs${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

# Check the actual dependency that failed before any model construction.
if [[ "$model" == N3 || "$model" == E3 ]]; then
    if [[ ! -x "$python_bin/uvx" ]]; then
        echo "required Cosmos checkpoint helper is unavailable: $python_bin/uvx" >&2
        exit 66
    fi
    "$python_bin/uvx" --version
    "$1" -c 'import cv2; from retinaface.data import cfg_re50; print("OpenCV/RetinaFace startup imports passed; zero model requests", flush=True)'
else
    "$1" -c 'import torch, transformers, natten; print("FLUX startup imports passed; zero model requests", flush=True)'
fi
if "$check_only"; then
    exit 0
fi
exec "$@"
