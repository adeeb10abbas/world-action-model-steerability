# Competence diagnostic: cancelled before outcomes (25 September 2026)

**Status: cancelled by user override before any diagnostic run.** No policy
server, simulator, model request, physical action or episode was started, and
no diagnostic outcome exists. Missing diagnostic data are unavailable, not zeros.
This note does not alter the frozen 1,566-cell study, its protocol, prompts,
queue, scorer, releases or records.

## Purpose (as planned)

In the 270 finished pilot/development episodes, successes were N3 3/90,
E3 0/90 and F3 0/90. The RoboLab leaderboard reports much higher competence
for these checkpoints. The diagnostic was meant to show whether our runtime
and integration reproduce that competence
([roster amendment](MODEL_ROSTER_AMENDMENT_20260924.md), "Show canonical-task competence alongside wording sensitivity").
The plan changed several times before any run. It went from stock RoboLab
tasks, to a steerable V1 comparison, to a camera A/B, to a validation gate
with the original cameras. The user then cancelled all runs to prioritise the
camera-reverted rerun.

## Read-only evidence gathered before cancellation

These are observations of existing study inputs, not new outcomes.

1. **Exterior cameras omit the robot.** The model inputs for
   `LAT-D01-E3-I-POS/attempt-001` were read from the study mailbox
   (`simulator/mailbox/responses/<step>.policy.00000{0,1,2}.npy`). They contain
   the wrist, `over_shoulder_left_camera` and `over_shoulder_right_camera`
   views, each 1280×720 uint8. At reset and at action steps 200 and 400, both
   `close-oblique-v3-full-objects-20260924` exterior views show only the table,
   the objects and a sliver of the robot base. The arm never appears, even
   though the joints moved (`arm_joint_pos` differs between steps). The
   original RoboLab DROID preset shows the arm over the shoulder
   ([contact sheet](../artifacts/workshops/spatial_grounding_v1/camera_checks_20260924/original/camera-projection-contact-sheet.jpg)).
   The views look back from the table's far side, so image left/right is
   mirrored relative to robot left/right. The pinned Cosmos server's fixed view
   description tells the model the bottom row shows "third-person perspective
   views of the scene from opposite sides, with the robot visible"
   (`cosmos_framework/scripts/action_policy_server_robolab.py`, 411d25b). The
   close-v3 inputs contradict that. Derived JPEGs are on the PVC under
   `/data/users/ali/sgw-01/competence-diagnostic-20260925/obs-inspect/`.
2. **Gripper convention matches upstream.** RoboLab's
   `BinaryJointPositionZeroToOneAction` (`robolab/robots/droid.py`, 0aef241)
   itself closes when the command is >0.5. The official `Cosmos3Client`
   binarizes at >0.5 before stepping. The SGW path's unbinarized continuous
   command therefore yields the same executed gripper action.
3. **Image packing differs slightly (secondary, untested).** The SGW N3/E3
   path sends three separate views. The pinned server keeps the wrist at
   1280×720, bilinearly resizes the exteriors to 640×360 with
   `F.interpolate`, which does not antialias, and then resizes the 1080×1280
   composite to 540×640. The official RoboLab client resizes each view to
   360×640 with openpi `resize_with_pad` before composing. The layout and final
   size match, but the resampling filters differ. No effect size was measured.
4. **Steerable V1 differs in pins.** V1 used RoboLab `992bc34`, Cosmos
   framework `1439c1d`, stock RoboLab DROID cameras and the official
   `policies/cosmos3/run.py` client. SGW uses RoboLab `0aef241` and Cosmos
   `411d25b`/`cf5d68c`. Any effect of these pins on the V1 comparison is
   unmeasured.

## Resources

Only 211247-alia40u-a40-1gpu and 211247-alia40q-a40-1gpu were used, for
read-only `kubectl exec` inspection and one short CPU-only HTTP connectivity
test (u→q, HTTP 200; the test server was stopped). A stray no-op `true` was also
executed once in 211247-alia40i-a40-1gpu; nothing there was changed. No GPU
lock was taken and no GPU process was started. Neither UUID has a lock file.
At release, 16:10:40 UTC, pod u (UID `acd83e87-e31c-4d16-9835-77ba2a68f06d`,
`GPU-e58ac27f-3d12-0208-aca3-a7c5b6f9e6c2`) and pod q (UID
`8f937736-b9f0-4c7f-9ecb-5ebf3e9d3eca`,
`GPU-41d6e6cc-52be-1c84-616a-e70a826c4452`) both showed 0 MiB and no compute
apps. This session never signaled any q process. At the same read, q's
guardian PID 4121 was `<defunct>`, and observers 11261 and 14965 were absent.
They were alive at 16:02 UTC. That change occurred outside this session and is
reported only for the coordinator's records.
