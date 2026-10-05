# Forecast media integrated on 5 October 2026

## Source and selection

Source commit: `155be5a` on `codex/nano-stock-workstation-20260926`. The two examples were selected before media inspection by the episode-identifier ordering recorded in `forecast_packet_retrieval_manifest.json`:

- Edge: `RWS-E3-S1-C01-B-D`, packet `Aef9bebaab690`.
- FLUX: `RWS-F3-S1-C01-B-D`, packet `A5ee6df16bd49`.

`forecast_media_provenance.json` and `forecast_media/verification.json` retain the request/action/camera evidence and 165 passing checks. The committed compact-media and eight original figure file hashes were independently checked against the provenance. The original evidence files, model outcomes, VLM labels, selection rule, and earlier failed retrieval record remain unchanged. This note supersedes only the earlier status that the media were unavailable.

## Publication integration

Appendix E now includes two readable prediction/execution figures, one figure preserving the original annotation imagery, a table of the original relation labels, and an explanation of measurement limitations. The publication derivatives are built by `build_forecast_publication_figures.py`. Raw pixels and the original legend are not corrected.

The source was based on a fresh read of live Overleaf `rev1.tex`, preserving coauthor changes through 4 October. Only the forecast appendix was replaced in the editor. The canonical local `main.tex` was untouched. Live-source readback matches the local revision. Compilation and page counts are recorded in `FINAL_QA.json`.

## What is established

Within each example, the prediction, command prefix, camera, and nominal frame-to-action mapping match. Frame k corresponds nominally to execution after k actions at 15 Hz. Frame 0 is reconstructed. Both examples begin at request 1 after each model has already executed its first chunk, so only their episode-start state is shared across models.

## What remains unresolved

These two checks do not establish alignment of all 864 forecasts, generated-motion pace, or annotation accuracy. Original legend numbers overlap arrows or other object circles. Two of six free-text responses misnumber objects, and one structured relation names the cube itself. All six structured moving-object fields identify object3, but this does not validate their spatial-relation labels. Presentation ambiguity is a plausible confound, not a demonstrated cause of the full-study disagreement.

No policy episodes, new VLM annotations, or cluster jobs were run for this integration.

The latest coauthor text overflowed the main paper by three lines before integration. Reducing paragraph spacing from 5.5pt to 2.5pt in the main paper restored four pages without changing wording, font sizes, margins, or figures. Appendix paragraph spacing remains 5.5pt. All new scientific text and graphics are confined to Appendix E.
