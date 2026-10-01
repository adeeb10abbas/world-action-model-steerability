# Forecast appendix evidence and graphics

This is a separate revision draft. It does not modify main.tex, released results, any Overleaf document, or experiment workers. No new policy/robot/VLM runs were performed.

## Strongest defensible insight

Exporting a future is not the same as obtaining an explanation. Diagnostic use requires reliable semantic readout, matching time/view/action context, and incremental value over a realistic baseline. Existing automated readout did not show that value. Poor agreement prevents concluding that the underlying videos carry none.

## Authoritative local sources

All paths below are relative to the repo root.

- `docs/robolab-workshop-20260926/CLUSTER_EXECUTION_SPEC.md`, sections 6-8: window selection, labels, primary diagnostic, controls, weighting, eight state-held-out folds.
- `docs/robolab-workshop-20260926/EXECUTION_RECORD.md`, A7-A11 and A11 results note: common rendered view, original human gate, post-result VLM substitution, model identifiers, blinding, adjudication, labeler disagreement, raw attempts retained.
- `docs/robolab-workshop-20260926/RESULTS_REVIEW_20260927.md`, section4: independent reproduction; conditional null; missing timestamp/export documentation; A3 mislabeled in original report; A4 100 seeds not2; event detector concern.
- `artifacts/robolab_workshop_20260926/results_vlm/diagnostic_utility.csv`: exact pooled and model Brier results and controls.
- `artifacts/robolab_workshop_20260926/results_vlm/results.json`: pooled conditional confidence interval, per-model diagnostics, control values, event matrix, permutation summary.
- `artifacts/robolab_workshop_20260926/results_vlm/vlm_agreement.json`: 864 primary windows, 862 extra first-request windows, raw agreement and kappa.
- `artifacts/robolab_workshop_20260926/analysis/forecast_labels_vlm.jsonl`: 864 adjudicated/unblinded label rows. Direct count gives 673 up-only, relation counts goal39/alternative99/not-goal608/unknown118, moving-object counts mover540/reference247/other15/multiple7/none54/unknown1.
- `artifacts/robolab_workshop_20260926/analysis/conf_features.jsonl`: 864 episode features. Direct count gives33 primary contradictory-release events and14 primary wrong-object events, no overlap. No primary positive event is request0; the review's request0 warnings refer to the separate first-request analyses, not all47 primary events.
- `artifacts/robolab_workshop_20260926/annotation/labels_vlm_a.jsonl`, `labels_vlm_b.jsonl`, and `labels_vlm_adjudicated.jsonl`: preserved independent and adjudicated observable labels, plus corresponding `_raw.jsonl` files.
- `artifacts/robolab_workshop_20260926/annotation/build_receipt.json`:864episodes/1726packets.
- `experiments/robolab_workshop/analyze.py`: fixed feature lists, CV, conditional bootstrap, no-motion synthetic A3, and100A4seeds.
- `experiments/robolab_workshop/worker.py:168`: uniform timestamp assignment k/15s, which must not itself be mistaken for model-source verification.

## Numbers deliberately omitted or qualified

- Original RESULTS.md achievement-stratum forecast-success counts use the invalid old stratum. Do not quote 46/203 versus150/425 as current; recalculation from the frozen goal status is required.
- A4's [8403,8502] stores seed endpoints, not two seeds. Correct count100.
- A4 percentile range is a permutation distribution, not E1's bootstrap CI; no saved p-value.
- A3 is synthetic no-motion/current-goal information, not an equivalently annotated persistence-image clip.
- A2 “goal” row is video-observable goal relation; “goal-consistent interaction” column is an execution-stage label. They are different constructs, so this is not a confusion matrix for common ground truth.
- “673 forecasts show upward motion” overstates ground truth; say the automated readout labels673 as upward only.
- “The null is not a coverage failure” overstates validity: decoded coverage is complete but semantic coverage is weak and mapping evidence remains incomplete.
- No verified forecast-only montage frames are present locally. Avoid copying execution montages and calling them predictions.

## Recommended graphics

1. `forecast_measurement_diagnostics.pdf` / `.png` (derived directly from released JSON/JSONL; generated for this revision): three panels showing relation-readout categories, inter-labeler agreement, and Brier change with pooled interval and descriptive per-model points. Caption must say categories are VLM assignments, agreement is not accuracy, and model intervals unavailable.
2. Existing `artifacts/robolab_workshop_20260926/results_vlm/fig_forecast_utility.pdf` can be reused, but check caption/labels for original A3/A4 terminology before publication.
3. A prediction/execution montage would require the actual same-request prediction clips currently on server, with initial scene, generated wrist/exterior sequence, corresponding execution, timestamps and original independent VLM labels. Select by an explicit illustrative rule and include a disagreement example; not only a visually favorable pair. No server work has been performed here.
4. Existing main-paper `paper/robolab_spatial_2026/figures/execution_examples.pdf` has only execution evidence. Its second row can be moved to the appendix independently of this section.
