# Proposed RoboLab workshop paper

**Read the scene and prompt catalog first. No new experiments have started.**

The fixed research question is: **Can a world-action model's predicted future help distinguish following the wrong goal from failing to execute the right one?**

| Read in this order | What it contains |
|---|---|
| [Illustrated PDF](../../output/pdf/ROBOLAB_SCENES_AND_PROMPTS.pdf) | Actual initial scene images, native nominal prompts, all proposed wording and goal changes |
| [Editable scene/prompt catalog](SCENES_AND_PROMPTS.md) | Same catalog for review and editing |
| [Paper design](PAPER_DESIGN.md) | Question, workshop fit, hypotheses, closest work, working abstract and four-page structure |
| [Experiment specification](EXPERIMENT_SPEC.md) | Fixed comparisons, stages, metrics, controls, budgets and agent work packages |
| [Prompt JSON](prompt_matrix.json) | Exact strings, goal bindings and hashes |
| [Study manifest](study_manifest.json) | Budget and eligibility summary; launch disabled |
| [Native task inventory](native_spatial_inventory.json) | All 29 spatial task definitions from the pinned RoboLab source |

The primary proposal uses five scenes, fourteen physical goals and forty-two instructions. The mug scene and extra distance/object/between-bin tests are separate. A maximum of 1,008 confirmation episodes is proposed for three models; model eligibility and measurements must be resolved first. Existing 15 Nano episodes remain exploratory evidence.

This proposal is separate from the old 87-layout SGW-01 package and its executable queue. No cluster agent should feed this catalog into the old launcher or assume that scene qualification, camera overrides or scores transfer between the two studies.
