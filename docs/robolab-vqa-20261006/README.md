# RoboLab VQA diagnostic — locked design

**RQA-20261006 · v1.0 · October 6, 2026**

The user approved three tests: scene understanding, instruction understanding, and instruction plus scene. Saved initial observations are primary; a shared sample of saved rollout observations is a separate robustness check. This is an inference-only addition to a four-page workshop paper. No new training, robot episodes, or manuscript changes are included.

Start with [EXPERIMENT_GUIDE.md](EXPERIMENT_GUIDE.md). The accompanying `question_catalog.json` contains the 36 original instruction strings, gold instruction roles, scene questions, and 16 new clause-placement controls. `protocol.json` records the design and source hashes; `frame_selection.json` fixes the secondary source episodes and timestamps. These are specification artifacts, **not an implemented runner or a completed evaluation**. Image availability, checkpoint eligibility, labels, and runtime configuration must be verified at the cluster before inference.

The separate [results report](../../reports/robolab-vqa-20261006/REPORT.md) is initialized with status **not run**. Agents must fill it after execution and preserve a versioned report for each run. [Coverage and decisions](DECISIONS_AND_COVERAGE.md) maps the agreed requirements to this packet, including the questions this scoped study cannot answer.

## Prompt to give an execution agent

Implement and run RQA-20261006 from `docs/robolab-vqa-20261006/EXPERIMENT_GUIDE.md` in the `world-action-model-steerability` repository, using the accompanying protocol, question catalog, and fixed frame selection. Use existing checkpoints and saved RWS-20260926 observations only. The executed study contains S1/S3/S4/S5, 32 physical starts, 12 goals, and 36 DIR/TF/RF instructions; the historical five-scene launch plan is superseded for this task.

First inventory saved images, synchronized state records, and exact model components. Then return a hashed, validated data release and an eligibility matrix identifying which checkpoints actually support native text/VQA readout. Preserve the exact instruction bytes, robot-frame definitions, and frozen bowl identities. Build the three tests, the text-only controls, and the small clause-placement control. Qualify on existing development fixtures, freeze the parser/settings, and run the fixed evaluation without outcome-based prompt tuning. Keep shared initial-state results separate from the fixed saved-rollout check. Continue eligible lanes when another is unsupported; never fabricate a VQA head or call an unsupported model a failure.

Deliver raw answers, exclusions and coverage, checkpoint/input provenance, deterministic scores with physical-start cluster intervals, a compact paper table, and an evidence-bounded interpretation. Generate the full separate report at `reports/robolab-vqa-20261006/REPORT.md`, retaining all planned results, including null/negative findings and failures. Preserve a versioned run report and update `CANDIDATE_FINDINGS.csv` so the author can later select supported findings for the paper. Commit and push implementation, small manifests, complete summary results, figures, and reports to `adeeb10abbas/world-action-model-steerability`, branch `codex/nano-stock-workstation-20260926`; verify the remote commit. Keep raw media/arrays, weights, and credentials outside Git with durable hashed references. Do not launch training, policy rollouts, new simulator scenes, extra benchmarks, or paper edits. Do not overwrite original evidence or treat old forecast VLM labels as ground truth. Follow the finite work and stop rules in the guide. Report implementation and execution separately; commands proposed in the guide must be implemented before they can be run.

## Suggested division when the user dispatches multiple agents

| Work package | Output |
|---|---|
| Data and questions | Shared frame release, synchronized gold labels, visibility review, exact query manifest |
| Checkpoints and inference | Eligibility/tensor audit, native VQA adapters, raw responses and runtime receipts |
| Scoring and paper summary | Parser checks, paired statistics, missingness report, one compact table and interpretation |

Data preparation and checkpoint inspection can proceed independently. Scoring can use synthetic fixtures while the data release is prepared. All inference lanes consume the same frozen release. This document does not itself dispatch agents or authorize this chat to launch cluster jobs.
