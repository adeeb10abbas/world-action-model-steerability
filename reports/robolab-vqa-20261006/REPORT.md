# RoboLab VQA diagnostic — separate results report

**Study:** RQA-20261006 · **Runs:** V1 [`r1-20261006`](runs/r1-20261006/REPORT.md) (design v1.0, October 6, 2026) and
V2 [`r2-final-20261007`](runs/r2-final-20261007/REPORT.md) (design v2.0, the final bounded follow-up, executed
2026-10-07 UTC)

**Status: V1 COMPLETE, PROVISIONAL ANSWERABILITY · V2 COMPLETE, PARTIALLY MACHINE-REVIEWED, PROVISIONAL VISUAL CONCLUSIONS.**
The study is closed after V2; no V3 is authorized. Nothing here has been inserted into any manuscript.

## V2 update: V1 → V2 comparison (added 2026-10-07)

V2 re-queried the three distinct readouts on the same saved S1/S3/S4 observations and exact instructions:

- N3-policy: Nano reasoner, equal to Qwen3-VL-8B-Instruct.
- E3-policy: Edge reasoner, equal to the Edge base reasoner.
- F3-qwen3vl4b: FLUX's shared encoder, equal to Qwen3-VL-4B-Instruct. Its image tests are auxiliary.

It ran 6,552 of 6,552 evaluation queries, all delivered and valid, with 0 retries. V2 was designed after reading V1
results. It is a follow-up diagnostic, not an independent replication, and it does not replace V1's primary
endpoint.

| Measurement | V1 (`r1-20261006`) | V2 (`r2-final-20261007`) | What the change supports |
|---|---|---|---|
| Instruction-readout protocol | B: free generation, strict JSON parser | B2: schema-constrained JSON (xgrammar) on the same payload, plus a text/header/image factorial (T/H/I/IH) | Differences between rows are decoding-protocol comparisons |
| Edge reasoner (E3) | Text TF 6/10, RF 0/10; image tuple 2.4%; 39 of 414 S1/S3/S4 responses strict-valid | Text 18/30 (DIR 6, TF 8, RF 4); image + header 34.0% [31.7, 36.5]; images lower accuracy (I − T −26.9 pp) | Format was a large barrier, but instruction difficulty remains under the assisted readout |
| Nano reasoner (N3) | Text 10/10 TF and RF; image RF 61.1% vs TF 100%; images and camera text always presented together | Text 30/30 (T and H). Image RF 93.1% (I) and 89.9% (IH). IH − H RF −10.1 pp [−14.6, −5.2]; H − T 0 discordant; IH − I RF −3.1 [−8.0, +1.7] | RF converse errors are associated with adding images, not camera text, and sit in 2 of 10 RF instructions |
| FLUX encoder (F3) | Text RF 3/10, TF 10/10; image RF 36.1% | Text RF 4/10 (T, all converse), TF 10/10; image RF 41.7% (auxiliary) | Language-path RF misreading persists under constrained decoding |
| Combined / current-state question (C → C2) | Uninformative: constant "no"; balanced accuracy 50.0–50.7% (53.1% N3-base) | Uninformative: constant "does not match" under both answer-code orders; balanced accuracy 48.5–50.1%; truth-changing pairs ≤ 1/11 | The null persists after fixing codes and wording, and the bias is semantic. V1's primary diagnostic remains uninformative |
| Visual answerability | Automated visibility pre-check; no review | Blinded machine review of 36 of 72 view sets (120 of 240 items). 7 of 12 reviewer agents failed without forms, and 1 form was excluded for evaluated-model use. Reviewed initial items: all answerable. Reviewed secondary items: 27 of 81 answerable. No answerable item contradicted geometry. Reviewed-mask C2 balanced accuracy 48.3–50.0% | Still provisional and partial, with no human review |
| Scene question (A) | Accuracy 50.5–71.4% on the initial bank across four readouts; converse-question gaps of mixed sign | No new inference. R1 answers were rescored on the machine-reviewed masks ([V2 TABLES §8](runs/r2-final-20261007/TABLES.md)) | Mask-only change |

