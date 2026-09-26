# Nano, Cosmos Edge and FLUX: cluster experiment specification

**Study: RWS-20260926, protocol 0.2. Prepared September 26, 2026.**

**Question: Can a world-action model's predicted future help distinguish following the wrong goal from failing to execute the right one?**

Run the same physical starting state and goal with three equivalent instructions. Record the model's proposed actions and its predicted video from the same inference call, then record what the robot actually does. Separately change the requested goal to test whether the model responds appropriately. The main result is whether the predicted video adds useful information beyond the current state and proposed actions. Task success and wording sensitivity are supporting results.

This is the implementation handoff for the existing [paper design](PAPER_DESIGN.md) and [scientific specification](EXPERIMENT_SPEC.md). It uses **stock RoboLab assets and cameras**. Do not resume the old SGW-01 scene campaign, its 87 layouts, camera overrides, 18 prompts or 1,566-cell queue. Preserve those historical files. No policy or cluster job was started while preparing this document. The user will dispatch this handoff to the execution agents.

## 1. Read these files, then implement

| File | Authority |
|---|---|
| [Scene and prompt PDF](../../output/pdf/ROBOLAB_SCENES_AND_PROMPTS.pdf) | Human-readable scene images, nominal prompts and every intervention |
| [prompt_matrix.json](prompt_matrix.json) | Exact prompt bytes, IDs and intended physical goals; do not retype or normalize strings |
| [MODEL_CONFIGS.json](MODEL_CONFIGS.json) | Model identities and requested settings, separate from runtime qualification |
| [planned_episodes.jsonl](planned_episodes.jsonl) | Every planned development and confirmation cell, with exact instruction |
| [planned_blocks.json](planned_blocks.json) | Whole state blocks and deterministic execution order |
| [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) | Work packages, interfaces, acceptance cases and proposed execution CLI |
| [EXPERIMENT_SPEC.md](EXPERIMENT_SPEC.md) | Statistical design and interpretation boundaries |

`planned_*` files are an enumeration, **not a runnable release**. Their state slots have not yet been bound to physical snapshots. The release builder must bind and check states, model receipts, scoring code and recording paths before accepting a launch. A document containing a model revision is not proof that the model has run.

Protocol 0.2 preserves the 42 prompts, 40 held-out physical starts and primary analysis. It adds immutable Edge/FLUX candidates, complete episode/block enumeration, engineering deadlines, a hard scripted-attempt cap, exact event rules and scheduling instructions. It separates saved-forecast inspection from final human annotation: engineering work may proceed while annotators are recruited; confirmation requires the forecast answerability check described below. Changes after the release freeze require an amendment and a new release hash.

## 2. What we already have, and what remains

| Available now | Still required from execution agents |
|---|---|
| Five native scene assets and their initial images | Register eight modest pose variations per scene and full reset snapshots |
| Exact 42-prompt core catalog, with hashes | Bind added goals to explicit scorers; check each goal once per accepted state |
| Working Nano transport and recording examples | Fixed-horizon runner with contacts, velocities, stable-release scoring and isolated resets |
| 15 exploratory Nano episodes, 209 saved predicted videos | Verify the physical-time and camera correspondence of returned futures |
| Nano checkpoint and retained runtime identity | Edge integration; FLUX same-sample video export |
| Paper question, comparisons and held-out analysis | Blinded annotation, locked analysis implementation and actual confirmation results |

Existing pilots are development evidence, never confirmation rows. The nine native tasks yielded 2/9 native first-hit successes; the mug run has a reset defect. These are single episodes, not performance estimates. See [wording pilot](../WORKSTATION_NANO_RESULTS_20260926.md) and [spatial pilot](../WORKSTATION_NANO_SPATIAL_RESULTS_20260926.md).

Reuse `tools/workstation_nano/run_stock_tasks.py`, `common.py`, `stock_tasks.py` and `tools/workstation_nano_server/server.py` for transport, source receipts and evidence capture. The stock runner's early termination and sparse measurements do **not** implement this study. Put new code in `experiments/robolab_workshop/`; do not alter active old workers.

## 3. Exact experiment matrix

