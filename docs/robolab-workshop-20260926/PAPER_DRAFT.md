# When Robot Actions Fail, Does the Predicted Future Explain Why?

*Draft for the CoRL 2026 workshop "Do Robots Need World Models?", research track, up to 4 pages.*
*Every number comes from `artifacts/robolab_workshop_20260926/` (see [RESULTS.md](RESULTS.md)); deviations
from the frozen design are listed in [EXECUTION_RECORD.md](EXECUTION_RECORD.md) (A1–A11).*

## Abstract

A failed robot placement does not show whether the policy pursued the wrong goal or failed to carry out the
right one. World-action models (WAMs) emit a predicted future video alongside each action chunk, which could
supply exactly this evidence. We test that possibility in a preregistered RoboLab study.
- **Design:** three released WAM policies; four stock scenes; twelve spatial goals; three wording forms per goal
  (native direct, explicit standard, and a logically equivalent inverted-reference form); eight held-out initial
  states. In total, 864 of 864 episodes were valid.
- **Wording:** equivalent inverted-reference wording lowers stable success by 12.2 points
  (95% CI [8.6, 15.4], Holm p = 0.0001), with the same direction in all three models. Ordinary rephrasing
  costs 4.1 points (CI [−0.2, 8.4], not significant).
- **Forecast utility (primary):** we labeled every contemporaneous forecast with two blinded vision-language
  models and added the labels to a privileged state-and-action baseline. The forecast did not improve held-out
  prediction of imminent wrong-object or contradictory-release events (Δ Brier = −0.0007,
  CI [−0.0018, +0.0002]), and was indistinguishable from permuted labels.
- **Why the forecasts say little:** most forecasts show only a grasp-and-lift (78% `up_only`) and seldom show a
  destination relation. Agreement between the two automated labelers was low (κ 0.08–0.40).

We conclude that, at the horizon these interfaces expose, predicted futures give no detectable diagnostic gain
over what state and planned action already reveal. Reading forecasts reliably is itself an open measurement
problem.

## 1. Question and interventions

**Question (fixed before collection).** Can a WAM's predicted future help separate "following the wrong goal"
from "failing to execute the right one"? We do not claim to read the model's internal state. We compare what is
observable in the prediction with what happens when the same action chunk is executed:
- which object moves;
- in which direction;
- which spatial relation is visible.