The robot wording effect remains the central result: TF − RF stable-ever +14.6 pp (N3), +8.1 (E3) and +13.8 (F3).
V2's component-level asymmetries share its direction in a QA interface only. They are no evidence about the
policies' internal computation or about causes of action failures.

V2 documents:

- [V2 report](runs/r2-final-20261007/REPORT.md)
- [V2 interpretation](runs/r2-final-20261007/INTERPRETATION.md)
- [V2 paper table](runs/r2-final-20261007/PAPER_TABLE.md)
- [V2 tables](runs/r2-final-20261007/TABLES.md)
- [V2 specification](../../docs/robolab-vqa-20261006/v2-final/FINAL_EXECUTION_SPEC.md)
- [V2 implementation record](../../docs/robolab-vqa-20261006/v2-final/IMPLEMENTATION_RECORD_V2.md)
- [Exact model-input images used by V1 and V2](../../artifacts/robolab_vqa_20261006/model_input_images/README.md) (300 PNG files, SHA256-verified)

The V1 report text below is unchanged.

---

**V1 (`r1-20261006`) status: COMPLETE, PROVISIONAL ANSWERABILITY.** All 8,288 evaluation calls of the four distinct readouts were
delivered (0 infrastructure-missing). Gold labels come from saved simulator geometry with an automated visibility
pre-check; **no human answerability review was performed**, so every result below is provisional. Nothing here has been
inserted into any manuscript.

**Purpose:** preserve the complete diagnostic results independently of the workshop manuscript, then let the authors
select supported findings for later inclusion.

[Locked guide](../../docs/robolab-vqa-20261006/EXPERIMENT_GUIDE.md) · [Implementation record](../../docs/robolab-vqa-20261006/IMPLEMENTATION_RECORD.md) ·
[Coverage audit](../../docs/robolab-vqa-20261006/DECISIONS_AND_COVERAGE.md) · [Run index](RUN_INDEX.json) ·
[Candidate findings](CANDIDATE_FINDINGS.csv) · [Run report](runs/r1-20261006/REPORT.md) ·
[All generated tables](runs/r1-20261006/TABLES.md) · [Interpretation](runs/r1-20261006/INTERPRETATION.md) ·
[Compact paper table](runs/r1-20261006/PAPER_TABLE.md)

## 1. Executive findings

Four distinct reasoner weight sets were evaluated. Two planned base/policy comparisons collapsed because the
executed policies' reasoners are **unadapted**:

- **R1 Qwen3-VL-8B-Instruct** is the executed N3 (Cosmos3-Nano-Policy-DROID) reasoner. All 750 reasoner tensors are
  byte-identical; the upstream lane shares this result.
- **R2 Cosmos3-Nano base reasoner** differs from R1 in 708 of 750 tensors. It is not the parent of the executed policy's
  reasoner.
- **R3 Cosmos3-Edge reasoner** is both the executed E3 policy's reasoner and the Edge base reasoner (identical loaded
  parameters).
- **R4 Qwen3-VL-4B-Instruct** is byte-identical to FLUX 3 Action's frozen shared encoder. It is an auxiliary control,
  not FLUX policy VQA.

