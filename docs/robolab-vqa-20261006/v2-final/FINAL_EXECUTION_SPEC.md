# RQA V2: final execution specification

**Design v2.0 · October 6, 2026 · handoff only, no V2 inference completed**

## 1. Purpose and stopping boundary

Produce a defensible, compact diagnostic of the reference-language effects already observed in RoboLab policies. Fix the known measurement problems once, then stop. This is a follow-up designed after reading V1 results, using the same observations and instructions; it is not an independent replication or a retrospective replacement of V1's primary endpoint.

The user authorized a final instruction set for execution agents. Publishing this specification does not launch jobs from the authoring chat. At dispatch, complete implementation, bounded inference, analysis, reporting, and GitHub delivery. Resolve routine engineering decisions without repeated design questions. Do not introduce new models, public benchmark sweeps, training, robot episodes, simulator renders, prompt search, or manuscript edits. No automatic V3, even if C2 remains uninformative.

Questions to settle:

1. Does Edge recover instruction roles and relations when output syntax is enforced?
2. Does adding image content, camera-orientation text, or both change instruction interpretation?
3. With a direct current-state question and counterbalanced answer codes, can the readouts distinguish matching from nonmatching arrangements?
4. Which visual items are actually answerable from the supplied views?

## 2. Authoritative evidence and immutable history

Start from the completed R1 results at repository commit `acbe7ce13947f43b52ac0585bf9e6929579e8c83`, or a descendant containing them. Inspect remote changes and integrate normally; never reset or force-push shared work.

Read these repository-relative sources:

- `docs/robolab-vqa-20261006/EXPERIMENT_GUIDE.md` and `IMPLEMENTATION_RECORD.md` for definitions and deviations.
- `docs/robolab-vqa-20261006/question_catalog.json` and `frame_selection.json` for exact instructions and fixed frames.
- `artifacts/robolab_vqa_20261006/release_r1/` for synchronized frames, images, queries, labels, and audit templates.
- `artifacts/robolab_vqa_20261006/eligibility/eligibility_audit.json` for checkpoint identity.
- `reports/robolab-vqa-20261006/runs/r1-20261006/` for full results, lane manifests, receipts, and the durable raw-artifact index.
- `experiments/robolab_vqa/` and `tests/robolab_vqa/` for the existing implementation.

R1 release content hash: `1e691df6b85576e0d75925cc7902a1f4e303267098483a81726f6ff63cda3046`. Verify it. Raw files were indexed under `/data/users/ali/rqa-20261006` on cluster PVC `211247-prod-pvc`; resolve their current accessible location and hashes rather than assuming an old pod exists.

Preserve R1 raw answers, scores, release, and versioned report. Save V2 under new release/run paths. Corrections to labels or normalization must be versioned, explained, and reported alongside the original results. Never silently reinterpret an invalid R1 answer as correct.

## 3. Models and data scope

Run exactly these distinct readouts, with R1 weights, processors, templates, BF16 settings, and native heads:

| Lane | Interpretation |
|---|---|
| `N3-policy` | Executed Nano reasoner; identical to its verified Qwen3-VL-8B upstream component |
| `E3-policy` | Executed Edge reasoner; identical to the verified Edge base reasoner |
| `F3-qwen3vl4b` | FLUX's frozen shared component; text-only B2 is relevant to its language path, image tests remain auxiliary |

Do not rerun identical upstream/base copies. Do not add `N3-base`: it is not the matched pre-robot parent of `N3-policy`. Reuse the lineage evidence and verify loaded parameter digests. Preserve Edge's documented packaging-only loader fix; do not alter weights or attach a head.

New inference uses only S1/S3/S4: **24 physical starts, 10 goals, 30 exact DIR/TF/RF instructions, 24 initial and 48 fixed secondary view sets**. Each view set contains the same three synchronized views as R1. S5's stacking/support ambiguity remains a separate V1 result, with no new S5 queries. Preserve exact instruction bytes, including whitespace, and historical IDs; display DIR/TF/RF.

Before scoring, verify all 30 instruction tuples and 16 placement-control tuples directly against their wording and the catalog. Record target/reference swaps, converse mappings, and the support-relation distinction explicitly. Use no evaluated model as a gold-label judge. If there is a demonstrable catalog error, record a versioned amendment before inference; do not change labels to agree with responses.

## 4. Answerability review and R1 answer audit

Prepare a blinded review packet for all 72 view sets, covering all 240 frame–goal relations before exclusions. Hide model identity, model answers, original action outcome, and frame-selection outcome. Show the exact evaluation-resolution views, camera legend, and neutral object/relation questions. Reviewers first record their own visible relation and confidence without seeing the simulator label; compare with the simulator label afterward.

