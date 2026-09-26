# Experiment specification: language interventions and forecast usefulness

**Status: design for review; no new model or simulator runs authorized by this file.**

The question is fixed in [PAPER_DESIGN.md](PAPER_DESIGN.md): **Can a world-action model's predicted future help distinguish following the wrong goal from failing to execute the right one?** All experiments below serve this question. [prompt_matrix.json](prompt_matrix.json) is the source of exact strings, IDs, hashes, scene identity and goal roles. This is a new stock-RoboLab proposal, not a change to the frozen SGW-01 queue.

## 1. What is held fixed and what changes

The unit of comparison is a **model, physical starting state and intended goal**, evaluated under D, S and I wording. D is the direct/native reference; S and I describe the same goal with opposite argument order in the relational clause. S versus I is primary for wording sensitivity; D versus S measures the cost of ordinary rephrasing. S versus I also changes converse-relation vocabulary, so it does not isolate token order or an internal linguistic mechanism.

Genuine goal counterfactuals change the target relation, destination or moved object while holding the scene fixed. They are positive controls for appropriate goal responsiveness, not paraphrases. Do not load a different scene for a different instruction. In particular, the native cube-right task has a different asset from cube-left; use the simple cube/bowl/banana scene for all four study goals.

Keep the robot, original RoboLab camera calibration, lighting, background, controller, object assets and checkpoint configuration fixed within each comparison. These are stock-background experiments. Removing the background or moving cameras would be a separately versioned appearance intervention, outside this primary study. No custom-office cleanup or new scene construction is needed here.

Cache the first full model input, including all images, proprioception and camera metadata, and reuse it byte-for-byte across the prompt conditions of a physical reset. Restore full simulator state, velocities and controller state for every episode; reset policy caches and record RNG state. After the first request, record fresh closed-loop observations. Do not claim identical later pixels when trajectories diverge. Log actual reset-state and first-input hashes; changing the seed alone is not evidence of a new layout.

## 2. Scope and exact budget

| Scene | Physical goals | Wording forms | Prompts per initial state | Confirmation episodes per model, 8 starts |
|---|---:|---:|---:|---:|
| S1: cube / bowl / banana | Left, right, front, behind: 4 | D/S/I | 12 | 96 |
| S2: mustard / bins | Left bin, right bin: 2 | D/S/I | 6 | 48 |
| S3: butter / raisin box | On top, left, right: 3 | D/S/I | 9 | 72 |
| S4: mustard / raisin box | On top, left, right: 3 | D/S/I | 9 | 72 |
| S5: two bowls | Left onto right, right onto left: 2 | D/S/I | 6 | 48 |
| **Primary total** | **14** | **3** | **42** | **336** |

S6, the mug scene, is held because the pilot reset had invalid non-target object states. Its nine prompts and the five optional prompts in the catalog are excluded. They cannot silently enter the confirmation budget.

Use eight newly registered initial states per primary scene, with one policy seed per state and shared physical states across models. There are **40 physical state clusters**, not 336 independent scenes. The eight starts vary existing object poses modestly; they are not eight new environment assets. The small number per scene will produce wide uncertainty intervals.

- Nano confirmation: **336 episodes**.
- Nano + qualified Edge: **672 episodes**.
- Nano + Edge + FLUX, only if all three expose qualified contemporaneous futures: **1,008 episodes**.
- Development: **42 Nano episodes** on the existing five canonical starts; at most **two integration episodes each** for Edge and FLUX. Maximum **46 development episodes**, excluded from confirmation.
- Total with all three qualified: **1,054 learned-policy episodes**, including development. This is a ceiling, not an instruction to launch.
- Physical qualification: at most one successful scripted trial per confirmation state/goal, **112 successful trials maximum**, without three-reset repetitions. Keep attempted failures; do not retry an unchanged failing setup.
- No repeated model sampling is hidden inside an episode. Extra policy seeds, resampling, candidate ranking and action-horizon changes are separate studies.

