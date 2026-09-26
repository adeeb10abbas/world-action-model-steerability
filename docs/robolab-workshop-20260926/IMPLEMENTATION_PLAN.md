# RoboLab three-model execution implementation plan

> **For agentic workers:** Use the executing-plans workflow to implement your assigned package task by task. The user distributes these roles; this file does not dispatch additional agents. Check off completed steps and return evidence, not just a narrative.

**Goal:** Collect a finite, reproducible native-RoboLab study testing whether WAM forecasts help diagnose wrong-goal behavior versus execution failure.

**Architecture:** One shared simulator/scorer/recorder implementation and three isolated model adapters. Immutable state and prompt manifests bind to complete per-model state blocks. Analysis consumes saved evidence, never the live policy.

**Tech stack:** Pinned RoboLab/Isaac simulation, model-native Python environments, NumPy evidence, Kubernetes Jobs, scikit-learn analysis. Only the manifest compiler exists today; runtime modules below are implementation deliverables.

**Spec:** [CLUSTER_EXECUTION_SPEC.md](CLUSTER_EXECUTION_SPEC.md), [EXPERIMENT_SPEC.md](EXPERIMENT_SPEC.md), [MODEL_CONFIGS.json](MODEL_CONFIGS.json).

## Global constraints

- Five native scenes; 42 exact prompts; 8 new starting states per scene; 336 confirmation episodes/model.
- Development cap 46 episodes; confirmation cap 1,008; offline adapter fixture calls at most six/model; no automatic policy retries.
- 15 Hz, 32-action chunks, fixed 30/30/40/40/20-second scene horizons, native early success disabled.
- N3/E3/F3 only; same-request forecasts; physically mapped executed prefixes; unknown evidence stays unknown.
- No new scene assets, old SGW queue, camera/background changes, tuning sweeps or learned-outcome-based state selection.
- Work under `experiments/robolab_workshop/`, `tests/robolab_workshop/` and this specification directory; preserve old workers.
- Six engineer-hours for scene/reset integration; four for FLUX video export. Record blockers and continue independent work.

## Review focus

1. Already-true goals must remain maintenance cases; native early success must not truncate the episode.
2. Reset leakage can invalidate pairing even when the seed matches; check state, policy and first-input hashes.
3. Bowl-role reversal and cube-right's different native asset can silently change the manipulation.
4. Video frame indices, queued actions and final short chunks can compare a forecast with an unexecuted future.
5. Pod restart or a lost response can duplicate inference, overwrite failures or count a partial episode as complete.

## Task 1 — common contracts, states and scoring

**Create:** `experiments/robolab_workshop/contracts.py`, `states.py`, `scoring.py`; `tests/robolab_workshop/test_scoring.py`, `test_states.py`.

**Inputs:** catalog, pinned task definitions, canonical native assets. **Outputs:** versioned `accepted_states.json`, `state_candidates.jsonl`, scripted receipts, source-bound scorer configuration.

Use this common JSON envelope between packages; arrays are referenced by artifact URI and SHA256:

```python
from typing import Literal, TypedDict

class Artifact(TypedDict):
    uri: str
    sha256: str

class EpisodeStatus(TypedDict):
    episode_id: str
    attempt_id: str
    status: Literal['complete', 'infra_error', 'model_output_invalid', 'simulation_invalid']
    requests_used: int
    actions_executed: int
    release_sha256: str

class RequestEvidence(TypedDict):
    request_index: int
    sim_start_s: float
    sim_end_s: float
    executed_prefix_length: int
    returned_actions: Artifact
    executed_actions: Artifact
    future: Artifact | None
    future_status: Literal['mapped', 'unmapped', 'unavailable']
    future_frame_times_s: list[float]
    last_eligible_frame: int | None
```

