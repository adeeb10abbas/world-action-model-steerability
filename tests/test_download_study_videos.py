"""CPU/filesystem tests: fake video bytes, no codecs, models, or cluster calls."""
import copy
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from tools import download_study_videos as downloader


def record(path: Path, relative: str) -> dict:
    raw = path.read_bytes()
    return {"path": relative, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def save_json(root: Path, relative: str, value: dict) -> dict:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))
    return record(path, relative)


@pytest.fixture
def package(tmp_path, monkeypatch):
    # Unit transport fixtures use one completed cell; the unmocked 1566-identity
    # contract is exercised separately without thousands of redundant transfers.
    monkeypatch.setattr(downloader, "STUDY_EPISODES", 1)
    root = tmp_path / "source"
    root.mkdir()
    cell, attempt = "N3-LAT-P01-D-POS", "attempt-001"
    manifest_path = f"attempts/{cell}/{attempt}/manifest.json"
    video_path = f"viewing/attempts/{cell}/{attempt}/videos/viewport.mp4"
    original = {"bytes": 999, "sha256": "a" * 64}
    # This is the exact AttemptRecorder.artifact_manifest shape. No real media.
    manifest = {
        "schema_version": "sgw-01-attempt-manifest-v1", "complete": True,
        "release_id": "release-test", "release_hashes": {"queue.jsonl": "b" * 64},
        "cell_id": cell, "attempt_id": attempt,
        "artifacts": {"videos/viewport.mp4": original,
                      "predictions/request-0000-arrays/array-00001.npy": {"bytes": 1234, "sha256": "c" * 64}},
        "result": {"status": "valid_model_failure", "failure_reason": "wrong_side"},
    }
    request_path = "predictions/request-0000.json"
    request = save_json(root, f"attempts/{cell}/{attempt}/{request_path}", {
        "future_status": "not_exposed", "raw_response": {},
    })
    manifest["artifacts"][request_path] = downloader.identity(request)
    manifest_record = save_json(root, manifest_path, manifest)
    path = root / video_path
    path.parent.mkdir(parents=True)
    path.write_bytes(b"synthetic CPU-only viewing-copy bytes")
    probe = {"width": 1280, "height": 720, "frame_count": 451, "fps_numerator": 15, "fps_denominator": 1}
    value = {
        "schema_version": downloader.INDEX_SCHEMA, "study_id": "SGW-01",
        "cohort_id": "synthetic-test-cohort", "planned_queue_sha256": "f" * 64,
        "study_status": "completed", "expected_episodes": 1, "completed_episodes": 1,
        "completion_receipt": save_json(root, "delivery/completion.json", {
            "schema_version": "sgw-01-cohort-analysis-v1", "cohort_id": "synthetic-test-cohort",
            "cohort_root": str(root),
            "planned_queue_sha256": "f" * 64, "complete": True,
            "coverage": {"expected": 1, "observed": 1, "completed": 1,
                         "missing": 0, "duplicate": 0, "technical_invalid": 0},
            "releases": [{"release_id": "release-test", "root": str(root / "release-test"),
                          "artifact_root": str(root), "hashes": manifest["release_hashes"],
                          "hashes_json_sha256": "b" * 64, "completion_pointers": [{
                              "cell_id": cell, "path": str(root / "cells" / f"{cell}.complete.json"),
                              "sha256": "d" * 64, "manifest_path": str(root / manifest_path),
                              "manifest_sha256": manifest_record["sha256"],
                          }]}],
            "ledger": [{"cell_id": cell, "release_id": "release-test", "attempt_id": attempt,
                        "analysis_status": "complete", "status": "valid_model_failure"}],
        }),
        "attempt_manifests": [manifest_record],
        "predictions": [{"manifest_path": manifest_path, "request_path": request_path, "status": "not_exposed"}],
        "videos": [{**record(path, video_path),
                    "original": {"manifest_path": manifest_path, "path": "videos/viewport.mp4", **original},
                    "encoding": {"codec": "h264", "encoder": "test encoder; not executed",
                                 "arguments": ["ffmpeg", "-crf", "18"],
                                 "source": probe, "output": copy.deepcopy(probe),
                                 "timing_basis": "recorded_presentation",
                                 "physical_time": {"status": "unavailable"}}}],
    }
    return {"root": root, "destination": tmp_path / "downloads", "value": value, "manifest": manifest}


