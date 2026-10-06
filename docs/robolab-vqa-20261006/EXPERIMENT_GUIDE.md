# RoboLab VQA diagnostic: execution guide

**RQA-20261006 · protocol v1.0 · design locked October 6, 2026**

## 1. Question, scope, and claim

**Does the wording sensitivity observed in the robot policy also appear when its available language/vision-language components interpret the same instructions and judge the same scenes?**

Run three separate tests: A, current scene relations; B, requested object roles and relation; C, whether a scene exhibits the arrangement requested by an instruction. Compare matched TF/RF items within each checkpoint and descriptively compare those effects with the already-recorded action outcomes. DIR provides an additional descriptive baseline.

This is a new, post-policy-results diagnostic. Freeze its queries, labels, exclusions, decoding, and analysis before reading its model answers. Do not describe it as prospectively preregistered before the original robot results. The design borrows RoboSpatial's configuration-question approach, but these are custom RoboLab data and scores, not official RoboSpatial benchmark scores.

**Limits:** inference only; saved observations only; no training, learned probes, new action runs, new scenes, forecasting evaluation, prompt search, public-benchmark sweep, or extra policy family. The user will dispatch execution agents separately. Preparing this packet launches nothing. No manuscript edits are part of execution.

## 2. Authoritative inputs

Use these repository-relative inputs, resolving their existing cluster/archive locations without copying old absolute paths blindly:

| Input | Use |
|---|---|
| `paper/robolab_spatial_2026/revisions/20261001/exact_tested_prompts.json` | Exact executed instructions; includes a trailing space in S4-TOP-D |
| `artifacts/robolab_workshop_20260926/release/release.json` and its bound states/rows | Executed release, state identities, original receipts |
| `paper/robolab_spatial_2026/analysis/episode_outcomes_corrected.csv` | Existing outcomes and corrected initial-truth strata |
| `paper/robolab_spatial_2026/revisions/20261001/runtime_settings.json` | Executed model source/weight evidence and its known gaps |
| `experiments/robolab_workshop/catalog.py`, `scoring.py`, and the executed geometry implementation | Object roles and predicate definitions; pin executed versions |
| `docs/robolab-workshop-20260926/EXECUTION_RECORD.md` | Deviations from the old launch plan |

Use S1, S3, S4, S5 only: eight starts each, 32 physical starts, 96 start–goal cells, 36 unique original instructions, 288 start–goal–form cells. S2 was omitted from the executed study. The historical 42-prompt/40-start plan and SGW-01 camera/layout catalog do not apply. New display labels are `DIR/TF/RF`; retain original source IDs and map `D/S/I` to these labels without changing prompt text or historical files.

The packet's hashes bind the local evidence used to prepare this design. An execution agent must resolve any mismatch rather than silently updating those hashes. Do not treat a historical planning pin as proof of which weights executed.

## 3. Image banks and fixed selection

### Primary bank: initial observations

Recover the common, cached request-0 observation for each of the 32 accepted starts. Verify its state identity and raw camera hashes across original model/goal/form cells. Use the same three native RGB views—wrist, left exterior, right exterior—at one physical timestamp. Views are simultaneous inputs, not three independent samples. Prefer saved lossless observations to re-encoded video. Do not substitute decoded predicted frame zero or a forecast contact sheet.

If initial images differ, investigate the provenance without model-answer access. Freeze one source only after establishing that it represents the same original physical reset; otherwise mark the affected start unavailable for a matched comparison. Do not render new starts to fill missing evidence.

### Secondary bank: saved rollout observations

`frame_selection.json` fixes one source episode per physical start, then selects 50% and 100% of that scene's scheduled horizon. This gives at most 64 additional three-view observations, from 32 existing episodes. Selection uses IDs alone, not success, predicted difficulty, or image appearance. Source policy and source wording are balanced as closely as possible by a deterministic rotation; goals rotate within scene.

