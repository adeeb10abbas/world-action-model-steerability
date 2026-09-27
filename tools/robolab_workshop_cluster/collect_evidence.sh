#!/bin/bash
# usage: collect_evidence.sh  -> copies compact evidence from the data volume into the repo artifacts dir
set -e
POD=211247-alia40b-a40-2gpu
R=/data/users/ali/rws-20260926
DEST=/Users/SZ5VJY/.copilot/session-state/5a07b8a7-a666-4758-8de5-62ca44621e3d/files/wams/artifacts/robolab_workshop_20260926
mkdir -p "$DEST"
kubectl exec -n 211247-prod "$POD" -c "$POD" -- bash -c "cd $R && tar czf - \
  states/accepted_states.json states/state_candidates.jsonl \
  \$(ls -d states/_scripted/_candidates__*/scripted_attempts.jsonl states/_scripted/S*-D00/scripted_attempts.jsonl 2>/dev/null) \
  \$(ls states/_candidates/*/proposals.jsonl) \
  \$(ls states/_scripted_rev*/*/scripted_attempts.jsonl 2>/dev/null) \
  release/release.json release/analysis_freeze.json release/EXECUTION_RECORD.at_release.md release/bound_confirmation_episodes.jsonl \
  \$(ls dev/servers/*/server_receipt.json) \
  \$(ls runs/lanes/*.jsonl) \
  \$(ls -d analysis/*.json analysis/*.jsonl results 2>/dev/null) \
  \$(ls annotation/build_receipt.json annotation/labels_template.csv 2>/dev/null) \
  \$(ls runs/episodes/*/COMPLETE.json) \
  \$(for d in runs/episodes/*; do a=\$(python3 -c \"import json;print(json.load(open('\$d/COMPLETE.json'))['attempt_dir'])\" 2>/dev/null) && echo \${a#$R/}/result.json; done) \
  2>/dev/null" | tar xzf - -C "$DEST"
du -sh "$DEST"