| Question | Finding (initial bank, S1/S3/S4 unless stated) | Supporting artifact | Limitation |
|---|---|---|---|
| Can the readout identify current spatial relations under reference reversal? (A) | Weak: accuracy 51.1% (R1, yes-biased, balanced 61.6%), 50.5% (R2), 52.7% (R4); R3 71.4% (balanced 68.4%). Converse-question (target − reference subject) gaps: −11.6 pp [−16.3, −6.6] (R1), +7.4 [+0.6, +13.7] (R2), −4.5 [−10.4, +1.0] (R3), −6.7 [−12.5, −0.6] (R4); signs are inconsistent across readouts | [TABLES §A](runs/r1-20261006/TABLES.md) | Calibration legend added (disclosed); provisional labels |
| Can it recover the requested target, reference and relation under DIR/TF/RF wording? (B) | Targets and references are recovered. With images, relation: TF 100% for R1, R2 and R4, but RF only 61.1% (R1), 53.5% (R2), 36.1% (R4). Lateral/front-behind RF errors are almost all the **converse** relation. Text-only (finite, S1/S3/S4): TF 10/10 and RF 10/10, 8/10, 3/10. Every discordant TF/RF text pair was TF-correct and RF-wrong | [TABLES §B](runs/r1-20261006/TABLES.md), [b_error_taxonomy.csv](runs/r1-20261006/results/b_error_taxonomy.csv) | R3 B mostly invalid format (vocabulary non-compliance); start intervals degenerate (answers constant across starts) |
| Can it combine the instruction with the image to judge the requested arrangement? (C, primary) | **Uninformative.** R1, R3 and R4 answered “no” to essentially every C query, with or without images. Accuracy = constant-“no” prior (69.4%); balanced accuracy 50.0–50.7%. TF − RF: 0.0 pp (R1, R4), +1.0 [+0.0, +3.1] (R3), −9.0 [−16.3, −1.7] (R2, balanced accuracy 53.1%) | [Fig. 1](runs/r1-20261006/figures/fig1_primary_C_TF_RF.png), [TABLES §C](runs/r1-20261006/TABLES.md) | Floor/constant-answer null; not evidence of wording robustness |
| How do these patterns compare with the existing policy wording effect? | Policy TF − RF stable-ever: N3 +14.6 pp [+8.1, +21.1], E3 +8.1 [+3.6, +12.8], F3 +13.8 [+7.6, +20.1]. The readouts show the same **direction** only in instruction interpretation (B), and only for converse RF phrasing. A clause-placement control without converse words produced no B errors | [Fig. 1](runs/r1-20261006/figures/fig1_primary_C_TF_RF.png), [INTERPRETATION](runs/r1-20261006/INTERPRETATION.md) | QA is not direct access to the policy's latent decision; no causal claim |

## 2. Run identity and evidence status

| Field | Value |
|---|---|
| Run ID / UTC start and end | `r1-20261006` · fixtures 22:09–22:13 · bank inference 22:15:13–22:24:42 · analysis 22:27 (2026-10-06) |
| Data-release SHA256 / protocol version | release content `1e691df6b85576e0d75925cc7902a1f4e303267098483a81726f6ff63cda3046` (`release.json` `ccccd81e…`) / 1.0 |
| Implementation commit / analysis commit | `4d2605c` (implementation); `5d7ef7b` (frozen release + runner used for inference, pushed before any evaluation query); `6d4babf` (qualification amendment, analysis code); report/figure commit in [RUN_INDEX.json](RUN_INDEX.json) |
| Checkpoint and processor manifest | [model_eligibility.csv](runs/r1-20261006/model_eligibility.csv), [lanes.json](runs/r1-20261006/lanes.json), [eligibility_audit.json](../../artifacts/robolab_vqa_20261006/eligibility/eligibility_audit.json) |
| Actual launch and analysis commands / environment receipt | [COMPLETION_RECEIPT.json](runs/r1-20261006/COMPLETION_RECEIPT.json), [run_receipts_summary.json](runs/r1-20261006/run_receipts_summary.json) (vLLM 0.26.0, torch 2.11.0+cu130, transformers 5.14.1, NVIDIA B200) |
| Human answerability audit | **Not performed.** Audit sheets and review template prepared ([audit_manifest.json](../../artifacts/robolab_vqa_20261006/release_r1/audit/audit_manifest.json)); results provisional |
| Full compact results and coverage tables | [results/](runs/r1-20261006/results/) (`results.json`, `metrics_long.csv`, `coverage.csv`, `breakdown.csv`, `label_variation.csv`, `action_join_counts.csv`, `b_error_taxonomy.csv`, `scored_rows.csv.gz`) |
| Durable raw-response/media artifact index and hashes | [artifact_index.json](runs/r1-20261006/artifact_index.json) (120 items, 225 MB on PVC `211247-prod-pvc`, `/data/users/ali/rqa-20261006`) |
| Actual GPU time / elapsed time | Bank: 0.57 B200 GPU-hours (431–569 s per lane, four GPUs in parallel); fixtures 696 s total; wall time from first GPU pod to deletion ≈ 35 min |
| Deviations and amendments | [Implementation record](../../docs/robolab-vqa-20261006/IMPLEMENTATION_RECORD.md) §3–§6 and Amendment A1 (all before bank queries); §10 below |