def refresh(package):
    manifest_path = package["value"]["attempt_manifests"][0]["path"]
    package["value"]["attempt_manifests"][0] = save_json(package["root"], manifest_path, package["manifest"])
    receipt_path = package["value"]["completion_receipt"]["path"]
    receipt = json.loads((package["root"] / receipt_path).read_bytes())
    for release in receipt.get("releases", []):
        for pointer in release.get("completion_pointers", []):
            if pointer["manifest_path"] == str(package["root"] / manifest_path):
                pointer["manifest_sha256"] = package["value"]["attempt_manifests"][0]["sha256"]
    package["value"]["completion_receipt"] = save_json(package["root"], receipt_path, receipt)
    identity = save_json(package["root"], "delivery/videos.json", package["value"])
    return {
        "index": package["root"] / identity["path"], "index_sha256": identity["sha256"],
        "metadata_root": package["root"], "destination": package["destination"],
        "source": downloader.Source("local", str(package["root"])), "reserve_bytes": 0,
    }


def local_video(package):
    return package["destination"] / "study" / package["value"]["videos"][0]["path"]


def expose_prediction(package):
    raw_path = "predictions/request-0000-arrays/array-00001.npy"
    request_path = "predictions/request-0000.json"
    request_record = save_json(
        package["root"], str(Path(package["value"]["attempt_manifests"][0]["path"]).parent / request_path),
        {"future_status": "decoded_unmapped", "raw_response": {
            "future": {"path": raw_path, "sha256": package["manifest"]["artifacts"][raw_path]["sha256"],
                       "shape": [451, 720, 1280, 3], "dtype": "uint8"}}},
    )
    package["manifest"]["artifacts"][request_path] = downloader.identity(request_record)
    package["value"]["predictions"][0]["status"] = "encoded"


def test_download_receipt_resume_and_offline_verification(package, monkeypatch):
    args = refresh(package)
    report = downloader.archive(**args)
    assert report["complete"] == 1 and report["missing"] == report["failed"] == 0
    assert report["verified_bytes"] == report["expected_bytes"]
    assert report["index_coverage_complete"]
    assert local_video(package).read_bytes() == (package["root"] / package["value"]["videos"][0]["path"]).read_bytes()
    receipt = json.loads(Path(report["receipt"]).read_text())
    assert receipt["files"][0]["original"]["sha256"] == "a" * 64
    assert receipt["files"][0]["outcome_status"] == "valid_model_failure"
    assert receipt["attempt_manifests"] == package["value"]["attempt_manifests"]
    assert receipt["source"]["root"] == str(package["root"])
    assert not list(package["destination"].rglob("*.npy"))
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("matching/verify must not transfer"))
    restarted = downloader.archive(**args)
    assert restarted["files"][0]["action"] == "skipped_matching"
    assert restarted["receipt"] != report["receipt"]
    assert downloader.archive(**args, verify_only=True)["index_coverage_complete"]


def test_existing_mismatch_stops_bulk_transfer_without_overwrite(package, monkeypatch):
    args = refresh(package)
    path = local_video(package)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"unrelated existing data")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("must not transfer"))
    report = downloader.archive(**args)
    assert report["failed"] == 1 and not report["index_coverage_complete"]
    assert "not overwritten" in report["files"][0]["error"]
    assert path.read_bytes() == b"unrelated existing data"


@pytest.mark.parametrize("failure", ["interrupted", "hash", "timeout"])
def test_failed_transfer_never_publishes_and_can_restart(package, monkeypatch, failure):
    args = refresh(package)
    actual_run = subprocess.run

    def failed_run(command, **kwargs):
        kwargs["stdout"].write(b"interrupted bytes")
        if failure == "timeout":
            raise subprocess.TimeoutExpired(command, 1)
        return subprocess.CompletedProcess(command, 1 if failure == "interrupted" else 0, stderr=b"interrupted")

    monkeypatch.setattr(subprocess, "run", failed_run)
    report = downloader.archive(**args)
    assert report["failed"] == 1 and report["verified_bytes"] == 0
    assert not local_video(package).exists()
    partial = package["destination"] / report["files"][0]["partial_path"]
    assert partial.is_file()
    verified = downloader.archive(**args, verify_only=True)
    assert verified["complete"] == 0 and verified["missing"] == 1
    monkeypatch.setattr(subprocess, "run", actual_run)
    assert downloader.archive(**args)["index_coverage_complete"]
    assert partial.read_bytes() == b"interrupted bytes"  # Do not delete unknown/stale partials.


