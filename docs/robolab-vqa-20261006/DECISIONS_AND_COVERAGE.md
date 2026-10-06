# Decisions and coverage audit

**Design v1.0; reporting requirement added October 6, 2026. No experiment has run.**

| Request or concern | Where addressed | Status / boundary |
|---|---|---|
| Keep the work small enough for a four-page workshop paper | Guide §§1, 9, 11 | Inference only; finite query cap; one candidate paper table; full findings live in a separate report |
| Use RoboSpatial-style questions on our RoboLab data | Guide §§1, 3–4; question catalog | Custom configuration-style diagnostic; no official RoboSpatial score or extra public-benchmark run |
| Scene understanding | Guide §4A | Paired visible-relation questions with a converse reference formulation |
| Instruction understanding | Guide §4B | Exact DIR/TF/RF prompts; target, reference, relation; image and text-only conditions |
| Instruction plus scene | Guide §4C | Current requested-arrangement verification; no-image control; distinct from predicting action success |
| Preserve the original manipulation | Guide §§2, 4; original instruction hashes | All 36 executed strings retained; historical D/S/I IDs map to DIR/TF/RF |
| Test reference before/after without also reversing relation vocabulary | Guide §5; 16 placement controls | Fixed directional words and clause relocation; separately reported; no action runs for these new strings |
| Starting frames versus saved rollout frames | Guide §3; frame selection manifest | All 32 starts; up to 64 fixed saved observations, same bank for all models; separate analyses |
| Objective VQA metrics | Guide §8 | Accuracy, balanced accuracy, field/tuple scores, paired gap, both-correct, disagreement, coverage |
| Independent sampling and uncertainty | Guide §8 | Physical-start clustering within scene; shared questions/frames are not independent scenes |
| Gold labels and robot coordinate frame | Guide §§3, 6 | Saved geometry and calibration; synchronized evidence; visibility/semantic audit; no VLM-generated gold |
| Already-satisfied / hatched goals | Guide §8 | Preserve corrected initial-truth strata and separate action analyses; initial arrangement is not achievement |
| Nesting/support ambiguity | Guide §§4, 6 | All bowl data retained separately; headline equivalent-wording pool uses S1/S3/S4 |
| Test the VLM separately from the policy | Guide §7 | Native base/policy component comparisons where valid; action outcomes reused, not regenerated |
| Same backbone and training differences | Guide §7 | Exact lineage, tensor/processor audits, frozen/co-training metadata; unsupported comparisons stay explicit |
| Include a known co-training comparison / Cosmos Policy | Guide §§7, 12–13 | **Not included in this scoped run.** Different policy family/objectives; no causal co-training comparison is promised |
| Verify π0.5 / knowledge-insulation training details | Guide §7 | **No π0.5 experiment or factual training claim is needed here.** Verify original sources separately before any later manuscript claim |
| Separate understanding from action alignment | Guide §§8, 12 | Descriptive joins; QA readout is not the policy's latent decision or a causal decomposition |
| Do not assume robot training degrades a capable VLM | Guide §§1, 7, 12 | No causal degradation claim; tensor-identical/frozen and unmatched components explicitly distinguished |
| Save to GitHub | Guide §11; README agent prompt | Packet/report scaffolding saved now; dispatched agents must save implementation and full results after execution |
| Generate a separate report for later paper selection | Guide §11; `reports/robolab-vqa-20261006/` | Complete report, versioned run reports, candidate-findings ledger; no automatic manuscript edits |

This packet addresses the agreed inference-only diagnostic, not every experiment that could answer Mark's broader training-recipe question. Compatibility, actual model scores, media alignment, and human answerability review remain unverified until execution. The user-approved earlier manuscript label and Discussion changes are separate artifacts; this protocol adds no experimental result to the paper.