For each frame–goal item record: both objects identifiable, robot-frame relation discernible, any required support/contact visible, boundary/occlusion/transit ambiguity, proposed visible relation, discrepancy with geometry, reviewer ID/type, and reason for exclusion. Preserve R1 synchronization, calibration, boundary, and transit exclusions. Additional ambiguity exclusions apply identically to every model and equivalent question form. Geometry remains the source of the physical predicate; a view that cannot establish it is unanswerable, not a model failure.

Use the existing audit requirements: one human reviews all applicable sheets; a second human reviews all flagged sheets and the applicable fixed R1 second-review sample. Resolve disagreements without model responses; unresolved items are unanswerable. Do not select review items by whether the model was right.

An execution agent can inspect the images and populate a **machine-review** ledger, but must not claim a human audit. If no human review is available, finish the finite run and report automated/machine-reviewed visual results as provisional. Deliver one complete human-review packet and a CPU-only rescore command. Do not repeatedly pause the overall task or fabricate reviewer sign-off. Human review can later finalize the mask without new inference. Record partial versus complete human coverage separately.

Keep V2 responses sealed from reviewers until the audit mask is locked where feasible. If a later reviewer has seen answers, disclose the review as unblinded; do not present it as prospective. Report original-mask and revised-mask results and exclusion counts, so review cannot silently improve scores. B2's requested tuple is defined by text; visual ambiguity alone does not exclude B2 items with available inputs.

Separately inspect the existing Edge B responses on the V2 scene set (up to 414 original/placement text/image requests). Classify failures as JSON structure, object vocabulary, relation vocabulary, multiple/conflicting answers, truncation, or other. This is a format audit, not an outcome-dependent parser repair. Preserve raw excerpts and original strict scores. Use no free-form model judge to rescue answers. Do not claim that every format failure was semantically correct.

## 5. B2: format-aided instruction interpretation

Use the exact R1 instruction-understanding wrapper, coordinate preamble, sorted scene object vocabulary including distractors, and full relation vocabulary. Preserve the original instruction verbatim. Change generation to **schema-constrained JSON decoding** through the installed inference engine:

- Exactly one object with `target`, `reference`, `relation`; all required, no additional keys.
- Target/reference enums each contain the complete scene object vocabulary, not only the correct pair.
- Relation enum remains `left_of`, `right_of`, `in_front_of`, `behind`, `on_top_supported`, `stacked_on`, `unknown`.
- Do not enforce target/reference inequality or use the gold tuple to prune choices.
- No worked examples, chain-of-thought request, answer-conditioned retries, or model-specific prompt.

Use the same constrained protocol for all three lanes. Validate the actual engine's schema support on the existing development fixtures and log the grammar/schema hash and backend. If unsupported after the engineering cap, mark that lane unsupported for B2; do not silently substitute a different protocol. Constrained decoding improves format compliance by construction; report semantic accuracy separately. It is an assisted readout, not evidence that free generation is repaired. R1 versus B2 is a decoding-protocol comparison, not a training effect.

For the 30 original instructions run this full factorial in every lane:

| Condition | Images | R1 camera-description text | Queries per lane |
|---|---|---|---:|
| T | absent | absent | 30 |
| H | absent | present | 30 |
| I | initial views | absent | 240 |
| IH | initial views | present | 240 |

Construct IH from the R1 B payload. Produce H by removing only image segments; I by removing only the three camera-specific header strings; T by removing both. Retain the same common scene-introduction text, coordinate preamble, instruction, object vocabulary, and whitespace rules in all four. This keeps text identical within each image contrast, including any camera-view introductory wording when pixels are omitted. Deduplicate identical no-image payloads; never count copies across eight starts as independent generations. Freeze and verify rendered prompt text equality for IH/H and I/T after removing image markers, plus exact header-only differences for IH/I and H/T.

Also repeat the existing 16 placement-only control instructions under T and IH: 16 text requests and 128 initial-image requests per lane. No new placement strings, no secondary B2, and no extra header factorial for placement controls.

Report tuple and field accuracies; TF–RF gap and both-correct counts; converse-relation errors separately from support-label swaps. Report the fixed eight lateral/front–behind goals separately from the full ten-goal set. Placement controls are a different construction and do not prove that all noun-order effects are absent.

The image contrasts are I−T and IH−H; the header contrasts are H−T and IH−I, with identical underlying instructions. Reuse each no-image answer against the corresponding initial cells for paired contrasts and explain the reuse. These test adding image content within this QA interface; they do not reveal the policy's internal action computation.

## 6. C2: one fixed current-state question

Keep exact original instructions, R1 coordinate definitions, camera presentation, and geometry labels. Do not supply the correct tuple, a B2 prediction, an object-position description, or the original action result.