At the currently used 15 Hz control rate, fixed observation horizons are 30 s for S1/S2, 40 s for S3/S4 and 20 s for S5. Per model the full confirmation ceiling is 165,600 control actions. With Nano's 32-action chunks it is 5,376 requests; do not assume other models have identical chunk timing or latency. The existing Nano CPU-offload run averaged roughly a minute per request: this confirmation alone is around 100 workstation hours including stepping, not another two-hour pilot. Cluster timing must be measured with the actual model configuration before scheduling the full queue.

## 3. Models and capture eligibility

| ID | Model | Current evidence | Role in this design |
|---|---|---|---|
| N3 | Cosmos3-Nano-Policy-DROID | Pinned checkpoint and working two-GPU runner; 209 returned RGB futures saved. | First diagnostic model. Time/camera mapping still must be qualified. |
| E3 | Cosmos3-Edge-Policy-DROID | Official model and RoboLab route exist; no local qualification receipt in this study. | Same-family replication after source/checkpoint/config and capture qualification. |
| F3 | FLUX 3 Action DROID, root BF16 | Official API currently returns actions; video latents are not exposed as decoded RGB. | Second-family replication only after an instrumented export is shown to preserve action output. Otherwise excluded from the forecast comparison. |

Preserve the intended N3/E3/F3 roster; do not replace a missing future with a zero score. Nano versus Edge is not a pure size ablation. If only Nano/Edge qualify, describe the result as a Cosmos-family study, not evidence across independent WAM families. An action-only FLUX result could support an explicitly separate behavior comparison, but cannot answer the primary forecast question and is not automatically scheduled.

N3 pins remain checkpoint `6706d7680581c255ff61e0f3bb49d90eac55c79e`, Cosmos source `411d25b2e35bc441126f48c44a4b93e1c0564274`, RoboLab `0aef241fb088ca21bb4ebd24448940ed56620d17`. Use its existing recorded guidance/denoising/precision configuration. E3/F3 immutable pins and effective defaults are required release fields; they are currently unresolved, so their queues must remain disabled. Do not copy Nano sampling settings onto them.

There is no pi baseline in the primary study. The relevant control is the same model's information with versus without its predicted future. A VLA comparison would answer a different question about behavioral robustness and would not establish a world-model training advantage under unmatched data and compute.

## 4. Stages and decisions before collection

### Stage A: answerability using recordings we already have

Use all 15 pilot episodes for artifact inventory. There are 209 retained forecasts; do not generate new predictions merely to inspect them.

1. Trace each checkpoint's output frame timestamps and view transforms to its native implementation. Validate against saved inputs, calibration and executed-action indices. Match only forecast times inside the actually executed prefix, within one control tick. Do not infer physical duration from the array length or video playback rate alone.
2. Inspect a deterministic sample: requests 0, floor((K-1)/2) and K-1 from each pilot episode, deduplicated. At most 45 clips. Two annotators independently label visible object identity, motion and relation without seeing prompt form, model identity, executed outcome or success score.
3. Record agreement, visibility and abstention. Require at least 80% raw agreement on the categorical observable labels in this small engineering sample and at least 60% jointly scorable clips. These are design thresholds for answerability, not measured facts or statistical power guarantees. Disagreements revise the rubric on pilot data only.
4. If physical-time/view mapping is unresolved, or two bounded rubric revisions still fail those thresholds, stop before the 42-episode development stage. Record the limitation; do not silently switch the primary question to action-only success.

No model training, simulator reruns or new learned-policy requests are needed for Stage A. A video that ends before any relevant event remains unresolved, even if it looks realistic.

### Stage B: finite development and protocol freeze

Use the five already observed canonical stock starts. Check all 14 physical goals once with a scripted placement/controller before evaluating added goals. A failed demonstration triggers a bounded geometry/scorer correction or a prospectively documented exclusion; do not choose goals based on Nano success. Do not build replacement scenes to make Nano look better.

Run the 42 Nano prompts once with full evidence. E3/F3 integration checks, when eligible, use S1-L-S and S5-LR-I only, one episode each. These are interface checks, not estimates of performance. Review prompt equivalence with two human readers and the intended terminal configurations; flag any disagreement before freezing strings. Finalize capture mapping, annotation instructions, thresholds and analysis code on development data. Stamp a release manifest containing their hashes. No confirmation data may be used for these choices.

