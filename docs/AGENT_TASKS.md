# Work split for the cluster agents

This study has one shared scene package and two model branches. Scene design
belongs to this repository. The cluster agents should use its selected scenes,
not invent another environment or restart the scene search.

The 1,044-episode study has not been started. The work below prepares a future
launch; running learned policies requires the user's separate instruction.

## 1. Shared scene transfer

Owner: one agent for both model branches.

1. Check `REPOSITORY_STATUS.json` and the final scene registry. Continue only
   when the physical package has 87 selected layouts and `ready: true`.
2. Install the pinned RoboLab checkout and exact asset bytes. Use
   [scene materialization](SCENE_MATERIALIZATION.md) to regenerate overlays
   at the cluster's real paths and produce the per-cell environment binding.
3. Preserve flat-table LAT/DIST, raised supports only for HEIGHT, clean
   lighting, the robot and all three cameras. Preserve measured object poses,
   side assignments, prompts and seeds. Reuse the completed scripted evidence.
4. Record the actual image, storage, source commit and asset paths. Give the
   same physical fixture hashes and environment binding to both model owners.

Deliverable: the materialized physical package and its exact location. This
does not create a runtime release or establish model/time-map qualification.

## 2. Model integration

Owners: one N3 agent and one D1 agent, working independently.

Use the official pinned model configuration and the existing wrapper. Bind
the actual policy endpoint, GPU ownership, reset/session behavior, action
interface and model-input cameras. Use `effective_policy_seed` from the frozen
queue; the environment uses its separate `environment_seed`.

Generated futures need an evidenced camera and physical-time mapping to the
actions that were actually executed. If that mapping or decoded output is
unavailable, retain the record and report the corresponding prediction metric
as unavailable. Do not assign zero or infer a timing map from array shape.

Deliverable: actual runtime and time-map evidence for the model, with remaining
gaps stated. Preparing code and configuration is allowed here; do not issue
learned-policy requests until the user authorizes that work.

## 3. Execution after authorization

Use the [18 existing model/family/stage partitions](CLUSTER_HANDOFF.md), with
P, then D, then C. Keep each six-condition block intact and in its frozen
order. All 18 releases belong under one **fresh clean-study parent**, separate
from earlier completion and attempt records. Respect the existing model locks.

Do not change scenes or prompts in response to model failures. Valid failures
are results. Technical interruptions retain their original records and use
the existing attempt/resume mechanism. Do not repeat completed cells.

Deliverables: 1,044 accounted-for planned cells, their completion/missingness
records, raw observations and generated outputs, and the recorded time maps.
The budget is 36 pilot, 144 development and 864 confirmation episodes.

## 4. Analysis and paper

Owner: one analysis agent, using the recorded outputs.

The primary comparison is reference-inverted versus subject-first wording for
the **same physical goal and starting scene**. Direct wording is a construction
control; the opposite goal checks directional responsiveness. Keep physical
goal separation in metres distinct from binary success asymmetry.

Compare generated futures with actual execution and persistence at verified
matching times. Report uncertainty across independent layouts; resets,
wordings and repeated frames do not create additional independent layouts.
Separate physical failures, technical missingness and unavailable predictions.

Follow [the equivalence safeguard](EQUIVALENCE_ANALYSIS_NOTE.md): a collapsed
bootstrap interval or nonsignificant difference does not establish equivalence.
Do not make a positive equivalence claim before a valid procedure is specified.

Removing DIST pedestals is a design correction, not an additional support
ablation. Cross-family differences do not isolate spatial-axis understanding.
Use only this clean cohort in the paper. Update claims from measured outcomes,
not from the scripted scene checks or from an expected finding.