Use this fixed wrapper after the common preamble and view segments:

```text
Instruction:
<EXACT_INSTRUCTION>

Treat the instruction as a description of a desired spatial relation between the named objects.
Evaluate only their arrangement in the supplied current camera views. Whether anyone moved an object,
whether a robot action occurred, and whether the arrangement was held over time are irrelevant.

Which statement is supported by the current views?
<ORDERED_OPTIONS>
Return exactly one code: A, B, or U.
```

Options in order 0:

```text
A: The current arrangement matches the spatial relation requested by the instruction.
B: The current arrangement does not match the spatial relation requested by the instruction.
U: The supplied visual evidence is insufficient to determine whether it matches.
```

Order 1 exchanges the two complete A/B option meanings; U stays unchanged. Run both orders for every item in fresh conversations. Constrain output to exactly one of `A`, `B`, `U`; parse to match/nonmatch/unknown using the manifest's mapping. The grammar must allow every option irrespective of the gold label. Do not choose whichever order scores better, vote across orders, or request explanations.

Run all 30 original instructions on their applicable initial and fixed secondary frames: 240 initial + 480 secondary requests, doubled for option order. Retain both banks separately. Also run 30 no-image requests per order, formed by removing only image segments from the initial-condition C2 payload, retaining the camera text. Deduplicate these 60 no-image requests per lane; the expected evidential response is U. Score their answer distributions and reuse against labels only as a disclosed language-prior control.

The wrapper and option orders are fixed now. Qualify input receipt and schema mechanics on existing development images; do not tune the wording based on accuracy. Wrong answers on development fixtures are not a reason to replace the prompt. If C2 remains constant, biased, or near baseline, retain the result and stop.

## 7. Scene understanding, metrics, and inference limits

No new A inference. Rescore the existing A answers on the reviewed S1/S3/S4 mask, preserving the original-mask scores. Keep answerability coverage and provisional status visible.

The V2 C2 diagnostic endpoints are balanced accuracy and the paired TF−RF correctness gap, separately for initial and secondary banks. Report positive/negative recalls, full answer distributions, constant-match/nonmatch baselines, both-correct TF/RF rate, and semantic agreement across option orders. Average correctness across the two orders within each item before scene/start aggregation; order duplicates are not independent samples. Show each order separately as a bias check. Unknown and delivered invalid answers are incorrect on answerable items; missing infrastructure responses remain missing with coverage reported.

Additionally use existing labels to form truth-changing frame pairs within the same physical start and goal. Select at most one pair per start–goal: earliest matching and earliest nonmatching observation from its initial/50%/100% frames, with frame ID breaking timestamp ties. No substitutions or selection based on responses. Report the finite pair count and whether both frames are classified correctly, separately by form, averaging over option order. This is a secondary temporal discrimination check, not a pooled initial/secondary primary score. Report zero available pairs as unavailable. Initial truth is constant within each goal, so initial balanced accuracy alone cannot prove image use.

For all paired model/wording/condition comparisons use common available items and disclose losses. Match R1 weighting: equal goals within scene and equal scenes; average repeated frames/orders within start–goal as applicable. For class metrics normalize declared item weights within each gold class, then average the two recalls. A one-class subset has undefined balanced accuracy. Also show raw integer denominators.

Use 10,000 physical-start bootstrap replicates within each of the three scenes, seed 6106; retain all conditions, goals, frames, answer orders, and model lanes from a sampled start. Use identical resamples for paired comparisons. These intervals condition on fixed scenes and wording templates. Text-only instruction results are finite counts over ten TF/RF goal pairs, not hundreds of independent language examples. Do not use repeated deterministic answers to imply broad precision.

Reuse R1 decoding except for the declared constraints: greedy, BF16, thinking disabled, at most 256 generated tokens, one completion, unchanged model/processor. No sampling sweep, voting, external tools, retrieval, prompt rewriting, or new head. Record token use, completion reason, input hashes, grammar hash, and effective settings. Use fixed query ordering by SHA256 of `6106|query_id` within bank; queries are independent conversations.

| Work | Per lane | Three lanes |
|---|---:|---:|
| B2 original T/H/I/IH | 540 | 1,620 |
| B2 placement T/IH | 144 | 432 |
| C2 initial, two orders | 480 | 1,440 |
| C2 secondary, two orders | 960 | 2,880 |
| C2 no-image, two orders | 60 | 180 |
| **Evaluation ceiling** | **2,184** | **6,552** |
| Qualification ceiling | 6 | 18 |