The file specifies source episode and requested physical time. Agents still must resolve the authoritative completed attempt, video/observation paths, ticks, and hashes. Use the first saved synchronized observation at or after the requested time, within one original control tick (1/15 s); otherwise record it as unavailable. At the horizon use the observation after the last executed action, not the preceding request input. No replacement episode or success-triggered frame may be chosen. Missing/occluded frames remain in the coverage ledger.

Every evaluated model receives the **same** secondary bank, and every eligible instruction for that scene is queried on every selected observation. A frame's source goal does not restrict its questions. Do not give each model only its own resulting frames. Keep primary and secondary statistics separate. Secondary frames remain clustered with their original physical start.

### Presentation and coordinate frame

Keep original orientations, aspect ratios, camera order, and RGB values. No object numbers/arrows over object pixels, cropping away references, stretching, mirroring, or image-dependent enhancement. If native multi-image input is unavailable, use a fixed aspect-preserving panel with camera headers outside the image area, record this adaptation, and use the same panel for the entire comparison. Native model resizing remains allowed and must be logged.

All spatial language uses the original robot frame, not screen-left/screen-right. Verify axis signs from the pinned predicates and camera extrinsics; do not infer them from a displayed screenshot. Freeze a common task preamble explaining that in-front/behind mean closer to/farther from the robot and left/right use the robot's viewpoint facing the workspace. Add a common, scene-independent camera/robot orientation legend outside the images only if the view geometry otherwise cannot be resolved. Derive it from calibration, not object positions or answers, and freeze it before evaluation. Such calibration assistance is a disclosed VQA presentation difference from policy input, not evidence that the action pathway received the same information.

For S5, left/right bowl identities are established at reset and remain fixed after movement. Secondary bowl questions require an initial-view identity reference alongside the current views; label the initial and current times explicitly. If identity cannot be followed without guessing, mark the item unanswerable. Do not silently rename bowls by their current location. S5 is reported separately as described below.

## 4. Three tests and exact output contracts

Each query is a fresh conversation with no previous questions, answers, policy outcome, source-model name, or hidden goal label. Preserve the original instruction inside the wrapper byte-for-byte. `question_catalog.json` contains the exact strings and canonical role answers; the final query manifest must include the complete rendered wrapper, preamble, and image references.

### A. Scene understanding

Supply the current views and one question from the catalog, such as:

> Is the Rubik's cube to the left of the bowl?

Its equivalent converse is a separate fresh query:

> Is the bowl to the right of the Rubik's cube?

Fixed answer instruction: `Answer with exactly one of: yes, no, unknown. Judge the current visible scene in the robot coordinate frame.`

Use both formulations for each of the 12 catalog goals, with labels from the same physical predicate where equivalence is justified. A is a perception/reference-reversal control; its two forms are called `target_subject` and `reference_subject`, not original policy TF/RF instructions. Support and nesting require the visibility rules below. S5 scene questions explicitly describe nesting in both forms and are not substituted into the original policy instructions.

### B. Instruction understanding

Supply an original instruction and ask:

```text
Instruction:
<EXACT_INSTRUCTION>

Interpret the requested outcome, not the current arrangement. Return one JSON object:
{"target": "...", "reference": "...", "relation": "..."}
The target is the object the instruction asks to move. The relation is the target's
requested final relation to the reference. Use the provided object and relation vocabulary.
```

Provide the complete scene object vocabulary, including distractors, in a fixed neutral order. Use the same full relation vocabulary for every scene: `left_of`, `right_of`, `in_front_of`, `behind`, `on_top_supported`, `stacked_on`, `unknown`. Do not reveal the valid target/reference pair or restrict relation options using the current goal. The catalog fixes accepted strings; no free-form semantic judge.

Run B once text-only on all 36 unique instructions, then with initial views on all 288 original start–goal–form cells. Do not repeat the same text-only query eight times and claim eight independent observations. `stacked_on` records the linguistic request in S5; it does not establish that nesting and all support paraphrases are physically interchangeable. A separate ambiguity annotation accompanies S5.

