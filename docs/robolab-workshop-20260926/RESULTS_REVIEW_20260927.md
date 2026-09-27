# Review of the completed RoboLab results

Reviewed September 27, 2026, against branch commit `cf9c9ce`. This document reviews the published artifacts; it does not replace the recorded outcomes or amend the analysis.

**Assessment:** There is a reproducible wording effect across three models. The main forecast experiment has not demonstrated incremental diagnostic value, but the noisy automated measurement prevents a strong conclusion about the information in the videos themselves. Two reporting/scoring issues should be fixed before circulating the draft. Neither requires another robot study.

## What was checked

- 864 unique confirmation episodes, 288 each for Nano, Cosmos Edge and FLUX; four scenes and 32 physical starts. All 96 model/state blocks are complete. The 144 bin-scene cells were omitted before confirmation in amendment A1.
- All 910 committed COMPLETE markers, including 46 development episodes, match the SHA256 of their committed result file.
- Confirmation receipts report 432,000 executed actions and 13,968 saved futures from 13,968 requests.
- All confirmation initial-state receipts agree with their frozen state and first-observation hashes; reported numerical restore difference is zero throughout.
- The pooled wording calculations were rerun from `analysis/conf_features.jsonl`. Their estimates and corrected p-values reproduce.
- A separate NumPy implementation of the fixed logistic diagnostic reproduced the E1 null within solver tolerance (approximately −0.00071 versus the saved −0.00073 Brier difference). Feature extraction and folds show no direct future-outcome leakage.

Raw tick logs, images and videos remain on the cluster. This review verifies the committed summaries, receipts and code; it does not independently replay or visually validate every physical trajectory or generated video.

## 1. The wording result is supported

The prespecified S−I contrast is **+12.15 percentage points** for the standard wording over equivalent inverted-reference wording: 288 pairs, 45 standard-only versus 14 inverted-only successes, Holm-corrected p=0.000120. The saved state-bootstrap 95% interval is [8.6,15.4] points. Ordinary rephrasing D−S is +4.08 points and not significant after correction (p=0.0890).

As a **post-hoc sensitivity check**, substituting end-of-episode stable success preserves the S−I effect: **+11.20 points**, interval [7.21,15.02], Holm p=0.00510. D−S remains inconclusive (+3.21 points, p=0.286). These checks support the wording finding but do not replace the prespecified endpoint or become newly “confirmatory.”

## 2. Fix achievement/maintenance labels from the frozen registry

The released `states/accepted_states.json` says S1-R, S3-R and S4-L are already satisfied for every accepted start. This gives **72 maintenance and 216 achievement episodes per model**. Published results instead count 62, 52 and 58 maintenance episodes respectively.

There are 44 misclassified episodes, and 36 of the 288 within-model/state/goal triplets disagree about the status of their shared initial goal. In all 44 cases, the relation is true at time zero, the full support/contact-dependent goal becomes true at 1/15 s, and a stable dwell completes around one second. They were incorrectly credited as achievements.

The likely cause is contact state that has not refreshed after restoring the simulator: `sim_env.py:175–196` restores/forwards/renders, `worker.py:95–102` immediately records tick zero, and `scoring.py:109–124` assigns the stratum from that tick's contact-dependent goal. The stratum error is demonstrated by the receipts; the precise contact-buffer mechanism still needs inspection of the raw tick logs.

Use the **frozen, pre-outcome goal status** for the stratum and propagate the correction to all achievement tables, paired strata and exploratory forecast-success comparisons. Do not change physical episodes or reclassify starts based on policy performance.

| Model | Published achievement success | Corrected achievement, ever stable ≥1 s | Corrected achievement, stable at end |
|---|---:|---:|---:|
| Nano | 80/226 (35.4%) | **70/216 (32.4%)** | 47/216 (21.8%) |
| Cosmos Edge | 41/236 (17.4%) | **21/216 (9.7%)** | 13/216 (6.0%) |
| FLUX | 90/230 (39.1%) | **76/216 (35.2%)** | 34/216 (15.7%) |

The pooled S−I/D−S stable-ever contrasts are unaffected: the recorded successes do not change, only stratum membership does. Keep both the original and corrected derived tables with a correction note.

## 3. “Reached a stable placement” is different from “finished successfully”

The registered endpoint is a one-second stable dwell **at any point**. This is implemented in `scoring.py:90–98` and is not a protocol violation. It is nevertheless easy to overstate in prose.