def test_missing_and_unfinished_sources(package):
    args = refresh(package)
    source_path = package["root"] / package["value"]["videos"][0]["path"]
    source_path.unlink()
    report = downloader.archive(**args)
    assert report["failed"] == 1 and report["verified_bytes"] == 0
    assert "FileNotFoundError" in report["files"][0]["error"]
    package["manifest"]["complete"] = False
    with pytest.raises(ValueError, match="unfinished"):
        downloader.archive(**refresh(package))


@pytest.mark.parametrize("bad_path", ["../escape.mp4", "/absolute.mp4", "viewing//x.mp4",
                                     "viewing/./x.mp4", "viewing/a\\b.mp4", "viewing/a.partial.mp4",
                                     "viewing/x.mp4/../z.mp4", "viewing/x.mp4."])
def test_reject_unsafe_paths_before_creation(package, bad_path):
    package["value"]["videos"][0]["path"] = bad_path
    with pytest.raises(ValueError):
        downloader.archive(**refresh(package))
    assert not package["destination"].exists()


@pytest.mark.parametrize("collision", ["duplicate", "case", "ancestor"])
def test_reject_ambiguous_collisions(package, collision):
    other = copy.deepcopy(package["value"]["videos"][0])
    if collision == "case":
        other["path"] = other["path"].upper()
    elif collision == "ancestor":
        other["path"] += "/nested.mp4"
    package["value"]["videos"].append(other)
    with pytest.raises(ValueError, match="colliding"):
        downloader.archive(**refresh(package))


@pytest.mark.parametrize("target", ["root", "directory", "file", "state", "ancestor"])
def test_destination_symlinks_do_not_escape(package, target):
    args = refresh(package)
    outside = package["root"].parent / "outside"
    outside.mkdir()
    sentinel = outside / "sentinel"
    sentinel.write_bytes(b"leave me alone")
    destination = package["destination"]
    if target == "root":
        destination.symlink_to(outside, target_is_directory=True)
    elif target == "ancestor":
        destination.symlink_to(outside, target_is_directory=True)
        args["destination"] = destination / "nested"
    elif target in {"directory", "state"}:
        destination.mkdir()
        (destination / ("study" if target == "directory" else ".video-downloads")).symlink_to(outside)
    else:
        video = local_video(package)
        video.parent.mkdir(parents=True)
        video.symlink_to(sentinel)
    if target in {"root", "state", "ancestor"}:
        with pytest.raises((OSError, ValueError)):
            downloader.archive(**args)
    else:
        assert downloader.archive(**args)["failed"] == 1
    assert sentinel.read_bytes() == b"leave me alone"
    assert sorted(path.name for path in outside.iterdir()) == ["sentinel"]


def test_source_symlink_rejected(package):
    args = refresh(package)
    path = package["root"] / package["value"]["videos"][0]["path"]
    outside = package["root"].parent / "other.mp4"
    outside.write_bytes(path.read_bytes())
    path.unlink()
    path.symlink_to(outside)
    report = downloader.archive(**args)
    assert report["failed"] == 1 and not local_video(package).exists()


def test_metadata_digest_and_symlink_are_checked(package):
    args = refresh(package)
    receipt = package["root"] / package["value"]["completion_receipt"]["path"]
    receipt.write_text('{"changed": true}')
    with pytest.raises(ValueError, match="mismatch"):
        downloader.archive(**args)
    with pytest.raises(ValueError, match="explicitly pinned"):
        downloader.archive(**{**args, "index_sha256": "0" * 64})
    receipt.unlink()
    receipt.symlink_to(args["index"])
    with pytest.raises(OSError):
        downloader.archive(**args)


def test_final_delivery_gate_is_not_video_count(package):
    for field, value in (("study_status", "running"), ("completed_episodes", 1565),
                         ("expected_episodes", 18), ("completed_episodes", True)):
        original = package["value"][field]
        package["value"][field] = value
        with pytest.raises(ValueError, match="completed-study gate"):
            downloader.archive(**refresh(package))
        package["value"][field] = original
    assert not package["destination"].exists()