Score each field and the complete tuple. In S5, the catalog assigns `stacked_on` to DIR/TF and `on_top_supported` to the literal RF request; preserve those distinct answers rather than forcing agreement. The historical intended goal remains recorded separately. Image-assisted B still primarily tests instruction interpretation; correct named-object fields alone do not demonstrate visual localization.

### C. Instruction plus scene — primary diagnostic endpoint

Supply the views and the exact original instruction:

```text
Instruction:
<EXACT_INSTRUCTION>

Does the current scene show the final spatial arrangement requested by this instruction?
Judge the arrangement now, not whether the robot moved the correct object or will succeed later.
Do not require a one-second dwell or infer an unseen action history.
Answer with exactly one of: yes, no, unknown.
```

Run all original DIR/TF/RF instructions on each initial observation, and then on each selected secondary observation from that scene. Main endpoint: C's paired TF-minus-RF correctness difference on semantically comparable initial-state items. Also report both-correct accuracy and balanced accuracy.

Run a small **no-image C control** on the 36 unique original instructions, using the same wrapper and coordinate definition but omitting images and image-specific legends. Reuse each response against the relevant frame labels; do not manufacture additional independent generations. Report answer/abstention distributions and accuracy separately. The starting layouts may have nearly constant truth for a given goal; a high C score alone is therefore insufficient evidence of visual use. Report within-goal label variation, the no-image result, and the secondary check together. No model fitting is involved.

## 5. Clause-placement control

The original TF/RF contrast changes both which object appears first in the relation clause and the relation vocabulary, such as left versus right. Preserve it exactly because it matches the paper. Add a separate small control that moves the reference clause while holding the directional expression fixed:

> Relative to the bowl, place the Rubik's cube to the left.
>
> Place the Rubik's cube to the left, relative to the bowl.

Use the 16 exact `reference_early/reference_late` strings in the catalog: two for each of the eight lateral goals in S1/S3/S4. Run B text-only, B with initial views, and C with initial views. This is a clause-order manipulation, with corresponding capitalization/punctuation changes; do not describe it as a perfect isolation of every syntactic variable. Keep its effect separate from TF/RF. Do not add support/nesting variants or run new policy episodes for these prompts. Their action effects remain unmeasured.

## 6. Gold labels, answerability, and the bowl caveat

Recover timestamp-aligned simulator object poses, role bindings, geometric predicates, and relevant contacts from saved records. Store predicate source/version, parameters, raw values, and label provenance. Gold labels must never be inferred from the tested model, old forecast VLM annotations, episode success, or a screenshot's apparent screen direction.

- A uses the instantaneous named relation. For support/nesting, retain the physical evidence needed for the actual words in the question.
- C uses the instantaneous arrangement explicitly requested by the instruction, including table support when stated and object support/nesting when applicable. Factor this from the original scorer; do not blindly reuse `stable_ever`, `stable_at_final`, or an all-purpose `goal` flag. Dwell, speed, and historical correct-object movement are not properties established by a single image. A and C labels can differ when C includes support requirements omitted from A.
- For lateral direction, retain the pinned directional-cone convention for correspondence to the study. Flag boundary cases before inference: within 5 degrees of the cone boundary or target/reference horizontal centers within 1 cm. Exclude these from answerable semantic scores, retaining counts and a separate all-geometry sensitivity table. Do not revise the margin after results.
- An unoccluded projected center is not sufficient visibility evidence. Review whether both objects, their relative placement, and any required support/containment are actually discernible in the supplied views. Hidden contact-force metadata may establish physical truth without making the image question answerable.
- Use `gold_label=yes/no` plus separate `answerable` and `exclusion_reason` fields. Ambiguous/hidden cases are unscorable for the visual endpoint, never automatically `no`. Keep a coverage denominator for every proposed question and remove equivalent pairs jointly from paired analysis.
- Before model inference, a human reviewer should inspect the 32 initial view sets and 64 selected secondary sets with the proposed labels and calibration. A second reviewer checks all flagged cases plus a deterministic 20% sample. Save adjudication and any unresolved cases. Agents may prepare the audit sheets; they must not claim automated inspection was human review. If reviewers are unavailable, inference may produce provisional results, but publication-ready answerability remains unverified and must be reported as such. No model answers may inform label changes.

