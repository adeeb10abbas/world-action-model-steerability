# RQA-20261006 run report — `r1-20261006`

**Immutable record of this run.** Later runs get their own directory; this file is not overwritten.
**Status:** complete; **answerability provisional** (no human review). Not inserted into any manuscript.

[Top-level report](../../REPORT.md) · [All generated tables](TABLES.md) · [Interpretation](INTERPRETATION.md) ·
[Paper table](PAPER_TABLE.md) · [Completion receipt](COMPLETION_RECEIPT.json) · [Artifact index](artifact_index.json) ·
[Lanes](lanes.json) · [Eligibility](model_eligibility.csv) · [Results](results/) · [Figures](figures/)

## Identity

| Field | Value |
|---|---|
| Run | `r1-20261006`; release `r1`; protocol 1.0; label version `rqa-gold-1`; parser `rqa-parse-1`; adapter `rqa-adapter-1`; analysis `rqa-analysis-1` |
| Release | content sha256 `1e691df6b85576e0d75925cc7902a1f4e303267098483a81726f6ff63cda3046`; `release.json` sha256 `ccccd81eeb908b8001fa8ff70c0d28917bebc6f1df2a96d8fd335161f54cf7a9`; validation passed |
| Commits | implementation `4d2605c`; release freeze and inference code `5d7ef7b` (pushed before any evaluation query); qualification amendment and analysis code `6d4babf`; report commit in [RUN_INDEX.json](../../RUN_INDEX.json) |
| Time (UTC, 2026-10-06) | fixtures 22:09–22:13; bank 22:15:13–22:24:42; analysis 22:27 |
| Compute | four NVIDIA B200 (one per distinct readout; device-plugin isolated), user-owned pods `211247-alirqa-*` in `211247-prod`; 0.57 GPU-hours bank inference; all GPU pods deleted afterwards |
| Software | vLLM 0.26.0 native reasoner classes, torch 2.11.0+cu130, transformers 5.14.1; BF16; greedy; ≤256 new tokens; `enable_thinking=False`; eager; FLASH_ATTN; no prefix caching; one isolated request at a time |
| Raw evidence | `/data/users/ali/rqa-20261006/` on PVC `211247-prod-pvc` (hashes in [artifact_index.json](artifact_index.json)) |

## Readouts

| Lane | Status | Identity | Evaluated as |
|---|---|---|---|
| N3-policy | evaluated | `nvidia/Cosmos3-Nano-Policy-DROID@6706d76`; reasoner tensors byte-identical to Qwen3-VL-8B-Instruct | R1 |
| N3-upstream-qwen3vl8b | shared (tensor-identical) | `Qwen/Qwen3-VL-8B-Instruct@0c351dd` | references R1 |
| N3-base | evaluated | `nvidia/Cosmos3-Nano@e59a53c`; 708/750 reasoner tensors differ from R1 | R2 |
| E3-policy | evaluated | `nvidia/Cosmos3-Edge-Policy-DROID@a7c7288`; reasoner identical to Edge base | R3 |
| E3-base | shared (tensor-identical) | `nvidia/Cosmos3-Edge@ff48d221` | references R3 |
| F3-qwen3vl4b | evaluated (auxiliary) | `black-forest-labs/flux-3-action-base@62878e2/text_encoder` ≡ Qwen3-VL-4B-Instruct | R4 |

## Coverage

All 2,072 queries per distinct readout were issued and delivered (8,288 total; 0 infrastructure-missing; 0 truncated).
Valid-format responses:

| Readout | Valid format |
|---|---|
| R1 | 2,072 |
| R2 | 2,072 |
| R3 | 1,650 (415 B and 7 A invalid) |
| R4 | 2,052 (20 B with out-of-vocabulary `on_top_of`) |

Answerable items:

| Item set | Answerable / proposed |
|---|---|
| A initial | 188/192 |
| C initial | 282/288 |
| Placement C | 124/128 |
| A secondary | 358/384 |
| C secondary | 414/576 |

Full breakdown: [TABLES.md](TABLES.md), [results/coverage.csv](results/coverage.csv).

## Results (initial bank, S1/S3/S4 unless stated)

