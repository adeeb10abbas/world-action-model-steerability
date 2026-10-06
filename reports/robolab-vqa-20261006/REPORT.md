# RoboLab VQA diagnostic — separate results report

**Study:** RQA-20261006, design v1.0

**Report initialized:** October 6, 2026

**Status:** NOT RUN — design and reporting structure only; no model findings yet.

**Purpose:** preserve the complete diagnostic results independently of the workshop manuscript, then let the authors select supported findings for later inclusion.

[Locked guide](../../docs/robolab-vqa-20261006/EXPERIMENT_GUIDE.md) · [Coverage audit](../../docs/robolab-vqa-20261006/DECISIONS_AND_COVERAGE.md) · [Run index](RUN_INDEX.json) · [Candidate findings](CANDIDATE_FINDINGS.csv)

## 1. Executive findings

**No results are available.** Do not turn planned comparisons into findings. After execution, summarize the three questions below with evidence links, effect sizes, uncertainty, and limitations; retain null or conflicting evidence.

| Question | Finding | Supporting artifact | Limitation |
|---|---|---|---|
| Can the readout identify current spatial relations under reference reversal? | Not run | Pending | — |
| Can it recover the requested target, reference, and relation under DIR/TF/RF wording? | Not run | Pending | — |
| Can it combine the instruction with the image to judge the requested arrangement? | Not run | Pending | — |
| How do these patterns compare with the existing policy wording effect? | Not analyzed | Pending | QA is not direct access to the policy's latent decision |

## 2. Run identity and evidence status

Fill this section for the latest validated run; link an immutable run-specific report and all prior runs through `RUN_INDEX.json`.

| Field | Value |
|---|---|
| Run ID / UTC start and end | Not run |
| Data-release SHA256 / protocol version | Pending / 1.0 |
| Implementation commit / analysis commit | Not implemented |
| Checkpoint and processor manifest | Not qualified |
| Actual launch and analysis commands / environment receipt | Pending |
| Human answerability audit | Pending |
| Full compact results and coverage tables | Pending |
| Durable raw-response/media artifact index and hashes | Pending |
| Actual GPU time / elapsed time | Not measured |
| Deviations and amendments | None executed; record any before affected inference |

Missing, unsupported, undefined, and unrun results must be labeled separately. Do not use zero as a placeholder. If inference is run before human answerability review, label all affected results provisional.

## 3. Dataset and exclusions

Planned banks: 32 initial three-view observations and up to 64 fixed saved-rollout observations from 32 source episodes. Original instructions: 36; clause-placement controls: 16. Original action evidence: 864 episodes, reused only. No new training or policy rollouts are included.

Report actual available/answerable counts by bank, scene, goal, question family, and label. Explain synchronization gaps, coordinate-frame ambiguities, occlusion, support ambiguity, and threshold-boundary exclusions. State within-goal yes/no variation and whether a balanced-accuracy denominator exists. Include the initial-truth strata used in action comparisons. Use a complete exclusions ledger rather than deleting unavailable items.

| Bank / stratum | Proposed view sets | Available | Answerable query pairs | Excluded / reason |
|---|---:|---|---|---|
| Initial, all scenes | 32 | Pending | Pending | Pending |
| Initial, main equivalent-wording pool S1/S3/S4 | 24 | Pending | Pending | Pending |
| Initial, S5 semantic diagnostic | 8 | Pending | Pending | Pending |
| Secondary, saved rollout observations | 64 maximum | Pending | Pending | Pending |

## 4. Checkpoint eligibility and training-path audit

Provide one row per attempted readout, including blocked or unsupported lanes. Identify exact base/policy lineage, changed/frozen tensors, tokenizer/vision/readout paths, documented co-training objectives, preprocessing differences, and head availability. Mark shared tensor-identical evaluations explicitly. Do not imply that standalone Qwen image QA is FLUX policy VQA or that Cosmos Policy is Cosmos3.

| Readout | Role in comparison | Exact weight/processor identity | Eligible tests | Verified / missing training-path evidence | Status |
|---|---|---|---|---|---|
| Pending inventory | — | Not verified | Not qualified | Pending | Not run |

## 5. Initial-state results — primary bank