**Language is the intervention.** Each physical goal is requested in three forms:
- **D:** the native RoboLab direct instruction.
- **S:** an explicit standard form ("place the cube to the left of the bowl").
- **I:** a logically equivalent form with the reference inverted ("place the cube so that the bowl is to the
  right of it").

D and S differ only by ordinary rephrasing; S and I describe the same goal. A policy that follows goals should
therefore be insensitive to both contrasts.

**Related work.**
- SG-WAM already reports semantic misalignment in WAM predictions.
- SC3-Eval compares action-conditioned simulation with execution.
- RoboLab supplies our environments.

Our contribution is narrower: (i) a paired, goal-preserving wording intervention at fixed initial states; and
(ii) a held-out test of whether the policy's *own contemporaneous* forecast adds diagnostic information beyond
state and planned action.

## 2. Setup

**Models.** Three released checkpoints with a decodable future:
- N3: Cosmos3 Nano policy.
- E3: Cosmos3 Edge policy.
- F3: FLUX 3 Action.

N3 versus E3 is not a controlled test of model size.

**Scenes and goals.** Four stock RoboLab scenes:
- S1: cube, bowl and banana. Goals: left, right, front, behind.
- S3: butter box and raisin box. Goals: on top, left, right.
- S4: mustard bottle and raisin box. Goals: on top, left, right.
- S5: two bowls. Goals: left bowl onto right, right bowl onto left.

A fifth scene (S2, bins) was omitted before confirmation because no valid start registered (A1).

**Episodes.**
- There are 12 goals × 3 forms × 8 frozen initial states (state clusters C01–C08), giving 288 episodes per model.
- Prompts are static; there is no oracle or subtask coaching.
- Code, prompts, states, scorers, rubric and feature schema were hashed into an immutable release before
  confirmation.

**Outcomes from simulator state (post-action only).**
- *Stable success:* the goal relation holds and the object is at rest.
- *Achievement stratum:* episodes whose goal did not already hold at reset. 172 *maintenance* episodes started
  satisfied, and all 172 stayed satisfied.
- *Executed next-chunk semantic event:* either a wrong object moved or a release contradicted the goal. The event
  is scored on the action chunk paired with the primary forecast.

**Forecast labels.** Each primary forecast was mapped to the executed camera and time window and rendered as a
blinded packet: an object-number legend plus 8 frames, with no prompt, model, goal or outcome. The rubric (v2)
records these fields:
- moving object;
- direction;
- visible final relation and its object;
- possible release;
- missing or hallucinated objects;
- an explicit `unknown`.

The protocol called for two blinded human annotators. We replaced them with two open-weight VLMs, Qwen3-VL-235B
and GLM-4.5V. Output was constrained to the rubric enums, and disagreements were adjudicated by the Qwen model;
this is a post-result amendment, disclosed as A11. All 864 forecasts decoded.

**Primary test (E1).**
- Model: L2 logistic regression.
- Folds: eight leave-one-state-cluster-out folds across all scenes and models.
- Baseline features: model, scene and goal; current object geometry and goal distance; gripper state; forward
  kinematics of the proposed chunk (nearest object and distance); prior contact and lift.
- Augmented features: the baseline plus forecast labels.
- Score: Brier(baseline) − Brier(augmented), with a conditional bootstrap interval.
- Controls: missingness-only and persistence augmentations (A3), and 100 within-scene state-donor permutations
  of forecast labels (A4).

## 3. Results

**Wording (E2, E3).** Tests are paired at fixed start and goal, use a state-cluster sign-flip test and are
Holm-corrected.

| Contrast | Δ stable success | 95% CI | Discordant pairs | p (Holm) |
|---|---|---|---|---|
| S − I (equivalent inverted reference) | **+0.122** | [+0.086, +0.154] | 45 / 14 | 0.0001 |
| D − S (ordinary rephrasing) | +0.041 | [−0.002, +0.084] | 25 / 13 | 0.089 |

Achievement-stratum success by form (D / S / I):
- N3: 42 / 40 / 25%.
- E3: 26 / 18 / 8%.
- F3: 49 / 39 / 30%.

Inverting the reference hurts every model, even though the requested physical goal is unchanged.

**Physical success (supporting).** Stable success overall and in the achievement stratum:
- N3: 142/288 overall; 80/226 (35%) in the achievement stratum.
- E3: 93/288 overall; 41/236 (17%).
- F3: 148/288 overall; 90/230 (39%).

By goal:
- Motions toward or away from the robot (S1-front, S1-behind) and S3-left rarely succeed.
- S5 bowl stacking separates the models: F3 30/48, N3 3/48, E3 3/48.

Failure stages over all 864 episodes:
- stable success: 383;
- lift without the goal: 287;
- contact without lift: 94;
- no mover contact: 69;
- goal reached but unstable: 31.

**Forecast utility (E1, primary).**

| | Brier without forecast | Brier with forecast | Δ | 95% CI |
|---|---|---|---|---|
| Pooled (n = 864, 47 events) | 0.0401 | 0.0409 | −0.0007 | [−0.0018, +0.0002] |
| Permuted forecast labels (A4) | | | −0.0005 | [−0.0018, +0.0005] |
| Missingness only | 0.0401 | 0.0401 | +0.00001 | |

By model, Δ is −0.0014 for N3, −0.0004 for E3 and +0.0011 for F3. **The primary claim is not supported.**

Predicted versus executed events:

| Forecast relation \ executed | Goal-consistent | Neutral | Other, no event | Wrong-goal event |
|---|---|---|---|---|
| goal (39) | 19 | 16 | 4 | 0 |
| alternative goal (99) | 62 | 29 | 5 | 3 |
| not goal (608) | 309 | 207 | 54 | 38 |
| unknown (118) | 65 | 41 | 6 | 6 |

**Why the forecast adds so little.**
- The forecast horizon mostly covers grasp and lift: 673 of 864 forecasts are `up_only`, and only 138 show any
  goal-type relation.
- Exploratory univariate signal:
  - Forecasts showing the *reference* object moving (247 of 864) were followed by a wrong-goal event 9.3% of the
    time, versus 3.5% after mover forecasts.
  - Stable success in the achievement stratum was 23% after reference-moving forecasts versus 35% after mover
    forecasts.
  - The signal is absent from the held-out comparison, which adds the forecast labels to scene, goal and planned-chunk
    kinematics. This is consistent with the planned action already carrying the information; we did not test that
    mechanism directly.

**Label reliability.** On primary windows, inter-VLM agreement was:

| Field | κ |
|---|---|
| moving object | 0.40 |
| direction | 0.11 |
| visible final relation | 0.08 |
| relation object | 0.11 |

All fields agreed in only 6% of packets. The labelers differ systematically in how readily they name a relation
and a release.

## 4. Interpretation and limitations

**What we can say.**
- Equivalent wording is a real, replicated failure mode of released WAM policies.
- At the exposed horizon, their forecasts give no detectable diagnostic gain over state and planned action.

A forecast that mostly depicts the lift phase cannot tell us where the object was going. Where the forecast
shows the reference object moving, the baseline's planned-chunk features appear to capture the same risk.

**What we cannot say.**
- That forecasts contain no information. Automated labels with κ at 0.1–0.4 could hide a real effect; a human- or
  tracker-labeled subset is the necessary next step.
- That world models are unnecessary, that WAMs are worse than VLAs, or that video generation causes action errors.
- Anything beyond one simulator, one robot, four scenes and eight starts per scene.

**Disclosed deviations.**
- S2 was omitted (A1).
- Automated labelers replaced humans after outcomes were visible (A11). The labelers were blind to outcomes, and
  the adjudicator is one of the two labelers.
- Physical outcomes use privileged simulator state; the E1 baseline is an analysis device, not a deployable
  monitor.

**Representative sequences.** For the camera-ready version, sequences will be selected by rule: the first
episode, in `episode_id` order, of (a) a forecast showing the reference object moving followed by an executed
wrong-goal event, and (b) a goal-relation forecast whose executed chunk did not reach the goal. Figures:
`results_vlm/fig_wording.pdf`, `fig_goal_response.pdf` and `fig_forecast_utility.pdf`.