**S5 semantic caveat:** “stacked on” and “underneath and supporting” can differ in whether nesting is required. Keep all 32 starts and all original strings in the dataset, but report S5 separately. The headline equivalent-wording contrast pools S1/S3/S4 (24 starts, 10 goals); the all-four-scene intended-goal table is a declared sensitivity result. Give S5 form-specific semantic labels when warranted and do not count a justified semantic difference as reference-language failure. This restriction is fixed before new model answers. The text-only instruction report retains all 36 items and shows S5 separately.

## 7. Model eligibility and comparison hierarchy

Prepare an eligibility matrix **before loading large inference jobs**. Prioritize the three existing policy families. At most six distinct readout lanes are allowed; tensor-identical lanes can share one evaluation after verification.

| Family | Planned VQA/text comparisons | Required qualification |
|---|---|---|
| N3 Cosmos3 Nano | Cosmos3-Nano base reasoner versus the reasoner from the executed DROID policy; optional exact upstream Qwen ancestor as the sixth lane | Trace the actual parent revision and tokenizer/vision components. Use the policy checkpoint's own weights and native text head. An upstream Qwen comparison spans more than robot adaptation and must be labeled accordingly. |
| E3 Cosmos3 Edge | Cosmos3-Edge base reasoner versus the executed DROID policy reasoner | Verify the exact backbone lineage, released predecessor, native VQA route, and all loaded weights. Do not substitute a guessed Qwen or generic Cosmos Reason model. |
| F3 FLUX 3 Action | The exact released shared Qwen3-VL-4B-Instruct component, if its executed identity is recoverable | Its released encoder is frozen and unmodified. The policy feeds text through it; camera evidence enters a different path. Standalone image VQA is an auxiliary capability control, not FLUX policy VQA. Text-only B is the closer component diagnostic. |

Public evidence motivating this audit: the Cosmos3 model cards describe native reasoner text/vision inputs; the Nano DROID recipe selects generation/action parameter groups for optimization; FLUX's card and code identify a frozen Qwen text encoder and its text-only policy call. These descriptions do not establish the identity of historical executed tensors. Links are in §13.

For each lane record parent/checkpoint revisions, tensor hashes, extraction key map, vision tower/projector, language model, text head, tokenizer/processor, prompt template, precision, preprocessing, and the actual camera/proprioception paths used in policy versus VQA. Record which components changed, which were frozen, and what co-training objectives are documented or unknown. Check policies' EMA choice where applicable. A fresh `main` revision is not a matched historical checkpoint.

If the relevant weights and processor are identical, say so; after a small deterministic output-parity check, run the bank once and reference that shared result. Do not present duplicate scores as independent evidence. If the native LM head was removed or cannot be restored from the **same** checkpoint/verified unchanged parent, mark VQA `unsupported`; do not attach a newly trained probe, swap in a convenient head, or score unsupported capability as zero. Extracted readout must match native text output on development fixtures before it is called equivalent.

FLUX's compact executed receipt has a missing checkpoint revision. Resolve it from retained files/hashes if possible. Otherwise label the shared-encoder run a released-component control with unverified historical identity, not a same-checkpoint comparison.

**Cosmos Policy and π0.5 are outside this scoped run.** Cosmos Policy is a different family from Cosmos3; its policy/world/value joint objective is not, by itself, evidence of generic VQA co-training or a native VQA head. Mark's training-recipe question remains only partially answerable here. This study cannot establish training-caused degradation or a causal benefit of co-training.