The pre-specified primary endpoint is C's TF-minus-RF accuracy difference on S1/S3/S4. Keep its estimate visible even if the largest effect occurs elsewhere. Report every qualified readout and raw denominators alongside scene-weighted scores. Include descriptive 95% intervals from the frozen physical-start bootstrap; do not assign that interval procedure to repeated text-only prompts.

| Readout | B tuple accuracy: text / image | A both-correct | C TF accuracy | C RF accuracy | C gap, pp [95% CI] | C both-correct | C balanced accuracy | Coverage |
|---|---|---|---|---|---|---|---|---|
| No evaluated readouts | Not run | Not run | Not run | Not run | Not run | Not run | Not run | Not run |

Link the complete machine-readable tables containing A accuracy/gap, B target/reference/relation/tuple scores, C accuracy/gap, yes/no recalls, both-correct and disagreement rates, invalid/unknown responses, and all DIR descriptive comparisons. The compact table must not replace the full export.

## 6. Controls and secondary analyses

### Text and image-use controls

Report text-only B separately from image-assisted B. Report C's no-image response reuse, abstentions, label variation, and scores without treating repeated use of a single answer as independent generation. Explain whether initial-state scores could reflect fixed layouts or goal priors.

### Reference-clause placement

Report early-minus-late effects for the 16 fixed control instructions, with denominators and uncertainty for eligible image tests. These instructions have no corresponding new action results. Do not conflate clause placement with the original reference/converse wording contrast.

### Saved rollout image bank

Use a separate table with the same A/C metrics, coverage, source-policy/source-form counts, and physical-start clustering. Explain consistency or disagreement with the initial-state result. No pooling that conceals a bank-specific result.

### S5 and relation-specific patterns

Report the bowl semantic distinction, literal/form-specific labels, and identity visibility. Show S5 separately; any all-scene intended-goal summary is a sensitivity result. Provide all scene/relation breakdowns rather than selecting only the strongest contrast. Label any newly inspected subgroup exploratory.

**All subsections above currently: not run.**

## 7. Connection to existing robot behavior

Join on verified scene/start/goal/form and checkpoint-family identity. Report QA-correct/action-arrangement-success and QA-correct/action-arrangement-failure counts descriptively, separating initially satisfied goals. Preserve both existing any-time and final-state outcomes. These are arrangement metrics, not verified correct-object instruction completion.

Discuss which diagnostic patterns are supported and which remain unresolved. High verbal QA with weak policy outcomes does not by itself identify a causal action-alignment failure. Existing-checkpoint comparisons do not isolate robot-training degradation or a benefit of co-training.

**Status: not analyzed.**

## 8. Complete artifacts and verification

Populate an artifact index with durable repository or storage locations, SHA256, role, run ID, and availability. Include raw response/failure archives, full compact scores and coverage, checkpoint receipts, labels/audit, synchronized frame manifest, frozen query manifest, output figures, environment/commands, analysis checks, and GitHub commit. Keep large raw data, weights, and credentials outside Git; commit the index and compact results.

Record what was actually verified, with separate statuses for implementation tests, frame/state synchronization, human answerability, checkpoint/readout parity, completed inference, statistical checks, and GitHub push. Passing specification checks is not runtime qualification.

## 9. Candidate findings for later manuscript inclusion

Maintain every proposed claim in [CANDIDATE_FINDINGS.csv](CANDIDATE_FINDINGS.csv). Each row requires supporting run/table/row IDs, denominators, uncertainty, counterevidence, scope limits, and primary/descriptive/exploratory status. Initially leave the author's decision blank. A candidate may be a null result or a limitation, not only a positive finding.

**No candidate findings yet.** After results, propose at most one compact main-text table and a short evidence-bounded paragraph for this four-page paper. Do not edit the manuscript or Overleaf automatically. The full report remains available regardless of what the authors later select.

## 10. Limitations and unresolved questions

Carry forward at minimum: four fixed scene types; correlated observations within 32 starts; limited wording templates; already-known original policy outcomes; visibility and calibration assistance; S5 semantics; native versus extracted QA readouts; frozen or unmatched components; missing historical FLUX weight identity if unresolved; and unsupported co-training/causal degradation claims. Add execution-specific limitations without removing inconvenient findings.

## 11. Change log

- **2026-10-06:** Initialized separate reporting structure and GitHub delivery requirements. Design unchanged; no experiments or model results.
