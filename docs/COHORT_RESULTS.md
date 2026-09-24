# Compile one clean SGW-01 study cohort

`tools/compile_study_cohort.py` is a downstream, CPU-only adapter for the
existing manifest compiler. It does not run policies or simulators, contact
the cluster, create execution releases, download evidence, or change recorded
outcomes. Run it against the authoritative mounted evidence after execution,
not as a gate on native execution.

## Explicit index

The execution owner supplies a JSON index, not a recursive search across old
experiments. Use `schema_version: "sgw-01-cohort-index-v1"`:

```json
{
  "schema_version": "sgw-01-cohort-index-v1",
  "cohort_id": "OWNER_ASSIGNED_CLEAN_STUDY_ID",
  "cohort_root": "/pvc/clean-study",
  "planned_queue_sha256": "07a2bd6c1893e7662db0c12c01843c20d743bfeb4cb1b506f238a37ae19e068a",
  "releases": [
    {
      "root": "/pvc/clean-study/release-N3-LAT-P",
      "release_id": "ACTUAL_RELEASE_RECEIPT_ID",
      "model": "N3",
      "family": "LAT",
      "stage": "P",
      "source_commit": "ACTUAL_40_CHARACTER_SOURCE_COMMIT",
      "hashes_json_sha256": "ACTUAL_SHA256_OF_RELEASE_HASHES_JSON"
    }
  ]
}
```

Replace placeholders with independently recorded identities; do not derive a
new expected hash from evidence that failed validation. `root` is the immutable
metadata directory containing the native `release_receipt.json`, `hashes.json`,
`queue.jsonl`, protocol, prompts, fixtures and runtime binding. The native
recorder writes to its **parent** directory's `cells/` and `attempts/`.
Multiple releases can share that parent. Paths in the index may be absolute
or relative to the index file. Recorded absolute paths must remain valid;
do not rewrite manifests or hashes to relocate them.

An index attests which releases belong to this fresh clean cohort; it is not
new release authority. Exclude historical cohorts and the 18 fixed-input
technical requests. Each metadata root, release ID and model/family/stage
partition must be unique. Different releases may have different explicitly
pinned source commits; the analysis checkout need not be the runtime checkout.

The helper uses `contract.load_release` to verify each immutable input map,
checks its indexed hash and source identity, and checks receipt partition,
full released partition membership/order, prompts, seeds, fixture/time-map
bindings and the exact frozen queue. Completion pointers are routed to their
own release and checked for identity and path containment before
`compile_registered_queue` verifies manifest, result and raw artifact hashes
against that release's hash map. No raw media is decoded or scored again.
Unknown cells, duplicates, out-of-root paths and corrupt/provenance-mismatched
evidence fail rather than becoming zeros or successful reports.

## Checkpoint and final commands

From the repository root, with Python 3.11 or later:

```sh
python tools/compile_study_cohort.py \
  --queue experiments/workshops/spatial_grounding_v1/spec/planned_cells.csv \
  --index /pvc/clean-study/cohort-index.json \
  --output /pvc/clean-study/analysis-checkpoint-001.json

python tools/compile_study_cohort.py \
  --queue experiments/workshops/spatial_grounding_v1/spec/planned_cells.csv \
  --index /pvc/clean-study/cohort-index-final.json \
  --output /pvc/clean-study/analysis-final.json \
  --require-complete
```

The explicit release list may be empty or a subset for a checkpoint. Every
report still has all **1,566 frozen cells in their original order**, not a
subset denominator. An indexed release may itself be incomplete. If a shared
artifact parent also contains pointers for an unindexed partition, those are
listed as `unindexed_not_validated`, never included in observed coverage.
Outside-queue IDs are always errors. Run checkpoints on a stable snapshot or
quiescent selected releases; concurrent publication is not a cohort snapshot.

Outputs use the existing atomic JSON writer and require a new output path.
Invalid evidence produces a nonzero exit without publishing a report.
`--require-complete` writes an honest incomplete report and exits 2 if any
planned cells or partitions remain unresolved. Without that option an honest
checkpoint exits 0. Neither command resumes or modifies execution.

## Completion evidence and analysis

The report itself is the completion evidence; no additional receipt is needed.
Its `schema_version` is **`sgw-01-cohort-analysis-v1`**. `cohort_id` and
`planned_queue_sha256` are strings, `complete` is a JSON boolean, and all
`coverage` counts are integers:

- `expected`: always 1566; `observed`: validated published completion pointers.
- `completed`: valid successes, valid model failures and legitimate censored
  results; `missing`: cells without an accepted completion pointer.
- `duplicate`: zero in a published report, because duplicates are hard errors.
- `technical_invalid`: unresolved cell-level technical-invalid published
  results, not the number of historical failed attempts.
- `expected_partitions`: 27; `observed_partitions`: indexed validated partitions.

`complete: true` requires all 27 partitions, all 1566 exact planned IDs,
`observed == completed == expected`, and zero missing/duplicate/technical
gaps. Pilot/development/confirmation retain budgets 54/216/1296. A native
technical-invalid attempt publishes no completion pointer: its cell remains
`not_run`/missing, with no fabricated score. The tool does not enumerate or
alter unpublished attempts. A later authorized successful resume resolves
that cell without discarding its historical attempt artifacts. An explicit
legacy technical-invalid pointer stays `incomplete`. Censored outcomes and
valid model failures are not infrastructure gaps.

The report retains per-release input hashes, source commits, completion
pointer/manifest/result references and hashes, index/compiler hashes, ledger,
missing IDs, confirmation estimates, primary statistics, neutral coverage and
the existing paper export plan. A downstream video helper can pin the entire
report's bytes/hash and require the completion facts above, labeling these
as compiler/owner evidence rather than independently verified raw scientific
results. Video counts never establish episode completeness.

The shared compiler translates actual `scoring.result_payload`'s
`requested_success` boolean to the existing `S` analysis field, preserving
null/absent values as unavailable and rejecting conflicting legacy `S`
values. Only registered integer/string goal signs are normalized. This is
schema adaptation, not rescoring. The wrapper combines validated rows before
calling the existing nine-test primary analysis **once**, so Holm correction
is global, not a combination of partition-adjusted values.

Confirmation layouts remain the independent units; families are not pooled.
The [prospective equivalence safeguard](EQUIVALENCE_ANALYSIS_NOTE.md) is
unchanged: all-zero or degenerate contrasts are inconclusive, and
`equivalent_success_relation` remains null. Unavailable prediction mapping
stays unavailable, does not become a zero and does not block valid behavioral
outcomes. Physical separation in metres is not binary success asymmetry.

Focused synthetic CPU regression command (no native dependencies needed):

```sh
python -m pytest -q tests/test_compile_study_cohort.py \
  tests/test_sgw_compile.py tests/test_sgw_compile_physical_separation.py
```
