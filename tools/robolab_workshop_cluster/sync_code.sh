#!/bin/bash
# usage: sync_code.sh <pod>   -> syncs repo code to /data/users/ali/rws-20260926/code
set -e
POD=${1:-211247-alia40a-a40-2gpu}
cd /Users/SZ5VJY/.copilot/session-state/5a07b8a7-a666-4758-8de5-62ca44621e3d/files/wams
COPYFILE_DISABLE=1 tar czf - experiments/__init__.py experiments/robolab_workshop docs/robolab-workshop-20260926 tools/build_robolab_execution_handoff.py tests/robolab_workshop 2>/dev/null | \
  kubectl exec -i -n 211247-prod "$POD" -- bash -c 'mkdir -p /data/users/ali/rws-20260926/code && tar xzf - -C /data/users/ali/rws-20260926/code 2>/dev/null; find /data/users/ali/rws-20260926/code -name "._*" -delete; echo synced'
