# RQA V2 implementation record (pre-inference)

**Written before any V2 evaluation or qualification query.** Implementation choices the V2 specification left to the
execution agent, and facts verified before inference. Later changes are appended as dated amendments; nothing above
an amendment is rewritten. V1 files, the `r1-20261006` run and the R1 release are unchanged.

## 1. Entry points (actual commands)

| Step | Command (cluster; CPU unless noted) |
|---|---|
| Release | `python -m experiments.robolab_vqa.v2.prepare --output /data/users/ali/rqa-20261006/release/r2-final --implementation-commit <sha>` |
| Validate | `python -m experiments.robolab_vqa.v2.validate --release /data/users/ali/rqa-20261006/release/r2-final/release.json` |
| Review packet | `python -m experiments.robolab_vqa.v2.review packet --release <r2>/release.json --output /data/users/ali/rqa-20261006/review/v2-packet` |
| Qualify (GPU) | `python -m experiments.robolab_vqa.v2.run --release <r2>/release.json --checkpoint <lane> --output /data/users/ali/rqa-20261006/runs/r2-final-20261007 --phase qualify --adapter-commit <sha>` |
| Evaluate (GPU) | same with `--phase eval` |
| Review ingest / rescore | `python -m experiments.robolab_vqa.v2.review ingest --packet <packet> --forms <csv,...> --output <ledger>` then `python -m experiments.robolab_vqa.v2.analyze ... --mask <ledger>/mask.json` |

