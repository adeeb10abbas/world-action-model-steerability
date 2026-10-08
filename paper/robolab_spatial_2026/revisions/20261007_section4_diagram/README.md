# Section 4 diagram correction — 2026-10-07

Restores the earlier Table 1 and places the actual VQA inputs and question in a compact flow diagram inside Section 4 of `rev_with_vqa.tex`. The old policy-rollout montage remains out of the VQA main text; the replacement test diagram is now Figure 3. The base revision and canonical source were not changed.

The diagram shows three unmodified evaluated camera images, the exact mustard-right RF instruction, a verbatim question excerpt, the language model, and the gold target/reference/relation used for scoring. It does not display a model-generated answer. Camera descriptions and vocabulary lists are omitted from the illustration and acknowledged in its caption. Text-only queries omit images.

Exact source query: `B2.IH.S4-C04-initial.S4-R-I`. Image hashes, the complete prompt and example answers are in `../20261007_readability/vqa_example/`. Regenerate the figure with `build_diagram.py` using Python with ReportLab.

## Verification

- Compiled successfully with latexmk, with no undefined references or overfull boxes.
- Four main-text pages; references on page 5; 24 pages including references and appendices.
- Inspected all four main-text pages visually.
- Table 1 matches the base revision exactly.
- Final PDF contains the full RF instruction including “on the table.”
- Retained constrained decoding, exact model identities, FLUX auxiliary image scores/caveat, unchanged-weight interpretation, causal limitations, and unresolved visual-label review.
- Overleaf source readback matched the local source; the live PDF was inspected on pages 4 and 5. Screenshots are saved here.
- No model inference, training, robot runs, or changes to experimental results.

The previous VQA source is preserved as `before_rev_with_vqa.tex`. Final checks and artifact hashes are recorded in `validation.json`.
