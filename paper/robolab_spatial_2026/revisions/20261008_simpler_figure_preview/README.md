# Simpler wording-effect figure preview

Author-requested preview of a forest plot: one mean and existing 95% confidence interval per model and comparison. Estimates and intervals are taken directly from the committed all-episode, any-time placement results. No outcomes, statistics, manuscript text, or active figure assets are changed.

Outputs: `output/figures/wording_effect_simple_preview.png` and `output/pdf/wording_effect_simple_preview.pdf` from the repository root. Run `uv run --no-project --with matplotlib python paper/robolab_spatial_2026/revisions/20261008_simpler_figure_preview/build_preview.py` to reproduce. The source CSV hash and exact displayed values are in `validation.json`.

All eight mean/interval triplets were independently cross-checked against the results JSON. The PNG and rendered vector PDF were visually inspected for legibility, clipping, and overlap. This is a preview only, not a replacement in Overleaf or the submission PDF.
