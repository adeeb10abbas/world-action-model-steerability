# Readability revision — 7 October 2026

The user rejected the compressed revision for sounding like a technical report. This pass restores connected research-paper paragraphs: each result makes a claim, explains it through a concrete example, and states its implication. The canonical `main.tex` remains untouched. The two before-files preserve the previously published revision.

## Editorial changes

- Restore the earlier narrative in both `revision_esmaeil.tex` (Overleaf `rev1.tex`) and `rev_with_vqa.tex`.
- Replace the abstract sentence about instruction “readouts” with a plain statement about reversing the requested spatial relation.
- Use “policy rollouts” in place of “executions” in prose. Historical asset filenames and LaTeX labels are retained.
- Retain DIR/TF/RF definitions, physical scene examples, paired starts, explicit rate denominators, and the explanation of hatched initially satisfied goals requested by Esmaeil.
- Keep Discussion and Conclusion combined and both main texts at four pages without reducing the existing font size or margins.
- In the VQA revision, remove the old main-text Figure 3 montage; policy rollout examples remain in Appendix D. Table 1 instead shows the exact three camera inputs and a verbatim excerpt of the actual question beside the three instructions.
- Table 2 names the tested models: Nano / Qwen3-VL-8B-Instruct; Edge / Cosmos3-Edge reasoner; FLUX / Qwen3-VL-4B-Instruct. FLUX image results were already run and are now shown as auxiliary (TF 100.0%, RF 41.7%), with the text-only role of Qwen in FLUX stated in the caption.

## Evidence boundaries

Mark's distinction between instruction interpretation and action generation is retained. No new training, inference, or robot episodes were performed. The tested component weights match upstream/base checkpoints; this does not establish training-induced degradation or causality between a QA answer and a robot failure. Controlled recipe/co-training attribution remains unavailable. Image–instruction arrangement judgments remain inconclusive and their image labels lack human review. Instruction-tuple answers are determined by the prompt and do not depend on those visual labels.

## Exact input example

Table 1 uses S4-C04's initial wrist, left exterior, and right exterior views from the released VQA inputs. All three PNGs were retrieved with upstream commit `630ded5` and verified against the original PNG SHA256 values. `vqa_example/` preserves the full prompt, verbatim excerpt, query and answers, and provenance. The images in `revision_assets/` preserve the exact bytes.

## Validation

`validation.json` records the source/PDF hashes and local build checks. Both PDFs begin references on page 5; appendices remain additional pages. All eight main-text pages were rendered and inspected. No experimental results were changed.

## Component-name and FLUX image-result clarification

The added table names follow the executed-checkpoint audit, not assumed architecture ancestry. Edge is the native Cosmos3-Edge reasoner; no separately named Qwen checkpoint is established as its identity. See `docs/robolab-vqa-20261006/IMPLEMENTATION_RECORD.md` and the R1 `lanes.json`.

Primary implementation references checked for this edit:
- Edge pinned configuration: https://huggingface.co/nvidia/Cosmos3-Edge/blob/ff48d22144de52de296a7b4d3a78914831007212/config.json
- FLUX shared encoder model card: https://huggingface.co/black-forest-labs/flux-3-action-base
- FLUX camera path through the video VAE: https://github.com/black-forest-labs/flux-action/blob/830f1ce178d7aea52f18fde31d8e8e36ce6bae21/src/flux_action/policy.py#L754-L770
- FLUX Qwen inputs are text tokens: https://github.com/black-forest-labs/flux-action/blob/830f1ce178d7aea52f18fde31d8e8e36ce6bae21/src/flux_action/models/text_encoder.py#L128-L140

The newly displayed FLUX IH scores (100.0% TF, 41.7% RF) already appeared in the V2 results and Appendix F. Showing them in the main table does not add an experiment or change their auxiliary interpretation.
