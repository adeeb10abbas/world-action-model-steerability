"""Synthetic, CPU-only records; no policy, simulator, video encoding, or cluster."""

import csv
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from experiments.workshops.spatial_grounding_v1 import compile as analysis
from experiments.workshops.spatial_grounding_v1.contract import (
    REQUIRED_BINDING_FIELDS, REQUIRED_RELEASE_FILES, load_release, sha256_file,
)
from experiments.workshops.spatial_grounding_v1.scoring import EpisodeScore, OutcomeStatus, result_payload
from tools import compile_study_cohort as cohort

QUEUE = cohort.SPEC / "planned_cells.csv"
with QUEUE.open(newline="") as stream:
    PLANNED = list(csv.DictReader(stream))


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n")
    return path


def _read(path):
    return json.loads(path.read_text())


def _rehash(root, entry):
    _write(root / "hashes.json", {
        name: sha256_file(root / name) for name in REQUIRED_RELEASE_FILES if name != "hashes.json"
    })
    entry["hashes_json_sha256"] = sha256_file(root / "hashes.json")


def _release(base, model="N3", family="LAT", stage="P", *, separate=False):
    partition_id = f"{model}-{family}-{stage}"
    root = base / partition_id / "release" if separate else base / f"release-{partition_id}"
    root.mkdir(parents=True)
    selected = [row for row in PLANNED if (row["model"], row["family"], row["stage"]) == (model, family, stage)]
    binding = {key: "synthetic-cpu-test" for key in REQUIRED_BINDING_FIELDS}
    binding.update(source_commit="a" * 40, resource_owner="synthetic-test",
                   worker_image_digest="synthetic@sha256:" + "b" * 64)
    _write(root / "runtime_binding.json", binding)
    fixtures = {"status": "qualified", "layouts": {
        row["layout_id"]: {"fixture_sha256": "f" * 64} for row in selected
    }, "time_maps": {model: "e" * 64}}
    _write(root / "fixtures.json", fixtures)
    for name in ("protocol.json", "prompts.json"):
        (root / name).write_bytes((cohort.SPEC / name).read_bytes())
    rows = [{**row, "release_id": partition_id, "status": "RELEASED",
             "fixture_sha256": "f" * 64, "time_map_sha256": "e" * 64,
             "runtime_sha256": sha256_file(root / "runtime_binding.json")} for row in selected]
    (root / "queue.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
    _write(root / "release_receipt.json", {
        "schema_version": "sgw-01-release-v1", "release_id": partition_id,
        "resource_owner": "synthetic-test", "source_queue_sha256": sha256_file(QUEUE),
        "model": model, "family": family, "stage": stage, "cell_count": len(rows), "status": "released",
    })
    entry = {"root": str(root), "release_id": partition_id, "model": model, "family": family,
             "stage": stage, "source_commit": "a" * 40}
    _rehash(root, entry)
    return root, entry


def _record(root, row, *, success=False, status=None, publish=True, attempt_id="attempt-001"):
    cell_id = row["cell_id"]
    directory = root.parent / "attempts" / cell_id / attempt_id
    score = EpisodeScore(
        status=OutcomeStatus.SAFETY_CENSORED if status == "censored" else OutcomeStatus.VALID_MODEL,
        requested_success=success, terminal_margin_m=None if status == "censored" else -0.1,
        relation_m=None, pickup_step=None, first_success_step=None,
        terminal_step=None if status == "censored" else 450, anchor_max_drift_m=0,
        reference_motion_ok=True, release_detached=True, failure_stage="pickup",
        safety_censored=status == "censored",
    )
    result = result_payload(score, release_id=row["release_id"], cell_id=cell_id,
                            attempt_id=attempt_id, completed_at_utc="2026-09-24T00:00:00Z")
    if status == "technical_invalid":
        result.update(status=status, requested_success=None, technical_cause="synthetic timeout")
    _write(directory / "result.json", result)
    for kind in ("actions", "states", "observations", "videos"):
        _write(directory / kind / "synthetic.json", {"synthetic_cpu_fixture": True})
    artifacts = {path.relative_to(directory).as_posix(): {
        "bytes": path.stat().st_size, "sha256": sha256_file(path),
    } for path in directory.rglob("*") if path.is_file()}
    manifest = _write(directory / "manifest.json", {
        "schema_version": "sgw-01-attempt-manifest-v1", "complete": True,
        "release_id": row["release_id"], "cell_id": cell_id, "attempt_id": attempt_id,
        "release_hashes": _read(root / "hashes.json"), "artifacts": artifacts, "result": result,
    })
    pointer = root.parent / "cells" / f"{cell_id}.complete.json"
    if publish:
        _write(pointer, {
            "release_id": row["release_id"], "cell_id": cell_id, "attempt_id": attempt_id,
            "manifest_path": str(manifest), "manifest_sha256": sha256_file(manifest),
            "result": {"path": str(directory / "result.json"), "sha256": sha256_file(directory / "result.json")},
        })
    return pointer, manifest


def _rows(root):
    return [dict(cell.row) for cell in load_release(root).cells]


def _index(tmp_path, entries):
    (tmp_path / "cohort").mkdir(exist_ok=True)
    return _write(tmp_path / "index.json", {
        "schema_version": cohort.INDEX_SCHEMA, "cohort_id": "synthetic-clean-cohort",
        "cohort_root": str(tmp_path / "cohort"), "planned_queue_sha256": sha256_file(QUEUE),
        "releases": entries,
    })


def _update_result(pointer, update):
    raw = _read(pointer)
    manifest_path = Path(raw["manifest_path"])
    manifest = _read(manifest_path)
    result_path = Path(raw["result"]["path"])
    result = _read(result_path)
    result.update(update)
    _write(result_path, result)
    manifest["result"] = result
    manifest["artifacts"]["result.json"] = {"bytes": result_path.stat().st_size, "sha256": sha256_file(result_path)}
    _write(manifest_path, manifest)
    raw["manifest_sha256"] = sha256_file(manifest_path)
    raw["result"]["sha256"] = sha256_file(result_path)
    _write(pointer, raw)


def test_shared_parent_independently_hash_bound_releases_preserve_frozen_ledger(tmp_path):
    root_a, entry_a = _release(tmp_path / "cohort")
    root_b, entry_b = _release(tmp_path / "cohort", model="E3")
    assert _read(root_a / "hashes.json") != _read(root_b / "hashes.json")
    row_a, row_b = _rows(root_a)[0], _rows(root_b)[0]
    _record(root_a, row_a, success=False)
    _record(root_b, row_b, success=True)
    report = cohort.compile_study_cohort(QUEUE, _index(tmp_path, [entry_a, entry_b]))
    assert not report["complete"]
    assert report["coverage"] == {
        "expected": 1566, "observed": 2, "completed": 2, "missing": 1564, "duplicate": 0,
        "technical_invalid": 0, "expected_partitions": 27, "observed_partitions": 2,
    }
    assert [row["cell_id"] for row in report["ledger"]] == [row["cell_id"] for row in PLANNED]
    by_id = {row["cell_id"]: row for row in report["ledger"]}
    assert by_id[row_a["cell_id"]]["status"] == "valid_model_failure"
    assert by_id[row_a["cell_id"]]["S"] == 0
    assert by_id[row_b["cell_id"]]["S"] == 1
    missing = next(row for row in report["ledger"] if row["analysis_status"] == "not_run")
    assert "S" not in missing and "requested_success" not in missing
    assert len(report["primary_statistics"]) == 9
    assert all(row["status"] == "unavailable" for row in report["primary_statistics"])
    assert report["releases"][0]["completion_pointers"][0]["manifest_sha256"]


@pytest.mark.parametrize("model", ["N3", "E3"])
def test_each_release_manifest_rejects_other_release_hash_map(tmp_path, model):
    first, first_entry = _release(tmp_path / "cohort")
    second, second_entry = _release(tmp_path / "cohort", model="E3")
    root, other = (first, second) if model == "N3" else (second, first)
    pointer, manifest = _record(root, _rows(root)[0])
    value = _read(manifest)
    value["release_hashes"] = _read(other / "hashes.json")
    _write(manifest, value)
    raw = _read(pointer)
    raw["manifest_sha256"] = sha256_file(manifest)
    _write(pointer, raw)
    with pytest.raises(ValueError, match="release provenance mismatch"):
        cohort.compile_study_cohort(QUEUE, _index(tmp_path, [first_entry, second_entry]))


@pytest.mark.parametrize("tamper", ["artifact", "manifest", "release_input", "hash_pin", "source", "source_queue",
                                  "partition", "count", "prompt", "result_partition", "queue"])
def test_tampering_or_provenance_mismatch_is_rejected(tmp_path, tamper):
    root, entry = _release(tmp_path / "cohort")
    pointer, manifest = _record(root, _rows(root)[0])
    queue = QUEUE
    if tamper == "artifact":
        (manifest.parent / "states" / "synthetic.json").write_text('{"synthetic_cpu_fixture":false}\n')
    elif tamper == "manifest":
        manifest.write_text(manifest.read_text() + " ")
    elif tamper == "release_input":
        (root / "fixtures.json").write_text("{}")
    elif tamper == "hash_pin":
        entry["hashes_json_sha256"] = "0" * 64
    elif tamper == "source":
        entry["source_commit"] = "c" * 40
    elif tamper in {"source_queue", "partition", "count"}:
        receipt = _read(root / "release_receipt.json")
        key, value = {"source_queue": ("source_queue_sha256", "0" * 64),
                      "partition": ("family", "DIST"), "count": ("cell_count", 5)}[tamper]
        receipt[key] = value
        _write(root / "release_receipt.json", receipt)
        _rehash(root, entry)
    elif tamper == "prompt":
        rows = _rows(root)
        rows[0]["environment_seed"] = "999"
        (root / "queue.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
        _rehash(root, entry)
    elif tamper == "result_partition":
        _update_result(pointer, {"model": "E3"})
    elif tamper == "queue":
        queue = tmp_path / "altered.csv"
        queue.write_bytes(QUEUE.read_bytes() + b"\n")
    with pytest.raises(ValueError):
        cohort.compile_study_cohort(queue, _index(tmp_path, [entry]))


def test_same_size_artifact_hash_tamper_is_rejected(tmp_path):
    root, entry = _release(tmp_path / "cohort")
    _, manifest = _record(root, _rows(root)[0])
    artifact = manifest.parent / "states" / "synthetic.json"
    artifact.write_text(artifact.read_text().replace("true", "null"))
    with pytest.raises(ValueError, match="artifact hash mismatch"):
        cohort.compile_study_cohort(QUEUE, _index(tmp_path, [entry]))


@pytest.mark.parametrize("kind", ["duplicate_cell", "unknown_cell", "wrong_release", "retired_model",
                                 "duplicate_release", "duplicate_partition", "outside_pointer",
                                 "outside_result", "outside_artifact", "outside_root"])
def test_identity_partition_and_root_bounds(tmp_path, kind):
    root, entry = _release(tmp_path / "cohort")
    pointer, manifest = _record(root, _rows(root)[0])
    entries = [entry]
    if kind == "duplicate_cell":
        (pointer.parent / "extra.complete.json").write_bytes(pointer.read_bytes())
    elif kind in {"unknown_cell", "wrong_release"}:
        raw = _read(pointer)
        raw["cell_id" if kind == "unknown_cell" else "release_id"] = "not-registered"
        _write(pointer, raw)
    elif kind == "retired_model":
        entry["model"] = "D1"
    elif kind == "duplicate_release":
        entries.append(dict(entry))
    elif kind == "duplicate_partition":
        other_root, other_entry = _release(tmp_path / "cohort", separate=True)
        other_entry["release_id"] = "another-N3-LAT-P"
        receipt = _read(other_root / "release_receipt.json")
        receipt["release_id"] = other_entry["release_id"]
        _write(other_root / "release_receipt.json", receipt)
        text = (other_root / "queue.jsonl").read_text().replace('"release_id": "N3-LAT-P"',
                                                              '"release_id": "another-N3-LAT-P"')
        (other_root / "queue.jsonl").write_text(text)
        _rehash(other_root, other_entry)
        entries.append(other_entry)
    elif kind == "outside_pointer":
        outside = tmp_path / "elsewhere.complete.json"
        pointer.rename(outside)
        pointer.symlink_to(outside)
    elif kind == "outside_result":
        raw = _read(pointer)
        raw["result"]["path"] = str(tmp_path / "result.json")
        _write(pointer, raw)
    elif kind == "outside_artifact":
        artifact = manifest.parent / "states" / "synthetic.json"
        outside = tmp_path / "outside.json"
        artifact.rename(outside)
        artifact.symlink_to(outside)
    elif kind == "outside_root":
        root, entry = _release(tmp_path / "outside")
        entries = [entry]
    with pytest.raises(ValueError):
        cohort.compile_study_cohort(QUEUE, _index(tmp_path, entries))


def test_cross_release_duplicate_cannot_enter_a_separate_artifact_root(tmp_path):
    first, first_entry = _release(tmp_path / "cohort", separate=True)
    second, second_entry = _release(tmp_path / "cohort", model="E3", separate=True)
    pointer, _ = _record(first, _rows(first)[0])
    duplicate = second.parent / "cells" / pointer.name
    duplicate.parent.mkdir()
    duplicate.write_bytes(pointer.read_bytes())
    with pytest.raises(ValueError, match="duplicate|outside owning"):
        cohort.compile_study_cohort(QUEUE, _index(tmp_path, [first_entry, second_entry]))


def test_partial_subset_does_not_consume_unindexed_releases(tmp_path):
    first, entry = _release(tmp_path / "cohort")
    second, _ = _release(tmp_path / "cohort", model="E3")
    _record(first, _rows(first)[0])
    _record(second, _rows(second)[0])
    report = cohort.compile_study_cohort(QUEUE, _index(tmp_path, [entry]))
    assert report["coverage"]["observed"] == 1
    assert len(report["unindexed_completion_pointers"]) == 1
    assert report["unindexed_completion_pointers"][0]["status"] == "unindexed_not_validated"
    assert report["coverage"]["missing"] == 1565


def test_technical_gaps_censoring_and_resolved_historical_attempts(tmp_path):
    root, entry = _release(tmp_path / "cohort")
    rows = _rows(root)
    _record(root, rows[0], status="technical_invalid")  # Accepted legacy pointer, still incomplete.
    _record(root, rows[1], status="technical_invalid", publish=False)
    _record(root, rows[2], status="technical_invalid", publish=False)
    _record(root, rows[2], success=False, attempt_id="attempt-002")
    _record(root, rows[3], status="censored", success=False)
    report = cohort.compile_study_cohort(QUEUE, _index(tmp_path, [entry]))
    assert report["coverage"]["observed"] == 3
    assert report["coverage"]["completed"] == 2
    assert report["coverage"]["technical_invalid"] == 1
    assert not report["complete"]
    ledger = {row["cell_id"]: row for row in report["ledger"]}
    assert ledger[rows[1]["cell_id"]]["analysis_status"] == "not_run"
    assert ledger[rows[2]["cell_id"]]["status"] == "valid_model_failure"
    assert ledger[rows[3]["cell_id"]]["status"] == "censored"


def test_real_result_schema_estimates_and_single_global_holm(tmp_path):
    first, first_entry = _release(tmp_path / "cohort", stage="C")
    second, second_entry = _release(tmp_path / "cohort", model="E3", stage="C")
    for root in (first, second):
        for row in _rows(root)[:6]:
            success = row["form"] == "I" and (root == first or row["physical_goal_sign"] == "1")
            _record(root, row, success=success)
    with patch.object(analysis, "compile_primary_statistics", wraps=analysis.compile_primary_statistics) as primary, \
         patch.object(analysis, "paired_signflip", side_effect=lambda values: .01 if values == [1.] else .02), \
         patch.object(analysis, "holm_adjust_primary", wraps=analysis.holm_adjust_primary) as holm:
        report = cohort.compile_study_cohort(QUEUE, _index(tmp_path, [first_entry, second_entry]))
    assert primary.call_count == holm.call_count == 1
    assert holm.call_args.args[0] == {"N3-LAT": .01, "E3-LAT": .02}
    stats = {(row["model"], row["family"]): row for row in report["primary_statistics"]}
    assert stats["N3", "LAT"]["p_holm"] == pytest.approx(.09)
    assert stats["E3", "LAT"]["p_holm"] == pytest.approx(.16)  # Not per-partition .18.
    assert stats["N3", "LAT"]["n_layouts"] == 1
    assert stats["N3", "LAT"]["equivalent_success_relation"] is None
    assert report["paper_export_plan"]["status"] == "validated_results"


def _ledger_cell(**updates):
    row = next(row for row in PLANNED if row["stage"] == "C")
    return {**row, "analysis_status": "complete", **updates}


@pytest.mark.parametrize("sign", [-1, 1, "-1", "1"])
def test_shared_helper_normalizes_only_registered_signs(sign):
    result = analysis.registered_compilation_from_rows([_ledger_cell(physical_goal_sign=sign, requested_success=False)])
    assert result.ledger[0]["physical_goal_sign"] == int(sign)
    assert result.ledger[0]["S"] == 0


@pytest.mark.parametrize("sign", [True, False, None, 0, 1., -1., "1.0", "+1", " 1", "invalid"])
def test_shared_helper_rejects_invalid_signs(sign):
    with pytest.raises(ValueError, match="physical_goal_sign"):
        analysis.registered_compilation_from_rows([_ledger_cell(physical_goal_sign=sign)])


@pytest.mark.parametrize("values", [{"requested_success": None}, {}, {"S": None}])
def test_missing_success_is_unavailable_not_zero(values):
    result = analysis.registered_compilation_from_rows([_ledger_cell(**values)])
    assert result.ledger[0].get("S") is None
    assert result.confirmation_estimates[0]["status"] == "incomplete"


@pytest.mark.parametrize("values", [
    {"S": 0, "requested_success": True}, {"S": 1, "requested_success": False},
    {"S": None, "requested_success": True}, {"S": 0, "requested_success": None},
    {"requested_success": 0}, {"requested_success": "false"}, {"S": "0"}, {"S": 2}, {"S": float("nan")},
])
def test_invalid_or_conflicting_success_fields_rejected(values):
    with pytest.raises(ValueError, match="invalid|conflicting"):
        analysis.registered_compilation_from_rows([_ledger_cell(**values)])


@pytest.mark.parametrize("values", [{"S": 0}, {"S": 1.}, {"S": 1, "requested_success": True}])
def test_compatible_historical_success_inputs_preserved(values):
    result = analysis.registered_compilation_from_rows([_ledger_cell(**values)])
    assert result.ledger[0]["S"] == values["S"]


def test_full_1566_scope_complete_and_one_missing_never_complete(tmp_path):
    entries = []
    last_pointer = None
    for model, family, stage in sorted(cohort.PARTITIONS):
        root, entry = _release(tmp_path / "cohort", model, family, stage)
        entries.append(entry)
        for row in _rows(root):
            last_pointer, _ = _record(root, row, success=False)
    index = _index(tmp_path, entries)
    report = cohort.compile_study_cohort(QUEUE, index)
    assert report["complete"]
    assert report["coverage"] == {
        "expected": 1566, "observed": 1566, "completed": 1566, "missing": 0, "duplicate": 0,
        "technical_invalid": 0, "expected_partitions": 27, "observed_partitions": 27,
    }
    assert len(report["confirmation_estimates"]) == 216
    assert all(row["n_layouts"] == 24 and row["equivalent_success_relation"] is None
               for row in report["primary_statistics"])
    assert all(row["p_holm"] == 1 for row in report["primary_statistics"])
    last_pointer.unlink()
    # The first run already covered the real statistics, including all-zero contrasts.
    with patch.object(analysis, "compile_primary_statistics", return_value=()):
        partial = cohort.compile_study_cohort(QUEUE, index)
    assert not partial["complete"]
    assert partial["coverage"]["missing"] == 1 and partial["coverage"]["observed"] == 1565


def test_cli_atomic_checkpoint_and_final_requirement(tmp_path):
    index = _index(tmp_path, [])
    output = tmp_path / "report.json"
    args = ["--queue", str(QUEUE), "--index", str(index), "--output", str(output)]
    assert cohort.main(args + ["--require-complete"]) == 2
    report = _read(output)
    assert report["schema_version"] == cohort.REPORT_SCHEMA and report["complete"] is False
    assert report["coverage"]["missing"] == 1566
    before = output.read_bytes()
    with pytest.raises(SystemExit):
        cohort.main(args)
    assert output.read_bytes() == before
    assert not list(tmp_path.glob(".report.json.*"))


def test_invalid_input_does_not_publish_success_shaped_report(tmp_path):
    root, entry = _release(tmp_path / "cohort")
    index = _index(tmp_path, [entry])
    (root / "queue.jsonl").write_text("tampered")
    output = tmp_path / "report.json"
    with pytest.raises(SystemExit):
        cohort.main(["--queue", str(QUEUE), "--index", str(index), "--output", str(output)])
    assert not output.exists()
