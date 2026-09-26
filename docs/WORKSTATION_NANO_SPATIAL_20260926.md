# Nano on additional stock RoboLab spatial tasks

The user requested the same Nano policy on other RoboLab spatial tasks. This is a separate, finite workstation pilot. The task list below was selected before collecting outcomes. It does not launch the cluster study or change the completed SGW scenes.

## Planned episodes

One episode per task, environment and deterministic policy seed 6100. Use the native default instruction, scene, original DROID wrist/left/right/head cameras, success condition, and timeout. The policy receives the same wrist/left/right inputs as the previous pilot. Native success termination is enabled.

| Task | Native limit | Maximum actions |
|---|---:|---:|
| RubiksCubeInFrontOfBowlTask | 30 s | 450 |
| RubiksCubeBehindBowlTask | 30 s | 450 |
| ButterAboveRaisinTask | 40 s | 600 |
| MustardAboveRaisinTask | 40 s | 600 |
| MustardInLeftBinTask | 30 s | 450 |
| MustardInRightBinTask | 30 s | 450 |
| BowlStackingLeftOnRightTask | 20 s | 300 |
| BowlStackingRightOnLeftTask | 20 s | 300 |
| WhiteMugInCenterOfTableTask | 30 s | 450 |

The maximum is 4,050 control actions and 133 inference requests. Successful episodes may end earlier. Allow four hours for the finite server; stop on an infrastructure error without automatic retries. A native task failure is an outcome and the next task proceeds normally.

## Policy and source identity

- Checkpoint: `nvidia/Cosmos3-Nano-Policy-DROID`, revision `6706d7680581c255ff61e0f3bb49d90eac55c79e`.
- Cosmos source: `411d25b2e35bc441126f48c44a4b93e1c0564274`.
- RoboLab source: `0aef241fb088ca21bb4ebd24448940ed56620d17`.
- Same two-RTX-3090 runtime with BF16 FSDP CPU offload, four denoising steps, guidance 3, shift 5, resolution 480, 15 Hz conditioning, history length 1, and 32-action chunks.
- No scene construction, camera edits, model tuning, quantization, or learned-policy changes.

Unlike the earlier fixed-horizon wording diagnostic, this pilot uses each task's native early-success rule and horizon. Its scores therefore must not be pooled with those earlier endpoint checks.

## Retained evidence and interpretation

Each task saves its exact instruction, native success parameters, initial physical state, per-step object poses and target grasp state, native success result, executed actions, input observations, returned action chunks, predicted video arrays, and rollout videos. Executed HDF5 actions are compared against the requested policy actions. Record whether the goal already held at reset; do not attribute such a success to learned skill.

One episode per task shows concrete behavior but cannot establish a per-task success probability or generalization advantage. Different scenes and objects confound cross-task difficulty comparisons. Predicted videos are retained, but forecast accuracy remains unscored until physical-time and camera correspondence are established.

## Run and output

On `workstation`, deploy the committed tools beneath `/home/ali/wam-nano-stock-20260926/code` and record that commit in `code/SOURCE_COMMIT`. Run:

```bash
bash /home/ali/wam-nano-stock-20260926/code/tools/run_workstation_nano_spatial.sh \
  /home/ali/wam-nano-stock-20260926 spatial-suite-001
```

The launcher writes `prospective-plan.json` and `SOURCE_COMMIT` before loading the model. Outputs go to `/home/ali/wam-nano-stock-20260926/spatial-suite-001/`; per-task `result.json` files and the final `episodes/summary.json` distinguish completed outcomes from partial attempts. Large arrays and videos remain on the workstation, outside Git. The six earlier wording outcomes remain in `attempt-006`.

## Status

**Completed:** All nine episodes finished with exit code zero at approximately 12:00 UTC on September 26. Native successes were butter-on-raisin and mug-at-center (2/9); the latter has a recorded scene caveat. See the [results and evidence](WORKSTATION_NANO_SPATIAL_RESULTS_20260926.md). The launch record below is historical.

Launched on 2026-09-26 at 09:41 UTC from commit `a3535b3`. The first task executed at least 32 policy actions and retained its first predicted video; its initial goal predicate was false. The batch was still running at the [recorded check](../artifacts/workstation_nano_spatial_20260926/launch_receipt.json), with no completed task outcomes asserted yet.

The task names, instructions, horizons, and native predicates were read from the pinned RoboLab source. Python compilation, launcher syntax, and the 9-task / 4,050-action / 133-request budget checks passed.