### Stage C: eight held-out starts per scene

Generate pose proposals deterministically from a registered seed (8200), around the native start. Move movable task objects only: independent x/y offsets in [-0.04, 0.04] m and yaw in [-10, 10] degrees in the robot frame. Keep table, robot, cameras, bins and other fixed supports unchanged; maintain the native resting height. For bowls, bind left/right identities by their positions at reset rather than hard-coding asset names.

Generate at most 32 proposals per scene; take the first eight passing model-blind checks. Require visible task objects in at least one exterior policy view, valid support, no unintended interpenetration, at least 1 cm separation in moved-object pose from prior accepted starts, and a 1 s settling check with less than 2 mm drift over the final 0.5 s. Pose filtering must use object geometry, not origin distance alone. New goals require disjoint reachable landing regions with at least 2 cm collision clearance; do not place them through the reference or robot. Run one scripted physical trial per accepted state/goal; do not repeat a passing trial. If eight states cannot be obtained within the bounded campaign, report the shortfall and amend the proposed sample size before model outcomes, rather than redesigning scenes indefinitely.

Store all proposals, rejections, selected states and bindings before learned-policy collection. These offsets and checks are a specification, not an implemented or validated sampler. The existing runner does not implement this stage yet.

### Stage D: confirmation

Randomize execution order within each model/state block using seed 8300, while retaining whole D/S/I goal triplets in the job manifest. The same instruction and state IDs must appear for every eligible model. Use deterministic policy seed 6100 within each model; equal seed numbers across architectures do not imply equal random draws. Do not drop a valid episode because it fails, has no grasp, or its forecast is inconvenient to label. Infra failures are explicit partial attempts with new IDs on any approved rerun; preserve the original.

Use the fixed family horizon with native early-success termination disabled. Log the first native-success event and continue to the time limit so transient and stable outcomes are distinguishable. This is a study-specific evaluation, not the unmodified RoboLab leaderboard protocol. Native score formulas and the existing pilot scores remain unchanged and separately reported.

## 5. Measurement and failure stages

For each step record all object poses, orientations, velocities, robot state, gripper aperture, object-gripper and relevant object-object/table contacts, and native predicates. `object_grabbed` in RoboLab means contact with the gripper; it must not be relabeled secure grasp.

Report the following measurements in order. Do not force overlapping failure mechanisms into a single causal explanation.

1. **Object selection:** identity of contacted and moved objects, including reference displacement. Record non-target interaction even when the requested target is later moved.
2. **Lift evidence:** target origin rises at least 2 cm from its settled initial value for at least 0.2 s. This is an operational lift measure, not proof of a secure grasp.
3. **Directional response:** target/reference displacement in the robot frame, not camera pixel direction. Report continuous signed change; temporary motion away from a goal is not automatically a misunderstanding.
4. **Placement:** goal relation and support/containment at release. Cube and added lateral placements require table support for the study's stable-placement metric. Preserve native predicates separately, including their differing contact requirements.
5. **Stable release:** goal predicate true, required support/containment present, gripper detached, target speed below 2 cm/s continuously for 1 s within the family horizon. Report any first hit separately; a hit too late for the dwell interval does not meet this stricter measure.
6. **Reference disturbance:** displacement above 2 cm for reference objects that the instruction does not ask to move. This is an additional observation, not a hidden exclusion.

For added lateral goals reuse the pinned robot-frame relation cone and add table support and release requirements; materialize these rules explicitly. For on-top and bin/bowl tasks, use the corresponding native support or containment predicate plus the stable-release criterion. Body origins need not equal geometric centroids; geometry-based scoring must use the same native geometry implementation throughout.

At reset, record every goal predicate. Report **achievement** where the goal starts false and **maintenance** where it starts true, with both denominators. Some mutually exclusive directional goals necessarily include an already-satisfied case on a given layout; do not pretend all counterfactual goals begin false. Evaluate within-goal wording effects separately in these strata, then show the declared aggregate.

## 6. Aligning and labeling forecast versus execution