## 3. Dataset and exclusions

Verified before preparation (inventory): `release.json` matches the protocol pin. All 864 bound episodes are complete
and valid with exact prompt bytes. Every original cell of each start used the same cached request-0 observation. All
64 secondary frames bind to exactly the requested tick, and their decoded lossless composite frame matches the recorded
per-frame hash. Instruction strings are inserted byte-for-byte, including the trailing space in `S4-TOP-D`.

| Bank / stratum | Proposed view sets | Available | Answerable query pairs | Excluded / reason |
|---|---:|---|---|---|
| Initial, all scenes | 32 | 32 (native 720×1280 wrist/left/right) | A 94/96 pairs; C 94/96 TF–RF pairs; B all | A 4 items, C 6 + placement-C 4 items: within 5° of the pinned 45° cone boundary (1 start each in S3-R and S4-L) |
| Initial, main equivalent-wording pool S1/S3/S4 | 24 | 24 | A 78/80 pairs; C 78/80 TF–RF pairs | as above |
| Initial, S5 semantic diagnostic | 8 | 8 | A 16/16; C 16/16 | none |
| Secondary, saved rollout observations | 64 maximum | 64 (lossless policy-input composite: wrist 360×640, exterior 180×320) | A 179/192 pairs; C 138/192 TF–RF pairs | A: cone boundary 14, S5 bowl identity not followable 12 items. C: cone boundary 21, S5 identity 18, target or reference touching the gripper (final arrangement vs transit ambiguous) 129 items; reasons can overlap (162 C items excluded) |

**Label structure.** Initial-state labels are constant within every goal, with no within-goal label variation:
- S1-R, S3-R and S4-L are initially satisfied (“yes”); every other goal is “no”.
- Pooled labels have both classes, so a balanced-accuracy denominator exists for S1/S3/S4 but not for S5 (all “no”).
- A constant “no” answer scores 69.4% macro accuracy on C in S1/S3/S4.
- Secondary frames add within-goal variation for 9 of 12 goals ([label_variation.csv](runs/r1-20261006/results/label_variation.csv)).
- Action comparisons use the corrected initial-truth strata: 216 maintenance and 648 achievement episodes.

## 4. Checkpoint eligibility and training-path audit

| Readout | Role in comparison | Exact weight/processor identity | Eligible tests | Verified / missing training-path evidence | Status |
|---|---|---|---|---|---|
| N3-policy | Executed N3 policy reasoner | `nvidia/Cosmos3-Nano-Policy-DROID@6706d76` (files match HF); vLLM `Cosmos3ForConditionalGeneration` | A, B text/image, C image/no-image | All 750 reasoner tensors are byte-identical to `Qwen/Qwen3-VL-8B-Instruct@0c351dd`; tokenizer, processor and template are identical. The understanding tower is unadapted Qwen; generation/action tensors are trained | **Evaluated (R1)** |
| N3-upstream-qwen3vl8b | Upstream ancestor named in the policy config | `Qwen/Qwen3-VL-8B-Instruct@0c351dd` | same | Identical loaded parameters, processor, rendered prompts and fixture outputs to N3-policy | Shared result (not independent) |
| N3-base | Cosmos3-Nano base reasoner | `nvidia/Cosmos3-Nano@e59a53c` (weights unchanged since the 2026-06-01 squash) | same | Differs from R1 in 708/750 tensors (all LM layers, 309/351 vision tensors; embeddings and LM head changed). It is a separately post-trained reasoner, **not** the executed policy's reasoner | **Evaluated (R2)** |
| E3-policy | Executed E3 policy reasoner | `nvidia/Cosmos3-Edge-Policy-DROID@a7c7288`; vLLM `Cosmos3EdgeForConditionalGeneration` + `rqa-adapter-1` | same | Loaded reasoner parameters are identical to the Edge base; only generation-path tensors differ, including `k_norm_und_for_gen` | **Evaluated (R3)** |
| E3-base | Cosmos3-Edge base reasoner | `nvidia/Cosmos3-Edge@ff48d221` (initial-release weights, before the 2026-08-24 checkpoint update) | same | Identical to E3-policy (digest `d5a61863…`) | Shared result (not independent) |
| F3-qwen3vl4b | FLUX 3 Action shared encoder component (auxiliary) | `black-forest-labs/flux-3-action-base@62878e2/text_encoder`; the executed path is recorded in the F3 server receipt | same (image QA = auxiliary capability control) | Byte-identical to `Qwen/Qwen3-VL-4B-Instruct@ebb281e` (tied LM head). The executed F3 receipt lacks a revision string; the retained HF download metadata and file hashes resolve it to 62878e2 | **Evaluated (R4)** |

