# Caption simplification - 9 October 2026

Shortens the two results-figure captions and removes the term "hatched" from the manuscript. Gray columns labeled "True at start" replace the repeated 100s for goals already satisfied before robot motion. Ordinary numeric 100s mean all eight runs passed the spatial placement check. The underlying episode outcomes and overall rates are unchanged; starting conditions remain included in Overall. Larger figure heights use the space released by shorter captions without changing manuscript fonts or margins.

The live Overleaf source was read before editing. Its newer abstract and introduction were preserved verbatim, and only the two figure captions and their matching methods reference were changed. `before_live.tex` is that starting snapshot; `before_local.tex` preserves the older local manuscript. This distinction prevents the earlier abstract from being restored accidentally.

Reproduce the figures from the repository root:

```sh
uv run --no-project --with matplotlib python paper/robolab_spatial_2026/revisions/20261009_caption_simplification/build_violin.py
uv run --no-project --with matplotlib python paper/robolab_spatial_2026/revisions/20261009_caption_simplification/build_heatmap.py
```

The heatmap builder checks all 108 goal cells against saved episode outcomes. All 81 displayed goal rates and 18 overall values are unchanged; the 27 initial-condition cells represent 216 passes already present in the saved data. The violin inherits its original data, means, intervals, and density settings. No new experiments or statistical analyses were run.

`validation.json` records the combined PDF checks. The paper has four main-text pages, one reference page, and thirteen appendix pages. Main pages were rendered and reviewed, with an independent check of page 3. No submission action was performed.
