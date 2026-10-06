# RQA-20261006 candidate compact table (not inserted into any manuscript)

Run `r1-20261006`; initial-state bank; headline pool S1/S3/S4 (24 starts, 10 goals). Estimates are macro-weighted (items within start×goal cell → starts → goals → scenes); 95% intervals: 10,000 percentile bootstrap replicates (seed 6106) resampling physical starts within scene, conditional on the four fixed scenes and prompt templates. Text-only B is a finite set (counts, no interval). Answerability labels are provisional (no human review). Rows are distinct reasoner weights; tensor-identical readouts share one row.

| Readout (distinct weights) | B tuple correct, text-only (finite) / image acc. | A both-correct | C TF acc. | C RF acc. | C TF−RF gap, pp [95% CI] | C both-correct | C balanced acc. (TF+RF) | Coverage (delivered / valid, answerable C pairs) |
|---|---|---|---|---|---|---|---|---|
| Cosmos3-Edge reasoner = E3 policy reasoner ≡ Cosmos3-Edge base reasoner | TF 6/10, RF 0/10 / 2.4% | 67.0% | 70.5% | 69.4% | +1.0 [+0.0, +3.1] | 69.4% | 50.7% | 2072/1650 of 2072; 78 C pairs |
| Qwen3-VL-4B-Instruct (FLUX shared encoder; auxiliary) | TF 10/10, RF 3/10 / 71.3% | 37.2% | 69.4% | 69.4% | +0.0 [+0.0, +0.0] | 69.4% | 50.0% | 2072/2052 of 2072; 78 C pairs |
| Cosmos3-Nano base reasoner | TF 10/10, RF 8/10 / 84.5% | 41.5% | 60.5% | 69.4% | -9.0 [-16.3, -1.7] | 51.0% | 53.1% | 2072/2072 of 2072; 78 C pairs |
| Qwen3-VL-8B-Instruct = N3 policy reasoner ≡ Qwen3-VL-8B-Instruct (upstream) | TF 10/10, RF 10/10 / 87.0% | 43.3% | 69.4% | 69.4% | +0.0 [+0.0, +0.0] | 69.4% | 50.0% | 2072/2072 of 2072; 78 C pairs |

Read C against the label prior: answering “no” to every answerable C item scores 69.4% here, and balanced accuracy 50% is chance. Full metrics, controls and caveats: TABLES.md and INTERPRETATION.md.
