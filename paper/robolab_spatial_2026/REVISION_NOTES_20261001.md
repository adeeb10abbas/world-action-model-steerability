# Revision for Esmaeil — 1 October 2026

Read `revision_esmaeil.tex`. This is a separate proposal based on the current Overleaf manuscript and its 30 unresolved comment threads. The existing `main.tex`, its tracked changes, and its comments are preserved. The four-author list and General Motors Robotics affiliation from the coauthor version are retained.

## Recommended argument

The paper should make three connected claims, with the numbers supporting each claim:

1. **Competence under one instruction does not establish consistency across equivalent instructions.** The paired comparison fixes the physical task and isolates a linguistic reformulation. The 12.2-point average difference is evidence for this behavioral gap, rather than the paper's entire contribution.
2. **An aggregate score can conceal relation-specific failures.** Opposing effects cancel within the cube scene. A zero average there does not mean wording is irrelevant, while the large mustard effect does not justify a universal prompting rule.
3. **A scored arrangement is not a complete measure of instruction following.** A relation can become true through moving the reference object, and an attained arrangement can be lost under continued control. Evaluation should separately check the requested object, resulting arrangement, and final outcome.

These claims now lead the Results paragraphs and carry through the abstract, introduction, discussion, and conclusion. A possible explanation—dependence on familiar object–relation combinations—is presented as an interpretation to test, not an established internal mechanism. We do not claim WAMs are worse than VLAs or that a forecast mechanism caused the effects.

The mustard montage remains Figure 3. The cube/bowl montage moves to Appendix D, with its scoring explanation and the six uncropped source frames. Bold run-in paragraph headings have been removed from the main narrative. Overall success rates remain in Figure 2.

## Response to every comment thread

Times refer to Esmaeil's 28 September Overleaf comments. Repeated times distinguish different anchors. Comments remain open for coauthor review.

| # | Time / concern | Change in proposed revision |
|---|---|---|
| 1 | 1:09 — abstract description categories unclear | Concrete mustard-right / box-left example appears before the result. |
| 2 | 1:09 — what is the metric's denominator? | Abstract calls it the proportion of runs reaching a stable placement; Methods defines the binary check and averaging. |
| 3 | 1:13 — execution examples unclear | Abstract explicitly says moving the wrong object and losing an attained arrangement. The evidence concerns executed robot behavior, not verbal context. |
| 4 | 3:05 — mover sounds like robot (table) | Rename to target-first, with target defined as the object the robot must move. Retain S as the recorded condition identifier. |
| 5 | 1:53 — D versus I? | Explain what D–I tests and add estimates, intervals, and a plot in Appendix C.1. Mark this added analysis as exploratory. |
| 6 | 3:42 — critical: tech report, no story | Rewrite Methods as a connected experimental argument and Results around the three claims above; rewrite Discussion and Conclusion. |
| 7 | 1:45 — missing Methods motivation | Add an opening paragraph tying repeated physical starts to the instruction-sensitivity question and the scoring examination. |
| 8 | 1:47 — explain scenes and goals | Name all four scenes and tasks in the main text; add scene images, a scene/goal table, and all 36 instructions in Appendix A. |
| 9 | 1:59 — why use RoboLab wording? | Define D as the benchmark's short original instruction where available, serving as the baseline. Do not invent diverse-human provenance. |
| 10 | 3:05 — mover naming (prose) | Use target-first consistently throughout prose and new figures. |
| 11 | 1:56 — dense definition | Explain D, then S, then I in separate connected sentences, tied to Table 1's exact example. |
| 12 | 2:10 — where are cameras? | Specify wrist-mounted and two fixed exterior views of the workspace in Appendix B; retain native camera configuration across instructions. |
| 13 | 2:13 — where are full settings? | Point to Appendix B, which includes model settings, chunk execution, request seed, durations, and scoring. |
| 14 | 2:26 — unrelated direction sentence | Place the robot-frame convention beside the spatial outcome definition and scene details. |
| 15 | 2:27 — analysis or check? | Distinguish the any-time placement check from the separate episode-end outcome. |
| 16 | 2:26 — ambiguous “it” | Replace shorthand with the requested arrangement, target object, or explicit criterion as appropriate. |
| 17 | 2:27 — relative positions? | Explain that either object's motion can change the relative arrangement; give the cube/bowl example. |
| 18 | 3:03 — what is a matched pair? | Define paired runs as resetting robot state, object poses, and initial observations before each instruction for the same model and goal. |
| 19 | 3:13 — naming and S abbreviation | Introduce target-first (S) in Table 1 and use S/I for the comparisons thereafter. |
| 20 | 3:15 — colon-heavy AI formatting | Remove main-text run-in headings and write ordinary paragraphs with topic sentences. |
| 21 | 3:17 — abstract statistical explanations | Explain positive S–I in the main text; Appendix B adds a worked binary example (+1, −1, 0), weighting, and bootstrap units. |
| 22 | 3:20 — initially true unclear | Say some goals already hold at reset; list the three goals and counts in Appendix B and mark them in Figure 2. |
| 23 | 3:21 — Methods lacks flow | Follow question → scenes → wording intervention → paired runs → outcomes → comparison. |
| 24 | 3:26 — Results assumes insider context | Begin with an interpretable claim, then evidence, then its meaning; avoid opening with unexplained coefficients. |
| 25 | 3:38 — narrow results, no generic insight | Add cancellation of opposite effects and the distinction between spatial placement and intended manipulation. |
| 26 | 3:30 — name SIMPLER | Explicitly name SIMPLER in the controlled-simulation discussion. |
| 27 | 3:31 — repeated undefined matched terminology | Define pairing once in Methods and avoid unexplained “matched execution” shorthand. |
| 28 | 3:33 — Discussion format | Replace compressed run-ins with three connected paragraphs. |
| 29 | 3:36 — deeper implications | Discuss consistency alongside competence, why one prompt rule is inadequate, and what success criteria must preserve. |
| 30 | 3:29 — actionable Conclusion | End with testing several descriptions per goal, object identity, and the final arrangement as the concrete takeaway. |

