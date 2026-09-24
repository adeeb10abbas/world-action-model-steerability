"""Archive finalized SGW-01 viewing copies, never run encoders or inference."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
from typing import Iterator
import uuid


INDEX_SCHEMA = "sgw-01-video-download-index-v1"
STUDY_EPISODES = 1566
VIDEO_SUFFIXES = {".mp4", ".m4v", ".mov", ".mkv", ".webm", ".avi"}
KINDS = {"valid_success": "study", "valid_model_failure": "study",
         "technical_invalid": "technical", "censored": "censored"}
RESERVE_BYTES = 1024**3
EXPOSED_FUTURES = {"decoded_unmapped", "exposed_and_retained"}
UNAVAILABLE_FUTURES = {"not_exposed", "decode_error", "latent_only_retained"}

# The same read-only, bounded reader runs locally in tests and in the source Pod.
# No shell, model imports, file writes, globbing, or remote temporary files.
SOURCE_READER = r"""
import os, stat, sys
root, relative, expected = sys.argv[1], sys.argv[2], int(sys.argv[3])
directory = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
try:
    for part in (root.strip("/") + "/" + relative).split("/")[:-1]:
        child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
        os.close(directory)
        directory = child
    fd = os.open(relative.split("/")[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size != expected:
            raise ValueError("source is not a regular file of the expected byte length")
        remaining = expected
        while remaining:
            chunk = stream.read(min(1024 * 1024, remaining))
            if not chunk:
                raise ValueError("source ended before expected byte length")
            sys.stdout.buffer.write(chunk)
            remaining -= len(chunk)
        after = os.fstat(stream.fileno())
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise ValueError("source changed during transfer")
        sys.stdout.buffer.flush()
finally:
    os.close(directory)
"""


def relative_path(value: object) -> str:
    if not isinstance(value, str) or not value or len(value) > 2048:
        raise ValueError(f"invalid relative path: {value!r}")
    parts = value.split("/")
    if any(not re.fullmatch(r"[A-Za-z0-9_-][A-Za-z0-9_.-]*", part)
           or part.endswith(".") for part in parts):
        raise ValueError(f"unsafe/noncanonical relative path: {value!r}")
    if any({"partial", "tmp", "part"} & set(part.lower().split(".")) for part in parts):
        raise ValueError(f"unfinished artifact path: {value}")
    return value


def identity(value: object) -> dict:
    if not isinstance(value, dict):
        raise ValueError("file identity must be an object")
    if type(value.get("bytes")) is not int or value["bytes"] <= 0:
        raise ValueError("file identity requires a positive integer byte length")
    if not isinstance(value.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", value["sha256"]):
        raise ValueError("file identity requires a lowercase SHA-256 digest")
    return {"bytes": value["bytes"], "sha256": value["sha256"]}


def unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def decode(raw: bytes) -> object:
    return json.loads(raw, object_pairs_hook=unique_object)


@contextmanager
def directory(root: Path, parts: tuple[str, ...] = (), *, create: bool = False) -> Iterator[int]:
    """Traverse with directory descriptors so symlink swaps cannot escape the root."""
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in (*root.absolute().parts[1:], *parts):
            if create:
                try:
                    os.mkdir(part, dir_fd=fd)
                except FileExistsError:
                    pass
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


def regular_file(fd: int, name: str):
    opened = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    if not stat.S_ISREG(os.fstat(opened).st_mode):
        os.close(opened)
        raise ValueError(f"not a regular file: {name}")
    return os.fdopen(opened, "rb")


def checked_bytes(raw: bytes, expected: dict, label: str) -> None:
    if len(raw) != expected["bytes"] or hashlib.sha256(raw).hexdigest() != expected["sha256"]:
        raise ValueError(f"byte length/SHA-256 mismatch: {label}")


def metadata(root: Path, record: dict) -> object:
    if not isinstance(record, dict):
        raise ValueError("metadata identity must be an object")
    path = relative_path(record.get("path"))
    expected = identity(record)
    parts = PurePosixPath(path).parts
    with directory(root, parts[:-1]) as fd, regular_file(fd, parts[-1]) as stream:
        raw = stream.read()
    checked_bytes(raw, expected, path)
    return decode(raw)


def checked_file(fd: int, name: str, expected: dict) -> None:
    digest = hashlib.sha256()
    size = 0
    with regular_file(fd, name) as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    if size != expected["bytes"] or digest.hexdigest() != expected["sha256"]:
        raise ValueError(f"byte length/SHA-256 mismatch (not overwritten): {name}")


def encoding_metadata(value: object, metadata_root: Path) -> None:
    if not isinstance(value, dict) or value.get("codec") not in {"h264", "h265"}:
        raise ValueError("viewing copy requires h264 or h265 encoding metadata")
    if (not isinstance(value.get("encoder"), str) or not value["encoder"].strip()
            or not isinstance(value.get("arguments"), list) or not value["arguments"]
            or any(not isinstance(arg, str) for arg in value["arguments"])):
        raise ValueError("encoding metadata requires encoder/version and exact argument list")
    fields = ("width", "height", "frame_count")
    source, output = value.get("source"), value.get("output")
    if not isinstance(source, dict) or not isinstance(output, dict):
        raise ValueError("source and output video measurements are required")
    if any(type(source.get(key)) is not int or source[key] <= 0
           or type(output.get(key)) is not int or output[key] <= 0 for key in fields):
        raise ValueError("video measurements must be positive integers")
    if any(source[key] != output[key] for key in fields):
        raise ValueError("viewing copy changes resolution or frame count")
    for probe in (source, output):
        fps = (probe.get("fps_numerator"), probe.get("fps_denominator"))
        if not all(key in probe for key in ("fps_numerator", "fps_denominator")) or (
                fps != (None, None) and any(type(part) is not int or part <= 0 for part in fps)):
            raise ValueError("presentation FPS requires positive rational values or explicit nulls")
    source_fps = (source["fps_numerator"], source["fps_denominator"])
    output_fps = (output["fps_numerator"], output["fps_denominator"])
    basis = ("recorded_presentation" if source_fps != (None, None)
             else "playback_only" if output_fps != (None, None) else "unavailable")
    if value.get("timing_basis") != basis or (basis == "recorded_presentation" and source_fps != output_fps):
        raise ValueError("presentation timing changed or unavailable timing was mislabeled")
    physical = value.get("physical_time")
    if not isinstance(physical, dict) or physical.get("status") not in {"unavailable", "verified"}:
        raise ValueError("physical timing must explicitly be unavailable or separately verified")
    if physical["status"] == "verified":
        metadata(metadata_root, physical.get("receipt", {}))


def completed_attempts(completion: dict, manifests: dict, records: dict) -> set[tuple[str, str]]:
    """Match compiler-verified identities only; never read or rescore results."""
    def absolute(value: object) -> PurePosixPath:
        if not isinstance(value, str):
            raise ValueError("compiler provenance path must be absolute")
        path = PurePosixPath(value)
        if not path.is_absolute() or str(path) != value or ".." in path.parts:
            raise ValueError("compiler provenance path must be canonical and absolute")
        return path

    cohort = absolute(completion.get("cohort_root"))
    ledger_rows = completion.get("ledger")
    if not isinstance(ledger_rows, list):
        raise ValueError("compiler report lacks completed ledger identities")
    ledger = {}
    for row in ledger_rows:
        if not isinstance(row, dict) or row.get("analysis_status") != "complete":
            raise ValueError("compiler ledger includes an unresolved identity")
        cell = relative_path(row.get("cell_id"))
        if cell in ledger:
            raise ValueError("duplicate completed ledger identity")
        ledger[cell] = row
    cells = set()
    required = set()
    for release in completion["releases"]:
        if not isinstance(release, dict):
            raise ValueError("compiler release provenance must be an object")
        artifact_root = absolute(release.get("artifact_root"))
        if not artifact_root.is_relative_to(cohort):
            raise ValueError("compiler artifact root escapes cohort")
        pointers = release.get("completion_pointers")
        if not isinstance(pointers, list):
            raise ValueError("compiler report lacks completed attempt identities")
        for pointer in pointers:
            if not isinstance(pointer, dict):
                raise ValueError("compiler completion identity must be an object")
            cell = relative_path(pointer.get("cell_id"))
            if "/" in cell or cell in cells:
                raise ValueError("duplicate/invalid completed cell identity")
            cells.add(cell)
            source = absolute(pointer.get("manifest_path"))
            if not source.is_relative_to(artifact_root / "attempts" / cell):
                raise ValueError("completed manifest lies outside owning cell")
            path = relative_path(source.relative_to(cohort).as_posix())
            manifest, record = manifests.get(path), records.get(path)
            if manifest is None or record is None:
                raise ValueError(f"delivery index omits completed study attempt: {path}")
            if (record["sha256"] != pointer.get("manifest_sha256") or manifest["cell_id"] != cell
                    or manifest["release_id"] != release.get("release_id")
                    or manifest["release_hashes"] != release.get("hashes")
                    or ledger.get(cell, {}).get("release_id") != manifest["release_id"]
                    or ledger.get(cell, {}).get("attempt_id") != manifest["attempt_id"]
                    or ledger.get(cell, {}).get("status") != manifest["result"]["status"]
                    or source != artifact_root / "attempts" / cell / manifest["attempt_id"] / "manifest.json"):
                raise ValueError(f"completed attempt provenance differs from compiler: {path}")
            if "videos/viewport.mp4" not in manifest["artifacts"]:
                raise ValueError(f"completed attempt lacks required viewport: {path}")
            required.add((path, "videos/viewport.mp4"))
    if len(cells) != STUDY_EPISODES or cells != set(ledger):
        raise ValueError(f"compiler report must identify exactly {STUDY_EPISODES} completed attempts")
    return required


def decoded_future(request: object) -> dict | None:
    if not isinstance(request, dict) or not isinstance(request.get("raw_response"), dict):
        raise ValueError("prediction request lacks raw response provenance")
    response = request["raw_response"]
    trace = response.get("native_trace")
    future = response.get("future")
    if future is None and isinstance(trace, dict):
        future = trace.get("future")
    status = request.get("future_status")
    if status in EXPOSED_FUTURES:
        if not isinstance(future, dict):
            raise ValueError("exposed prediction lacks retained decoded array identity")
        return future
    if status not in UNAVAILABLE_FUTURES or future is not None:
        raise ValueError("prediction availability contradicts recorder metadata")
    return None


def prediction_coverage(value: dict, manifests: dict, metadata_root: Path,
                        entries: list[dict]) -> list[dict]:
    represented = {(entry["manifest_path"], entry["original"]["path"]): entry for entry in entries}
    dispositions = value.get("predictions", [])
    if not isinstance(dispositions, list):
        raise ValueError("prediction dispositions must be an explicit list")
    declared = {}
    for row in dispositions:
        if not isinstance(row, dict):
            raise ValueError("prediction disposition must be an object")
        key = (relative_path(row.get("manifest_path")), relative_path(row.get("request_path")))
        if key in declared:
            raise ValueError(f"duplicate prediction disposition: {key}")
        declared[key] = row
    checked = []
    exposed = set()
    for path, manifest in manifests.items():
        artifacts = manifest["artifacts"]
        requests = {name for name in artifacts if re.fullmatch(r"predictions/request-\d+\.json", name)}
        for name in artifacts:
            match = re.match(r"(predictions/request-\d+)-arrays/", name)
            if match and match[1] + ".json" not in requests:
                raise ValueError(f"prediction arrays lack recorder request metadata: {path}: {name}")
        for request_path in sorted(requests):
            row = declared.pop((path, request_path), None)
            if row is None:
                raise ValueError(f"prediction delivery disposition is missing: {path}: {request_path}")
            request_identity = {"path": str(PurePosixPath(path).parent / request_path),
                                **identity(artifacts[request_path])}
            request = metadata(metadata_root, request_identity)
            future = decoded_future(request)
            if future is None:
                if row.get("status") != request["future_status"]:
                    raise ValueError("declared unavailable prediction differs from recorder status")
            else:
                original = relative_path(future.get("path"))
                if (original not in artifacts or future.get("sha256") != identity(artifacts[original])["sha256"]
                        or not original.startswith("predictions/") or not original.endswith(".npy")):
                    raise ValueError("exposed prediction identity differs from recorder manifest")
                if row.get("status") != "encoded" or (path, original) not in represented:
                    raise ValueError(f"exposed prediction lacks its registered viewing derivative: {path}: {original}")
                source = represented[(path, original)]["encoding"]["source"]
                if (future.get("dtype") != "uint8"
                        or future.get("shape") != [source["frame_count"], source["height"], source["width"], 3]):
                    raise ValueError("prediction viewing copy source geometry/dtype differs from recorder")
                exposed.add((path, original))
            checked.append({**row, "request_record": request_identity, "recorded_status": request["future_status"]})
    if declared:
        raise ValueError(f"prediction dispositions reference unknown recorder requests: {sorted(declared)}")
    if any(original.startswith("predictions/") and original.endswith(".npy") and (path, original) not in exposed
           for path, original in represented):
        raise ValueError("a viewing derivative claims an unexposed or noncanonical prediction array")
    return checked


def load_index(index: Path, expected_sha256: str, metadata_root: Path) -> tuple[dict, list[dict]]:
    raw = index.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("download index SHA-256 differs from explicitly pinned identity")
    value = decode(raw)
    if not isinstance(value, dict) or value.get("schema_version") != INDEX_SCHEMA:
        raise ValueError(f"expected {INDEX_SCHEMA}")
    if (value.get("study_id") != "SGW-01" or value.get("study_status") != "completed"
            or type(value.get("expected_episodes")) is not int or value["expected_episodes"] != STUDY_EPISODES
            or type(value.get("completed_episodes")) is not int or value["completed_episodes"] != STUDY_EPISODES):
        raise ValueError("final completed-study gate is not satisfied; no downloads permitted")
    completion = metadata(metadata_root, value.get("completion_receipt", {}))
    if (not isinstance(completion, dict) or completion.get("schema_version") != "sgw-01-cohort-analysis-v1"
            or completion.get("complete") is not True
            or not isinstance(value.get("cohort_id"), str) or not value["cohort_id"]
            or completion.get("cohort_id") != value["cohort_id"]
            or not isinstance(value.get("planned_queue_sha256"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", value["planned_queue_sha256"])
            or completion.get("planned_queue_sha256") != value["planned_queue_sha256"]):
        raise ValueError("compiler completion receipt is incomplete or cohort/queue identity differs")
    coverage = completion.get("coverage")
    required_coverage = {"expected": STUDY_EPISODES, "observed": STUDY_EPISODES, "completed": STUDY_EPISODES,
                         "missing": 0, "duplicate": 0, "technical_invalid": 0}
    if not isinstance(coverage, dict) or any(
            type(coverage.get(key)) is not int or coverage[key] != count for key, count in required_coverage.items()):
        raise ValueError("compiler completion receipt has unresolved coverage gaps")
    if not isinstance(completion.get("releases"), list) or not completion["releases"]:
        raise ValueError("compiler completion receipt lacks release provenance")
    records = value.get("attempt_manifests")
    if not isinstance(records, list) or not records:
        raise ValueError("finalized attempt manifest identities are required")
    manifests = {}
    expected_videos = set()
    occupied: set[str] = set()
    parents: set[str] = set()

    def reserve(path: str) -> None:
        key = path.lower()
        ancestors = {parent.as_posix() for parent in PurePosixPath(key).parents if parent.as_posix() != "."}
        if key in occupied or key in parents or ancestors & occupied:
            raise ValueError(f"duplicate/colliding path: {path}")
        occupied.add(key)
        parents.update(ancestors)

    for record in records:
        if not isinstance(record, dict):
            raise ValueError("attempt manifest identity must be an object")
        path = relative_path(record.get("path"))
        reserve(path)
        manifest = metadata(metadata_root, record)
        if not isinstance(manifest, dict) or manifest.get("schema_version") != "sgw-01-attempt-manifest-v1":
            raise ValueError(f"unsupported attempt manifest: {path}")
        if manifest.get("complete") is not True:
            raise ValueError(f"unfinished attempt manifest: {path}")
        cell = relative_path(manifest.get("cell_id"))
        attempt = relative_path(manifest.get("attempt_id"))
        if "/" in cell or "/" in attempt or PurePosixPath(path).parts[-4:] != ("attempts", cell, attempt, "manifest.json"):
            raise ValueError(f"manifest path disagrees with recorder identity: {path}")
        if (not isinstance(manifest.get("release_id"), str) or not manifest["release_id"]
                or not isinstance(manifest.get("release_hashes"), dict) or not manifest["release_hashes"]
                or not isinstance(manifest.get("result"), dict)
                or manifest["result"].get("status") not in KINDS
                or not isinstance(manifest.get("artifacts"), dict)):
            raise ValueError(f"incomplete attempt provenance: {path}")
        for artifact, info in manifest["artifacts"].items():
            relative_path(artifact)
            if PurePosixPath(artifact).suffix.lower() in VIDEO_SUFFIXES:
                identity(info)
                expected_videos.add((path, artifact))
        manifests[path] = manifest
    expected_videos.update(completed_attempts(completion, manifests, {row["path"]: row for row in records}))
    videos = value.get("videos")
    if not isinstance(videos, list) or not videos:
        raise ValueError("final viewing-copy index has no videos")
    entries = []
    represented = set()
    for video in videos:
        if not isinstance(video, dict):
            raise ValueError("video identity must be an object")
        path = relative_path(video.get("path"))
        reserve(path)
        if not path.startswith("viewing/") or PurePosixPath(path).suffix.lower() != ".mp4":
            raise ValueError("only separate viewing/*.mp4 derivatives may be downloaded")
        expected = identity(video)
        encoding_metadata(video.get("encoding"), metadata_root)
        original = video.get("original")
        if not isinstance(original, dict):
            raise ValueError(f"viewing copy lacks original identity: {path}")
        original_path = relative_path(original.get("path"))
        manifest_path = relative_path(original.get("manifest_path"))
        manifest = manifests.get(manifest_path)
        if manifest is None or original_path not in manifest["artifacts"]:
            raise ValueError(f"original is absent from bound attempt manifest: {path}")
        if identity(original) != identity(manifest["artifacts"][original_path]):
            raise ValueError(f"original identity differs from attempt manifest: {path}")
        if (PurePosixPath(original_path).suffix.lower() not in VIDEO_SUFFIXES
                and not (original_path.startswith("predictions/") and original_path.endswith(".npy"))):
            raise ValueError("viewing source must be a recorded video or retained prediction array")
        key = (manifest_path, original_path)
        if key in represented:
            raise ValueError(f"ambiguous multiple viewing copies for original: {key}")
        represented.add(key)
        kind = KINDS[manifest["result"]["status"]]
        entries.append({
            "path": path, **expected, "local_path": f"{kind}/{path}", "category": kind,
            "original": original, "encoding": video["encoding"], "manifest_path": manifest_path,
            "release_id": manifest["release_id"], "release_hashes": manifest["release_hashes"],
            "cell_id": manifest["cell_id"], "attempt_id": manifest["attempt_id"],
            "outcome_status": manifest["result"]["status"],
        })
    if expected_videos - represented:
        raise ValueError(f"final index omits recorded videos: {sorted(expected_videos - represented)}")
    value["predictions"] = prediction_coverage(value, manifests, metadata_root, entries)
    return value, entries


@dataclass(frozen=True)
class Source:
    transport: str
    root: str
    context: str | None = None
    namespace: str | None = None
    pod: str | None = None
    container: str | None = None
    remote_python: str = "python3"

    def command(self, entry: dict) -> list[str]:
        if (not self.root.startswith("/") or self.root == "/"
                or str(PurePosixPath(self.root)) != self.root or ".." in PurePosixPath(self.root).parts):
            raise ValueError("source root must be an explicit canonical absolute non-root path")
        arguments = ["-c", SOURCE_READER, self.root, relative_path(entry["path"]), str(entry["bytes"])]
        if self.transport == "local":
            return [sys.executable, *arguments]
        if self.transport != "kubectl" or not all((self.context, self.namespace, self.pod, self.container)):
            raise ValueError("kubectl requires explicit context, namespace, Pod, and container")
        if (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]*", self.pod)
                or not re.fullmatch(r"[A-Za-z0-9_/.-]+", self.remote_python)
                or self.remote_python.startswith("-")):
            raise ValueError("invalid Pod or remote Python executable")
        return ["kubectl", f"--context={self.context}", f"--namespace={self.namespace}",
                "exec", self.pod, f"--container={self.container}", "--",
                self.remote_python, *arguments]


def free_bytes(fd: int) -> int:
    usage = os.fstatvfs(fd)
    return usage.f_bavail * usage.f_frsize


def publish_json(fd: int, name: str, value: dict) -> None:
    temporary = f".{uuid.uuid4().hex}.partial"
    opened = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=fd)
    with os.fdopen(opened, "w") as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.link(temporary, name, src_dir_fd=fd, dst_dir_fd=fd, follow_symlinks=False)
    os.unlink(temporary, dir_fd=fd)
    os.fsync(fd)


def archive(*, index: Path, index_sha256: str, metadata_root: Path, destination: Path,
            source: Source, verify_only: bool = False, reserve_bytes: int = RESERVE_BYTES,
            timeout: float = 300) -> dict:
    if type(reserve_bytes) is not int or reserve_bytes < 0 or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("reserve bytes must be nonnegative and timeout finite and positive")
    manifest, entries = load_index(index, index_sha256, metadata_root)
    for entry in entries:
        source.command(entry)
    destination = destination.absolute()
    if destination.is_symlink():
        raise ValueError("destination root must not be a symlink")
    with directory(destination, (".video-downloads",), create=True) as state_fd:
        lock = os.open("lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=state_fd)
        try:
            if not stat.S_ISREG(os.fstat(lock).st_mode):
                raise ValueError("archive lock is not a regular file")
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            report = {
                "schema_version": "sgw-01-local-video-coverage-v1",
                "created_at_utc": datetime.now(timezone.utc).isoformat(),
                "index": {"path": str(index.absolute()), "sha256": index_sha256},
                "source": asdict(source), "destination": str(destination),
                "owner_claim": {key: manifest[key] for key in (
                    "study_id", "study_status", "cohort_id", "planned_queue_sha256",
                    "expected_episodes", "completed_episodes", "completion_receipt")},
                "attempt_manifests": manifest["attempt_manifests"],
                "predictions": manifest["predictions"],
                "scope": "supplied index only; video counts are not study episode counts",
                "mode": "verify" if verify_only else "download", "files": entries, "errors": [],
            }
            for entry in entries:
                parts = PurePosixPath(entry["local_path"]).parts
                try:
                    with directory(destination, parts[:-1]) as fd:
                        checked_file(fd, parts[-1], entry)
                    entry.update(status="complete", action="skipped_matching")
                except FileNotFoundError:
                    entry["status"] = "missing"
                except (OSError, ValueError) as exc:
                    entry.update(status="failed", error=str(exc))
            pending = [entry for entry in entries if entry["status"] == "missing"]
            required = sum(entry["bytes"] for entry in pending) + reserve_bytes
            available = free_bytes(state_fd)
            report["preflight"] = {
                "transfer_bytes": required - reserve_bytes, "headroom_bytes": reserve_bytes,
                "required_bytes": required, "available_bytes": available,
                "shortfall_bytes": max(0, required - available),
            }
            if not verify_only and any(entry["status"] == "failed" for entry in entries):
                report["errors"].append("existing destination conflict; no transfers started")
            elif not verify_only and pending and available < required:
                report["errors"].append("insufficient disk space; no transfers started")
            elif not verify_only:
                for entry in pending:
                    parts = PurePosixPath(entry["local_path"]).parts
                    try:
                        with directory(destination, parts[:-1], create=True) as fd:
                            if free_bytes(fd) < entry["bytes"] + reserve_bytes:
                                raise OSError("disk space changed since aggregate preflight")
                            temporary = f".video-download-{uuid.uuid4().hex}.partial"
                            opened = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=fd)
                            entry["partial_path"] = str(PurePosixPath(*parts[:-1], temporary))
                            with os.fdopen(opened, "wb") as stream:
                                result = subprocess.run(source.command(entry), stdin=subprocess.DEVNULL,
                                                        stdout=stream, stderr=subprocess.PIPE, timeout=timeout)
                                if result.returncode:
                                    raise OSError(f"source transfer exited {result.returncode}: "
                                                  f"{result.stderr.decode(errors='replace').strip()}")
                                stream.flush()
                                os.fsync(stream.fileno())
                            checked_file(fd, temporary, entry)
                            os.link(temporary, parts[-1], src_dir_fd=fd, dst_dir_fd=fd, follow_symlinks=False)
                            os.unlink(temporary, dir_fd=fd)
                            os.fsync(fd)
                            entry.pop("partial_path")
                            entry.update(status="complete", action="downloaded")
                    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
                        entry.update(status="failed", error=str(exc))
                        report["errors"].append("transfer failed; remaining files not attempted (no automatic retry)")
                        break
            report.update(
                complete=sum(entry["status"] == "complete" for entry in entries),
                missing=sum(entry["status"] == "missing" for entry in entries),
                failed=sum(entry["status"] == "failed" for entry in entries),
                expected_bytes=sum(entry["bytes"] for entry in entries),
                verified_bytes=sum(entry["bytes"] for entry in entries if entry["status"] == "complete"),
            )
            report["index_coverage_complete"] = not (report["missing"] or report["failed"] or report["errors"])
            receipt_name = f"coverage-{uuid.uuid4().hex}.json"
            report["receipt"] = str(destination / ".video-downloads" / receipt_name)
            publish_json(state_fd, receipt_name, report)
            return report
        finally:
            os.close(lock)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("command", choices=("download", "verify"))
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--index-sha256", required=True)
    parser.add_argument("--metadata-root", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--transport", choices=("local", "kubectl"), required=True)
    parser.add_argument("--source-root", required=True)
    for name in ("context", "namespace", "pod", "container"):
        parser.add_argument(f"--{name}")
    parser.add_argument("--remote-python", default="python3")
    parser.add_argument("--reserve-bytes", type=int, default=RESERVE_BYTES)
    parser.add_argument("--timeout", type=float, default=300)
    args = parser.parse_args()
    try:
        report = archive(
            index=args.index, index_sha256=args.index_sha256, metadata_root=args.metadata_root,
            destination=args.destination,
            source=Source(args.transport, args.source_root, args.context, args.namespace,
                          args.pod, args.container, args.remote_python),
            verify_only=args.command == "verify", reserve_bytes=args.reserve_bytes, timeout=args.timeout,
        )
    except (OSError, ValueError) as exc:
        print(json.dumps({"error": str(exc), "index_coverage_complete": False}), file=sys.stderr)
        return 1
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0 if report["index_coverage_complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