| Scene / base task | Goals on the SAME asset | Forms per goal | Episodes/model, 8 starts | Horizon / max requests |
|---|---|---:|---:|---|
| S1 `RubiksCubeLeftOfBowlTask` | Cube left, right, in front of, behind bowl | D, S, I | 96 | 30 s / 15 |
| S2 `MustardInLeftBinTask` | Mustard in left or right bin | D, S, I | 48 | 30 s / 15 |
| S3 `ButterAboveRaisinTask` | Butter on top of, left of, right of raisin box | D, S, I | 72 | 40 s / 19 |
| S4 `MustardAboveRaisinTask` | Mustard on top of, left of, right of raisin box | D, S, I | 72 | 40 s / 19 |
| S5 `BowlStackingLeftOnRightTask` | Left bowl onto right; right bowl onto left | D, S, I | 48 | 20 s / 10 |
| **Total** | **14 goals, 42 prompts, 40 physical states** | | **336** | **5,376 requests/model** |

All models use 15 Hz control, 32 returned actions and 32 executed actions per request except the final truncated chunk. This is synchronous simulation: pause simulation during inference. Wall-clock inference latency does not advance simulated physics.

- **D:** direct wording; native default only where the catalog explicitly says so.
- **S:** manipulated object first in the relation clause.
- **I:** reference object first, with the converse relation, but the same manipulated object and intended goal.
- **Different goals:** a separate manipulation, not an equivalent paraphrase. S5 also changes which bowl moves.

Example, S1-left: D = `Put the rubiks cube to the left of the bowl`; S = `Place the Rubik's cube so that the Rubik's cube is to the left of the bowl.`; I = `Place the Rubik's cube so that the bowl is to the right of the Rubik's cube.` All three ask the robot to move the cube. The complete strings live in the catalog and the episode rows, including the trailing space in native S4-TOP-D.

**Scene pitfalls:** the native cube-right task loads a different asset; use `rubiks_cube_banana_bowl.usda` for every S1 goal. S3/S4 lateral goals are study additions on existing assets. S5 left/right identities are assigned from reset geometry and then remain fixed. Do not recompute object identity after the bowls move. S6 mug, distance, banana and between-bin extras are excluded. No π baseline, new robot, camera sweep, guidance sweep, denoising sweep or finetuning belongs in this run.

## 4. Three model lanes

Here, **Nano = N3 Cosmos3 Nano Policy DROID; Cosmos = E3 Cosmos3 Edge Policy DROID; Flux = F3 FLUX 3 Action DROID root BF16**. These are three checkpoints, not three unrelated meanings of “Cosmos.”

| Setting | N3 | E3 | F3 |
|---|---|---|---|
| Checkpoint revision | `6706d7680581c255ff61e0f3bb49d90eac55c79e` | `a7c7288f9b6ac1684e993007b0f9703dd26e58ef` | `3d0887bdc7acee1686b19afac267125d519ff4f1` |
| Source commit | retained `411d25b2e35bc441126f48c44a4b93e1c0564274` | `cf5d68c00d97ccd2480a2320ed652b92dec63102` | `e2dd1d8dbc5977b54315d61f7548c63c043d6d4f` |
| Precision | BF16, retained path | BF16 | Root BF16; no variants/quantization |
| Sampler / steps / shift | UniPC / 4 / 5 | UniPC / 4 / 5 | cosmos_unipc order 2 / 4 / 5 |
| Guidance | 3, all denoising steps | 3, inclusive interval [960,1001] | video 4, action 1 |
| Prompt handling | retain verified native transform | native JSON formatting enabled | native task string and package processors |
| Policy seed | 6100, deterministic each request | 6100, deterministic each request | set native inference seed to 6100; record effective seed each request |
| State/history | retained 8D joint-pos, history 1 | joint-pos, history 1 | root DROID config, 8D absolute commands |
| Futures | RGB exists; mapping pending | enable native decode; unqualified locally | instrumentation needed; unqualified locally |

Pin RoboLab to `0aef241fb088ca21bb4ebd24448940ed56620d17`. Preserve original `WRIST_LEFT_RIGHT_HEAD` calibration. The policy uses wrist, left and right; head is not a fourth model input. Cache a common raw first observation per physical state; let each model apply its native preprocessing. Require identical packed first inputs **within each model** across prompts, not identical tensors across different model APIs.

