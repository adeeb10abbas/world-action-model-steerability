# Final local video delivery

`tools/download_study_videos.py` archives **H.264 viewing copies** (H.265 also
accepted) only after the entire study has finished. It does not encode media,
run models, manage cluster resources, change releases/completion pointers, or
modify original evidence. Full-quality videos, arrays and checkpoints remain
unchanged on the persistent cluster drive. No video blobs belong in Git or LFS.

The requested laptop destination is
`/Users/SZ5VJY/Downloads/world-action-model-steerability-videos`.
If space is insufficient, wait for the user's external drive and use its
destination instead. Do not delete unrelated data or quietly start a partial
bulk download.

## Owner-side inputs

The execution owner must first finish the study and publish the cohort compiler's
final `sgw-01-cohort-analysis-v1` report. The downloader checks its pinned bytes
and these explicit facts: `complete: true`; integer `coverage.expected`,
`coverage.observed` and `coverage.completed` all 1566; `coverage.missing`,
`coverage.duplicate` and `coverage.technical_invalid` all zero; and matching
`cohort_id` and `planned_queue_sha256`. Release provenance must be present.
This is compiler/owner evidence, not a duplicate raw-result verifier, success
score, or experimental release/runtime gate. Model failures and censored
outcomes retain the compiler's existing semantics.
The technical-invalid coverage field counts **unresolved cells**, not older
failed attempts of cells that later completed. Such historical recordings are
still retained and can be included in the technical archive.

After completion, the owner separately encodes viewing copies on the cluster
from retained media, without inference or changes to masters. Preserve source
resolution and every frame. Preserve known presentation timing. Keep the exact
encoder/version, argument list (including quality settings), measured source
and output dimensions/frame counts, and source identity. Publish the closed,
verified derivatives in a separate `viewing/` tree. **Never append derivatives
to or rewrite a completed scientific attempt manifest.**

The original recorder schema is `sgw-01-attempt-manifest-v1`: `complete: true`,
release/cell/attempt identity, `release_hashes`, `result.status`, and an
`artifacts` map from attempt-relative path to `{bytes, sha256}`. The separate
delivery index binds each derivative back to one such original entry. It must
cover every recorded video in every supplied manifest, including failed or
technical attempts. Arrays are not videos: the recorder currently persists
raw predictions as `.npy` plus request envelopes. If the owner exposes a
prediction viewing copy, its original may reference a retained
`predictions/*.npy` artifact. The downloader never decodes that array, invents
a missing prediction, or treats an unlisted array as an available video.

Copy only compact metadata to a local metadata directory, retaining the
cohort-relative paths of the completion report, any timing receipts and
`attempts/<cell_id>/<attempt_id>/manifest.json` files. Publish a separate JSON
index with this shape; angle-bracket strings and numbers below are illustrative
placeholders, **not a completion receipt or executable study evidence**:

```json
{
  "schema_version": "sgw-01-video-download-index-v1",
  "study_id": "SGW-01",
  "cohort_id": "<same as final compiler report>",
  "planned_queue_sha256": "<same as final compiler report>",
  "study_status": "completed",
  "expected_episodes": 1566,
  "completed_episodes": 1566,
  "completion_receipt": {
    "path": "delivery/cohort-analysis.json", "bytes": 123, "sha256": "<64 lowercase hex>"
  },
  "attempt_manifests": [
    {
      "path": "attempts/<cell_id>/<attempt_id>/manifest.json",
      "bytes": 123, "sha256": "<64 lowercase hex>"
    }
  ],
  "videos": [
    {
      "path": "viewing/attempts/<cell_id>/<attempt_id>/videos/viewport.mp4",
      "bytes": 123, "sha256": "<derivative SHA-256>",
      "original": {
        "manifest_path": "attempts/<cell_id>/<attempt_id>/manifest.json",
        "path": "videos/viewport.mp4",
        "bytes": 456, "sha256": "<unchanged original artifact SHA-256>"
      },
      "encoding": {
        "codec": "h264",
        "encoder": "<encoder and version>",
        "arguments": ["<exact actual encoding arguments, including quality settings>"],
        "source": {
          "width": 1280, "height": 720, "frame_count": 451,
          "fps_numerator": 15, "fps_denominator": 1
        },
        "output": {
          "width": 1280, "height": 720, "frame_count": 451,
          "fps_numerator": 15, "fps_denominator": 1
        },
        "timing_basis": "recorded_presentation",
        "physical_time": {"status": "unavailable"}
      }
    }
  ]
}
```

For a decoded prediction whose physical timing is unverified, retain
`physical_time.status: "unavailable"`. When the source has no recorded
presentation rate, set **both source FPS fields to `null`**. A selected output
playback rate requires `timing_basis: "playback_only"`; it is not a physical
time mapping. If both rates are unavailable, both pairs are null and the basis
is `"unavailable"`. Known source rates require identical output rational FPS
and `"recorded_presentation"`. Never infer physical FPS from array shape.
A separately established physical mapping can use
`{"status": "verified", "receipt": {"path": "...", "bytes": 123, "sha256": "..."}}`;
that receipt is hash-checked, not scientifically requalified by this tool.
Preserve additional recorded timing metadata in the encoding object.