## 8. Scoring and analysis

Freeze parsing before inference. For A/C, trim surrounding whitespace and one terminal punctuation mark; accept case-insensitive exact `yes`, `no`, or `unknown`. Conflicting, verbose, truncated, or malformed outputs are invalid, not repaired with another model. For B, accept exactly one JSON object with the three required fields and catalog enum values; reject duplicate keys or missing fields. Log raw text. An explicit development-tested fenced-JSON normalization may be frozen, but no ad hoc post-result repair.

| Metric | Definition / use |
|---|---|
| Accuracy | Correct answers / answerable queries with delivered model responses, including invalid/unknown responses as incorrect |
| Balanced accuracy | Mean recall of gold `yes` and `no`; report each recall and support. Undefined where one class is absent—never substitute ordinary accuracy or a zero. |
| Tuple accuracy | All three B fields correct; also show target, reference, and relation accuracy |
| Paired gap | Mean within-item correctness(TF) − correctness(RF), in percentage points; A uses its own subject-order pair, placement control early − late |
| Both-correct | Fraction of complete answerable pairs with both answers correct |
| Disagreement | Fraction of pairs with differing parsed answers; diagnostic only, since consistent wrong answers also exist |
| Coverage | Proposed, answerable, queried, delivered, valid-format, unknown, invalid, and infrastructure-missing counts |

Primary analysis: C TF–RF accuracy gap on initial-state S1/S3/S4; report per eligible checkpoint and both-correct accuracy. B tuple gap and A subject-order gap localize the pattern. DIR comparisons, placement controls, S5, secondary images, and before/after checkpoint contrasts are descriptive diagnostics. Do not select the strongest checkpoint/endpoint as a new primary after inspecting answers. A near-zero difference with a broad interval is inconclusive, not proof of equivalence.

Match the paper's weighting: average questions/forms as appropriate within goal and start, goals equally within scene, then scenes equally. Show raw counts alongside these macro estimates. For balanced accuracy, compute class-specific weighted recalls over the declared evaluation set and average them; do not average undefined per-scene balanced accuracies. Report pooled-label versus per-goal class coverage so a one-class subset remains visible.

Use 10,000 percentile bootstrap replicates, seed 6106, resampling physical starts **within scene**, retaining all frames/goals/forms/checkpoints from each sampled start. Use the same bootstrap samples for paired checkpoint differences. State explicitly that intervals concern the sampled starts conditional on four fixed scene types and fixed prompt templates; they do not establish broad scene/language generalization. Text-only B has 36 unique instructions, not 288 independent observations: report finite-set counts and paired correctness tables without a state-bootstrap CI. For no-image C, reused answers may be scored against frame labels, but uncertainty is conditional on those fixed answers.

No p-value fishing or default significance stars. If an inferential multi-checkpoint significance claim is later requested, register the family and multiplicity procedure before reading the relevant results. The default delivery is paired estimates and descriptive intervals.

Join initial-state VQA records to original action outcomes using scene/start/goal/form and a documented checkpoint-family mapping. Show descriptive understanding-correct/action-success and understanding-correct/action-failure counts per model. Preserve `stable_ever` and `stable_at_final` as existing arrangement outcomes. Neither alone verifies manipulation of the requested object; do not rename them complete instruction success. Report initially satisfied goals separately using corrected registry labels. Do not recompute action labels or compare post-action VQA judgments as if they were independent pre-action predictions.

## 9. Finite workload and inference settings

Counts are query invocations per fully eligible distinct checkpoint, before visibility exclusions and deduplication:

| Part | Maximum calls |
|---|---:|
| A: initial, 96 start–goal cells × 2 forms | 192 |
| B: original text-only + original initial-image | 36 + 288 |
| C: original initial-image | 288 |
| Placement controls: B text-only + B image + C image | 16 + 128 + 128 |
| C: no-image original control | 36 |
| **Primary bank and controls** | **1,112** |
| Secondary A + C: two additional observations per start | 384 + 576 |
| **Total** | **2,072** |