CPU python: `/data/users/ali/vla_wam/envs/robolab-v2-isaac50/bin/python`; GPU python: the R1 vLLM environment
`cosmos3-edge-vllm-omni-900a7f08-py313` (vLLM 0.26.0, xgrammar 0.2.3, torch 2.11.0+cu130). Run ID `r2-final-20261007`
(UTC execution date; the user's local date was 2026-10-06).

## 2. Verified sources

- R1 release `release.json` sha256 `ccccd81e…` and content sha256 `1e691df6…` verified on the PVC; all R1 file hashes match.
- All 46 instruction tuples (30 original S1/S3/S4 + 16 placement) were derived from their wording by fixed deterministic
  patterns (no model) and match the catalog: `tuple_verification.json`. Every RF string names the reference as the
  relation-clause subject and uses the converse relation (10/10); no DIR/TF/placement string does. TOP wordings map to
  `on_top_supported` (“on top of and supported by”, “underneath and supporting” as its converse, “on top of” and “on”
  with support implied). No catalog amendment is needed.

## 3. Queries (2,184 per lane, 6,552 total)

- **B2:** IH is the frozen R1 B payload. H removes image segments; I removes exactly the three calibration header
  strings (surrounding newlines kept); T removes both. The camera-introduction line stays in all four. H, T and
  placement T are identical across the eight starts (verified) and are generated once per instruction, then reused for
  paired contrasts.
- **C2:** the frozen R1 C payload (same views, headers and presentation) with only the R1 C wrapper replaced by the fixed
  V2 wrapper. Orders 0/1 swap the complete A/B meanings; U is unchanged. The no-image control is the initial payload
  minus image segments, with camera text kept, deduplicated across starts.
- **All planned items are queried, including items excluded by the R1 mask.** The R1 exclusions (cone boundary, R1
  transit/gripper rule) are applied at scoring, identically for every lane and form. This keeps the CPU rescoring path
  free of new inference.
- **Order:** primary items (all B2, C2 initial, C2 no-image) in sha256(`6106|query_id`) order, then C2 secondary in the
  same order.

## 4. Constrained decoding (verified in the installed engine, CPU only)

- vLLM 0.26 `StructuredOutputsParams` is used, with engine-level `structured_outputs_config={"backend": "xgrammar",
  "disable_any_whitespace": true}`.
- **B2:** JSON schema with required `target`, `reference`, `relation`. Target and reference enums each hold the complete
  sorted scene vocabulary, including distractors; the relation enum is the full list; `additionalProperties: false`.
  xgrammar strict mode enforces declared property order with compact separators. The output format is therefore
  exactly `{"target": "…", "reference": "…", "relation": "…"}`, the wrapper's own example.
- **C2:** choice `A|B|U`.
- **Pre-inference engineering fix:** manifests are serialized with sorted keys, which would have reordered the schema
  properties (reference first) and forced reference-first answers. The schema is therefore stored as an
  order-preserving JSON string, and validation checks the order.
- On CPU, each constraint was compiled against each lane's real tokenizer. Valid target-first answers complete at EOS
  (stop ids 151645 Qwen, 11 Edge). Reference-first order, out-of-vocabulary values, fences, extra keys and malformed
  codes are rejected.
- Bitmask application on GPU uses xgrammar's Triton kernel; gcc is present, and no nvcc JIT is needed.
- Grammar and schema hashes are logged in every response.

## 5. Readouts and budget

- **Lanes:** N3-policy, E3-policy, F3-qwen3vl4b only.
- **Weights and decoding:** R1 weights, processors, chat templates and BF16. Greedy decoding; at most 256 new tokens;
  `enable_thinking=False`; eager; FLASH_ATTN; non-JIT sampler.
- **Edge:** retains R1's packaging-only `rqa-adapter-1`.
- **Digest check:** loaded-parameter digests are checked against R1 before any generation. A mismatch aborts the lane
  without spending budget.
- **Budget:**
  - The attempt ledger counts every engine generate call.
  - Qualification is the 6 fixtures once per lane (no repeats). They use D00 development material with non-catalog
    wording and cover B2 T/IH/I and C2 initial/secondary/no-image.
  - Each evaluation query is attempted once.
  - At most one retry per infrastructure-missing query, drawn from 30 shared retry slots (atomic mkdir).
  - 3 consecutive infrastructure failures stop a lane.
- **No smoke-test generations were run for V2.** All mechanics were checked on CPU.

## 6. Answerability review and masks (frozen)

- **Packet:** 72 view sets and 240 frame–goal relations, under opaque review IDs.
  - Sheets show the exact evaluation-resolution views (secondary views also 2× pixel-replicated), with
    calibration-derived LEFT/FARTHER arrows outside the image area.
  - Neutral per-pair questions.
  - The geometry key is kept in `key/`, used only by `ingest`.
  - The fixed R1 second-review sample is restricted to S1/S3/S4.
- **Masks:**
  - **original** = R1 mask.
  - **revised** = original AND review-answerable: identifiable, discernible, required support or table contact
    visible, no ambiguity flag, confidence not low; for C also no transit/gripper.
  - **strict** = revised minus discrepancies with geometry. Discrepancies are flagged for a second review.
- **Human review:** none is available in this pass. An agent (machine) review will populate a ledger labelled
  `reviewer_type=machine` without access to V2 responses or simulator labels. Machine-reviewed results are
  provisional; the human packet and CPU rescore command are delivered.

## 7. Analysis definitions (frozen in `experiments/robolab_vqa/v2/scoring.py`)

Parser `rqa-v2-parse-1` (strict JSON / exact code). Order averaging happens within items: a C2 item needs both orders.
Weights are equal across scenes, across goals within a scene and across starts within a goal; class recalls use
declared item weights normalized within each class. Balanced accuracy is undefined for one-class subsets. The bootstrap
uses 10,000 replicates, seed 6106, with starts resampled within each of S1/S3/S4 and shared across lanes and conditions.
Text-only B2 results are finite counts. Truth-changing frame pairs: per start–goal, the earliest matching and earliest
nonmatching frame among initial/50%/100% (frame ID breaks ties), scored by form with orders averaged.

## Amendment V2-A1 — qualification runner fault before any generation (2026-10-07 01:39 UTC)

- **What happened.** The first qualification call on each lane (`V2DEV.Q1`, 01:38 UTC) raised `KeyError: 'bank'` while
  the runner built the response record. Development fixtures carry `condition` but no `bank` key. The runner had
  already written one ledger entry per lane (`<lane>.V2DEV.Q1.a1`).
- **No generation occurred.** The exception came before the engine call; the logs show only weight loading. No model
  output exists for these entries, and the processes exited.
- **Fix (runner only).** The record now uses `payload.get("bank")`. The ledger entry is written after the record is
  built, immediately before the engine call. Qualification counts as already made only if it produced a response
  record. Queries, payloads, constraints, parsers, scoring and the release are unchanged (release content `2a3d5d69…`).
- **Accounting.** The three aborted ledger entries are retained. They are counted conservatively against the 6,600
  ceiling by pre-consuming 3 of the 30 shared retry slots, so the remaining retry capacity is 27 and ledgered attempts
  cannot exceed 6,600. Qualification is rerun once with fresh attempt IDs (`.a2`).

## Execution note E1 (2026-10-07 13:15 UTC) — evaluation complete; analysis driver committed before results were read

- **Evaluation.** All three lanes passed the mechanical qualification gate. Six fixtures each delivered schema-valid
  output through the xgrammar backend, with image receipt confirmed by prompt-token counts. Evaluation ran from 01:42
  to 01:52 UTC: 2,184 of 2,184 queries delivered and format-valid per lane, with 0 infrastructure errors, 0 retries and
  0 truncations.
- **Attempt ledger.**

  | Ledger entries | Count |
  |---|---:|
  | Aborted-before-generation (Amendment V2-A1) | 3 |
  | Qualification generations | 18 |
  | Evaluation generations | 6,552 |
  | **Total ledger entries** | **6,573** |
  | Model generations | 6,570 |

  The hard cap is 6,600. The three GPU pods were deleted at 13:12 UTC after their GPUs were verified at 0 MiB.
- **Analysis code timing.** `experiments/robolab_vqa/v2/analyze.py` and `edge_audit.py` were written during evaluation
  (after the freeze, before any evaluation response was opened) and are committed here before the first analysis run.
  They use only the frozen scoring functions (`scoring.py`, committed at `515bab8`) and the frozen release.
- **Machine review.** The first machine-review attempt (six blinded agents launched 01:36 UTC) produced no forms: every
  agent failed on a network/DNS outage on the orchestrating workstation. The review was relaunched at 13:10 UTC with the
  same blinded prompts, adding a second independent machine reviewer for every sheet (agents 7–12).
  - Reviewers see only the packet sheets and instructions, never model responses or simulator labels.
  - The mask rule is frozen in code. The revised mask excludes an item if any reviewer marks it unanswerable; the
    strict mask additionally excludes any geometry discrepancy. Any inter-reviewer disagreement implies such a
    discrepancy.
  - The forms were completed after V2 responses existed but without access to them. The audit is therefore a
    machine audit, not a human one, and is reported as provisional.