For each inference request save the original and model-packed input, exact user prompt and appended model template, action chunk before/after native postprocessing, actual executed prefix length, decoded forecast or missingness reason, frame timestamps, camera transforms and crop/resize mapping. Also retain the native source/checkpoint receipt, reset snapshot, per-step state and input/output hashes.

The primary scored window per episode is the **first request whose pre-request gripper TCP is within 10 cm of the geometric surface of any movable task object**. Select it from pre-request state, without looking at the returned forecast, prompt form or later outcome. If no request qualifies, use request 0 and record the fallback. The first request is also a separate descriptive window; if it is the same request, do not duplicate it. Record all other futures, but do not treat them as independent samples or choose a more dramatic window after seeing results.

Compare at the last mapped forecast time lying inside the executed prefix, retaining the intervening sequence. If an action chunk returns 32 controls but only 2 were executed, only those 2 controls' physical interval is eligible. Do not compare an unexecuted part of the forecast with later closed-loop behavior after replanning.

Annotators see initial object-ID legends and calibrated views, but not condition, model, task success, or the executed video. Label the forecast's moving object, visible motion direction, release/placement if visually resolved, hallucinated/missing objects and confidence. Distinguish motion toward/away from a goal from a wrong final placement. Apply the instruction-to-goal mapping afterward. The executed comparison uses simulator state plus blinded video review for ambiguous identity cases. Predictions that cannot support a 3D relation are unknown; no invented depth or contact label is allowed.

The **primary event target** is an observable wrong-object interaction or a released placement in a contradictory goal region within this action prefix. A temporary detour or stationary reaching phase is not such an event. Track neutral/no-decision and unknown cases explicitly. Describe this as an operational behavioral event, not evidence of internal misunderstanding.

## 7. The actual experiments and ablations

| ID | Comparison | Purpose | Extra rollouts beyond the registered prompt matrix |
|---|---|---|---:|
| E1 | State/action baseline versus the same baseline plus forecast features | Primary: does the exposed future add diagnostic information? | 0 |
| E2 | S versus I at the same state and goal | Does equivalent reference wording change the observable goal-following event? | 0 |
| E3 | D versus S | Control for rephrasing before interpreting the S/I contrast. | 0 |
| E4 | Different goal rows within each fixed scene | Check intended goal responsiveness; do not conflate role reversal with paraphrase. | 0 |
| A1 | Native first-hit success versus stable placement/release | Reveal what binary success hides. This is a scoring comparison, not a new policy run. | 0 |
| A2 | Prediction/execution event table, including unknowns | Separate forecasts that reflect an error from forecasts execution does not realize. Descriptive analysis. | 0 |
| A3 | Persistence video versus the generated forecast, same labeling method | Check whether apparent predictive value comes from an already-present state. | 0 |
| A4 | Forecast features with permuted episode association within model/scene/goal | Negative control for the forecast-utility analysis; permutations respect state grouping. | 0 |

These are four comparisons and four analyses/controls, not eight separately collected studies. No guidance sweep, denoising sweep, background sweep, new robot, finetuning, or massive extra task suite is needed to answer the primary question.

**Optional later:** repeat the 12 S1-left/right and S2-left/right prompts on the same eight states using policy seed 6101: 96 extra Nano episodes. This measures sampling sensitivity, not new independent layouts. Distance, banana-object, between-bin and mug extensions require their own goal qualification and prospective amendment. They do not automatically run after the primary queue.

## 8. Primary analysis, baselines and uncertainty

Use identical held-out examples and the same fixed learner for the two diagnostic conditions. Baseline inputs are the model/scene/goal category, current target-to-goal distance, nearest-object identity/distance along the proposed forward-kinematics TCP path, gripper state, and previous contact/lift state. These use only information available at request time plus the proposed actions; future executed state is prohibited. Privileged simulator state makes this a strong analysis baseline, not a deployable real-robot diagnostic.

The augmented condition adds only the blinded forecast labels: anticipated moving object, visible direction, predicted relation when observable, and missing/ambiguous-object flags. Use fixed L2 logistic regression with C=1 and training-fold-only standardization; no confirmation-set hyperparameter search. Store the feature schema before the first confirmation episode. Persistent-current-frame features are a separate negative control. Both models predict the same binary event target from section 6.

