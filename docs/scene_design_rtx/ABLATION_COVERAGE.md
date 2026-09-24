# SGW-01: clean WAM study coverage

**Research plan, 24 September 2026.** Physical qualification of all 87 selected clean layouts is complete; all 522 selected scripted trials passed before the closer-camera revision. Those results remain evidence for unchanged geometry, not new goal trials with the revised views. LAT and DIST use a flat tabletop; only HEIGHT uses raised supports. Model requests and learned-policy episodes are both zero. Model/runtime qualification, physical time maps and analysis remain pending. This plan reports no learned-policy findings and does not authorize the 1,044-cell study.

The paper asks whether equivalent descriptions preserve a WAM's spatial goal, and whether its generated future accurately describes the motion that its actions produce. Prediction must be compared with both execution and a persistence baseline at the same physical time. The study uses **Cosmos3 Nano Policy DROID (N3)** and **DreamZero's official conditional-action path (D1)**.

The [study repository](https://github.com/adeeb10abbas/world-action-model-steerability) contains the [frozen specification](../../experiments/workshops/spatial_grounding_v1/spec/README.md), [18 exact prompt strings](../../experiments/workshops/spatial_grounding_v1/spec/prompts.json), and [planned queue](../../experiments/workshops/spatial_grounding_v1/spec/planned_cells.csv). Planned cells are not completed observations.

## Comparisons and contribution

| Question | Matched comparison | Required output |
|---|---|---|
| Does the requested goal change the placement? | Positive versus negative physical goal within D, C and I | Physical endpoint separation, per-goal success and requested margins |
| Does sentence construction affect behavior? | C minus D at the same goal and layout | Paired success and margin effects |
| Does equivalent reference inversion preserve the goal? | I minus C at the same goal and layout | Primary success effect, margin effect and success/failure transitions |
| Do these effects differ across spatial tasks? | Separate LAT, HEIGHT and DIST analyses for N3 and D1 | Six model-family reports, including side strata |
| Is the generated future informative? | Generated future versus persistence at matching camera and physical horizon | Relative-position error, prediction skill and localization coverage |
| Where do predictions disagree with execution? | Predicted and actual relation at the same horizon | Four agreement categories plus unknown cases and coverage bounds |
| When does a failure become observable? | Pickup, transport, placement, release and terminal stability | Stage timelines, reference motion and first versus final success |

D is direct wording, C is the subject-first relational clause, and I is the equivalent inverted clause. **I−C is the primary matched ablation: instruction wording changes while the physical goal and initial scene state remain identical. C−D is secondary and uses the same matching rule.** C−D changes several wording features, including “Put” versus “Place … so that,” and does not isolate sentence length or syntax alone. I−C measures the specified reformulation, not an internal parsing mechanism.

LAT uses robot-left/right with the cube and bowl directly on the table. DIST compares full three-dimensional Euclidean distance to the bowl and plate, with all three objects directly on the table. Both families require released placement onto the table. Only HEIGHT uses raised supports, for higher/lower placement around the bowl's height.

Removing DIST pedestals is scene cleanup, not a measured support ablation; support presence is not a study factor. The families differ in references, geometry and placement requirements, so comparisons across them cannot identify a pure causal effect of spatial axis or relation type. Their raw success rates do not rank abstract concept difficulty. The contribution is the measured relationship between language effects, generated futures and execution in this controlled setting. It does not identify the causal benefit of world modeling or establish that generated video is an internal plan.

## Frozen sample and scene balance

Each model-layout block contains D+/D−/C+/C−/I+/I− once.

| Stage | Layouts per family | Episodes per model-family | Across two models and three families |
|---|---:|---:|---:|
| Recording pilot | 1 | 6 | 36 |
| Development | 4 | 24 | 144 |
| Confirmation | 24 | 144 | 864 |
| Total | 29 | 174 | **1,044** |

There are **174 six-cell blocks**. Both models receive the same accepted layouts. Pilot and development observations do not enter confirmation estimates. The independent unit is the layout, not a frame, request or repeated condition. DreamZero's fixed effective noise seed is not independent sampling.

Each family now has 29 distinct qualified layouts: one pilot on the seeded right side, **two development layouts per side and twelve confirmation layouts per side**, totaling 14 left and 15 right layouts. Measured side means cube starting y relative to the fixed robot frame for LAT, upper versus lower support y for HEIGHT, and bowl minus plate y for DIST. Testing opposite goals is distinct from balancing the initial arrangement.

The final campaign explicitly reused **14 passing and two rejected candidates** from prior clean scripted checks. Those outcomes were already known when the final execution plan was recorded. New candidate designs and their order were recorded before their new trials. Selection followed the declared order and physical qualification; no layout was chosen by learned-policy success.

Each selected scene independently passed both goals across three resets with the unchanged 450-action scripted controller. Requirements include neutral signed relation within 5 mm; 3 mm / 2 degree reset agreement; at least 30 mm requested goal margin; recorded pickup; detached release; and stable supported placement. Both DIST anchors are monitored, and any reference movement above 5 mm prevents success. Scripted feasibility is separate from learned-policy performance.

The [ready scene registry](../../artifacts/workshops/spatial_grounding_v1/scene_package_20260924/scene-registry.json) binds exact designs, measured captures, candidate identities and six-trial verification receipts. All distinct-layout, measured-side and selection-order requirements were met at **2026-09-24 12:29:07 UTC**. The [completion receipt](../../handoff/physical-scene-completion.json) records 87 selected layouts, eight retained rejected candidates and 205 unused registered candidates deliberately left unrun once quotas were met. Source references can relocate without rewriting original evidence. A ready physical scene package is not a model-study release.

## Prospective camera revision

The registered [`close-oblique-v2-20260924` camera configuration](../../experiments/workshops/spatial_grounding_v1/close_cameras.json) changes both exterior camera poses and focal lengths for all 87 unique layouts. Two elevated oblique cameras on the far side of the table target the task area and look back toward the robot. Each layout uses the same registered cameras across D+/D−/C+/C−/I+/I− and both models. Robot, wrist camera, objects, supports, scoring and the 18 prompts are unchanged.

[Figure 10, PDF page 14, of the TRI LBM paper](https://arxiv.org/pdf/2507.05331#page=14) provides a qualitative reference for elevated tabletop framing. This revision does not replicate the paper's hardware or camera calibration. Its representative task images are not all from the same relative camera. Our camera fit varies with task geometry, so cross-family magnification differences cannot identify concept effects.

Legacy sensor names retain `over_shoulder_left_camera` and `over_shoulder_right_camera`, but these are now far-side views. **Screen-left is not robot-left.** LAT still scores robot-frame +y while frozen prompts do not specify viewpoint. Equivalent reference inversion changes the relational clause rather than the frame; consistent directional reversal can reflect frame choice or relation grounding, which this design does not separate.

The first close-camera prototype was rejected for arm occlusion and remains historical evidence. The revised native checks cover P01 and D01 for LAT, HEIGHT and DIST: **12 resets, 18 hold steps and 90 exact observation/sensor RGB matches**, with all three camera streams advancing together at 15 Hz. Reset poses agreed and timestamps restarted at zero, but separate reset renders were not byte-identical. No goal-qualification trials were repeated and no models were called. Exterior cube and reference objects are visible in the six inspected layouts; the unchanged wrist view still clips references in HEIGHT and DIST.

Offline projection checks cover 174 exterior views across the 87 prior measured geometries, including scored objects/supports, both goal destinations and a 0.12 m lift envelope, with a minimum boundary margin of 38.98 native pixels. These projections are not visibility proof during arbitrary arm motion. On the six native layouts, projected cube width after proportional 320×180 resizing is 28.87 px in LAT, 20.52 px in HEIGHT and 15.17–15.62 px in DIST; these are framing measurements, not model performance. Offline destination materialization passed for 87 revised layouts and 1,044 cell bindings. Offline image preprocessing also passed on six native inputs and one synthetic input without model requests. Full live model transforms, generated-future time maps and semantic-label validation remain separate gates. See the [camera alignment record](../CAMERA_ALIGNMENT.md) and [new materialization receipt](../../handoff/close-camera-materialization.json).

The paper's three scene panels are unmodified native P01 reset images from the revised left exterior sensor, with no diagnostic overlays. The original 522 passing trials remain attached to their original camera/geometry receipts.

## Generated future versus execution and persistence

A generated frame is scored only when its physical target time, source camera and preprocessing are documented, and the time lies inside the action prefix executed before replanning. N3 executes up to 32 actions per request; D1 executes eight. Account for context frames, cropping and packed views. Presentation FPS is not a time map, and the availability of a camera does not establish which image the model consumed. Record actual policy inputs and corresponding continuous simulator views.

Use development data to select the largest supported positive horizon H separately for each model, then freeze H across that model's forms and families. For n requests, select indices `floor[0.25(n−1)]` and `floor[0.75(n−1)]`, deduplicating if necessary. Select from metadata rather than image clarity. Retain first requests for matched-input checks; later requests have different closed-loop observations and are not prompt-only comparisons.

For target-anchor relative image coordinate u, normalized by the image diagonal, compute:

- Prediction error: `||u_pred(H) − u_actual(H)||`.
- Persistence error: `||u_current − u_actual(H)||`.
- Prediction skill: persistence error minus prediction error; positive values favor prediction.

Retain cube and anchor localization separately, including both DIST anchors. Two blinded raters locate centers; discrepancies above 0.02 image diagonals require adjudication. Average selected requests within an episode, then paired conditions within a layout. The maximum initial confirmation workload is 1,728 selected requests and 10,368 frame judgments before adjudication. Continuous accuracy is conditional on valid localization, with coverage reported for every condition.

World-height and Euclidean-distance signs cannot be inferred automatically from image-up or pixel distance. Validate each family/view labeling procedure using **50 offline reference images per family**: 20 balanced unambiguous development states, 20 balanced unambiguous held-out states, and 10 ambiguous/occluded variants. Require at least 19/20 correct held-out signs; unknown labels are not correct, and genuinely ambiguous states must not receive forced signs. Changed views, crops or procedures require their own validation.

At the matching H, report both consistent, prediction-only consistent, execution-only consistent, both inconsistent, and unknown. Forecast H is compared with execution H, not task success at action 450. Freeze stationary/moving handling at 0.02 image diagonals. Unknown forecasts remain unavailable, with binary missingness bounds and condition-specific denominators. A failed semantic-label or time-map check limits prediction claims without erasing valid execution evidence.

## Physical endpoints and statistical limits

With signed relation r and goal sign q, requested margin is `M = q*r`. The corrected compiler reports **physical separation `r(+) − r(−) = M(+) + M(−)` in metres**, separately from success asymmetry `S(+) − S(−)`. Placements at +0.13 m and −0.13 m have 0.26 m physical separation even when both succeed and success asymmetry is zero. Valid manipulation failures retain observed endpoints; missing or censored endpoints have unavailable separation.

Report I−C primary and C−D secondary effects on success and margin, each goal separately, transitions and stage diagnostics. Use 20,000 layout-cluster bootstrap resamples, keeping all six conditions together, and 100,000 fixed-seed paired sign flips with Holm correction over the six primary model-family tests. State the sign-flip exchangeability assumption. Report `n_complete/24` and missing/censored cells for each confirmation branch; a nonempty subset is not completed confirmation.

Safety terminations count as unsuccessful in the all-trial binary endpoint, but continuous terminal margins remain censored. Conditional continuous estimates and full-cohort bounds must be identified. Unknown binary prediction labels receive zero/one bounds. Equivalence requires 90% paired intervals inside both ±0.10 success probability and ±0.02 m margin, including missingness and censoring. Nonsignificance is not equivalence, and 24 layouts per family does not guarantee power for small effects. Descriptive bootstrap intervals cannot establish equivalence on their own. All-zero or otherwise zero-variance layout contrasts are inconclusive; a positive equivalence claim requires a valid finite-sample procedure fixed before confirmation. Follow the [prospective equivalence safeguard](../EQUIVALENCE_ANALYSIS_NOTE.md).

## Remaining work before results can support the paper

1. **Verify the destination scene handoff.** Regenerate the selected scenes against the pinned assets and exact qualified inputs, retaining original evidence and physical fixture identities. Completed source-scene qualification does not qualify a relocated runtime.
2. **Qualify both model interfaces and recording.** Verify resets, actual model inputs, decoded futures, action prefixes and physical time maps for N3 and D1. The pilot validates measurement; development fixes H and analysis choices before confirmation.
3. **Complete prediction annotation.** Implement and verify coordinate localization, rater disagreement/adjudication, persistence skill and the held-out semantic-label procedure. Existing categorical annotation records alone do not complete these outputs.
4. **Complete the analysis export.** Produce all six model-family coverage rows, language-effect tables, physical separation, prediction/persistence skill, disagreement, and side/stage diagnostics. The physical-separation correction is implemented; full coverage accounting, prediction metrics and the two-endpoint equivalence calculation still need completed outputs.
5. **Verify the report before confirmation.** Use a labeled engineering fixture containing success, valid manipulation failure, anchor disturbance, safety censoring, technical missingness and unknown forecasts. These software checks are not observations. Freeze stationary/moving, first/later-request and alternative-supported-H sensitivity analyses before confirmation.

The study remains limited to D/C/I × LAT/HEIGHT/DIST × N3/D1 in the clean setting. The planned learned-policy run starts only after the separate launch decision. The eventual paper must report unavailable measurements explicitly, including the possibility that generated futures add little diagnostic value beyond execution scores.