The owner must include all attempts and all exposed prediction derivatives in
the final index. Checking the supplied index cannot detect an entire omitted
attempt or a never-exported prediction. Video count is never episode count.
Native diagnostic outputs with a different manifest schema are not silently
accepted as study attempts; keep their independent archive/index separate.

## Download and verify

Run from this repository with Python 3.11+; the helper uses only the standard
library. Obtain `INDEX_SHA256` from the owner's independently published final
index identity. All paths in the index are canonical, ASCII, cohort-relative
paths; absolute paths, traversal, temporary names, symlinks and case-insensitive
or parent/child collisions are rejected.

```sh
python3 -m tools.download_study_videos download \
  --index "$METADATA_ROOT/delivery/videos.json" \
  --index-sha256 "$INDEX_SHA256" \
  --metadata-root "$METADATA_ROOT" \
  --destination /Users/SZ5VJY/Downloads/world-action-model-steerability-videos \
  --transport kubectl --source-root "$COHORT_ROOT" \
  --context "$CONTEXT" --namespace "$NAMESPACE" \
  --pod "$AUTHORIZED_READER_POD" --container "$CONTAINER" \
  --remote-python python3 --reserve-bytes 10737418240 --timeout 600
```

The owner selects an existing authorized reader Pod; the tool never creates
one. Kubernetes access uses the caller's existing credentials without storing
them. Transfers use argument-vector `kubectl exec` and a fixed stdlib Python
reader: no remote shell interpolation, writes, temporary files, or model
imports. The source root and descendants must be real directories, not
symlinks. `COHORT_ROOT` is the shared **parent of the release metadata
directories** (`release.root.parent`), containing `attempts/` and `cells/`;
it is not an individual release directory. Do not mix cohorts in one index.
`--remote-python` may be an explicit interpreter path. Each transfer
has a finite timeout; there are no automatic transport retries.

Replace `download` with **`verify`**, retaining the same flags, for entirely
local coverage checking. Verify mode never invokes the source transport, even
with `--transport kubectl`. For an already mounted/local source or CPU test,
use `--transport local --source-root /absolute/source` and omit Kubernetes
flags; this uses exactly the same bounded file-reader code.
Codec/frame/timing metadata are pinned owner-side measurements. The helper
checks their consistency and file digests; it does not decode or independently
probe media.

The JSON output and immutable `.video-downloads/coverage-<id>.json` receipt
report per-file `complete`/`missing`/`failed`, expected/verified bytes, original
and derivative identities, source configuration, manifest hashes, owner
completion evidence, and errors. `index_coverage_complete` means only that
this index's files were checked, not that the study succeeded. Exit status is
zero only for complete coverage; malformed inputs, unfinished manifests,
incomplete compiler evidence, disk shortage and transfer failures exit nonzero.

## Recovery and space

Before any download, all existing final paths are rehashed and checked for
conflicts. Aggregate preflight compares **all missing bytes plus headroom**
against fresh available disk bytes, reporting `required_bytes`,
`available_bytes` and `shortfall_bytes`. The default reserve is 1 GiB; the
example explicitly reserves 10 GiB. No transfers start on a conflict or failed
preflight. Space is checked again before each file because other workloads can
consume it. A later failure stops the batch, preserves completed files and
reports remaining files as missing.

Downloads use exclusive random `.partial` files, verify length and SHA-256,
then atomically hard-link into the final path without replacing anything.
Final files with matching bytes are skipped on restart; mismatching files
fail explicitly. A directory lock rejects concurrent helper runs.
Interrupted partials are never complete or trusted for byte-range resume.
Rerun the same command: the interrupted file restarts from byte zero, while
verified final files are skipped. Old partials are retained, consume disk and
are never deleted automatically; inspect and remove only the specific partial
identified by a failed receipt if needed. A hard interruption may leave a
partial without a final receipt; run local verification before recovery.

Completed-index revisions can add later-published derivatives after study
completion. Use a new pinned index digest, retain earlier metadata/receipts,
and rerun; existing matching files are reused. Each file stays beneath
`study/`, `technical/` or `censored/` followed by its original `viewing/`
hierarchy. Technical/censored files remain separate and are not converted
into successful study episodes.

Focused validation, with the repository's test environment:

```sh
python -m pytest -q tests/test_download_study_videos.py
```

These tests use synthetic bytes and local/mock transports, not real media,
encoders, simulators, models or cluster resources. Add this explicit test path
to broader CI selection when integrating; the repository currently enumerates
default test paths in `pyproject.toml`.