@pytest.mark.parametrize("field,value", [
    ("complete", False), ("cohort_id", "other"), ("planned_queue_sha256", "0" * 64),
    ("schema_version", "unknown"), ("expected", 18), ("observed", 1565),
    ("completed", 1565), ("missing", 1), ("duplicate", 1), ("technical_invalid", 1),
    ("missing", False),
])
def test_compiler_report_gate(package, field, value):
    path = package["value"]["completion_receipt"]["path"]
    report = json.loads((package["root"] / path).read_text())
    if field in report["coverage"]:
        report["coverage"][field] = value
    else:
        report[field] = value
    package["value"]["completion_receipt"] = save_json(package["root"], path, report)
    with pytest.raises(ValueError, match="compiler completion receipt"):
        downloader.archive(**refresh(package))
    assert not package["destination"].exists()


def test_aggregate_disk_preflight_refuses_all_copy(package, monkeypatch):
    second = copy.deepcopy(package["value"]["videos"][0])
    second["path"] = second["path"].replace("viewport.mp4", "prediction.mp4")
    raw_path = "predictions/request-0000-arrays/array-00001.npy"
    second["original"].update(path=raw_path, **package["manifest"]["artifacts"][raw_path])
    package["value"]["videos"].append(second)
    expose_prediction(package)
    args = refresh(package)
    available = second["bytes"] + 100
    monkeypatch.setattr(downloader, "free_bytes", lambda _: available)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("no transfer with inadequate space"))
    report = downloader.archive(**{**args, "reserve_bytes": 100})
    assert report["preflight"] == {
        "transfer_bytes": report["expected_bytes"], "headroom_bytes": 100,
        "required_bytes": report["expected_bytes"] + 100, "available_bytes": available,
        "shortfall_bytes": second["bytes"],
    }
    assert report["missing"] == 2 and report["verified_bytes"] == 0
    assert "no transfers started" in report["errors"][0]
    assert not list(package["destination"].rglob("*.partial"))


def test_concurrent_download_is_rejected(package, monkeypatch):
    args = refresh(package)
    state = package["destination"] / ".video-downloads"
    state.mkdir(parents=True)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("locked destination must not transfer"))
    with (state / "lock").open("w") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            downloader.archive(**args)


def test_incremental_final_index_and_technical_separation(package):
    downloader.archive(**refresh(package))
    video = copy.deepcopy(package["value"]["videos"][0])
    raw_path = "predictions/request-0000-arrays/array-00001.npy"
    video["original"] = {"manifest_path": package["value"]["attempt_manifests"][0]["path"],
                         "path": raw_path, **package["manifest"]["artifacts"][raw_path]}
    video["path"] = video["path"].replace("viewport.mp4", "prediction-0000.mp4")
    (package["root"] / video["path"]).write_bytes(b"decoded same-request future viewing copy")
    video.update(record(package["root"] / video["path"], video["path"]))
    video["encoding"]["source"].update(fps_numerator=None, fps_denominator=None)
    video["encoding"]["timing_basis"] = "playback_only"
    package["value"]["videos"].append(video)
    expose_prediction(package)
    report = downloader.archive(**refresh(package))
    assert report["complete"] == 2
    assert [entry["action"] for entry in report["files"]] == ["skipped_matching", "downloaded"]
    assert report["files"][1]["encoding"]["physical_time"] == {"status": "unavailable"}
    # A separate synthetic finalized technical attempt, not a scientific outcome rewrite.
    technical = copy.deepcopy(package["manifest"])
    technical["attempt_id"] = "technical-attempt-001"
    technical["result"] = {"status": "technical_invalid", "technical_cause": "test"}
    manifest_path = package["value"]["attempt_manifests"][0]["path"].replace("attempt-001", "technical-attempt-001")
    technical["artifacts"].pop(raw_path)
    technical["artifacts"].pop("predictions/request-0000.json")
    package["value"]["attempt_manifests"].append(save_json(package["root"], manifest_path, technical))
    item = copy.deepcopy(package["value"]["videos"][0])
    source_bytes = (package["root"] / item["path"]).read_bytes()
    item["path"] = item["path"].replace("attempt-001", "technical-attempt-001")
    target = package["root"] / item["path"]
    target.parent.mkdir(parents=True)
    target.write_bytes(source_bytes)
    item["original"]["manifest_path"] = manifest_path
    package["value"]["videos"].append(item)
    report = downloader.archive(**refresh(package))
    assert report["complete"] == 3
    assert report["files"][-1]["category"] == "technical"
    assert report["files"][-1]["local_path"].startswith("technical/")