Native readout only: no head was attached, swapped or trained, and no output was extracted from hidden states.
`rqa-adapter-1` is a packaging-only fix:
- It drops the generation-path `k_norm_und_for_gen` tensor that vLLM's Edge mapper did not skip.
- It adds a config view so the Edge policy loads with the Edge reasoner class.
- No reasoner weight is altered.

Documented co-training objectives remain partially unknown: public model cards describe Cosmos3 reasoner training data, not the DROID policy recipe's frozen parameter groups. The tensor audit establishes what changed in the released files.
Cosmos Policy and π0.5 are outside this run.

## 5. Initial-state results — primary bank

Pre-specified primary endpoint: C TF − RF accuracy difference on S1/S3/S4. Rows are distinct readouts. Estimates are
macro-weighted: items → start×goal cell → starts → goals → scenes. Intervals are 95% percentile bootstraps
(10,000 replicates, seed 6106) resampling physical starts within scene. They are conditional on four fixed scene types
and fixed prompt templates. Text-only B is a finite set.

| Readout | B tuple correct, text-only (finite) / image acc. | A both-correct | C TF accuracy | C RF accuracy | C gap, pp [95% CI] | C both-correct | C balanced accuracy | Coverage |
|---|---|---|---|---|---|---|---|---|
| R1 Qwen3-VL-8B ≡ N3 policy reasoner | TF 10/10, RF 10/10 / 87.0% | 43.3% | 69.4% | 69.4% | +0.0 [+0.0, +0.0] | 69.4% | 50.0% | 2,072/2,072 delivered and valid; 78 C pairs |
| R2 Cosmos3-Nano base reasoner | TF 10/10, RF 8/10 / 84.5% | 41.5% | 60.5% | 69.4% | −9.0 [−16.3, −1.7] | 51.0% | 53.1% | 2,072/2,072; 78 C pairs |
| R3 Cosmos3-Edge reasoner ≡ E3 policy and base | TF 6/10, RF 0/10 / 2.4% | 67.0% | 70.5% | 69.4% | +1.0 [+0.0, +3.1] | 69.4% | 50.7% | 2,072 delivered / 1,650 valid; 78 C pairs |
| R4 Qwen3-VL-4B ≡ FLUX shared encoder (auxiliary) | TF 10/10, RF 3/10 / 71.3% | 37.2% | 69.4% | 69.4% | +0.0 [+0.0, +0.0] | 69.4% | 50.0% | 2,072 delivered / 2,052 valid; 78 C pairs |

The C estimates should be read with the answer distributions ([Fig. 3](runs/r1-20261006/figures/fig3_answer_distributions.png)):
- R1 and R4 answered “no” to all 240 initial C queries in S1/S3/S4.
- R3 answered “yes” once.
- Recall of the 66 initially satisfied (“yes”) items was 0% (R1, R4), 1.4% (R3) and 22.6% (R2).
- R2's negative gap arises because it answered “yes” to some DIR/TF queries (16 of 24 TF “yes” answers wrong) and never
  to RF queries.