| Readout | B tuple correct, text-only (finite) / image acc. | A both-correct | C TF acc. | C RF acc. | C TF−RF, pp [95% CI] | C both-correct | C balanced acc. |
|---|---|---|---|---|---|---|---|
| R1 Qwen3-VL-8B ≡ N3 policy reasoner | TF 10/10, RF 10/10 / 87.0% | 43.3% | 69.4% | 69.4% | +0.0 [+0.0, +0.0] | 69.4% | 50.0% |
| R2 Cosmos3-Nano base reasoner | TF 10/10, RF 8/10 / 84.5% | 41.5% | 60.5% | 69.4% | −9.0 [−16.3, −1.7] | 51.0% | 53.1% |
| R3 Cosmos3-Edge ≡ E3 policy and base | TF 6/10, RF 0/10 / 2.4% | 67.0% | 70.5% | 69.4% | +1.0 [+0.0, +3.1] | 69.4% | 50.7% |
| R4 Qwen3-VL-4B ≡ FLUX shared encoder | TF 10/10, RF 3/10 / 71.3% | 37.2% | 69.4% | 69.4% | +0.0 [+0.0, +0.0] | 69.4% | 50.0% |

- **C (primary):** uninformative. R1/R3/R4 answered “no” to essentially all C queries, with or without images.
  Accuracy equals the constant-“no” prior (69.4%); recall of initially satisfied items is 0–1.4%.
- **B with images:** TF 100% versus RF 61.1% / 53.5% / 36.1% for R1 / R2 / R4. Lateral and front/behind RF errors are
  mostly the converse relation. For R1 the errors appear only with images (text-only RF 10/10; exploratory).
- **Placement control:** no B errors (R1, R2, R4).
- **A:** near chance for R1, R2 and R4 (51–53%); R3 71.4%.
- **Secondary bank:** same C pattern (balanced accuracy 50–55%; gaps ≤ +2.4 pp).
- **S5:** separate; semantic split between `stacked_on` and `on_top_supported`.
- **Existing policy TF−RF (stable-ever):** N3 +14.6 [+8.1, +21.1]; E3 +8.1 [+3.6, +12.8]; F3 +13.8 [+7.6, +20.1].

Figures: [Fig. 1 primary endpoint and wording gaps](figures/fig1_primary_C_TF_RF.png) ·
[Fig. 2 tests overview](figures/fig2_tests_overview.png) · [Fig. 3 answer distributions](figures/fig3_answer_distributions.png).

## Deviations, amendments and disclosures

All of the following were decided before any bank query unless noted.

- **Presentation:**
  - A calibration-derived camera orientation legend was added: the starting-pose wrist image is rotated relative to
    the robot.
  - The secondary bank uses the lossless policy-input composite, the only saved synchronized three-view observation at
    the selected ticks.
  - S5 secondary queries include start-time reference views and a fixed identity note.
- **Exclusions:** gripper-contact exclusion for C on secondary frames; S5 bowl-identity exclusion when both bowls moved
  more than 2 cm.
- **Adapter `rqa-adapter-1` (packaging only):**
  - The vLLM Edge mapper now skips the generation-path `k_norm_und_for_gen` tensor.
  - The Edge policy loads through a config view.
  - Engine settings: FLASH_ATTN, non-JIT sampler.
- **Amendment A1 (after six fixtures per lane):**
  - The parity rule ignores processor writer metadata and requires identical rendered prompts.
  - Two lanes became shared tensor-identical results.
  - The bank ran on four GPUs.
- **Human review:** answerability review not performed; results provisional.
- **Post-result, descriptive only:** the B error taxonomy, the image-dependence observation for R1, and the constant-“no”
  baseline line in Fig. 1.

## Verification

- 13 unit tests pass.
- Inventory checks: 32/32 starts and 64/64 frames verified.
- Release validation passed; the cluster code hash matched the freeze commit.
- Lane identity groups were confirmed by loaded-parameter digests and fixture parity.
- 8,288/8,288 calls were delivered.
- The analysis reproduces from [results/scored_rows.csv.gz](results/scored_rows.csv.gz) and the frozen release.