## Expanded appendix

- **A:** scene overview, all goals, starting conditions, durations, and all 36 exact tested prompts.
- **B:** inference settings, scoring definitions, initially satisfied goals, worked paired example, averaging and uncertainty.
- **C:** added D–I comparison, relation-specific effects, any-time versus end outcomes, and complete per-goal/model counts.
- **D:** the second montage, selection/time/crop provenance, and uncropped execution frames.
- **E:** the original forecast question, annotation change, window selection, model inputs, VLM agreement, label coverage, diagnostic comparisons, controls, measurement limitations, and a concrete next-step analysis.

The forecast result is conditional: the automatically extracted features did not improve the recorded diagnostic. Low annotator agreement is not proof of poor forecast quality, nor is agreement between two VLMs a correctness standard. Timing/camera correspondence and automated failure detections still need validation. The original question and post-outcome change in paper focus are documented in the appendix.

## Remaining material

The existing execution frames and all recorded numerical analyses are included. Forecast contact sheets/videos are not available in this checkout. A read-only retrieval attempt reached a cluster-authentication requirement; no cluster jobs or new robot episodes were launched. `revisions/20261001/forecast_packet_retrieval_manifest.json` records two deterministic packets, their exact server paths, and requested files. These can be added as qualitative examples after retrieval and timing checks; they are not necessary to compile this revision.

We also retain the evidence limits instead of silently resolving them: the compact FLUX receipt lacks a full executed-weight revision, the diagnostic is conditioned on fitted predictors and noisy annotations, and no WAM-versus-VLA comparison was run.

## Files and build

Compile `revision_esmaeil.tex` with pdfLaTeX/BibTeX (or `latexmk -pdf revision_esmaeil.tex`). Use the existing CoRL style, bibliography and two original result plots, plus `revision_assets/`. No margin or font-size changes were made to the main manuscript. The intended layout is four main pages, references beginning on page 5, and appendices thereafter. See `revisions/20261001/FINAL_QA.json` for verified page count and synchronization status.
