#!/bin/bash
# Run on the cluster after labelers A and B finish:
#   bash $R/code/tools/robolab_workshop_cluster/finish_vlm.sh <adjudicator-endpoints>
set -euo pipefail
R=/data/users/ali/rws-20260926
P=/data/users/ali/vla_wam/envs/robolab-v2-isaac50/bin/python
EP=${1:?adjudicator endpoints}
A=$R/annotation
cd $R/code
m() { $P -m experiments.robolab_workshop.$*; }
m vlm_label clean --src $A/labels_vlm_a_raw.jsonl --dest $A/labels_vlm_a.jsonl
m vlm_label clean --src $A/labels_vlm_b_raw.jsonl --dest $A/labels_vlm_b.jsonl
m vlm_label agreement --annotation $A --labels $A/labels_vlm_a.jsonl $A/labels_vlm_b.jsonl --dest $A/vlm_agreement.json
m vlm_label adjudicate --annotation $A --labels $A/labels_vlm_a.jsonl $A/labels_vlm_b.jsonl --endpoints "$EP" \
  --model qwen3-vl-235b --out $A/labels_vlm_adjudicated_raw.jsonl --concurrency 32
m vlm_label clean --src $A/labels_vlm_adjudicated_raw.jsonl --dest $A/labels_vlm_adjudicated.jsonl
m annotation unblind --out $A --labels $A/labels_vlm_a.jsonl $A/labels_vlm_b.jsonl \
  --adjudication $A/labels_vlm_adjudicated.jsonl --dest $R/analysis/forecast_labels_vlm.jsonl
mkdir -p $R/results_vlm
m analyze --features $R/analysis/conf_features.jsonl --labels $R/analysis/forecast_labels_vlm.jsonl --out $R/results_vlm
m report --features $R/analysis/conf_features.jsonl --results $R/results_vlm/results.json --release $R/release/release.json \
  --out $R/results_vlm
cp $A/vlm_agreement.json $R/results_vlm/
echo FINISHED
