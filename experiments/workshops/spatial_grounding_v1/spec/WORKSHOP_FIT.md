# Workshop framing for the clean WAM study

The fixed study compares N3 and D1 on the clean LAT, HEIGHT and DIST fixtures. Its 1,044 planned cells and scientific thresholds are unchanged. The maintained paper is [docs/scene_design_rtx/overleaf/main.tex](../../../../docs/scene_design_rtx/overleaf/main.tex); this file explains its research framing.

## The question

When spatial instructions change, do a world–action model's generated futures remain a reliable account of what its robot actually does? Controlled changes in goals and equivalent descriptions let the study measure execution and prediction together. Wording sensitivity alone would not establish the WAM contribution.

The intended workshop framing is benchmark design, with a narrower connection to prediction reliability for evaluation. The study inspects each WAM's own joint predictions and actions. It does not test arbitrary alternative policies, policy rankings, deployment safety or a causal benefit from predictive training. Submission requirements should be checked against the workshop's current call when preparing the actual submission; this specification is not a submission receipt.

## Measurements that support the contribution

1. **Executed outcome:** D/C/I wording is compared for the same physical goal and scene; the opposite goal checks directional responsiveness. I−C is the principal language contrast, with C−D as a construction control.
2. **Prediction fidelity:** compare decoded futures with actual movement at verified matching physical times within the executed action prefix. Persistence is the required equal-input baseline; report available coverage and missingness.
3. **Prediction–execution disagreement:** report both outputs correct, both wrong, prediction correct/execution wrong, the reverse, and unobservable cases at the same horizon.
4. **Additional information from forecasts:** compare these observations with the execution-only pickup, transport and release account. Show what discrepancy becomes observable without claiming an internal semantic mechanism or an untested failure detector.

A short-horizon generated relation is not a prediction of final success after later replanning. A generated video need not cause its jointly produced actions. If aligned prediction measurements remain unavailable, the intended WAM-specific contribution remains incomplete. Differences between model branches do not establish that world models are necessary or causally better than another policy architecture.

## Paper structure and scope

Use the clean D/C/I setup, a main execution-effect figure, an aligned prediction–execution figure/table with coverage and persistence skill, and a focused account of what remains unresolved. Report layout-level uncertainty, physical separation in metres, binary outcomes and technical missingness distinctly. Preserve negative findings and any result that forecasts add little diagnostic information.

Only the clean cohort supplies numerical study evidence. Scene qualification is scripted feasibility evidence; CPU checks are engineering evidence. Neither is learned-model performance. Full prompts remain in the frozen registry, while current implementation and handoff details live in [AGENT_TASKS.md](../../../../docs/AGENT_TASKS.md) and [CLUSTER_HANDOFF.md](../../../../docs/CLUSTER_HANDOFF.md). No extra model or behavioral baseline is part of the scope.
