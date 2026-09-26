# Nano performance on nine additional RoboLab tasks

All nine episodes completed on September 26, 2026. RoboLab scored **2/9 native successes**. This is one episode per task at one seed, not a reliable estimate of per-task success rates. All goals were false at the first policy observation.

| Task | Native outcome | Simulated duration | Observation from recorded state |
|---|---|---:|---|
| Cube in front of bowl | Failure | 30.0 s | Moved the cube but ended with gripper contact, about 16.6 cm above its initial height. |
| Cube behind bowl | Failure | 30.0 s | Moved and released the cube; final placement failed the native relation. |
| Butter on raisin box | Success | 11.5 s | Native support, footprint, and gripper-detachment conditions became true. |
| Mustard on raisin box | Failure | 40.0 s | Brief gripper contact; maximum origin-height increase was only 2.9 cm. Final bottle orientation was tipped. |
| Mustard in left bin | Failure | 30.0 s | Lifted and moved the bottle; ended outside the bin, about 7.9 cm left of its starting lateral position. |
| Mustard in right bin | Failure | 30.0 s | Lifted and moved the bottle; ended outside the bin, about 5.8 cm right of its starting lateral position. |
| Left bowl on right bowl | Failure | 20.0 s | Target contact occurred, but its maximum origin-height increase was under 5 mm. |
| Right bowl on left bowl | Failure | 20.0 s | No recorded gripper contact with the requested target bowl. |
| Mug at table center | Success, scene caveat | 29.8 s | Native centering, table-contact, and gripper-detachment conditions became true. Two non-target objects were already below the table at reset. |

## What the results support

The policy ran through all tasks without an infrastructure interruption, but task completion was poor in this small pilot. Failures occurred at different stages: target interaction, lifting, placement, and release. The native `object_grabbed` signal means gripper contact; its occurrence in eight of nine episodes is not proof of eight secure grasps.

The two bin commands produced endpoints on opposite lateral sides of the start while both failed containment. That is a useful candidate for separating directional response from successful execution. With one episode per command, it does not establish robust language grounding or a causal failure mechanism.

The mug scene needs a separate validity flag. At the first policy observation, the bowl and banana origins were already approximately 123 m below table height. Their absence cannot be attributed to Nano. Preserve the native success in the raw results rather than silently dropping it or changing its score. This pilot does not establish a clean, complete stock-scene reset for that task.

Success termination ends an episode as soon as the native predicate becomes true; no extra post-release stability interval was collected. Rollout video writers omit the terminal frame, so the final displayed frame precedes the scored state by one control step. Predicted futures remain unscored because their physical-time and camera alignment is not yet qualified.

## Evidence

- [Completed native summary](../artifacts/workstation_nano_spatial_20260926/completed/episodes/summary.json)
- [Compact analysis and consistency checks](../artifacts/workstation_nano_spatial_20260926/completed/analysis.json)
- [Last recorded frames across all tasks](../artifacts/workstation_nano_spatial_20260926/completed/spatial-contact-sheet.jpg)
- [Prospective protocol](WORKSTATION_NANO_SPATIAL_20260926.md)

The run retained **3,620 executed actions, 119 inference requests and predicted videos, and 18 rollout videos**. Per-task pose lengths, request counts, retained-future counts, and executed-chunk totals agree. The runner verified native HDF5 actions exactly matched requested policy actions. Exit code was zero; both GPUs were idle at the results check.

Raw arrays, HDF5 recordings, and videos remain at `/home/ali/wam-nano-stock-20260926/spatial-suite-001` on `workstation`. Compact results, poses, exact task configurations, and previews are retained in this repository. No additional episodes were launched during this results review.
