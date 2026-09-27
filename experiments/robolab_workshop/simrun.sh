#!/bin/bash
# Run a python module in the pinned RoboLab/Isaac environment.
# usage: simrun.sh <gpu_index> <log_file> <module> [args...]
GPU=$1; LOG=$2; shift 2
export CUDA_DEVICE_ORDER=PCI_BUS_ID CUDA_VISIBLE_DEVICES=$GPU
export LD_LIBRARY_PATH=/data/users/ali/vla_wam/envs/robolab-native-libs-ubuntu2204/usr/lib/x86_64-linux-gnu:/data/users/ali/glvnd/lib:/data/users/ali/vla_wam/envs/fastwam-native-libs/lib:/usr/lib/x86_64-linux-gnu
export OMNI_KIT_ACCEPT_EULA=YES ACCEPT_EULA=Y PRIVACY_CONSENT=Y
LANE_CACHE=/tmp/rws-cache-$(hostname)-$GPU${RWS_CACHE_TAG:+-$RWS_CACHE_TAG}
mkdir -p $LANE_CACHE
export XDG_CACHE_HOME=$LANE_CACHE WARP_CACHE_PATH=$LANE_CACHE/warp MPLCONFIGDIR=$LANE_CACHE/mpl
export PYTHONPATH=/data/users/ali/rws-20260926/code:/data/users/ali/rws-20260926/external/RoboLab-0aef241:/data/users/ali/openpi/packages/openpi-client/src
export PYTHONUNBUFFERED=1
cd /data/users/ali/rws-20260926/code
if [ "$LOG" = "-" ]; then exec /data/users/ali/vla_wam/envs/robolab-v2-isaac50/bin/python -m "$@"; fi
mkdir -p $(dirname $LOG)
exec setsid nohup /data/users/ali/vla_wam/envs/robolab-v2-isaac50/bin/python -m "$@" > "$LOG" 2>&1 < /dev/null &
