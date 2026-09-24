# Start here: clean SGW-01 handoff

**Prepare the clean study; no learned-policy launch is authorized.** Read the [repository overview](../../../../README.md), [current status](../../../../REPOSITORY_STATUS.json), [agent work split](../../../../docs/AGENT_TASKS.md) and [cluster handoff](../../../../docs/CLUSTER_HANDOFF.md). Those documents describe the current implemented path and remaining native prerequisites.

## Scientific contract

Read [EXPERIMENT_SPEC.md](EXPERIMENT_SPEC.md) for the D/C/I comparison, fixed physical scorer, aligned forecast/persistence analyses and missingness rules. [WORKSHOP_FIT.md](WORKSHOP_FIT.md) explains the WAM contribution. Use only the clean cohort in the [canonical paper](../../../../docs/scene_design_rtx/overleaf/main.tex).

Preserve the 18 exact prompt strings, 1,044 planned cell identities, seeds and within-block order. A layout/model block contains all six conditions. Pilot/development/confirmation totals remain 36/144/864. The existing production release/worker path supports 18 model × family × stage partitions, with intact matched blocks.

## Implemented and pending

Scene generators, the scorer, recorder, wrappers, release builder and production worker exist. Continue qualification and integration through those entrypoints. Do not reimplement the worker or launch a second scene search because older planning records describe implementation as unverified.

The shared scene package needs 87 qualified selected layouts. Use the active bounded candidate registration and preserve its first-100-per-family eligibility and existing clean receipts. Then follow [scene materialization](../../../../docs/SCENE_MATERIALIZATION.md) to regenerate path-bound overlays against the cluster's pinned assets. Native model reset/action behavior, decoded-future camera/time mapping, ownership, image and persistent-storage bindings require real receipts before a later authorized release.

The task roles and their concrete deliverables are maintained in [AGENT_TASKS.md](../../../../docs/AGENT_TASKS.md). Preparing this handoff does not dispatch agents, allocate resources, issue inference or apply a Job. Future study execution requires the user's separate instruction and a fresh clean release namespace; prior completion pointers cannot fill it.

## Handoff evidence

Report current qualified scene counts and remaining gaps, exact source/input/runtime hashes, the materialized package location, model/time-map qualification and any blocked branch. After a future authorized run, report accounted-for cells, valid failures, technical attempts, censoring, prediction coverage and raw storage location. A process or pod existing is not proof of model progress, and a scripted pass is not a policy result.

Do not change prompts, thresholds or scenes in response to policy failure. Keep valid failures, missingness and partial records. The frozen source registry remains unchanged; current package documentation and status do not grant launch or publication permission.