N3 retains its working runtime; do not upgrade it to match E3 merely for cosmetic consistency. Report the two source revisions. E3/F3 pins were resolved from public metadata on September 26 and have not been run here. F3's newer root package is intentional; do not substitute the older documentation example revision, or a distilled/FP8 variant. No claim about model size alone is justified by this comparison.

**Critical adapter checks:** seven absolute joint targets in radians, correct native gripper conversion exactly once, RGB channel order, correct wrist/left/right assignment, no duplicate tiling, full per-episode cache/RNG reset, and no action averaging across samples. Check open/closed gripper values against the actual RoboLab client conversion. Do not copy an inversion between APIs without tracing its convention.

**FLUX export limit: four engineer-hours.** Tap video latents from the action sample already generated; decode them without another sampler call. In eager mode, compare unmodified versus instrumented actions on two saved observations (S1 and S5), same seed/config/device. Require exactly equal returned float32 action arrays and matching postprocessed commands; if equality fails, retain both outputs and diagnose once within the time limit. No permissive tolerance chosen after seeing the difference. Keep a patch diff, source hash and frame mapping. If this cannot be established, mark F3 forecast-ineligible, finish its two integration episodes if its action path is valid, and leave its 336 confirmation cells blocked. N3/E3 proceed independently. Action-only F3 confirmation is a separate explicit amendment, not a silent replacement for this question.