| Model | Goal stable ≥1 s at some point | Goal stable at episode end |
|---|---:|---:|
| Nano | 142/288 (49.3%) | 77/288 (26.7%) |
| Cosmos Edge | 93/288 (32.3%) | 45/288 (15.6%) |
| FLUX | 148/288 (51.4%) | 69/288 (24.0%) |

**192 of the 383 stable-ever successes are not stable at the end.** Among the 172 episodes currently labeled maintenance, only 76 remain stable at the end. The draft's statement that all 172 “stayed satisfied” is therefore false. Report both endpoints, name the registered endpoint precisely, and avoid ranking models as overall task completers using stable-ever alone.

## 4. Keep the forecast conclusion conditional on its measurement

Saved E1: Δ Brier = **−0.000732**, conditional interval [−0.001771,+0.000163], with 47 positive events in 864 windows. This does not support the proposed diagnostic improvement. It also does not prove that forecast videos contain no additional information.

The two automated labelers agree poorly: κ=.40 for moving object, .11 for direction and .08 for relation; only about 6% agree on every field. The human-to-VLM substitution was made after behavioral outcomes were read, and one labeler also adjudicated. Disclose these facts prominently and describe E1 as the **original primary question evaluated using a post-result annotation amendment**. Do not silently relabel it a secondary question because its result is null.

Recommended wording:

> Under the automated annotation procedure used here, forecast-derived labels did not improve held-out event prediction beyond privileged state and proposed actions. Low label agreement prevents separating an uninformative forecast from an unreliable readout of that forecast.

Further checks using existing recordings:

1. **Semantic coverage:** 864 decoded clips is export coverage, not interpretable coverage. There are 118 unknown relations and 673 `up_only` directions. Add the planned jointly interpretable analysis with a fixed definition; do not select examples for favorable results.
2. **A3:** `analyze.py:67–70` synthesizes no-motion labels and supplies a privileged current goal flag. This is not the promised persistence image labeled by the same procedure. Rename the implemented control accurately or label the saved current-frame persistence clips with the unchanged pipeline.
3. **A4:** the “2 seeds” entry in RESULTS.md misreads range endpoints. Frozen code iterates 8403–8502, **100 seeds**; JSON stores `[8403,8502]`. Its percentile interval describes the permutation distribution, not the same confidence interval as E1. Avoid implying an additional formal test that was not performed.
4. **Temporal correspondence:** `worker.py:168–169` assigns frame k to k/15 s for every model. FLUX capture does reuse the same action/video sample, which is appropriate. Attach the missing source-derived temporal/view mapping and action-preservation qualification receipts; absence in Git is not proof the mapping is wrong.
5. **Event validity:** 33 of 47 primary positives are contradictory-release events, versus 14 wrong-object events. The release detector accepts a contact-to-detached transition without requiring substantive prior manipulation. Request-zero examples trigger immediately after initial contact loss. Inspect a deterministic set of primary positive events in raw recordings, particularly near reset, before calling all of them wrong-goal decisions.
6. **Human/tracker validation:** select a modest, explicitly exploratory blinded subset of the existing packets, stratified by model and relation visibility without choosing by desired outcome. Estimate automated-label error and reassess whether the current readout can answer E1. Do not launch more robot episodes before resolving this measurement issue.

## 5. Other draft corrections

- The native-first-hit comparison applies to 504 native-matched episodes and their 126 stable successes. Another 257 study-goal successes have no matched native checker. Qualify the “every stable success” statement accordingly.
- D is native wording **where the catalog marks it native**; added goals are not all native RoboLab instructions.
- State counts are eight starts **per scene**, 32 physical starts overall. Repeated forms and models are not extra independent environments.

## Suggested order of work

1. Correct strata from the frozen registry, rebuild affected tables and add terminal-stability reporting.
2. Correct the draft's success, coverage, A3 and A4 descriptions. Preserve the original primary question and disclose deviations.
3. Attach the forecast timing/export receipts and inspect primary positive-event clips.
4. Validate forecast labels on a bounded subset of existing recordings, then decide whether E1 supports a useful measured negative result or remains inconclusive.

There is enough behavioral evidence to develop a serious workshop submission. Its strongest supported empirical result is the sensitivity to equivalent spatial wording. The forecast component becomes convincing through better measurement and precise claims, not through another large scene or rollout campaign.
