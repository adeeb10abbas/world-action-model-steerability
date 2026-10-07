# Four-page revisions and VQA integration - 2026-10-07

## Deliverables

- `../../revision_esmaeil.tex`: revised existing paper, uploaded to Overleaf as `rev1.tex`.
- `../../rev_with_vqa.tex`: separate revision adding the approved V2 instruction-understanding findings.
- `before_rev1.tex`: preserved pre-edit source, verified against the original live Overleaf source before editing.
- `../../../../output/pdf/same_goal_different_words_revision.pdf` and `same_goal_different_words_with_vqa.pdf`: compiled outputs.

Both versions have four pages of main text; references start on page 5. The complete PDFs have 22 and 24 pages because references and appendices are retained. No font, margin, template, bibliography, figure-image, or experimental-data changes were used to meet the main-text limit. Canonical `main.tex` is unchanged. The existing revision's references and appendices are byte-for-byte unchanged. The VQA revision adds Appendix F and clarifies the historical FLUX policy-manifest limitation relative to the later shared-encoder audit.

## Esi's feedback retained

The final audit checked `../20261001/esmaeil_comments.txt`, not just overall length. Both versions retain a concrete equivalent-wording example in the abstract, an explicit outcome denominator, an opening Methods sentence connecting the research question to the paired experiment, clear scene and instruction definitions, and a connected scientific narrative. Main-text run-in headings were removed. Long compound sentences were shortened. Discussion and Conclusion are now one section.

Terminology remains Direct (DIR), Target-first (TF), and Reference-first (RF). Target-first refers to the relational clause; every instruction still requests moving the same target. The hatched goals already hold at reset, remain included, and have an exclusion sensitivity analysis. Scored spatial relations are not equated with correct object manipulation or persistence.

## Mark's feedback retained

The VQA revision tests language components separately from action generation, using the exact policy instructions and additional reference-placement controls. It reports the available checkpoint identities rather than inventing a before/after robot-training comparison. No new training was run. Unavailable matched training data prevent isolating training-recipe or co-training effects. The work does not establish that robot training degraded the tested component weights, or that QA errors cause action failures. Mark's tentative pi0.5 example is not used as evidence. Including Cosmos3 policies is not presented as a controlled test of the original Cosmos Policy training recipe.

The VQA contribution is constrained target/reference/relation tuple accuracy. Edge and FLUX make reference-first errors from text alone. Nano is correct on text-only prompts but makes errors on two reference-first instructions when images are included. Its image comparison holds camera-orientation text fixed. FLUX's image QA remains auxiliary because its policy uses the tested encoder for text only. Complete conditions, denominators, placement controls, and component lineage are in Appendix F.

The prespecified arrangement-matching primary test and bounded follow-up remain explicitly inconclusive. Their visual labels lack human review. This revision makes no positive claim about scene understanding from that test. Instruction labels follow from the prompt and do not depend on a human image audit.

## Evidence and verification

VQA source: `reports/robolab-vqa-20261006/runs/r2-final-20261007/REPORT.md`, its committed result tables and lineage receipts, and `docs/robolab-vqa-20261006/v2-final/FINAL_EXECUTION_SPEC.md`. Those source results were not edited.

Both project builds passed latexmk/pdflatex with no overfull boxes or undefined references. Main-text pages were rendered and visually checked. Appendix F was also rendered and checked. `validation.json` records source/PDF hashes and page counts. The live Overleaf source was read back after upload and matched the local source for each version. Both also compiled successfully in Overleaf, with References visibly starting on page 5.
