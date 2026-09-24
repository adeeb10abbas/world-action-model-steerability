# SGW-01: clean WAM study coverage

**Research plan, 24 September 2026.** The clean LAT, HEIGHT and DIST scene generators are implemented. LAT and DIST use a flat tabletop; only HEIGHT uses raised supports. The paper's three illustrative examples each have six independently verified passing scripted trials. Qualification of the final 87-layout set is still running and is not complete. This plan reports no learned-policy findings and does not authorize the 1,044-cell study.

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

Each family requires a seeded pilot side, **two development layouts per side and twelve confirmation layouts per side**. Measured side means cube starting y relative to the fixed robot frame for LAT, upper versus lower support y for HEIGHT, and bowl minus plate y for DIST. Testing opposite goals is distinct from balancing the initial arrangement. Candidate lists and selection order are declared before outcomes; no layout is chosen by model success. A finite campaign retains its failed and incomplete candidates.

Each selected scene must independently pass both goals across three resets with the unchanged 450-action scripted controller. Requirements include neutral signed relation within 5 mm; 3 mm / 2 degree reset agreement; at least 30 mm requested goal margin; recorded pickup; detached release; and stable supported placement. Both DIST anchors are monitored, and any reference movement above 5 mm prevents success. Scripted feasibility is separate from learned-policy performance.

The [scene package builder](../../tools/build_scene_package.py) binds exact designs, measured captures, candidate identities and six-trial verification receipts. It records rejected and pending candidates, checks distinct geometry and measured side quotas, and reports partial coverage until all requirements hold. Source references can relocate without rewriting original evidence. A ready physical scene package is not a model-study release.

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

Safety terminations count as unsuccessful in the all-trial binary endpoint, but continuous terminal margins remain censored. Conditional continuous estimates and full-cohort bounds must be identified. Unknown binary prediction labels receive zero/one bounds. Equivalence requires 90% paired intervals inside both ±0.10 success probability and ±0.02 m margin, including missingness and censoring. Nonsignificance is not equivalence, and 24 layouts per family does not guarantee power for small effects.

## Remaining work before results can support the paper

1. **Finish physical qualification and freeze the clean registry.** Complete all three families' distinct layouts and side quotas, preserving every rejection and partial attempt. Verify portable scene regeneration against the pinned runtime and measured geometry.
2. **Qualify both model interfaces and recording.** Verify resets, actual model inputs, decoded futures, action prefixes and physical time maps for N3 and D1. The pilot validates measurement; development fixes H and analysis choices before confirmation.
3. **Complete prediction annotation.** Implement and verify coordinate localization, rater disagreement/adjudication, persistence skill and the held-out semantic-label procedure. Existing categorical annotation records alone do not complete these outputs.
4. **Complete the analysis export.** Produce all six model-family coverage rows, language-effect tables, physical separation, prediction/persistence skill, disagreement, and side/stage diagnostics. The physical-separation correction is implemented; full coverage accounting, prediction metrics and the two-endpoint equivalence calculation still need completed outputs.
5. **Verify the report before confirmation.** Use a labeled engineering fixture containing success, valid manipulation failure, anchor disturbance, safety censoring, technical missingness and unknown forecasts. These software checks are not observations. Freeze stationary/moving, first/later-request and alternative-supported-H sensitivity analyses before confirmation.

The study remains limited to D/C/I × LAT/HEIGHT/DIST × N3/D1 in the clean setting. The planned learned-policy run starts only after the separate launch decision. The eventual paper must report unavailable measurements explicitly, including the possibility that generated futures add little diagnostic value beyond execution scores.