Use eight folds indexed by held-out layout number across all five scenes. All prompts, models and repeated observations derived from a physical state stay in one fold. Compare paired Brier errors; define improvement as Brier(baseline) minus Brier(augmented). Report calibration, event prevalence, AUROC only if both classes are present, and coverage. If there are too few events or the interval overlaps zero, report insufficient evidence rather than claiming utility. Evaluate both (a) all eligible windows, with explicit missing-forecast features, and (b) the jointly interpretable subset; never hide coverage differences.

For wording, report paired S-I and D-S differences in event frequency and stable physical success, plus distributions of continuous displacement. Weight each scene equally, then goals equally within scene, to avoid the four-goal cube scene dominating. Provide per-scene results and preserve the achievement/maintenance distinction. Use a state-cluster bootstrap stratified by scene with 10,000 resamples; all goal forms and models for a state remain together. Show 95% intervals and raw paired counts. Correct the two confirmatory wording contrasts with Holm's method; optional relation-specific comparisons are exploratory. Frames and inference requests are not independent trials.

## 9. Concrete work packages for cluster agents

This section allocates implementation work; it does not dispatch agents or start jobs.

| Package | Inputs | Required output and completion condition |
|---|---|---|
| Scene/goal binding | Catalog, pinned task files, pilot reset evidence | Asset/binding ledger, new-goal scorers, bounded accepted-state manifest, scripted qualification receipts. No changes to robot/cameras/background. |
| Forecast adapter | Pinned model source, saved input/action/future artifacts | Per-model view/time mapping and export receipt; action equality before/after instrumentation for FLUX. Unknown capture means disabled forecast queue. |
| Runner | Prompt hashes, state manifest, model receipt | Whole paired blocks, fixed horizon, isolated resets, exact recording contract, explicit partial attempts and zero automatic policy retries. Existing nine-task runner is a reference, not a drop-in implementation. |
| Annotation | Blinded predicted clips and object legends | Independent labels, adjudication record, coverage/agreement table, frozen event rubric. No prompt-form or outcome leakage. |
| Analysis/paper | Frozen release plus completed evidence | Predeclared primary comparison, paired effects, all failures/unknowns, figures and claim table. No selecting only successful layouts. |

## 10. Schedule and release boundary

- **September 26-28:** review the prompt catalog, check existing forecast mapping, finalize the question and event rubric.
- **September 29-October 1:** bounded goal/reset checks and finite development; freeze the manifest. Do not spend this period building new scenes.
- **October 2-6:** confirmation on the cluster, only for qualified models; retain full paired blocks and monitor disk/runtime budgets.
- **October 7-9:** blinded labels, locked analysis, paper figures and results-based abstract.
- **October 10-11:** scientific review, four-page formatting, reproducibility check and submission preparation.
- **October 12:** listed workshop deadline; exact timezone and submission form requirements must be checked before submission. No submission is authorized by this specification.

No current launch command implements this design. Missing components are the bounded state sampler, added-goal bindings, fixed-horizon event recorder, per-model forecast mapping, annotation rubric, and held-out diagnostic analysis. This document makes those requirements reviewable before implementation or cluster expenditure.

## Sources checked for this design

- [Workshop call, motions and dates](https://do-robots-need-world-models.github.io/).
- [Pinned RoboLab task definitions](https://github.com/NVlabs/RoboLab/tree/0aef241fb088ca21bb4ebd24448940ed56620d17/robolab/tasks/benchmark).
- [Nano model card](https://huggingface.co/nvidia/Cosmos3-Nano-Policy-DROID) and [Edge model card](https://huggingface.co/nvidia/Cosmos3-Edge-Policy-DROID).
- [FLUX predicted-video limitation](https://docs.bfl.ai/flux_3/flux3_action_inference#predicted-video).
- Existing results: [six wording episodes](../WORKSTATION_NANO_RESULTS_20260926.md) and [nine spatial episodes](../WORKSTATION_NANO_SPATIAL_RESULTS_20260926.md).