- [ ] Implement native goal bindings before pose sampling. Copy source function/parameters into a receipt. Keep native and study scores distinct.
- [ ] Add scoring fixtures: intended/opposite/ambiguous direction; table-supported versus airborne placement; containment versus near-bin; support versus overhead-but-not-supported; gripper contact without lift; dwell of 0.99 s versus 1.00 s. Test initial-truth strata separately from achieved goals.
- [ ] Test S1 all goals use the identical simple asset. For S5 swap initial bowl poses and verify role bindings swap once, then remain fixed during movement.
- [ ] Restore full state and render/cache first raw observation. Compare numeric state, velocities, controller caches and first-input bytes across two resets; no policy call needed. Any mismatch blocks pairing, not the entire project.
- [ ] Run the bounded canonical and candidate campaign from the specification. Never repeat a passed demonstration. Save accepted and rejected candidates in proposal order, with actual filenames/hashes.
- [ ] Return 40 accepted state bindings or an explicit shortfall report before any confirmation outcome. Do not manufacture placeholder snapshots.

Acceptance command after implementation: `python -m pytest tests/robolab_workshop/test_scoring.py tests/robolab_workshop/test_states.py -q`. These are CPU fixtures; native receipts are separate.

## Task 2 — three model adapters

**Create:** `experiments/robolab_workshop/adapters/nano.py`, `edge.py`, `flux.py`, `forecast_map.py`; `tests/robolab_workshop/test_adapter_contract.py`, `test_forecast_map.py`.

**Inputs:** saved raw observation, literal prompt, model config, per-episode reset. **Outputs:** returned actions, effective prompt/seed/config, same-sample future or explicit missing status, source-derived view/time map, runtime receipt.

- [ ] Implement a serialized `reset(seed: int) -> dict` and `infer(observation: dict, prompt: str) -> dict` in each model-native server. Client wrappers return arrays/metadata without silently changing units or queue length.
- [ ] N3: reuse the functioning wrapper and retained runtime. Preserve seed behavior, native preprocessing and source; instrument the existing request rather than running a separate video query.
- [ ] E3: use the pinned official action server with JSON prompt formatting and [960,1001] guidance interval. Record the actual template after preprocessing. Verify action/state/gripper convention against the RoboLab client.
- [ ] F3: load the pinned root BF16 package and fixed shared encoders. Set seed 6100 and eager preparation before qualification; retain native sampler/processors. Export the same video sample and compare original/instrumented actions on two fixed observations. Record equality or blocker within four engineer-hours.
- [ ] Test channel/view identity with distinct synthetic RGB values; open/closed gripper conversions; reset between differing instructions; rejection of wrong dimensions/nonfinite commands; unavailable future; and a final two-action executed prefix from a 32-action return.
- [ ] Trace camera composition and temporal convention from source. Map frame physical times explicitly; trim by executed interval. Retain frame 0 for context but do not count a present-state frame as a future event.
- [ ] Return per-model runtime receipts; do not block other models because one adapter fails. At most six offline fixture calls/model, recorded in `adapter_calls.jsonl`.

Acceptance: `python -m pytest tests/robolab_workshop/test_adapter_contract.py tests/robolab_workshop/test_forecast_map.py -q`, plus actual fixture receipts. Synthetic tests cannot qualify a checkpoint.

## Task 3 — recorder, release builder and bounded worker

**Create:** `experiments/robolab_workshop/recording.py`, `release.py`, `worker.py`; `tests/robolab_workshop/test_recording.py`, `test_release.py`, `test_worker_resume.py`.

**Inputs:** planned rows/blocks, accepted states, runtime/scoring/annotation receipts. **Outputs:** immutable release; episode evidence; complete/partial ledger; model-lane progress.

- [ ] Implement the fixed-horizon loop using the pinned native stepping/controller path. Disable success termination and environment auto-reset. Pause simulation during synchronous inference. Capture the per-step data in the specification.
- [ ] Add tests with a fake server and simulator: initial goal true still reaches horizon; invalid action stops before stepping; 450 actions consume 15 requests and truncate the last to 2; unchanged prompt bytes survive round trip; an uncertain timeout causes zero retries.
- [ ] Implement atomic episode claims, per-request durable records and COMPLETE markers. Test crash before response, after response, before COMPLETE, and duplicate block claim. Resume skips only validated complete cells and refuses ambiguous partial cells without a separate retry authorization record.
- [ ] Make the release builder reject missing state hashes, wrong model pins, unmatched first inputs, changed prompt bytes, unknown camera/time mapping, missing human answerability receipt, unqualified goals, and any optional/held scene.
- [ ] Freeze common input hashes before confirmation; a later model can add its receipt against the same common release. Preserve all source versions and result attempts.
- [ ] Run finite development rows, prepare the deterministic clip sample, complete the answerability check, then materialize confirmation lanes. Do not generate extra development rollouts automatically.

