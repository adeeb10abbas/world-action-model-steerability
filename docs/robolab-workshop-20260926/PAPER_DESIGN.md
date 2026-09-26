# When Robot Actions Fail, Does the Predicted Future Explain Why?

**Research-paper design for the CoRL 2026 workshop, Do Robots Need World Models?**

Design date: September 26, 2026. Start with [the illustrated scene and prompt catalog](SCENES_AND_PROMPTS.md). This is a proposed study, not a report of completed confirmation experiments. The earlier clean-scene protocol and its results are preserved separately.

## The question, fixed before collection

**Can a world-action model's predicted future help distinguish following the wrong goal from failing to execute the right one?**

We make this observable rather than claiming to read the model's mind. We compare which object moves, the direction of its movement, and the visible spatial relation in a predicted video with what happens when the accompanying action chunk is executed. A short video cannot establish the model's internal understanding, eventual task success, contact forces, or stable support.

Language is the intervention, not the entire contribution. Equivalent descriptions keep the requested physical goal fixed; genuine goal counterfactuals change the destination, relation, or manipulated object. These controlled changes let us test whether the extra predicted video is informative when behavior changes or fails.

The decisive test is whether forecast-derived observations improve prediction of an imminent wrong-object or wrong-direction event over information available without that forecast. Separately, we measure how often equivalent wording changes both prediction and execution. We will not run a large benchmark and choose an interesting question afterward.

## Why this paper belongs at this workshop

The primary fit is **Motion 6: what current benchmarks can establish about world models**. Success alone collapses wrong-object selection, directional response, missed grasps and failed placement into one number. The secondary fit is **Motion 4: whether model-based evaluation is trustworthy**. We ask whether an exposed prediction supplies useful evidence about behavior, or creates false reassurance. Motion 2 is related through goal changes, but we do not have a controlled training comparison that establishes a benefit from explicit dynamics prediction.