All-geometry sensitivity, re-including the 2 boundary pairs: R2 −9.4 [−16.7, −2.4]; the other readouts are unchanged.
All four scenes, with S5 RF scored against the intended stacked goal: R2 −6.7 [−12.2, −1.3]; the other readouts are
+0.8 or 0.0.

**B with images** (S1/S3/S4): DIR / TF / RF tuple accuracy and TF − RF gap.

| Readout | DIR / TF / RF | TF − RF gap |
|---|---|---|
| R1 | 100 / 100 / 61.1% | +38.9 pp, degenerate interval |
| R2 | 100 / 100 / 53.5% | +46.5 [+44.4, +49.7] |
| R4 | 77.8 / 100 / 36.1% | +63.9 [+59.7, +68.1] |
| R3 | 1.0 / 6.2 / 0.0% | +6.2 [+2.1, +10.4] (format failures) |

RF errors on the 80 S1/S3/S4 RF image queries:

| Readout | Converse relation | `on_top_supported` ↔ `stacked_on` swaps (TOP) | Invalid |
|---|---:|---:|---:|
| R1 | 32/80 | 0 | 0 |
| R2 | 18/80 | 16 | 0 |
| R4 | 40/80 | 8 | 4 |

For R1, text-only RF is 10/10 but image-conditioned RF is 48/80, so the converse errors appear only when images are
present (exploratory observation). DIR − TF differences are 0 for R1 and R2.

## 6. Controls and secondary analyses

### Text and image-use controls

**Text-only B** (36 instructions; counts) — tuple correct, with DIR / TF / RF breakdown:

| Readout | Tuple correct | DIR / TF / RF |
|---|---:|---|
| R1 | 34/36 | 10 / 12 / 12 (2 DIR errors are S5 `stacked_on` → `on_top_supported`) |
| R2 | 32/36 | 12 / 12 / 8 |
| R3 | 14/36 (valid 20/36) | 6 / 8 / 0 |
| R4 | 27/36 | 12 / 12 / 3 |

Discordant TF/RF pairs were always TF-correct/RF-wrong (R2 4, R3 8, R4 9).

**No-image C** (36 fixed answers, reused against initial-frame labels; uncertainty conditional on those answers):

| Readout | No-image answers | Reused S1/S3/S4 accuracy |
|---|---|---:|
| R1 | 36/36 “no” | 69.4% |
| R4 | 36/36 “no” | 69.4% |
| R2 | 31 “no” + 5 “unknown” (all RF) | 59.3% |
| R3 | 32 “no” + 4 “unknown” (DIR) | 62.0% |

Because initial C answers equal the no-image answers for R1 and R4 and are near-constant for R3, the initial C scores
reflect the label prior, not visual use. Fixed layouts make goal priors sufficient for high raw accuracy.

### Reference-clause placement

Early − late, same relation words; no action outcomes exist:
- B text-only: all 8 pairs correct for R1, R2 and R4. R3: 3 both correct, 1 early-only, 1 late-only, 3 neither.
- B with images: 0.0 pp for every readout.
- C with images: R1 and R4 0.0 pp (constant answers); R2 +7.1 [−1.6, +16.1]; R3 −5.2 [−7.3, −2.1].

Clause placement is not conflated with the TF/RF converse contrast. It does not reproduce the RF interpretation errors.

### Saved rollout image bank

64 frames, 32 source episodes. Source model N3 11, E3 11, F3 10; source form DIR 10, TF 11, RF 11. Shown at
policy-input resolution.

| Readout | A accuracy | C TF − RF | C balanced accuracy |
|---|---:|---|---:|
| R1 | 58.3% | 0.0 | 50.0% |
| R2 | 64.2% | +1.1 [+0.0, +3.7] | 55.1% |
| R3 | 52.9% | +2.4 [+0.0, +6.6] | 51.5% |
| R4 | 53.9% | 0.0 | 50.0% |

Recall of “yes” items was 0–11.1% (90 items). The secondary bank reproduces the initial-bank pattern and is never
pooled with it.

### S5 and relation-specific patterns