@pytest.mark.parametrize("change", ["frame_count", "fps", "codec", "original", "omitted", "timing"])
def test_derivative_provenance_and_completeness(package, change):
    video = package["value"]["videos"][0]
    if change == "frame_count":
        video["encoding"]["output"]["frame_count"] -= 1
    elif change == "fps":
        video["encoding"]["output"]["fps_numerator"] = 30
    elif change == "codec":
        video["encoding"]["codec"] = "vp9"
    elif change == "original":
        video["original"]["sha256"] = "d" * 64
    elif change == "omitted":
        package["manifest"]["artifacts"]["videos/another-camera.mp4"] = {"bytes": 1, "sha256": "e" * 64}
    else:
        video["encoding"]["timing_basis"] = "verified_physical"
    with pytest.raises(ValueError):
        downloader.archive(**refresh(package))
    assert not package["destination"].exists()


def test_kubectl_is_argument_vector_not_shell(package, monkeypatch):
    args = refresh(package)
    source = downloader.Source("kubectl", "/cohort with spaces", "ctx;echo nope", "namespace",
                               "recording-reader", "reader", "/usr/bin/python3")

    def mock_kubectl(command, **kwargs):
        assert command[:7] == ["kubectl", "--context=ctx;echo nope", "--namespace=namespace", "exec",
                               "recording-reader", "--container=reader", "--"]
        assert command[7:9] == ["/usr/bin/python3", "-c"]
        assert command[-3] == "/cohort with spaces"
        assert "shell" not in kwargs
        assert kwargs["stdin"] == subprocess.DEVNULL
        kwargs["stdout"].write((package["root"] / command[-2]).read_bytes())
        return subprocess.CompletedProcess(command, 0, stderr=b"")

    monkeypatch.setattr(subprocess, "run", mock_kubectl)
    assert downloader.archive(**{**args, "source": source})["index_coverage_complete"]


def test_cli_rejects_nonstudy_scope(package):
    args = refresh(package)
    command = [
        sys.executable, "-m", "tools.download_study_videos", "verify",
        "--index", str(args["index"]), "--index-sha256", args["index_sha256"],
        "--metadata-root", str(args["metadata_root"]), "--destination", str(args["destination"]),
        "--transport", "local", "--source-root", "/nonexistent-source", "--reserve-bytes", "0",
    ]
    completed = subprocess.run(command, capture_output=True, text=True)
    assert completed.returncode == 1
    assert "completed-study gate" in json.loads(completed.stderr)["error"]


def test_duplicate_json_keys_rejected():
    with pytest.raises(ValueError, match="duplicate JSON key"):
        downloader.decode(b'{"videos": [], "videos": [1]}')


def test_actual_recorder_manifest_is_supported(package):
    from types import SimpleNamespace
    from experiments.workshops.spatial_grounding_v1.recorder import AttemptRecorder

    old = package["manifest"]
    recorder = AttemptRecorder(
        SimpleNamespace(root=package["root"] / old["release_id"], release_id=old["release_id"],
                        hashes=old["release_hashes"]),
        SimpleNamespace(cell_id=old["cell_id"]), "technical-attempt-001",
    )
    original_path = recorder.path / "videos/viewport.mp4"
    original_path.parent.mkdir(parents=True, exist_ok=True)
    original_path.write_bytes(b"retained master; synthetic test data")
    manifest = recorder.artifact_manifest({"status": "technical_invalid", "technical_cause": "test"})
    manifest_path = (recorder.path / "manifest.json").relative_to(package["root"]).as_posix()
    package["value"]["attempt_manifests"].append(record(recorder.path / "manifest.json", manifest_path))
    video = copy.deepcopy(package["value"]["videos"][0])
    raw = (package["root"] / video["path"]).read_bytes()
    video["path"] = video["path"].replace("attempt-001", "technical-attempt-001")
    target = package["root"] / video["path"]
    target.parent.mkdir(parents=True)
    target.write_bytes(raw)
    video["original"].update(manifest["artifacts"]["videos/viewport.mp4"], manifest_path=manifest_path)
    package["value"]["videos"].append(video)
    report = downloader.archive(**refresh(package))
    assert report["complete"] == 2 and report["files"][-1]["category"] == "technical"
    assert original_path.read_bytes() == b"retained master; synthetic test data"