The [current call](https://do-robots-need-world-models.github.io/) accepts research papers of up to four pages, invites negative or surprising results, and lists October 12, 2026 as the submission deadline. Archival status is still listed as TBD. This plan targets the research track, with measured outcomes rather than a position statement.

**Not our claim:** world models are necessary; WAMs are worse than VLAs; generated video causes action errors; Nano versus Edge isolates model size; or one seed establishes general robustness.

## What is already known from our runs

| Evidence | Observation | Boundary |
|---|---|---|
| Six Nano wording episodes on one physical scene | Direct and subject-first left/right endpoint checks passed; both reversed-reference checks failed. One inversion moved the reference bowl first. | One scene/seed; one relation held at reset; initial rendered pixels varied slightly. These are motivating observations, not confirmation. |
| Nine native RoboLab spatial episodes | Two native successes; bin commands produced opposite lateral responses without successful containment. Other failures involved contact, lifting or release. | One episode per task. Mug success has a reset-scene caveat. Native early termination differs from the six wording episodes. |
| Saved model outputs | 209 same-request predicted videos across 15 episodes. | Camera/time correspondence and annotation reliability are not yet qualified. Their existence is not evidence that the forecast correctly represents execution. |

The nine-task score is not the proposed contribution. The more useful observation is that a failed task may still exhibit a meaningful response to language, and equivalent wording can disturb object or relation selection.

## Closest work and the novelty we must earn

- [SG-WAM](https://arxiv.org/abs/2608.08839) already identifies semantic misalignment in WAM predictions and proposes VLM-based guidance. We cannot claim first discovery that WAMs can ignore or misinterpret instructions.
- [SC3-Eval](https://arxiv.org/abs/2606.18610) studies consistent action-conditioned video simulation for policy evaluation, including diagnostic reproduction of failures. A generic prediction-versus-execution comparison is also not new.
- [OpenWAM](https://openwam.stanford.edu/) studies composable prediction/action programs. Our evaluation of released checkpoints does not isolate architecture or information-flow causality.
- [RoboLab](https://arxiv.org/abs/2604.09860) supplies the benchmark environments. Reusing its tasks is infrastructure, not the paper's novelty.

Our proposed distinction is a **paired, goal-preserving language intervention** combined with a **held-out test of whether the policy's own contemporaneous forecast adds diagnostic information**. We expose both cases where prediction and action agree on the wrong object/relation and cases where a visually goal-compatible forecast is not realized. This is a candidate contribution pending a full related-work comparison and new results, not a priority claim.

## Prespecified claims and what would refute them

| Claim under test | Evidence required | Outcome that does not support it |
|---|---|---|
| The forecast adds diagnostic information. **Primary.** | Held-out reduction in Brier error for next-chunk wrong-object/direction events after adding forecast features to the same state/action baseline, with uncertainty and coverage reported. | No improvement, uncertain improvement, or predictions too ambiguous/short to classify. |
| Equivalent wording can change goal following in both prediction and action. **Secondary.** | Paired S-versus-I changes at fixed initial state and goal, replicated across held-out starts; direct-versus-S estimates ordinary rephrasing cost. | Differences vanish with replication, are explained by input mismatch, or only final placement changes without a semantic event. |
| Failure types hidden by the success score are distinguishable. **Descriptive.** | Predeclared object, movement, placement, release and prediction/execution labels applied to all eligible episodes, including unknowns. | Unreliable labels or arbitrary post-hoc categories. |

The primary claim does not require a positive result. Reliable evidence that forecasts are uninformative, overoptimistic, or often uninterpretable would directly address the workshop. It does require enough valid matched observations to distinguish that finding from a broken interface or invalid scene.

## A small set of interpretable outcomes

For an aligned action prefix, assign predicted and executed semantic events as goal-compatible, wrong object/relation, or unresolved. Report the full table, including unresolved events.

| Predicted event | Executed event | Allowed interpretation |
|---|---|---|
| Wrong object/relation | Same wrong object/relation | The visible forecast reflects the behavioral error. It does not prove the forecast caused it. |
| Goal-compatible | Wrong object/relation or failed visible movement | Prediction/execution mismatch; inspect tracking and contact evidence. Do not automatically call this an internal controller defect. |
| Wrong object/relation | Goal-compatible | The forecast is misleading despite suitable execution. |
| Goal-compatible | Goal-compatible | Local semantic agreement; eventual placement may still fail. |
| Unresolved | Any, or vice versa | Insufficient observable evidence, not a scored zero or a success. |

Physical success is separately evaluated from simulator state. A generated image of an object on a box is only visually compatible with support; it is not evidence of support forces.

## Proposed four-page paper

**Title:** When Robot Actions Fail, Does the Predicted Future Explain Why?

**Page 1:** State the question; introduce the two kinds of language intervention; show one real paired example with the instruction, prediction and execution. Explain what existing language-robustness and model-evaluation work already covers.

**Page 2:** Five stock scenes, fourteen goals, three wording forms, paired starts and the forecast/action alignment rule. Define the semantic event labels, the baseline without forecast, and the held-out comparison. A compact scene/prompt panel replaces a long benchmark catalog.

**Page 3:** Primary forecast-utility result with coverage and confidence intervals; S-versus-I effects on predicted and executed events; native and standardized physical success as separate supporting measurements.

**Page 4:** Complete prediction/execution outcome table, two representative failure sequences selected by a declared rule, limitations, and the consequence for evaluating world-action models. No unsupported claim that this establishes whether world models are necessary.

Exact prompts, source pins, exclusions, all outcomes and additional videos belong in the public artifact or supplement as permitted by the final submission rules. Do not assume references or appendices are excluded from the four-page limit until the submission instructions confirm it.

### Working abstract: proposal, not a finished-results abstract

A failed robot placement does not reveal whether the robot pursued the wrong goal or failed to carry out the intended movement. World-action models generate future video alongside actions, potentially providing evidence that task success alone cannot offer. We ask whether these predictions help diagnose goal-following failures. We design a paired evaluation on existing RoboLab scenes using two interventions: equivalent descriptions of a fixed goal, and instructions that change the required object, relation, or destination. Predicted object and motion events are compared with the execution of the same action prefix, while physical success is measured separately. The central test measures whether forecast-derived observations add diagnostic value beyond the current state and proposed action trajectory on held-out initial states. Exploratory Nano runs motivate this distinction: directional responses can occur without task completion, and reversed-reference wording can change which object is manipulated. The proposed study tests when an exposed future is informative, misleading, or too ambiguous to interpret, rather than treating video plausibility as evidence of reliable control.

Replace the prospective sentences with measured results only after the registered study is complete.

## Decision before spending cluster time

1. Review [the prompt catalog](SCENES_AND_PROMPTS.md) for semantic equivalence and useful goal changes.
2. Use the existing 209 saved forecasts to qualify time/view correspondence and test the annotation scheme; no new inference is needed for this first step.
3. Run the finite development stage only after its interfaces and physical goals are ready. Freeze metrics, prompt hashes, state manifests and exclusions before confirmation.
4. If the forecast is unavailable or unusable, do not launch a large action-only study and present it as an answer to this question. Keep that limitation explicit and revise the proposed contribution before further collection.

The detailed experiment contract is in [EXPERIMENT_SPEC.md](EXPERIMENT_SPEC.md). No experiment is launched by creating these documents.