No secondary B repetition or secondary placement sweep. Six lanes maximum means 12,432 evaluation calls, plus at most six existing-development fixture queries per lane; tensor identity or eligibility can reduce this. Counts include S5 items even though their effects are reported separately. A frame set is not an independent scene.

Use deterministic native text decoding, greedy when supported, BF16 where supported, no self-consistency voting, external tools, retrieval, prompt upsampling, or answer-conditioned retries. Ask for short answers without chain-of-thought. Freeze a maximum 256 generated tokens for an instruct/non-thinking readout. If a released native reasoner requires a thinking mode, give it a separately declared fixed budget up to 2,048 tokens and label this difference; do not truncate it silently or vary the budget after evaluation. Template and mode must be matched within a base/policy pair. Record seeds, effective options, token usage, and truncation.

Hardware: reuse the user's cluster environments and checkpoint cache, resolving current paths and scheduler configuration at dispatch. Prefer one inference worker per eligible model on an available GPU that fits its native BF16 readout; select tensor parallelism only after a memory estimate. Do not hard-code old pod names, occupy unrelated GPUs, or change global environments. No simulator GPU or action server is needed. Do not fabricate runtime/GPU-hour estimates: measure fixture latency and project the remaining fixed query count before the full queue.

Allow at most two engineering hours per unsupported extraction/adapter lane, then report the blocker and continue eligible lanes. Development checks use existing D00/pilot material only, never held-out answers for tuning. An execution agent can resolve a documented packaging or transport bug, but must version the adapter and retain affected outputs. Preserve semantic failures and invalid generations; do not regenerate until they become correct. Resume only missing requests after infrastructure recovery, preserving attempt IDs; skip validated completed queries. Stop at the finite manifest boundary.

## 10. Implementation contracts and release order

Put new runner code under `experiments/robolab_vqa/`, its meaningful checks under `tests/robolab_vqa/`, and documentation here. These new runtime modules are **not supplied by this packet**. Do not edit the original policy study's evidence or scorer in place.

1. **Inventory:** resolve original completed attempts, cached initial images, saved rollout media/ticks, camera calibration, initial bowl roles, and eligible checkpoints. Return `inventory.json` and `model_eligibility.csv`.
2. **Prepare:** bind `frame_selection.json` to timestamps and evidence; generate exact queries from the catalog and fixed wrappers; create gold/visibility audit packets without model names or outcome labels. Return the proposed immutable data release.
3. **Validate and freeze:** check original prompt hashes against executed rows; verify 32-start identity, three-view time alignment, TF/RF label equivalence where applicable, exclusions, distinct frame IDs, unchanged image order, and output schemas. Freeze annotation and decoding/settings before evaluation. If human answerability audit is pending, flag the release provisional.
4. **Qualify:** run at most six development fixtures per lane to check loading, image reception, output format, native/extracted readout parity as needed, and memory. Do not require high spatial accuracy as a gate or tune the prompt to improve it.
5. **Infer:** execute primary manifest first, then secondary; within each bank order queries by SHA256 of `6106|query_id`. Isolate conversations and record raw responses atomically. Reuse exact identical text-only requests. Each model uses the same data release and query order.
6. **Analyze:** apply frozen parsers and gold; produce denominators, intervals, breakdowns, and action joins. Independently check a hand-calculated synthetic paired example and bootstrap clustering. Return all limitations.

Required row fields:

```text
query: query_id, release_sha256, test[A/B/C], bank[initial/secondary/no_image],
scene_id, physical_start_id|null, frame_id|null, source_episode_id|null,
requested_time_s|null, observed_time_s|null, view_paths_and_sha256,
goal_id, original_prompt_id|null, display_form, instruction_utf8_sha256|null,
full_prompt, full_prompt_sha256, pair_id|null, equivalence_status,
gold_answer, answerable, exclusion_reason, annotation_version

response: query_id, checkpoint_id, checkpoint_manifest_sha256, adapter_commit,
processor_id_and_revision, effective_decoding, attempt_id, status,
raw_response, parsed_response, prompt_tokens, output_tokens, latency_s,
input_payload_sha256, timestamp_utc, error|null
```

