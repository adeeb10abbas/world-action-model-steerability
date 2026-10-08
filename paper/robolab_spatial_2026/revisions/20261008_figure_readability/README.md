# Figure readability revisions — 8 October 2026

Addresses the author's four comments on page 3. The one-second placement description and figure footers now appear in captions, and their internal whitespace is removed. The original violin distribution remains. The heatmap uses explicit target/reference group headings, dark dividers, and unambiguous bowl labels. Previously blank hatched cells now print their verified 100% any-time rates. The caption explains 0 = 0/8 and 100 = 8/8; hatched 100s are goals already satisfied at reset, not new placements achieved by the robot. Increasing the heatmap height makes its rows easier to read and removes stretched page-three gaps without changing manuscript fonts or margins. The redundant “Stable-placement rates (%)” label is removed.

All original rates, means, intervals, observations, and density settings are unchanged. `heatmap_numeric_validation.json` checks every goal cell against the saved episode records: 81 previously displayed rates retained, 27 formerly blank hatched cells verified as 216/216 passes, 39 zero cells verified as 0/8, and 18 unchanged overall values.

From the repository root, reproduce the current assets with:

```sh
uv run --no-project --with matplotlib python paper/robolab_spatial_2026/revisions/20261008_figure_readability/build_violin.py
uv run --no-project --with matplotlib python paper/robolab_spatial_2026/revisions/20261008_figure_readability/build_heatmap.py
```

Compile `rev_with_vqa.tex` as usual. `before.tex` preserves the preceding caption revision. `validation.json` records the final combined PDF checks. The final PDF remains four main-text pages, one reference page, and thirteen appendix pages. Compilation has no unresolved references, overfull boxes, or underfull vertical boxes. The matching Overleaf source and figure assets were compiled and visually verified; `overleaf_figures_verified.jpg` records page 3. No new experiments or submission actions were performed.