Required CLI contract to implement (these commands **do not exist yet**):

```sh
python -m experiments.robolab_workshop.release \
  --spec-dir docs/robolab-workshop-20260926 \
  --states /study/inputs/accepted_states.json \
  --receipts /study/inputs/receipts \
  --output /study/releases/rws-v02

python -m experiments.robolab_workshop.worker \
  --release /study/releases/rws-v02/release.json \
  --assignment /study/releases/rws-v02/assignments/N3-lane-01.json \
  --output /study/runs/rws-v02 --resume-complete-only
```

`/study` is the specified container mount, to be backed by the operator's actual persistent data store. The release tool writes assignment files containing only registered block IDs and refuses existing different releases. It must not contact a policy server. The worker requires a frozen, qualified model lane and an explicit deployment by the user/assigned execution agent.

Acceptance: `python -m pytest tests/robolab_workshop/test_recording.py tests/robolab_workshop/test_release.py tests/robolab_workshop/test_worker_resume.py -q`, plus a fake-worker end-to-end run with no GPU/model import.

## Task 4 — deploy finite lanes

**Create:** `experiments/robolab_workshop/deploy.py`; generated manifests under the data release's `jobs/`, not the old SGW Kubernetes directory.

- [ ] Resolve actual namespace, image digests, PVC, node/GPU allocation and server endpoints. Use existing authorized cluster configuration. Keep credentials outside Git.
- [ ] Generate finite Jobs with restartPolicy Never, backoffLimit 0, measured deadlines and disjoint whole-block assignments. A persistent server may process a lane's fixed assignment; do not spin up a server per prompt.
- [ ] Render and validate YAML without submitting, check the planned counts against the release, then launch only the assigned eligible lane. A user dispatch of this runbook supplies execution scope; this document's preparation did not start a job.
- [ ] Return job IDs, data URIs, budget/deadline calculation and a 60 s heartbeat. A failed lane preserves partial evidence and does not kill other lanes or restart itself.
- [ ] At the end run a completeness check by episode ID/hash, not the number of video files. Record every blocked or missing cell.

## Task 5 — labels, locked analysis and paper outputs

**Create:** `experiments/robolab_workshop/annotation.py`, `features.py`, `analyze.py`; `tests/robolab_workshop/test_analysis.py`; `analysis_schema.json` in the frozen release.

- [ ] Build blinded annotation packets and mapping kept separate from annotators. Use the fixed window rule; test fallback and truncation. Prepare independent human-label forms and retain original/adjudicated labels.
- [ ] Implement fixed state/action and forecast feature sets, explicitly excluding outcome and prompt-form columns. Unit-test that changing final success alone cannot change an input feature.
- [ ] Implement eight state-held-out folds, scene/goal/model weighting, bootstrap and two wording tests from the specification. Test that all models/forms for a state occupy one fold, one-class folds use the declared constant, and unknown predictions are not scored as zero.
- [ ] Produce `coverage.csv`, `episode_outcomes.csv`, `paired_wording.csv`, `goal_response.csv`, `forecast_events.csv`, `diagnostic_utility.csv`, three figures and a claim/evidence table. Include failed and blocked cells in denominators/reasons.
- [ ] Add one reproducible `python -m experiments.robolab_workshop.analyze --release ... --runs ... --labels ... --output ...` entry point; resolve these paths in the delivered command. Freeze code before reading confirmation outcomes.
- [ ] Draft the paper from actual results. A positive result requires incremental held-out value with uncertainty and coverage; a negative/underpowered result is reported honestly. Do not describe all policy failures as language misunderstanding.

Acceptance: `python -m pytest tests/robolab_workshop/test_analysis.py -q`, followed by a complete saved-data run. Run only relevant tests; once the checks and receipts pass, proceed to collection rather than widening the engineering project.
