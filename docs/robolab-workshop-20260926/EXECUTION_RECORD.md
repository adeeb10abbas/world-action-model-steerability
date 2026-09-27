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

**A10. Analysis code finalized after release freeze, before any confirmation outcome was read.**
- After `release.json` was frozen (sha256 `cd0d4783…`, 03:01 UTC on 2026-09-27), confirmation lanes started at
  03:02 UTC.
- `analyze.py` then gained the A2 agreement table, a `--phase` flag for development-only verification, and a
  correction to the state-cluster bootstrap and A4 fold-wise derangement. `report.py` (tables and figures) was
  added.
- `release/analysis_freeze.json` hashes the final analysis code and records that 26 COMPLETE markers existed at
  freeze time. Their outcomes had not been read. `features.py`, `scoring.py`, `annotation.py`, the rubric and the
  feature schema are unchanged from the release.

## Confirmation launch

- Release: 864 bound episodes = 3 models × 32 blocks × 9 episodes on average (S1 12, S3 9, S4 9, S5 6 per block).
  The 144 S2 episodes are omitted.
- 43 lanes: N3 16, E3 13, F3 14. Each lane has one serialized policy server (B200/A100) and one Isaac simulator
  process, with two simulators per A40.
- Each lane was assigned whole blocks once, by longest-processing-time on the development wall times. Projected
  finish is 1.8 h at most, for about 70 simulator GPU-hours plus 43 policy-server lanes.
- The launcher is `files/bin/launch_confirm.py`. Per-lane ledgers are `runs/lanes/conf-<server>.jsonl`, and logs are
  `runs/_logs/conf-<server>-<scene>.log`.

## Confirmation completion and first read of outcomes

- All 864 bound episodes completed and were valid by 05:20 UTC on 2026-09-27: N3 288, E3 288, F3 288. There
  were no infrastructure failures and no missing cells, so all 32 blocks per model are whole.
- Features were computed with the frozen development calibration (`analysis/conf_features.jsonl`). The frozen
  `analyze.py` was run once with 10,000 state-cluster bootstrap draws. `report.py` then rendered the tables and
  figures in `artifacts/robolab_workshop_20260926/results/`. This was the first time confirmation outcomes were
  read.
- All 43 policy servers were stopped by pid afterwards, leaving every GPU at 0 MiB.

## Post-result amendment

**A11. Automated VLM labelers replace the two human annotators (decided after the outcomes in the previous
section were read).**
- The principal investigator judged 1,726 packets (864 primary windows plus 862 request-0 windows) too many for
  human annotation, so blinded labeling is done by open-weight vision-language models instead:
  - **Labeler A:** `Qwen/Qwen3-VL-235B-A22B-Instruct-FP8`, served with vLLM 0.26 at pipeline-parallel 2 across two
    B200 pods.
  - **Labeler B:** `zai-org/GLM-4.5V-FP8`, one replica per B200.
  - **Adjudicator:** labeler A, shown the packet and the two disputed candidate values in a per-packet random
    order, without model names. The allowed values for each disputed field are the two candidates plus `unknown`.
- Blinding is unchanged. Each labeler sees only `legend.png` and 8 evenly spaced frames of the mapped forecast
  (`forecast.mkv`), including the last mapped frame. It never sees the key, prompt, form, model, goal or outcome.
- Outputs are JSON constrained to the rubric v2 enums (`vlm_label.py`), with temperature 0 and seed 0. Every raw
  response and its free-text observation is kept.
- Consequences:
  - E1, A2, A3 and A4 become **automated-annotation results**. The rubric, features, unblinding semantics and
    analysis code are unchanged.
  - The decision was made after outcome rates were visible. Because the labelers are blind to the outcome, this
    can bias only which labeling source was chosen, not the labels themselves. It is disclosed as post-result.
  - VLM labels are not human judgments. Inter-labeler agreement (A2 table) and a spot-check of packets are
    reported alongside E1.
- Hardware note: the three 4×A100 pods have 40 GB GPUs and cannot hold the 222 GB FP8 checkpoint. Two B200 pods
  were joined with vLLM multi-node instead. No new pods were created: the scheduler had no free multi-GPU B200
  capacity.
- Tooling: `annotation.py build` gained `--shard/--nshards` and a `finalize` step so the 1,726 packets could be
  built on 32 processes. Packet contents and opaque IDs are unchanged.

## A11 results note: automated labeling completed (September 27, 2026)

**Runs**
- Both labelers labeled all 1,726 packets: labeler A (Qwen3-VL-235B) in 973 s, labeler B (GLM-4.5V) in 980 s.
  Neither had any residual failure.
- Adjudication covered the 1,656 packets where the two labelers disagreed on at least one field.
  - One packet (`Afb978a9bcc38`) repeatedly returned output that could not be parsed at temperature 0.
  - To fix this, `vlm_label.py` now retries a failed call at temperature 0.2 with a new seed. The retry changes only
    calls whose deterministic attempt failed; that one packet was then adjudicated.
  - Every raw attempt, including the error record, is kept in `labels_vlm_adjudicated_raw.jsonl`.
- Infrastructure fix: `finish_vlm.sh` was first piped to the pod on stdin. ffmpeg consumed that stdin, which
  truncated the script after adjudication. ffmpeg now runs with `-nostdin`, and the script runs from a file. No
  labels were affected.

**Agreement**
- Agreement between the two labelers is low. On primary windows, κ is 0.40 for moving object, 0.11 for direction
  and 0.08 for visible final relation. All fields agree in only 5.9% of packets. Request-0 windows are lower still.
- The adjudicator is labeler A and chose labeler A's value more often for relations (438 vs 213). For direction it
  chose labeler B's value more often (267 vs 173). Adjudicated labels therefore lean toward A but do not simply copy
  it.
- The A11 decision was made before any VLM output was seen. The agreement statistics were computed after
  labeling. No labeling prompt, schema or model was changed in response to agreement or outcomes.

**Outcome**
- E1 is null: Δ Brier = −0.0007, 95% CI [−0.0018, +0.0002], with 47 events in 864 episodes. It cannot be told
  apart from the permuted-label control A4.
- Given the label reliability, this is reported as "no detectable diagnostic gain from automatically labeled
  forecasts". It is not evidence that the forecasts contain no information.
- The event-rate split by the forecast's moving object (reference 9.3% vs mover 3.5%) was computed after the
  results and is labeled exploratory in `RESULTS.md`.

**Shutdown:** all vLLM servers on the four B200 pods were stopped by pid, and their GPUs were confirmed at 0 MiB.