S5 is reported separately.

- **Initial C:** S5 has only “no” labels, so every readout scores 100% and balanced accuracy is undefined.
- **B with images:** readouts split on the semantic boundary.
  - R1 maps “Stack … on” to `on_top_supported`: DIR 0/16 against the `stacked_on` gold; literal RF 16/16.
  - R2 and R4 map the literal RF “underneath and supporting” to `stacked_on`: RF 0/16; DIR and TF 16/16.
  - This is a justified semantic distinction, not counted as reference-language failure.
- **Secondary S5:** 18 complete C pairs give wide intervals, e.g. R2 +33.3 [+8.3, +64.3]. These are exploratory.
- **Relation-level breakdowns:** [breakdown.csv](runs/r1-20261006/results/breakdown.csv).
  - Lateral and front/behind items drive the A errors (R1 says “yes” to most lateral questions).
  - TOP questions are answered “no” correctly by the Qwen-lineage readouts.
- Any newly inspected subgroup is exploratory.

## 7. Connection to existing robot behavior

Joined on scene/start/goal/form. Family mapping: R1 and R2 → N3 episodes, R3 → E3, R4 → F3. The counts are
descriptive ([action_join_counts.csv](runs/r1-20261006/results/action_join_counts.csv)).

- **C:** answers were constant, so C correctness is fully determined by the initial-truth stratum. Achievement goals
  are “correct”; maintenance goals are “incorrect” for R1/R3/R4. The join is therefore uninformative about individual
  episodes.
- **B with images, R1 vs N3 actions (achievement stratum, stable-ever):**
  - B-correct items: 62 successes / 122 failures (33.7%).
  - B-incorrect items: 8 / 24 (25.0%).
  - B-incorrect items are almost all RF converse errors, so this split is confounded with wording form.
- Both existing endpoints (`stable_ever`, `stable_at_final`) are retained in the export. These are arrangement metrics,
  not verified correct-object instruction completion.

Supported pattern (guide §12):
- For the executed N3 and E3 policies, the readout weights are frozen/tensor-identical, while action behavior shows a
  TF > RF gap. There is no evidence that these readout weights lost ability during adaptation.
- The readouts themselves mis-parse converse RF phrasing when images are present.
- B is strong for TF/DIR, A is weak, and C is uninformative. This points to relation-wording interpretation and
  robot-frame visual relations as candidate contributors.
- A causal decomposition is not licensed.
- High verbal QA with weak policy outcomes does not by itself identify an action-alignment failure.
- Existing-checkpoint comparisons cannot isolate robot-training degradation or co-training benefit.

## 8. Complete artifacts and verification

| Item | Location (Git) | Raw / durable location (hash-indexed) |
|---|---|---|
| Code | `experiments/robolab_vqa/`, `tests/robolab_vqa/` | — |
| Frozen release (manifests, gold, frames, images index, validation, audit template) | `artifacts/robolab_vqa_20261006/release_r1/` | `/data/users/ali/rqa-20261006/release/r1` (300 lossless PNGs incl. 12 development-fixture views, payloads, audit sheets) |
| Inventory and tensor audit | `artifacts/robolab_vqa_20261006/{inventory,eligibility}/` | per-tensor hash maps, cells, ticks on PVC |
| Raw responses, rendered prompts, fixtures, receipts | indexed in [artifact_index.json](runs/r1-20261006/artifact_index.json) | `/data/users/ali/rqa-20261006/runs/r1-20261006/<lane>/` |
| Compact scores, coverage, breakdowns, metric export | [runs/r1-20261006/results/](runs/r1-20261006/results/) | analysis dir on PVC |
| Figures | [runs/r1-20261006/figures/](runs/r1-20261006/figures/) | — |