def test_full_1566_completed_identity_contract(tmp_path):
    assert downloader.STUDY_EPISODES == 1566
    manifests, records, pointers, ledger = {}, {}, [], []
    hashes = {"queue.jsonl": "a" * 64}
    for index in range(1566):
        cell = f"synthetic-cell-{index}"
        path = f"attempts/{cell}/attempt-001/manifest.json"
        manifests[path] = {
            "schema_version": "sgw-01-attempt-manifest-v1", "complete": True,
            "cell_id": cell, "attempt_id": "attempt-001", "release_id": "synthetic-release",
            "release_hashes": hashes, "artifacts": {"videos/viewport.mp4": {"bytes": 1, "sha256": "c" * 64}},
            "result": {"status": "valid_model_failure"},
        }
        records[path] = {"sha256": "b" * 64}
        pointers.append({"cell_id": cell, "manifest_path": "/cohort/" + path, "manifest_sha256": "b" * 64})
        ledger.append({"cell_id": cell, "attempt_id": "attempt-001", "release_id": "synthetic-release",
                       "analysis_status": "complete", "status": "valid_model_failure"})
    report = {"cohort_root": "/cohort", "ledger": ledger, "releases": [{
        "release_id": "synthetic-release", "artifact_root": "/cohort", "hashes": hashes,
        "completion_pointers": pointers,
    }]}
    assert len(downloader.completed_attempts(report, manifests, records)) == 1566
    metadata_root = tmp_path / "metadata"
    videos = []
    probe = {"width": 64, "height": 48, "frame_count": 5, "fps_numerator": 15, "fps_denominator": 1}
    for pointer, (path, manifest) in zip(pointers, manifests.items(), strict=True):
        records[path] = save_json(metadata_root, path, manifest)
        pointer["manifest_sha256"] = records[path]["sha256"]
        videos.append({
            "path": "viewing/" + str(Path(path).parent / "videos/viewport.mp4"), "bytes": 1, "sha256": "d" * 64,
            "original": {"manifest_path": path, "path": "videos/viewport.mp4", "bytes": 1, "sha256": "c" * 64},
            "encoding": {"codec": "h264", "encoder": "synthetic contract fixture", "arguments": ["synthetic"],
                         "source": probe, "output": probe, "timing_basis": "recorded_presentation",
                         "physical_time": {"status": "unavailable"}},
        })
    report.update(
        schema_version="sgw-01-cohort-analysis-v1", cohort_id="synthetic-full-cohort", complete=True,
        planned_queue_sha256="f" * 64,
        coverage={"expected": 1566, "observed": 1566, "completed": 1566,
                  "missing": 0, "duplicate": 0, "technical_invalid": 0},
    )
    receipt = save_json(metadata_root, "delivery/completion.json", report)
    index = save_json(metadata_root, "delivery/videos.json", {
        "schema_version": downloader.INDEX_SCHEMA, "study_id": "SGW-01",
        "study_status": "completed", "cohort_id": report["cohort_id"], "planned_queue_sha256": "f" * 64,
        "expected_episodes": 1566, "completed_episodes": 1566, "completion_receipt": receipt,
        "attempt_manifests": list(records.values()), "videos": videos, "predictions": [],
    })
    completed = subprocess.run([
        sys.executable, "-m", "tools.download_study_videos", "verify",
        "--index", str(metadata_root / index["path"]), "--index-sha256", index["sha256"],
        "--metadata-root", str(metadata_root), "--destination", str(tmp_path / "archive"),
        "--transport", "local", "--source-root", "/nonexistent-source", "--reserve-bytes", "0",
    ], capture_output=True, text=True, timeout=30)
    assert completed.returncode == 1, completed.stderr
    assert json.loads(completed.stdout)["missing"] == 1566
    assert json.loads(completed.stdout)["verified_bytes"] == 0
    nested = copy.deepcopy(report)
    nested["releases"][0]["artifact_root"] = "/cohort/lane"
    for pointer in nested["releases"][0]["completion_pointers"]:
        pointer["manifest_path"] = pointer["manifest_path"].replace("/cohort/", "/cohort/lane/", 1)
    assert len(downloader.completed_attempts(
        nested, {"lane/" + path: value for path, value in manifests.items()},
        {"lane/" + path: value for path, value in records.items()},
    )) == 1566
    missing = records.pop(next(iter(records)))
    with pytest.raises(ValueError, match="omits completed study attempt"):
        downloader.completed_attempts(report, manifests, records)
    records[next(iter(manifests))] = missing
    ledger[0]["attempt_id"] = "different-attempt"
    with pytest.raises(ValueError, match="provenance differs"):
        downloader.completed_attempts(report, manifests, records)
    ledger.pop(0)
    pointers.pop(0)
    with pytest.raises(ValueError, match="exactly 1566"):
        downloader.completed_attempts(report, manifests, records)


