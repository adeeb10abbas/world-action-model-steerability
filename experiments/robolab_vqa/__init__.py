"""RQA-20261006: inference-only RoboLab VQA diagnostic (scene, instruction, instruction+scene).

Design: docs/robolab-vqa-20261006/EXPERIMENT_GUIDE.md. Modules:
  common      constants, hashing, catalog loading, query ordering
  labels      gold labels, boundary flags and visibility pre-checks from saved tick records
  prompts     frozen wrappers and chat-message rendering
  inventory   resolve saved observations / ticks / hashes on the cluster (inventory.json)
  eligibility checkpoint lineage and tensor audit (model_eligibility.csv)
  prepare     build the immutable data release (images, queries, gold, audit packets)
  validate    release checks before inference
  parse       frozen answer parsers
  adapters    native reasoner readouts (vLLM)
  run         execute a lane over the frozen release
  analyze     scoring, paired statistics, coverage, tables and figures
"""