The FLUX public API limitation is documented in [predicted video](https://docs.bfl.ai/flux_3/flux3_action_inference#predicted-video). Model-specific settings are supported by the pinned [Cosmos server](https://github.com/NVIDIA/cosmos-framework/blob/cf5d68c00d97ccd2480a2320ed652b92dec63102/cosmos_framework/scripts/action_policy_server_robolab.py), its [Edge launch instructions](https://github.com/NVIDIA/cosmos-framework/blob/cf5d68c00d97ccd2480a2320ed652b92dec63102/docs/action_policy_droid_server.md), and the [FLUX root config](https://huggingface.co/black-forest-labs/flux-3-action-droid/blob/3d0887bdc7acee1686b19afac267125d519ff4f1/config.native.json). Do not treat generic language-generation settings in Edge's `generation_config.json` as its action sampler.

## 5. Finite preparation, then collection

### A. Existing evidence and adapters — first working session

1. Check out the handoff commit and run `python3 tools/build_robolab_execution_handoff.py --check`. Record actual code, image, asset and checkpoint hashes once; reuse receipts unless an input changes. Download weights once to persistent storage, not on every job.
2. Inspect existing Nano requests 0, middle and last from each of the 15 pilots, at most 45 clips. Trace view crops/padding and physical frame times from source. The 33-frame array and MP4 playback FPS alone do not establish correspondence.
3. Implement recording and scoring in parallel with E3 and F3 adapters. Independent work does not require all three models to be ready. Use two saved-observation adapter fixtures per model; these are bounded offline requests, not new robot episodes. Capture memory, latency and bytes per request from these and the development episodes; no separate performance sweep.
4. Freeze the observable-label rubric using pilot/development data. Before a model's confirmation release, two independent human annotators must reach at least 80% raw agreement on visible categorical labels and at least 60% jointly scorable mapped clips on the available deterministic engineering sample. For E3/F3 use requests 0/middle/last from their two integration episodes (at most six clips each); do not present that tiny check as accuracy validation. Allow two rubric revisions, never choose clips for looking good. Report per-model coverage again on confirmation.

Missing annotators must be reported early, with the prepared clips and instructions. They need not block adapter/scorer development. Do not pass off two calls to one language model as independent human annotation. If source timing remains unresolved, do not launch that model's confirmation queue.

### B. Development — 46 episodes maximum

- Use the existing canonical start for each scene, outside the eight confirmation slots.
- Check the 14 canonical goals once with a scripted controller. A valid demonstration establishes feasibility; one failure gets a recorded explanation, not an open-ended controller project.
- N3: one episode for each of the 42 core prompts.
- E3 and F3: exactly S1-L-S and S5-LR-I, one episode each. A valid action-only F3 integration episode is allowed even if RGB export remains blocked.
- These 46 cells include the simulator integration checks. Do not add a second uncounted “smoke suite.” Maximum six offline adapter fixture calls/model, including server warmup and the paired FLUX export check; log all calls. No simulator rollout is disguised as a fixture.
- Fix implementation mistakes on development evidence. Never tune sampling, prompts or scene geometry to obtain more policy successes. Development failures count toward the cap; a rerun needs an explicit amended budget.

Across all three models, the complete planned inventory caps at 519,000 executed control actions and 16,850 episode inference requests; including the 18 offline fixture/warmup requests gives 16,868 model calls. Reset/metadata RPCs do not generate predictions. These are upper bounds before optional omissions, not measured consumption.

### C. Register forty starting states — no asset design

Use seed 8200. Per scene, propose at most 32 variations of existing movable-object x/y within ±4 cm and yaw within ±10 degrees around the native start. Keep native resting height, table, bins, robot, cameras and lighting. Fixed supports stay fixed; movable reference objects may vary where the native scene permits. Preserve object scale, friction and mass.

Accept the first eight model-blind valid starts in proposal order: supported, no unintended interpenetration, task objects visible in a policy exterior view, distinct mover pose by at least 1 cm, and less than 2 mm drift over the last 0.5 s of a 1 s settle. Cache the fully settled state and first raw model observation together. Save native and study goal predicates at reset.

For every accepted candidate, try each of its physical goals once with the scripted controller. Require disjoint reachable landing regions and 2 cm collision clearance for added lateral goals. A placement directly teleported into the goal tests the scorer only; it does not prove physical reachability. A failed goal rejects that candidate for **all models and all prompt forms**, with its reason retained. Do not retry unchanged candidates. Cap this campaign at **140 scripted goal attempts total**, in addition to the 14 canonical checks; stop after eight accepted states/scene. At most 112 accepted state/goal receipts are needed.

**Time limit: six engineer-hours for goal binding and reset qualification.** If a native scene has a genuine defect, or the quota cannot be reached within the attempt limit, record the shortfall and a proposed smaller study before collecting confirmation outcomes. Do not invent replacement scenes, recycle a start eight times or silently call repeated seeds independent layouts. A smaller prospectively registered sample is preferable to another scene-design week.

Store each scene's C01–C08 slots, proposal IDs, object-role bindings, robot/controller/physics/RNG states, camera calibration, reset/first-input hashes, initial goal truth values and scripted receipts in `accepted_states.json`. Record rejected proposals in `state_candidates.jsonl`.

### D. Release and confirmation

Freeze code, exact prompts, model receipts, eight starts/scene, scorer parameters, annotation rubric and analysis feature schema. Produce an immutable `release.json` containing their hashes. Bind a model lane only after its adapter and forecast checks pass. Later model eligibility is recorded in an additive receipt without modifying completed episodes or the common states/scorers.

Run 336 cells per eligible model in the supplied deterministic block order. A block is one model × one physical start × all scene prompts, with D/S/I triplets intact. Complete blocks are the progress unit. Models may run concurrently in separate lanes; inference requests in a lane remain serialized. No early stopping for good or bad performance. No skipping a difficult prompt or replacing a bad forecast.

## 6. Runner and scoring contract

Restore **full** simulator, controller and policy state before every episode. Disable native success termination and automatic environment reset until the fixed horizon ends. Keep native first-hit scores as separate fields. If the simulator terminates for an invalid numerical state, save a partial attempt; do not let an auto-reset produce a second episode under the same ID. Falling objects and bad grasps are valid policy outcomes if the simulator remains valid.

Name scores explicitly: `native_base_task_first_hit` always refers to the unchanged base task loaded with the scene; `study_goal_first_hit` refers to the requested goal; `native_matched_task_first_hit` is populated only when that requested goal and asset match an actual native task, otherwise null. In particular, a cube-left base-task hit cannot count as cube-right success, and the native on-top predicate cannot score an added lateral instruction. A1 compares goal-matched native first-hit with stable success only where such a native task exists; study-goal first-hit versus stable success is available for every row.

At every control tick record simulator time; all named-object poses, orientations and velocities; joint/gripper state; object-gripper contacts; relevant support/containment contacts; native predicates; study predicates; actual commands; and synchronized executed camera streams. Use original task geometry routines, not guessed axis signs from images. Copy the exact source functions/parameters into the scoring receipt. Contact with a gripper alone is not a secure grasp.

| Measurement | Operational rule |
|---|---|
| Lift | Mover rises ≥2 cm relative to its settled start for ≥0.2 s |
| Stable placement | Goal relation plus its required support/containment, gripper detached, mover speed <2 cm/s continuously for ≥1 s within horizon |
| Reference disturbance | Reference not designated as mover displaced >2 cm; retain as an observation, not an exclusion |
| S1 lateral/depth and S3/S4 added lateral | Pinned robot-frame native relation cone, plus table support for stable placement |
| S2 bins, S3/S4 top, S5 stacking | Corresponding native containment/support predicate plus stable-release rule |
| Initially true goal | Separate maintenance stratum; do not report it as newly achieved |

Report both “ever stable within horizon” and “stable at final horizon”; the former is the prespecified success endpoint. At 15 Hz the dwell must span at least 1.0 s by timestamps, not merely contain 15 samples. A final-chunk truncation never earns unobserved dwell time.

Primary diagnostic window: the first inference request for which the **pre-request** TCP is within 10 cm of any movable task object's geometric surface. If no such request exists, use request 0 and flag fallback. Keep request 0 as a separate descriptive window without duplicate counting. Selection cannot consult forecasts or later outcomes.

Define the binary execution event inside that mapped, actually executed prefix:

1. **Wrong-object manipulation:** gripper contact with an object other than the requested mover lasts ≥0.2 s, and during the prefix that object moves ≥2 cm or rises ≥2 cm relative to its pre-request pose. Incidental contact alone and target-to-support contact are insufficient. This is a behavioral label, not a claim about intention.
2. **Contradictory released placement:** a contact-to-detached transition for the requested mover occurs in the prefix, followed by support/containment in a predefined alternative-goal region for ≥0.2 s within that prefix, while the intended relation is false. Contact may already be present at the request boundary. Alternatives are S1 L/R/F/B excluding the requested one, S2 the other bin, S3/S4 TOP/L/R excluding the requested one. Overlapping or ambiguous regions are not contradictory. S5 wrong bowl movement is event 1; a failed stack or dropped bowl alone is execution failure, not a different spatial goal.

If either is observed, event=1. Otherwise event=0 when the complete mapped execution interval is available; keep `neutral_no_decision`, `goal_consistent_interaction`, and `physical_failure` as separate descriptive flags. Unknown execution timing/state yields an unknown target, excluded with denominator shown. Generic failure, no movement, low success and image motion away from the target are not automatically wrong-goal events.

## 7. Evidence and forecast labels

Each request record must contain `episode_id`, `attempt_id`, request index, exact prompt SHA, effective native prompt/template, input hashes, simulated start/end times, seed, returned/postprocessed/executed actions, actual prefix length, inference time, camera transforms, per-frame physical time and a reason for any missing future. Arrays/videos live on the data volume; Git holds code and compact receipts.

Save futures from the **same sample as the executed action chunk**. Label only mapped frames at or before the last executed action. Never compare an unexecuted forecast suffix with behavior after a later replan. Preserve the final truncated chunk. Store raw lossless returned RGB for inference inputs/futures, and lossless or otherwise verified frame-exact executed recordings; a review MP4 is a convenience copy, not the sole measurement artifact.

Use a stable opaque annotation ID. Annotators see the initial object-ID legend and calibrated forecast views, but not prompt, form, model, task success, execution clip or identifying filenames. Record moving object, direction, visible final relation, possible release, missing/hallucinated object and unknown flags. Apply intended-goal semantics after labels are frozen. RGB cannot establish physical support forces or 3D containment when occluded. Adjudicate disagreements after independent labels and preserve both originals.

Per episode store `episode.json`, `requests.jsonl`, `states.*`, `initial_state.*`, `first_observation.*`, action arrays, future arrays, executed recordings and `result.json`. `result.json` contains status, all denominators, first-hit time, stable-success times, failure-stage flags, initial truth stratum, selected primary request and complete artifact checksums. Write a `COMPLETE.json` marker last, atomically, only after validation. An episode directory alone is not proof of completion.

## 8. Analyses and ablations — reuse these episodes

| ID | Fixed comparison | What it tells us |
|---|---|---|
| E1, primary | State/action diagnostic vs the identical diagnostic plus forecast labels | Whether future video adds held-out information about the next-prefix event |
| E2 | S versus I, same state and goal | Sensitivity to equivalent reference wording |
| E3 | D versus S | Ordinary rephrasing control |
| E4 | Different physical goals on the same scene | Whether instructed goals separate behavior at all |
| A1 | Native first-hit vs stable release | Whether success depends on transient geometry |
| A2 | Forecast/execution agreement table, including unknown and no-decision | Errors visible in the forecast versus errors appearing during execution |
| A3 | Current-frame persistence vs generated forecast | Whether the future adds more than the visible current state |
| A4 | Forecasts permuted between different states within model/scene/goal/form | Negative control for episode-specific predictive information |

No extra rollouts are needed for these eight comparisons. The optional 96 Nano second-seed episodes and all catalog extras stay disabled.

Use L2 logistic regression C=1, `class_weight=None`, fixed solver seed 8400 and train-fold standardization/one-hot categories. Primary score is held-out **Brier(baseline) − Brier(+forecast)**; positive means added value. Use eight folds holding out C01, then C02, etc. across **all scenes and models together**, keeping each physical state out of both training and feature fitting. If a training fold contains one class, use its Jeffreys-smoothed constant prevalence `(positives+0.5)/(n+1)` for both learners and flag the degenerate fold. No hyperparameter search. Do not claim diagnostic utility if there are no informative events, negligible scorable coverage or an interval crossing zero.

Baseline features: model/scene/goal category; current mover/reference relative position in robot coordinates (x,y,z, metres); current geometric distance to the registered goal region; present goal truth; gripper closed fraction; minimum geometric distance and nearest-object identity along FK of the proposed action chunk; prior target contact and lift indicators. Goal regions and FK sampling come from frozen scoring/kinematic code. No actual future state, final success, prompt form or future contact enters the baseline. Augmented features add only the blinded observable forecast labels, with explicit unknown categories. Inspect missingness-only augmentation separately so a gain driven by abstention is not described as better spatial prediction.

The primary estimate weights models equally, scenes equally within model and goals equally within scene. Report each model separately as replication, with model-wise intervals; the pooled estimate is the single confirmatory E1 comparison. Report all eligible executed windows with missing forecast features, and the jointly interpretable subset. Label the baseline as privileged simulator analysis, not an on-robot deployment claim.

For E2/E3 report state-paired signed differences (S−I and D−S), raw discordant counts, stable success, event frequency and continuous target displacement; retain achievement/maintenance strata. Confirmatory wording tests use stable success only: two-sided state-cluster sign-flip tests (100,000 seeded draws, +1 correction), Holm correction across the two contrasts. Event and relation-specific wording effects are secondary/descriptive. Use 10,000 state-cluster bootstrap draws stratified by scene, moving all forms/models/goals for a state together; show 95% percentile intervals. Never bootstrap frames as independent trials. For E1 bootstrap out-of-fold paired losses and disclose that intervals are conditional on the fitted cross-validation models.

For A4, work inside each held-out fold: derange the seven training-state IDs within each scene, and assign the held-out state's forecast features a randomly chosen training-state donor. Apply the same donor mapping across models/goals/forms so complete state associations move together. No held-out forecast or execution label enters fitting. Repeat the complete pipeline for 100 seeds. Permute forecast features only; never move execution labels or baseline features. Use seed 8401 for bootstrap, 8402 for wording sign flips and 8403–8502 for A4. Use development data to verify this code; no feature changes after confirmation outcomes are opened.

## 9. Kubernetes execution and recovery

Use one serialized policy server and one simulator worker per lane. N3/E3/F3 can have independent lanes; extra lanes require independent server state and disjoint block assignments. Do not share a global reset RPC among concurrent episodes. The baseline is `num_envs=1`; vectorization is an optional engineering change requiring proof of state/camera isolation, not a prerequisite.

The cluster operator supplies actual namespace, image digests, GPU node selectors, data PVC/object-store URI, source roots and credentials through its existing mechanism. These are deployment inputs, not values to guess in this repository. Preserve separate simulator and policy environments: pinned RoboLab/Isaac stack for simulation, retained Nano runtime, Edge's pinned lockfile, FLUX's own lockfile/NATTEN-compatible image. Do not upgrade one shared environment until all dependencies import.

Use `batch/v1 Job`, `restartPolicy: Never`, **`backoffLimit: 0`**, `parallelism: 1`, explicit GPU/CPU/memory requests, and a finite active deadline. Prefer a persistent lane that consumes a fixed list of whole blocks to amortize model loading. Partition the 40 confirmation blocks/model among available lanes once. The default is one lane/model, not 120 simultaneous model replicas.

Derive the lane deadline before launch as `ceil(1.5 × (cold_start_s + planned_requests × measured_p95_request_s + planned_actions × measured_p95_step_s + measured_write_s))`. Use development measurements including decode/recording; request the appropriate scheduler wall-time or split by whole blocks. Report projected finish time and GPU-hours before starting the confirmation queue. Do not promise a one-day run based on workstation or unrelated model timing.

Persist artifacts before acknowledging a cell. Use an atomic filesystem claim or object-store conditional write for block ownership; no two lanes may own the same episode. A per-request 900 s timeout and 60 s heartbeat are initial upper bounds, not automatic retry signals. Send heartbeats out-of-band so inference does not suppress them.

On failure, record `infra_error`, `model_output_invalid`, `simulation_invalid` or a completed policy outcome. Fail the lane on timeout, NaN commands, receipt mismatch, storage failure or reset mismatch; preserve partial artifacts and stop only that lane. Do not automatically resample, restart a model request, or rerun a bad policy outcome. A lost request may already have sampled actions. On manual restart, skip only cells with validated COMPLETE markers, quarantine partial attempts and create a new attempt ID for any explicitly approved rerun. Other lanes continue. Budget amendments must distinguish retries from unique episodes.

Provision from measured bytes, with ≥30% headroom and weights/assets separately. Nano's raw future shape alone is about 33.45 MB/request: roughly 180 GB for 5,376 forecasts/model, or 540 GB if all three had that shape, **before inputs and executed recordings**. Other model shapes may differ. Use lossless compression, per-request flushing and persistent storage; do not discover insufficient disk halfway through collection.

## 10. Work allocation and completion

| Owner | Deliverable | Stop rule |
|---|---|---|
| Coordinator / runner agent | Common state/score/recording implementation; release; finite cluster jobs; progress ledger | No scene construction; six-hour scene/goal engineering cap; report unresolved implementation issues |
| Nano agent | Reuse working N3, map futures, run its 42 development and 336 confirmation cells when released | No checkpoint upgrade or sampling sweep |
| Cosmos agent | Pin E3, preserve JSON/guidance settings, two integration then 336 confirmation cells | Report compatibility blocker without holding N3 |
| FLUX agent | Root BF16 adapter, same-sample export/equality check, two integration then 336 if eligible | Four-hour export cap; no action-only substitution |
| Analysis / paper agent | Blinded clip packets, feature schema, held-out analysis, figures and result-dependent claims | No selecting outcomes or silently changing the question |

These roles are a handoff, not agents dispatched by this document. The owner may combine roles. The first working session should produce working adapters, a bounded reset campaign and an explicit blocker list. Freeze and begin qualified lanes as soon as the listed requirements pass; do not spend days polishing infrastructure.

Every progress report gives counts by model and phase: planned, blocked, running, complete-valid, partial/invalid; completed **whole state blocks**; requests/actions used; disk used; measured remaining time; and the exact next blocker. Report zero as zero and unknown as unknown.

Completion means: 336 valid recorded confirmation episodes for each eligible model; every omitted cell/reason listed; state-paired result tables with coverage; two independent annotation files plus adjudication; exact receipts and raw artifact index; reproducible analysis command; paper-ready goal-response, wording-effect and forecast-utility figures; and a four-page results-grounded draft. A stopped F3 integration can still yield a useful N3/E3 paper, but cannot be reported as a three-model forecast study.

The contribution must remain proportional to the findings. Equivalent wording failures alone are not new enough; the paper should establish whether forecasts expose or fail to expose those failures under controlled paired inputs. This directly serves the workshop's debate about what explicit predictions provide for evaluating and trusting robot behavior. It does not establish that robots need world models or that predictions cause their actions.