def test_whole_completed_attempt_cannot_be_replaced_by_historical_one(package):
    args = refresh(package)
    historical = copy.deepcopy(package["manifest"])
    historical["attempt_id"] = "historical-attempt"
    historical["result"]["status"] = "technical_invalid"
    historical_path = f"attempts/{historical['cell_id']}/historical-attempt/manifest.json"
    package["value"]["attempt_manifests"] = [save_json(package["root"], historical_path, historical)]
    index = save_json(package["root"], "delivery/videos.json", package["value"])
    with pytest.raises(ValueError, match="omits completed study attempt"):
        downloader.archive(**{**args, "index_sha256": index["sha256"]})
    assert not package["destination"].exists()


@pytest.mark.parametrize("absent", ["original", "derivative"])
def test_required_completed_viewport_cannot_be_omitted(package, absent):
    if absent == "original":
        package["manifest"]["artifacts"].pop("videos/viewport.mp4")
    else:
        package["manifest"]["artifacts"]["videos/other-camera.mp4"] = package["manifest"]["artifacts"]["videos/viewport.mp4"]
        package["value"]["videos"][0]["original"]["path"] = "videos/other-camera.mp4"
    with pytest.raises(ValueError, match="required viewport|omits recorded videos"):
        downloader.archive(**refresh(package))
    assert not package["destination"].exists()


@pytest.mark.parametrize("declaration", ["encoded", "not_exposed", "decode_error"])
def test_exposed_future_cannot_be_omitted_or_declared_unavailable(package, declaration):
    expose_prediction(package)
    package["value"]["predictions"][0]["status"] = declaration
    with pytest.raises(ValueError, match="exposed prediction lacks"):
        downloader.archive(**refresh(package))
    assert not package["destination"].exists()


def test_even_unavailable_future_needs_explicit_matching_disposition(package):
    package["value"]["predictions"] = []
    with pytest.raises(ValueError, match="disposition is missing"):
        downloader.archive(**refresh(package))
    package["value"]["predictions"] = [{
        "manifest_path": package["value"]["attempt_manifests"][0]["path"],
        "request_path": "predictions/request-0000.json", "status": "decode_error",
    }]
    with pytest.raises(ValueError, match="unavailable prediction differs"):
        downloader.archive(**refresh(package))


def test_request_identity_is_checked_without_array_transfer(package):
    args = refresh(package)
    request = package["root"] / Path(package["value"]["attempt_manifests"][0]["path"]).parent / "predictions/request-0000.json"
    request.write_text('{"future_status":"not_exposed","raw_response":{}}')
    with pytest.raises(ValueError, match="mismatch"):
        downloader.archive(**args)


@pytest.mark.parametrize("status", ["not_exposed", "decode_error", "latent_only_retained"])
def test_recorded_unavailable_predictions_remain_explicit(package, status):
    request_path = "predictions/request-0000.json"
    record_path = str(Path(package["value"]["attempt_manifests"][0]["path"]).parent / request_path)
    request = save_json(package["root"], record_path, {"future_status": status, "raw_response": {}})
    package["manifest"]["artifacts"][request_path] = downloader.identity(request)
    package["value"]["predictions"][0]["status"] = status
    report = downloader.archive(**refresh(package))
    assert report["index_coverage_complete"]
    assert report["predictions"][0]["status"] == report["predictions"][0]["recorded_status"] == status
    assert report["complete"] == 1  # Only the viewport, never an invented forecast.


def test_canonical_future_selection_matches_adapter():
    first, trace = {"path": "first.npy"}, {"path": "trace.npy"}
    request = {"future_status": "decoded_unmapped", "raw_response": {
        "future": first, "native_trace": {"future": trace},
    }}
    assert downloader.decoded_future(request) is first
    request["raw_response"]["future"] = None
    assert downloader.decoded_future(request) is trace