Keep gold/hidden metadata out of the actual model payload. Image basenames and IDs must not encode the correct relation or outcome. Plain text-only items have no fake physical-start ID. Infrastructure failures are missing, distinct from delivered invalid responses; paired comparisons use a common available set and disclose missingness. Do not hide incomplete lanes behind a high valid-response accuracy.

The intended command interface, **to be implemented and verified by the execution agent**, is:

```text
python -m experiments.robolab_vqa.prepare --spec-dir docs/robolab-vqa-20261006 --source-root <verified-existing-data-root> --output <new-release-dir>
python -m experiments.robolab_vqa.validate --release <new-release-dir>/release.json
python -m experiments.robolab_vqa.run --release <new-release-dir>/release.json --checkpoint <eligible-checkpoint-id> --output <new-results-dir>
python -m experiments.robolab_vqa.analyze --release <new-release-dir>/release.json --responses <new-results-dir> --output <new-analysis-dir>
```

These are contracts, not currently working launch commands. Agents must provide the actual tested commands and environment receipt after implementation. Raw images/videos, model weights, and credentials remain outside Git. Commit only appropriate code, small manifests, summaries, and provenance.

## 11. Deliverables and stop conditions

Return:

- Immutable data release, frame bindings, exact queries, gold labels, review/exclusion ledger, and source hashes.
- Model eligibility/training-path table, matched-weight evidence or explicit provenance gap, environment and decoding receipts.
- Raw responses and failures; summary CSV/JSON; initial versus secondary results; scene/relation/wording breakdown; paired intervals; no-image and placement controls.
- `PAPER_TABLE.md` with one compact row per distinct qualified readout: B tuple accuracy, A both-correct, C TF/RF accuracy and gap/interval, C both-correct, and coverage. Put full breakdowns in a separate results artifact, not automatically in the manuscript.
- `INTERPRETATION.md`: what is supported, what is inconclusive, what cannot be inferred, and a proposed short paragraph suitable for a four-page paper. Do not insert it into Overleaf without the user requesting that edit.
- A completion receipt listing queries planned/completed/missing, actual commands, elapsed/GPU time, failures, and whether labels were human-audited.

### Separate report and GitHub delivery

The user explicitly requested a separate report so findings can be considered for the manuscript later. Populate `reports/robolab-vqa-20261006/REPORT.md` using the initialized structure. The full report must retain **every planned endpoint and qualified lane**, not just favorable or interesting results. Keep primary and secondary banks, original prompts and placement controls, S5 semantics, text-only controls, unsupported checkpoints, invalid responses, and infrastructure missingness visible. No blanks that resemble zeros; use `not run`, `unsupported`, `missing`, or `undefined` with reasons.

For each actual run, create `reports/robolab-vqa-20261006/runs/<run_id>/REPORT.md` and compact result/coverage/provenance tables, then append the run to `RUN_INDEX.json`. Do not overwrite a previous run's report. The top-level report can summarize the latest validated release and link all earlier runs. Include a complete metric export and suitable saved figures, not only screenshots of selected cells. Label provisional human-answerability review or incomplete provenance prominently.

Update `CANDIDATE_FINDINGS.csv` with candidate claims, exact supporting run/table/row identifiers, uncertainty and denominators, limitations/counterevidence, primary versus descriptive status, and a proposed manuscript use. Initially mark each as `unreviewed` and leave `author_decision` blank. The author decides what to include later. Interesting examples or post-result subgroups must be labeled exploratory; choosing a finding for exposition does not promote it to a pre-specified primary endpoint. Retain the complete report when a subset enters the paper.

