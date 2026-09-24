"""CPU-only compilation of explicitly indexed, immutable SGW-01 releases."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
import re
import sys
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments.workshops.spatial_grounding_v1 import compile as analysis
from experiments.workshops.spatial_grounding_v1.contract import (
    REQUIRED_RELEASE_FILES, STAGE_EPISODES, Release, load_json, load_release, sha256_file,
)
from experiments.workshops.spatial_grounding_v1.recorder import atomic_json

SPEC = ROOT / "experiments/workshops/spatial_grounding_v1/spec"
INDEX_SCHEMA = "sgw-01-cohort-index-v1"
REPORT_SCHEMA = "sgw-01-cohort-analysis-v1"
PARTITIONS = {
    (model, family, stage)
    for model in ("N3", "E3", "F3")
    for family in ("LAT", "HEIGHT", "DIST")
    for stage in STAGE_EPISODES
}
RELEASE_FIELDS = {"status", "fixture_sha256", "runtime_sha256", "time_map_sha256"}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _path(value: Any, base: Path, label: str) -> Path:
    _require(isinstance(value, str) and bool(value.strip()), f"missing {label} path")
    return (base / value).resolve()


def _within(path: Path, root: Path, label: str) -> None:
    _require(path.is_relative_to(root), f"{label} outside root: {path}")


def _partition(row: Mapping[str, Any]) -> tuple[str, str, str]:
    return (row["model"], row["family"], row["stage"])


def _load_indexed_release(
    entry: Mapping[str, Any], index_dir: Path, cohort_root: Path,
    planned: Sequence[Mapping[str, str]], queue_hash: str,
) -> Release:
    root = _path(entry.get("root"), index_dir, "release root")
    _within(root.parent, cohort_root, "release artifact parent")
    for name in REQUIRED_RELEASE_FILES:
        _within((root / name).resolve(), root, "immutable release input")
    _require(sha256_file(root / "hashes.json") == entry.get("hashes_json_sha256"),
             f"indexed hashes.json mismatch: {root}")
    release = load_release(root)
    receipt = load_json(root / "release_receipt.json", "release receipt")
    partition = _partition(entry)
    _require(partition in PARTITIONS, f"unknown release partition: {partition}")
    _require(release.release_id == entry.get("release_id"), "indexed release_id mismatch")
    _require(receipt.get("schema_version") == "sgw-01-release-v1"
             and receipt.get("status") == "released", "not a study release receipt")
    _require(_partition(receipt) == partition, "release receipt partition mismatch")
    _require(receipt.get("source_queue_sha256") == queue_hash, "release source queue provenance mismatch")
    commit = entry.get("source_commit")
    _require(isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{40}", commit) is not None
             and release.binding.get("source_commit") == commit, "release source commit provenance mismatch")
    for name in ("protocol.json", "prompts.json"):
        _require(release.hashes[name] == sha256_file(SPEC / name), f"frozen {name} provenance mismatch")
    expected = [row for row in planned if _partition(row) == partition]
    _require(type(receipt.get("cell_count")) is int and receipt["cell_count"] == len(expected)
             and len(release.cells) == len(expected) == STAGE_EPISODES[partition[2]],
             "release partition cell count mismatch")
    release.partition(*partition)
    fixtures = load_json(root / "fixtures.json", "fixtures")
    for cell, frozen in zip(release.cells, expected, strict=True):
        _require(all(str(cell.row.get(key)) == value for key, value in frozen.items()
                     if key not in RELEASE_FIELDS), f"released cell differs from frozen queue: {cell.cell_id}")
        _require(cell.row["runtime_sha256"] == release.hashes["runtime_binding.json"],
                 f"cell runtime provenance mismatch: {cell.cell_id}")
        _require(cell.row["fixture_sha256"] == fixtures.get("layouts", {}).get(
            cell.row["layout_id"], {}).get("fixture_sha256")
            and cell.row["time_map_sha256"] == fixtures.get("time_maps", {}).get(cell.model),
            f"cell fixture/time-map provenance mismatch: {cell.cell_id}")
    return release


def _pointer_inputs(pointer: Path, release: Release, planned: Mapping[str, str]) -> dict[str, Any]:
    """Check ownership/containment before the existing compiler verifies bytes."""
    artifact_root = release.root.parent
    _within(pointer.resolve(), (artifact_root / "cells").resolve(), "completion pointer")
    raw = load_json(pointer, "completion pointer")
    cell_id = planned["cell_id"]
    _require(pointer.name == f"{cell_id}.complete.json", "completion pointer filename/cell mismatch")
    attempt_id = raw.get("attempt_id")
    _require(isinstance(attempt_id, str) and re.fullmatch(r"[A-Za-z0-9_-]+", attempt_id) is not None,
             "invalid completion attempt_id")
    attempt_root = (artifact_root / "attempts" / cell_id / attempt_id).resolve()
    _within(attempt_root, artifact_root, "attempt")
    manifest_path = _path(raw.get("manifest_path"), artifact_root, "manifest")
    result_ref = raw.get("result")
    _require(isinstance(result_ref, dict), "completion pointer lacks result reference")
    result_path = _path(result_ref.get("path"), artifact_root, "result")
    _require(manifest_path == attempt_root / "manifest.json" and result_path == attempt_root / "result.json",
             "completion manifest/result outside owning attempt")
    manifest = load_json(manifest_path, "attempt manifest")
    result = manifest.get("result")
    _require(isinstance(result, dict), "attempt manifest lacks result")
    for record in (raw, manifest, result):
        _require(record.get("release_id") == release.release_id and record.get("cell_id") == cell_id
                 and record.get("attempt_id") == attempt_id, "completion release/cell/attempt identity mismatch")
    _require(manifest.get("schema_version") == "sgw-01-attempt-manifest-v1"
             and result.get("schema_version") == "sgw-01-result-v1", "unknown recorded result schema")
    artifacts = manifest.get("artifacts")
    _require(isinstance(artifacts, dict) and "result.json" in artifacts, "manifest lacks result artifact")
    for name, metadata in artifacts.items():
        artifact = (attempt_root / name).resolve()
        _within(artifact, attempt_root, "artifact")
        _require(isinstance(metadata, dict) and artifact.is_file()
                 and metadata.get("bytes") == artifact.stat().st_size, f"artifact size mismatch: {artifact}")
    for key, value in planned.items():
        if key in result and key not in RELEASE_FIELDS:
            _require(str(result[key]) == value, f"result overrides frozen {key}: {cell_id}")
    return {
        "cell_id": cell_id, "path": str(pointer.resolve()), "sha256": sha256_file(pointer),
        "manifest_path": str(manifest_path), "manifest_sha256": raw.get("manifest_sha256"),
        "result": {"path": str(result_path), "sha256": result_ref.get("sha256")},
    }


def compile_study_cohort(queue: Path, index_path: Path) -> dict[str, Any]:
    """Read only indexed study roots; never execute, rescore, or discover cohorts."""
    queue, index_path = queue.resolve(), index_path.resolve()
    index_hash = sha256_file(index_path)
    index = load_json(index_path, "cohort index")
    _require(index.get("schema_version") == INDEX_SCHEMA, "unknown cohort index schema")
    _require(isinstance(index.get("cohort_id"), str) and bool(index["cohort_id"].strip()), "missing cohort_id")
    cohort_root = _path(index.get("cohort_root"), index_path.parent, "cohort root")
    _require(cohort_root.is_dir(), "cohort root does not exist")
    queue_hash = sha256_file(queue)
    _require(queue_hash == index.get("planned_queue_sha256") == sha256_file(SPEC / "planned_cells.csv"),
             "planned queue differs from frozen source/index")
    with queue.open(newline="") as stream:
        planned = list(csv.DictReader(stream))
    by_id = {row["cell_id"]: row for row in planned}
    _require(len(planned) == len(by_id) == 1566
             and {_partition(row) for row in planned} == PARTITIONS, "invalid frozen study scope")
    entries = index.get("releases")
    _require(isinstance(entries, list), "index releases must be an explicit list")
    releases: dict[str, Release] = {}
    by_partition: dict[tuple[str, str, str], str] = {}
    roots: set[Path] = set()
    provenance: list[dict[str, Any]] = []
    for entry in entries:
        _require(isinstance(entry, dict), "release index entry must be an object")
        release = _load_indexed_release(entry, index_path.parent, cohort_root, planned, queue_hash)
        partition = _partition(entry)
        _require(release.release_id not in releases, "duplicate release identity")
        _require(release.root not in roots, "duplicate release root")
        _require(partition not in by_partition, "duplicate release partition")
        releases[release.release_id] = release
        by_partition[partition] = release.release_id
        roots.add(release.root)
        provenance.append({
            "release_id": release.release_id, "root": str(release.root),
            "artifact_root": str(release.root.parent),
            "model": partition[0], "family": partition[1], "stage": partition[2],
            "source_commit": entry["source_commit"],
            "hashes_json_sha256": entry["hashes_json_sha256"], "hashes": dict(release.hashes),
            "expected": len(release.cells), "completion_pointers": [],
        })
    pointers: dict[str, list[Path]] = {release_id: [] for release_id in releases}
    inputs: dict[str, list[dict[str, Any]]] = {release_id: [] for release_id in releases}
    seen: set[str] = set()
    excluded: list[dict[str, Any]] = []
    for artifact_root in sorted({release.root.parent for release in releases.values()}):
        cells_root = artifact_root / "cells"
        _within(cells_root.resolve(), artifact_root, "cells directory")
        for pointer in sorted(cells_root.glob("*.complete.json")):
            _within(pointer.resolve(), cells_root.resolve(), "completion pointer")
            raw = load_json(pointer, "completion pointer")
            cell_id = raw.get("cell_id")
            _require(isinstance(cell_id, str) and cell_id in by_id, "completion pointer outside frozen queue")
            _require(cell_id not in seen, f"duplicate completion cell across releases: {cell_id}")
            seen.add(cell_id)
            expected_release = by_partition.get(_partition(by_id[cell_id]))
            release_id = raw.get("release_id")
            if expected_release is None and release_id not in releases:
                excluded.append({"cell_id": cell_id, "path": str(pointer), "sha256": sha256_file(pointer),
                                 "release_id": release_id, "status": "unindexed_not_validated"})
                continue
            _require(release_id == expected_release and release_id in releases,
                     f"completion pointer release partition mismatch: {cell_id}")
            release = releases[release_id]
            _require(release.root.parent == artifact_root, "completion pointer outside owning release artifact root")
            inputs[release_id].append(_pointer_inputs(pointer, release, by_id[cell_id]))
            pointers[release_id].append(pointer)
    baseline = analysis.compile_registered_queue(queue, [], expected_release_hashes={})
    ledger = {row["cell_id"]: row for row in baseline.ledger}
    for record in provenance:
        release = releases[record["release_id"]]
        compiled = analysis.compile_registered_queue(queue, pointers[release.release_id],
                                                     expected_release_hashes=release.hashes)
        selected = {cell.cell_id for cell in release.cells}
        ledger.update((row["cell_id"], row) for row in compiled.ledger if row["cell_id"] in selected)
        record["completion_pointers"] = inputs[release.release_id]
        record["observed"] = len(pointers[release.release_id])
    combined = analysis.registered_compilation_from_rows(ledger[row["cell_id"]] for row in planned)
    technical = [row["cell_id"] for row in combined.ledger if row["analysis_status"] == "incomplete"]
    complete = combined.complete and set(by_partition) == PARTITIONS
    _require(sha256_file(index_path) == index_hash and sha256_file(queue) == queue_hash,
             "cohort input changed during compilation")
    return {
        "schema_version": REPORT_SCHEMA, "cohort_id": index["cohort_id"],
        "cohort_root": str(cohort_root), "complete": complete,
        "planned_queue_sha256": queue_hash,
        "inputs": {"queue": str(queue), "index": str(index_path), "index_sha256": index_hash,
                   "compiler_sha256": sha256_file(Path(analysis.__file__)),
                   "cohort_compiler_sha256": sha256_file(Path(__file__))},
        "coverage": {
            "expected": len(planned), "observed": len(planned) - len(combined.missing_cell_ids),
            "completed": sum(row["analysis_status"] == "complete" for row in combined.ledger),
            "missing": len(combined.missing_cell_ids), "duplicate": 0, "technical_invalid": len(technical),
            "expected_partitions": len(PARTITIONS), "observed_partitions": len(by_partition),
        },
        "releases": provenance, "unindexed_completion_pointers": excluded,
        "missing_cell_ids": combined.missing_cell_ids, "duplicate_cell_ids": combined.duplicate_cell_ids,
        "technical_invalid_cell_ids": technical, "ledger": combined.ledger,
        "confirmation_estimates": combined.confirmation_estimates,
        "primary_statistics": analysis.compile_primary_statistics(combined),
        "paper_export_plan": analysis.render_paper_export_plan(combined),
        "coverage_table": analysis.render_neutral_coverage_table(combined),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=Path, required=True, help="exact frozen 1566-cell planned CSV")
    parser.add_argument("--index", type=Path, required=True, help="explicit hash-pinned cohort index")
    parser.add_argument("--output", type=Path, required=True, help="new downstream report path")
    parser.add_argument("--require-complete", action="store_true", help="exit 2 after writing an incomplete report")
    args = parser.parse_args(argv)
    try:
        _require(not args.output.exists(), "report output already exists; use a new checkpoint path")
        report = compile_study_cohort(args.queue, args.index)
        for release in report["releases"]:
            root = Path(release["artifact_root"])
            _require(not args.output.resolve().is_relative_to(Path(release["root"]))
                     and not any(args.output.resolve().is_relative_to(root / name) for name in ("cells", "attempts")),
                     "report output must not modify release inputs or recorded evidence")
        atomic_json(args.output, report)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    if args.require_complete and not report["complete"]:
        print("Cohort is incomplete; checkpoint report written, not final results.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
