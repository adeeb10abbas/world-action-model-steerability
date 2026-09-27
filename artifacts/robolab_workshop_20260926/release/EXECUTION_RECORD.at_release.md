# RWS-20260926 execution record: amendments and deviations

Handoff commit: `1da9e9da50f599585cf5d2069e5a234d8db7a625` (branch `codex/nano-stock-workstation-20260926`).
Data volume: `/data/users/ali/rws-20260926` (namespace `211247-prod`). This file is the disclosed
amendment log. Items A1–A9 were recorded **before any confirmation outcome existed**. Later entries say when they
were made.

## Pre-confirmation amendments (before release freeze)

**A1. S2 start shortfall → a smaller study with four scenes.** Proposals were evaluated for all five scenes (32 each,
seed 8200). Valid starts per scene: S1 15, S2 13, S3 17, S4 17, S5 10.

- Every one of the 13 valid S2 candidates failed its first scripted goal (R): 11 `lift_no_goal`, 2
  `contact_no_lift`. The canonical D00 S2-R check also failed with the frozen controller.
- Diagnosis: the palm blocks the descent at a TCP height of about 0.164 m. The fingers can hold only the tapered top
  2–3 cm of the mustard bottle, and it slips out during transit. This is a controller or native-geometry
  infeasibility, not an asset problem we were allowed to redesign.
- Per spec §5C ("record the shortfall and a proposed smaller study"), confirmation uses the 32 accepted starts of
  S1, S3, S4 and S5.
- For each model: 32 blocks and 288 episodes (S1 96, S3 72, S4 72, S5 48). The 48 S2 episodes per model (144 in
  total) are omitted with reason `S2_no_accepted_start`. They are listed in `release/release.json`.
- No scene was invented, recycled or reseeded.

**A2. Scripted controller revisions on D00.** The canonical once-checks used controller rev1. Before the candidate
campaign, the scripted controller was revised on the D00 starts only. Those runs were not charged, were kept in
separate `_scripted_revN` directories, and gave:

| Rev | Change | D00 goals passed |
|---|---|---|
| rev4 | Null-space projector | 10/14 |
| rev5 | Integral joint command and start-centred yaw fold | 13/14 |
| rev6 | Carry step limit | 12/14 |
| rev7 | Integrator reset per segment | 13/14 |

- Rev7 was frozen before the first charged candidate attempt. The only rev7 D00 failure is S2 R.
- Charged candidate attempts: 115 of 140, all with rev7.
- Controller revisions never touched model inputs, prompts, scoring or starts.

**A3. Judge v3 and scorer v2 (before release).**
- The scripted judge changed from v1 (reject initially true goals) to v2 (maintenance goals must be re-established
  after lift-off) to v3 (finite-difference mover speed).
- The episode scorer's speed definition changed to the finite-difference definition before release.
- All 46 development episodes are rescored with the frozen scorer by `features.py`. Their stored `result.json`
  files still carry scorer v1.

**A4. Scripted fail-fast and goal order.**
- Charged candidates stop at the first failed goal, so an unchanged candidate is never retried.
- S2 candidates were run in goal order R, L so that a failure costs one attempt. S2 L was therefore never tried on
  a candidate whose R had failed.

**A5. One infrastructure rejection.**
- S1-P04 goal B was rejected with `controller_error: OSError errno 116 (stale file handle)`. The cause was concurrent
  scripted processes sharing RoboLab's native HDF5 recorder file on NFS.
- To avoid a model-blind retry of an unchanged candidate, the rejection stands. It is disclosed as an
  infrastructure, not controller, rejection. S1-P12 filled the slot.
- Confirmation workers use a per-process native recorder directory under `/tmp`, so this collision cannot recur
  there.

**A6. Execution mechanism.**
- Lanes run as long-lived processes started with `kubectl exec` inside the user's existing, idle A40, A100 and B200
  pods, not as `batch/v1` Jobs. Every lane still has one serialized policy server and one simulator process.
- Each lane receives a fixed list of whole blocks (a longest-processing-time assignment computed once), and episodes
  are claimed atomically. There are no automatic retries or restarts.
- Two simulator processes share each A40 GPU, with per-lane Isaac/Kit caches. N3 runs 16 server lanes, E3 13 and
  F3 14, instead of the default one lane per model. All servers of a model have identical receipts and configuration
  (checked by `release.py`).

**A7. Forecast rubric v2 and the forecast view.**
- Before release, the annotation rubric gained a `relation_object` field and robot-frame direction words
  (`closer_to_robot` / `farther_from_robot`, matching RoboLab's `in_front_of` / `behind` x-axis sign).
- Forecast composites are resampled to a single 544×640 layout (wrist 360 rows over two exterior panes of 184 rows),
  so frame size does not reveal the model.
- Rendering style may still differ by model. This residual blinding limitation is disclosed.

**A8. Visibility and distinctness checks.**
- Visibility means that the object's bounding-box centre projects inside at least one exterior policy image with
  positive depth. There is no occlusion test.
- The 1 cm mover-distinctness check compares each candidate against earlier *valid* proposals.
- The cached first observation is used as request 0's input.

**A9. Human annotation gate.**
- E1, A2, A3 and A4 need two independent blinded human label files plus adjudication. Blinded packets are built by
  `annotation.py build`.
- Until the labels exist, those analyses are reported as `forecast_labels_pending` and are never imputed.
- The confirmatory wording tests (E2 and E3), E4 and A1 do not depend on labels.
