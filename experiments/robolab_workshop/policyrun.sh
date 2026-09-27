#!/bin/bash
# Launch one serialized policy server lane.
# usage: policyrun.sh <N3|E3|F3> <gpu_index> <port> <run_dir> [extra args...]
MODEL=$1; GPU=$2; PORT=$3; RUN=$4; shift 4
SGW=/data/users/ali/sgw-01/current-20260924a
case $MODEL in
  N3) PY=/data/users/ali/vla_wam/envs/cosmos-nano-411d25b-v3-exact/bin/python
      SRC=/data/users/ali/vla_wam/external/cosmos-framework-411d25b
      CKPT=/data/users/ali/vla_wam/checkpoints/cosmos3_nano_policy_droid
      ARGS="--revision 6706d7680581c255ff61e0f3bb49d90eac55c79e"
      export HF_HOME=/data/users/ali/vla_wam/cache/huggingface-cosmos
      SRCPATH=$SRC ;;
  E3) PY=/data/users/ali/vla_wam/envs/cosmos-edge-a904d2d-v3-exact/bin/python
      SRC=$SGW/external/cosmos-cf5d68c
      CKPT=$SGW/checkpoints/cosmos3-edge-a7c7288
      ARGS="--revision a7c7288f9b6ac1684e993007b0f9703dd26e58ef"
      export HF_HOME=/data/users/ali/vla_wam/cache/huggingface-cosmos
      SRCPATH=$SRC ;;
  F3) PY=$SGW/envs/flux-e2dd1d8/bin/python
      SRC=$SGW/external/flux-action-e2dd1d8
      CKPT=$SGW/checkpoints/flux-3-action-droid-3d0887b
      ARGS="--base $SGW/checkpoints/flux-3-action-base-62878e2"
      SRCPATH=$SRC/src ;;
  *) echo "bad model" >&2; exit 64 ;;
esac
export CUDA_DEVICE_ORDER=PCI_BUS_ID CUDA_VISIBLE_DEVICES=$GPU
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONUNBUFFERED=1
export PATH=$(dirname $PY):$PATH
export LD_LIBRARY_PATH=/data/users/ali/vla_wam/envs/robolab-native-libs-ubuntu2204/usr/lib/x86_64-linux-gnu:/data/users/ali/glvnd/lib:/data/users/ali/vla_wam/envs/fastwam-native-libs/lib:/usr/lib/x86_64-linux-gnu
export UV_CACHE_DIR=$SGW/cache/uv UV_TOOL_DIR=$SGW/cache/uv/tools
LANE_CACHE=/tmp/rws-policy-$(hostname)-$GPU-$PORT
mkdir -p $LANE_CACHE $RUN
export XDG_CACHE_HOME=$LANE_CACHE TRITON_CACHE_DIR=$LANE_CACHE/triton TORCHINDUCTOR_CACHE_DIR=$LANE_CACHE/inductor
export PYTHONPATH=/data/users/ali/rws-20260926/code:$SRCPATH
cd /data/users/ali/rws-20260926/code
setsid nohup $PY -m experiments.robolab_workshop.policy_server --model $MODEL --port $PORT --run-dir $RUN \
  --source $SRC --checkpoint $CKPT $ARGS "$@" > $RUN/server.log 2>&1 < /dev/null &
echo "pid $!"