| Verification | Status |
|---|---|
| Implementation tests | 13 passed (`tests/robolab_vqa`: parsers, hand-calculated paired example, start-clustered bootstrap, labels/prompts, ceilings) |
| Frame/state synchronization | Verified: 32/32 starts and 64/64 frames bound with hash checks |
| Release validation | Passed; frozen and pushed (`5d7ef7b`) before any evaluation query |
| Human answerability | **Not performed (provisional)** |
| Checkpoint/readout parity | Native vLLM readouts. Tensor-identical groups confirmed by loaded-parameter digests, processor identity, rendered prompts and six fixtures each |
| Completed inference | 8,288/8,288 evaluation calls delivered; 0 infrastructure-missing; 0 truncated |
| Statistical checks | Bootstrap clustering and paired example unit-tested; same resamples across readouts |
| GitHub push | Results commit `98f85cf` pushed to `codex/nano-stock-workstation-20260926` and verified on the remote; see [RUN_INDEX.json](RUN_INDEX.json) |

## 9. Candidate findings for later manuscript inclusion

Thirteen candidates are recorded in [CANDIDATE_FINDINGS.csv](CANDIDATE_FINDINGS.csv). All are `unreviewed`, and
`author_decision` is blank. They cover:

- lineage facts (CF01–CF02);
- the uninformative primary endpoint and its no-image corollary (CF03–CF04);
- the RF converse-relation interpretation pattern and its exploratory image dependence (CF05–CF06);
- the null clause-placement control (CF07);
- weak robot-frame relations (CF08);
- the secondary-bank replication (CF09);
- R3 format non-compliance (CF10);
- S5 semantics (CF11);
- the R1−R2 contrast (CF12);
- the uninformative action join (CF13).

A candidate compact table is in [PAPER_TABLE.md](runs/r1-20261006/PAPER_TABLE.md). An evidence-bounded paragraph is
in [INTERPRETATION.md](runs/r1-20261006/INTERPRETATION.md). Neither has been inserted into any manuscript or Overleaf.

## 10. Limitations and unresolved questions

- **Scope:** four fixed scene types; correlated observations within 32 starts; limited wording templates; the original
  policy outcomes were already known.
- **Answerability:** human answerability review not performed. Visibility is an automated projected-centre pre-check;
  secondary frames use exterior views only, because per-tick wrist poses were not saved.
- **Presentation:**
  - A calibration-derived camera orientation legend was added because the starting-pose wrist view is rotated relative
    to the robot. This is a disclosed presentation difference from the policy input.
  - The secondary bank is at policy-input resolution.
  - S5 secondary queries add start-time reference views.
- **Wrapper interpretation:** the C wrapper may have been read as a completion question. The constant “no” answers make
  the primary endpoint uninformative, which is a floor result, not equivalence.
- **Uncertainty:** B intervals are degenerate or narrow because answers barely vary across starts; the effective
  wording sample is 10 S1/S3/S4 instruction pairs.
- **R3 format:** strict vocabulary/format scoring makes R3's B unevaluable. No post-result repair was applied.
- **S5:** stacking/support semantics differ by form and readout.
- **Readout type:** these are native text readouts, not policy latents. The vLLM Edge loader needed a packaging patch
  (`rqa-adapter-1`). A single greedy decoding is used per query.
- **Comparisons:** R2 vs R1 reflects Cosmos reasoning post-training rather than robot adaptation, and cross-family
  comparisons are confounded. No co-training or causal-degradation claim is licensed. R4 image QA is an auxiliary
  control, not FLUX policy VQA.
- **FLUX revision:** the F3 revision is resolved from retained download metadata and file hashes, not from the original
  receipt string.
- **Unresolved:** whether the policies' action pathways inherit the converse-phrasing difficulty, and how a human audit
  would change answerability.

## 11. Change log

- **2026-10-06:** Initialized separate reporting structure and GitHub delivery requirements. Design unchanged.
- **2026-10-06 (run r1-20261006):**
  - Implemented the runner, labels and analysis.
  - Froze and pushed release r1 before inference.
  - Qualified six lanes (four distinct readouts).
  - Ran 8,288 evaluation calls on four B200 GPUs.
  - Analyzed, and populated this report, the run report, the paper table, the interpretation and the candidate-findings
    ledger.
  - Pre-inference amendments: Implementation record §3–§6 and A1.
  - Provisional pending human answerability review.