Exclusions/deduplication/unsupported lanes can reduce counts, never increase them. At most one retry is allowed for an infrastructure-missing request, with a new attempt ID; never regenerate a delivered answer. There is a shared budget of 30 retry attempts across all lanes; no repeats of qualification calls. At most three consecutive infrastructure failures stop the lane. The hard ceiling is **6,600 generation attempts**: 6,552 distinct evaluation IDs, 18 fixture calls, and at most 30 infrastructure retries. Two engineering hours maximum per incompatible lane, then publish the limitation and continue eligible work. Unused capacity cannot be reassigned to extra questions or prompt experiments.

## 8. Implementation and release gates

Extend the existing package with explicit versioned V2 entry points/configuration. V1 defaults and recorded outputs must remain reproducible. No unrelated refactoring. Implement a CPU-only review/rescore path so human annotations never require rerunning models.

Before evaluation, save and push:

- V2 exact rendered queries, full input segments, image bindings/hashes, original instruction hashes, bank/form/condition/order IDs, gold and eligibility metadata kept outside model payloads.
- All output schemas and option mappings, parser version, decoding/runtime/adapter identities, loaded model digests, source R1 hash, and data/audit release hash.
- A full planned-query manifest including excluded and unsupported rows with reasons; no silent denominator drops.
- A small validation receipt with exact count checks, byte-preserved instructions, paired input equality, correct order mappings, no gold leakage, and source-frame alignment.

Meaningful CPU checks must cover: counterbalanced codes mapping to identical semantics; unknown/invalid/missing accounting; duplicate/extra JSON key rejection; complete distractor vocabularies; paired header/pixel contrasts; no-image deduplication; a hand-calculated balanced-accuracy and paired-gap example; shared-start bootstrap grouping; and non-overwrite of R1 paths. Inspect all relevant test failures. Do not add tests that merely restate implementation details.

Run at most six qualification calls per lane from existing development material to check B2/C2 schema mechanics, image receipt, and resource use. Freeze the final code/schema/release and push before the first evaluation query. Native structured-output API details must be checked in the installed environment; this handoff does not assume an unverified command/API exists. Publish the actual verified command afterward. Do not silently fall back to free-form generation.

If a genuine implementation fault is discovered after evaluation starts, stop the affected component and retain its outputs. Fix the defect in a versioned amendment. Reuse unaffected responses; any required rerun of delivered queries requires a separately disclosed author decision, not an automatic outcome-driven loop. Complete the rest and publish a partial report if necessary.

## 9. Reporting and final stop

Create `reports/robolab-vqa-20261006/runs/r2-final-<execution-date>/` with a complete `REPORT.md`, `PAPER_TABLE.md`, `INTERPRETATION.md`, coverage/metrics CSV or JSON, review ledger, full manifest, hashed durable raw-artifact index, and completion receipt. Record actual dates rather than assuming execution occurs on October 6. Append to `RUN_INDEX.json` and update the top-level report to compare V1 and V2 while linking the unchanged R1 report. Add candidate findings as unreviewed; leave author decisions blank.

The compact table must keep N3/E3/F3 visible, distinguish FLUX's language-path versus auxiliary image tests, and show B2 text counts, relevant image-condition TF/RF accuracy, C2 balanced accuracy and gap, coverage, and audit status. Save detailed header/pixel and option-order results outside the four-page manuscript.

Answer these questions plainly in the interpretation:

- Was Edge previously blocked mainly by answer format, or does instruction difficulty remain under the assisted readout? Do not over-attribute a cross-protocol change.
- Do reference-first errors remain with matched headers, and what do the pixel/header contrasts actually support?
- Does C2 distinguish both truth classes and changing frames, or remain uninformative? Preserve V1's uninformative prespecified primary diagnostic explicitly.
- Which visual conclusions have human support, and which remain provisional?
- What can be included in a four-page paper, and what remains an unresolved measurement limitation?

Keep the original policy wording effect central. Do not infer that robot adaptation degraded unchanged reasoner weights, that co-training helped, or that a QA error caused an action failure. Do not turn a missing private training dataset into a new required experiment. No new action joins are needed to finish V2; existing joins remain descriptive and confounded.

Commit/push implementation, frozen protocol amendments, small manifests, all compact results, and complete reports to `adeeb10abbas/world-action-model-steerability`, branch `codex/nano-stock-workstation-20260926`; verify the remote commit. Keep weights, media, large raw output, credentials, and environments outside Git with durable hashes and paths. Publish failures and provisional status as carefully as favorable outcomes. Do not edit Overleaf or manuscript files.

Finish with counts planned/delivered/missing/valid, actual GPU time and commands, review status, GitHub links and commit, and the strongest supported statement plus remaining limitations. **After this bounded pass, stop. A persistent failure is a final reported outcome, not permission to design V3.**