Save the implementation, protocol/release amendments, small input manifests, summary CSV/JSON, generated summary figures, and the full separate report to GitHub at `adeeb10abbas/world-action-model-steerability`, branch `codex/nano-stock-workstation-20260926`. Record code and analysis commit identities and verify local/remote commit agreement after the push. Coordinate commits when multiple agents share the branch; integrate remote work without force-pushing or overwriting another agent's changes. A repository save is required after results, including a partial run or blocker report.

Raw response/media/array archives and weights stay in durable external storage with paths and hashes in the committed artifact index; do not put secrets, environments, expiring signed links, or large raw recordings into Git. The report must remain traceable to those artifacts. Updating the report does not authorize changing Overleaf or either manuscript source.

Stop an affected lane on missing native head, unresolvable weight lineage, incompatible image pathway, repeated infrastructure fault, or the integration time cap. Stop affected image items on missing synchronization/calibration/visibility evidence. Continue independent eligible work; do not expand the experiment to rescue an unavailable result. A provisional or partly unsupported result is preferable to relabeling a different model as the policy backbone.

## 12. Interpretation rules

| Observation | Defensible reading |
|---|---|
| B weak with or without images | Instruction interpretation/readout is already difficult on these prompts |
| B strong; A weak | Visual relation/coordinate-frame understanding may contribute |
| A and B strong; C weak | Combining the instruction with the visible arrangement may contribute |
| All three strong; policy wording gap remains | Explicit QA capability does not guarantee the action policy uses that information effectively |
| Base versus policy readout differs with genuinely comparable weights/path | A checkpoint-associated difference, subject to preprocessing/readout/training-history confounds |
| Frozen/tensor-identical readout; action behavior differs | No evidence that this readout's weights lost ability during that adaptation; investigate conditioning/action mapping |

These are diagnostic patterns, not a causal decomposition. Verbal readout is not direct access to the policy's latent decision; aggregate high VQA and low action success do not identify individual failure causes. No degradation or co-training-benefit claim is licensed by cross-family scores. A narrow/noisy estimate remains a result; do not keep adding tests until a story appears.

## 13. Verified external references

Checked October 6, 2026; pin exact versions at execution. Keep citations attached to the particular factual claim they support.

- [RoboSpatial-Home dataset](https://huggingface.co/datasets/chanhee-luke/RoboSpatial-Home): configuration questions concern visible object relations; context is pointing and compatibility concerns fit. This run adapts the configuration idea, not its whole benchmark.
- [RoboSpatial evaluation code](https://github.com/chanhee-luke/RoboSpatial-Eval): released VQA/pointing evaluation. Our paired metrics and stricter output parser are additional custom choices.
- [Cosmos3-Nano model card](https://huggingface.co/nvidia/Cosmos3-Nano) and [Cosmos3-Edge model card](https://huggingface.co/nvidia/Cosmos3-Edge): public base releases and native model capabilities; not proof that every policy export retains a usable head.
- [Nano DROID recipe](https://github.com/NVIDIA/cosmos-framework/blob/main/cosmos_framework/configs/base/experiment/action/posttrain_config/action_policy_droid_nano.py): generation/action parameter selection and robot adaptation recipe. Audit the executed revision, not just this current file.
- [FLUX shared-component model card](https://huggingface.co/black-forest-labs/flux-3-action-base) and [text encoder implementation](https://github.com/black-forest-labs/flux-action/blob/main/src/flux_action/models/text_encoder.py): frozen, unmodified Qwen3-VL-4B-Instruct component and its text-only use in the policy.
- [Cosmos Policy training recipe](https://nvidia-cosmos.github.io/cosmos-cookbook/recipes/post_training/predict2/cosmos_policy/post_training.html): separate Predict-family policy/world/value training. Do not equate it with generic image-question co-training.

What'sUp, RoboVQA, and public RoboSpatial evaluation are outside this locked first run. They can be cited as related evaluation resources, but should not displace the matched RoboLab question.
