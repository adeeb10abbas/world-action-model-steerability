# Four-page workshop draft

**Same Goal, Different Words: Spatial Instruction Sensitivity in World–Action Models**

Target: [Do Robots Need World Models? at CoRL 2026](https://do-robots-need-world-models.github.io/). This is an editable research draft, not a submission. The entire PDF, including references, is four pages. This is a conservative drafting choice: the workshop website says only “Up to 4 pages, CoRL template” and does not specify whether references count (rechecked September 27, 2026). The linked OpenReview page did not expose an additional rule. It uses the official CoRL 2026 style in `preprint` mode; authors remain anonymous until the author list is supplied. Before submission, confirm the workshop's anonymization and reference-page rules and use its requested mode. No authorship, acceptance, or award is implied.

## Files

- `main.tex`: canonical manuscript. The Overleaf project compiles the equivalent flat bundle as `rws_main.tex`; its older `main.tex` and scene-design files are preserved.
- `figures/wording_effect.pdf`: paired-state violin plots with observed starts, means, and state-cluster uncertainty. The prior forest version is retained separately.
- `figures/goal_response_by_form.pdf`: goal × model × wording breakdown. `goal_response.pdf` is an optional shorter aggregate view.
- `scene_mustard.jpg`: unmodified pilot scene image from `docs/robolab-workshop-20260926/scene_images/S4.jpg`; illustrative asset view, not a claimed confirmation episode.
- `analysis/`: corrected derived strata, unchanged physical outcomes, exact plot data and provenance.
- `RELATED_WORK_NOTES.md`, `references.bib`: primary-source checks and published-paper structure examples.
- `VIDEO_REQUEST.md`: exact four server recordings and montage requirements. No videos have yet been inspected locally or incorporated into the paper.
- `../../output/pdf/same_goal_different_words.pdf`: compiled draft.
- `../../output/pdf/same_goal_different_words_overleaf.zip`: seven-file upload bundle.

## Build and reproduce

From this directory:

```sh
latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
python3 package_overleaf.py
```

For the derived results and figures, install NumPy and Matplotlib in a separate environment and run `python3 generate_figures.py` from the repository root. The script checks hashes and reproduces the original prespecified all-episode contrasts before producing corrected subgroup tables. It does not import a simulator or launch policies.

The unmodified `corl_2026.sty` and `corlabbrvnat.bst` came from the [ZIP linked by the official author instructions](https://2026.corl.org/contributions/instruction-for-authors), downloaded September 27, 2026. This draft changes neither template margins nor type sizes.

## Claim boundaries

The scene/goal-weighted prespecified secondary S−I contrast is +12.15 percentage points for the original stable-ever endpoint. The manuscript makes it central after seeing results and explicitly discloses that scope change. It retains the unresolved original forecast-diagnosis question and post-result annotation amendment; it does not claim that predictions are uninformative.

Achievement strata come from the frozen accepted-state registry, correcting 44 inconsistent per-episode labels. Raw episode outcomes and historical `RESULTS.md` remain untouched. This paper's derived achievement rates supersede the inconsistent values for its tables. Final-state sensitivity is explicitly post-hoc.

The score checks a stable relational predicate, not complete instruction execution. Reference motion can cause a predicate pass; seven Nano cube-behind I passes have no detected target lift and substantial reference motion. Existing summaries support the stated observations, but full videos are still needed before narrating the actual manipulation sequence. This caveat is in the paper and video request.

The exact declared official model revisions were verified. The compact FLUX runtime receipt has a null revision field and a checkpoint path with the expected prefix; a full executed-weight manifest is still needed for complete provenance. This does not alter the recorded behavioral comparisons.

## Checks completed

- Recomputed paired contrasts and corrected strata from committed records.
- Independent factual/editorial review of counts, native/added-goal scope, intervention semantics, and claims.
- Local LaTeX build: four pages including references; no unresolved references or overfull boxes.
- All four rendered pages inspected; scientific figures are vector PDFs.
- Overleaf compiled successfully to four pages; downloaded PDF text matches the local draft after whitespace normalization. `QA.json` records this verification.
- Old Overleaf source downloaded as a local backup before adding this draft. No experiment jobs or paper submissions launched.

The current PDF is ready for author review. The requested videos can replace the small pilot illustration or support an optional workshop video, without changing the statistical results.
