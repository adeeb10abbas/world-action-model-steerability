# RoboLab workshop paper and cluster handoff

**Ready to share with execution agents; no new experiments have started.** Start with the scene/prompt catalog to understand the study, or the cluster handoff to implement it.

The fixed research question is: **Can a world-action model's predicted future help distinguish following the wrong goal from failing to execute the right one?**

| Read in this order | What it contains |
|---|---|
| [Cluster execution specification](CLUSTER_EXECUTION_SPEC.md) | Full N3/E3/F3 run contract, exact budgets, finite preparation, scoring, capture and Kubernetes requirements |
| [Copyable agent handoff](AGENT_HANDOFF.md) | One prompt to send your execution coordinator |
| [Implementation work packages](IMPLEMENTATION_PLAN.md) | Files, interfaces, acceptance cases and division of work |
| [Model pins and settings](MODEL_CONFIGS.json) | Checkpoint/source identities and per-model sampling/preprocessing differences |
| [All planned episodes](planned_episodes.jsonl) / [blocks](planned_blocks.json) | 1,008 confirmation plus 46 development cells; unbound planning inventory, not a launch release |
| [Illustrated PDF](../../output/pdf/ROBOLAB_SCENES_AND_PROMPTS.pdf) | Actual initial scene images, native nominal prompts, all proposed wording and goal changes |
| [Editable scene/prompt catalog](SCENES_AND_PROMPTS.md) | Same catalog for review and editing |
| [Paper design](PAPER_DESIGN.md) | Question, workshop fit, hypotheses, closest work, working abstract and four-page structure |
| [Experiment specification](EXPERIMENT_SPEC.md) | Fixed comparisons, stages, metrics, controls, budgets and agent work packages |
| [Prompt JSON](prompt_matrix.json) | Exact strings, goal bindings and hashes |
| [Study manifest](study_manifest.json) | Budget and eligibility summary; launch disabled |
| [Native task inventory](native_spatial_inventory.json) | All 29 spatial task definitions from the pinned RoboLab source |

The primary proposal uses five scenes, fourteen physical goals and forty-two instructions. The mug scene and extra distance/object/between-bin tests are separate. A maximum of 1,008 confirmation episodes is proposed for three models; model eligibility and measurements must be resolved first. Existing 15 Nano episodes remain exploratory evidence.

This proposal is separate from the old 87-layout SGW-01 package and its executable queue. No cluster agent should feed this catalog into the old launcher or assume that scene qualification, camera overrides or scores transfer between the two studies.
