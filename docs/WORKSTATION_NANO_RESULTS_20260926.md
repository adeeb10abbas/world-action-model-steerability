# First completed Nano stock-scene comparison

All six episodes in attempt 006 completed, with 450 actions each, from
06:42 to 08:27 UTC on 26 September 2026. The run recorded 2,700 executed
actions, 90 same-request predicted videos, and 12 native episode videos.
The server stopped after the runner finished; its final SIGTERM records are
the launcher's normal cleanup. There were no partial episodes in this attempt.

## Observed outcomes

| Wording | Requested cube left of bowl | Requested cube right of bowl |
| --- | --- | --- |
| Direct: “Put the cube to the left/right of the bowl” | Endpoint relation met | Endpoint relation met |
| Rephrased: “Place the cube so that the cube is to the left/right of the bowl” | Endpoint relation met | Endpoint relation met |
| Reversed reference: “Place the cube so that the bowl is to the right/left of the cube” | Endpoint relation not met | Endpoint relation not met |

These are six individual observations, not estimated success rates. Each run
recorded a cube grasp and a subsequent release. The right relation already
held at reset, so endpoint predicates alone do not establish task execution.

The reversed-reference failures differed:

- **I-right:** the instruction requested the cube right of the bowl by saying
  the bowl should be left of the cube. The cube ended 12.5 cm to the bowl's
  left in the robot frame. The bowl remained in place.
- **I-left:** the instruction explicitly asked to move the cube, but video
  inspection shows the robot lifting the bowl first. The bowl subsequently
  fell from the table. Its final height was -0.611 m, compared with 0.077 m
  initially. The robot later grasped and moved the cube; the endpoint still
  failed the requested relation. This is not a clean directional-error case
  because the reference object also moved.

The first case motivates testing direction interpretation; the second motivates
testing which object is selected for manipulation. These observations do not
identify an internal model mechanism or establish where prediction and action
diverge. That requires inspection of the saved predictions with camera and
time correspondence checked first.

## Recording checks and limitations

All six HDF5 action arrays have shape (450, 8) and exactly match the saved
requested-step actions. Each episode has 451 pose records, 15 decoded futures
of shape (33, 528, 640, 3), and chunk execution counts of 14 x 32 plus 2.
Initial physical states are bitwise identical across the six conditions.

Rendered images are not identical. Relative to D-left, initial raw shoulder
images differ by about 1.1 intensity levels out of 255 on average, and wrist
images by 3.0–3.2. The run therefore controls physical initial state but does
not provide an identical-pixel wording intervention. It also uses one scene
and one environment/policy seed; replication is required before any broader
robustness claim.

Next useful experiments are repetitions with identical cached initial model
inputs and controlled simulator resets, then multiple layouts and seeds.
Before assigning failures to the world model or action selection, compare
whether each same-request prediction contains the wrong object or direction
and whether execution follows it. No additional experiments were launched
while collecting this result summary.

Compact results and trajectories are in
`artifacts/workstation_nano_20260926/completed/summary.json` and
`artifacts/workstation_nano_20260926/completed/episodes/`.
Full raw arrays, HDF5 files and videos remain on the workstation at
`/home/ali/wam-nano-stock-20260926/attempt-006`.
