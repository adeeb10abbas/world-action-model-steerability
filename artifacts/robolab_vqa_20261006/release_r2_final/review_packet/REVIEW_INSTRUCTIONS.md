# RQA V2 answerability review packet

72 view sets, 240 frame-goal relations. Fill `review_form_blank.csv` (one row per review ID) **before**
looking at anything in `key/`. Sheets show the exact evaluation-resolution views (secondary views are also shown 2x
pixel-replicated; the original files are in `views/`). Arrows beside each view show the robot's LEFT and FARTHER
directions derived from camera calibration; the moving wrist camera of saved-rollout frames has no fixed legend.

Answer for TARGET relative to REFERENCE in the robot frame: left/right from the robot's viewpoint, in_front = closer to
the robot, behind = farther. Use `diagonal_ambiguous` when the dominant direction is near 45 degrees and `cannot_tell`
when it is not visible. Q3/Q4 (support, table contact) apply to scenes with a raisin box. Mark `transit_or_gripper=yes`
if either object touches the gripper or appears in motion. Confidence low means you would not rely on the answer.

Protocol: reviewer 1 completes all rows; reviewer 2 completes all flagged rows (any ambiguity, low confidence, or a
post-comparison discrepancy) plus the fixed second-review sample: RV-3cf8fa1f93, RV-46c6a21335, RV-47d4ffa741, RV-67e634534b, RV-6f36528bcb, RV-712f53d935, RV-7785b8a661, RV-9544990ec2, RV-9c2b672d61, RV-9f9364308f, RV-bdea502e20, RV-c0118af5cd, RV-e60224fe66, RV-f86a769832. Resolve disagreements without model
responses; unresolved items are unanswerable. Set reviewer_type to human or machine truthfully.

Rescore without new inference:
`python -m experiments.robolab_vqa.v2.review ingest --packet <this dir> --forms <form1.csv>,<form2.csv> --output <ledger dir>`
then `python -m experiments.robolab_vqa.v2.analyze ... --mask <ledger dir>/mask.json`.
