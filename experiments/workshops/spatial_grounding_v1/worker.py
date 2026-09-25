"""Finite, durable SGW-01 partition worker; production adapters are fail-closed.

Bare-Pod v2 admission requires allow_parallel_existing_pod_lanes and an exact
existing_pod_supervisor_entrypoint in the immutable runtime binding. Its shared
study-root locks cover one physical GPU UUID and one model/family/stage partition.
An optional declared GPU-name/count pool allows fresh operational admission
without changing the release; model_gpu_counts retains its worst-case Pod sizes.
"""

from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
from datetime import datetime, timedelta, timezone
import fcntl
import errno
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import traceback
from typing import Any, Callable, Mapping, Protocol
import uuid

from .contract import Cell, ContractError, Release, load_release, validate_stage_authorizations, verify_completion_pointer
from .gpu_idle_probe import select_idle
from .recorder import AttemptRecorder, atomic_json, fleet_is_held, next_attempt_number, request_fleet_hold, utc_now
from .block_scheduling import MODE as BLOCK_MODE, begin_once, protocol_runtime, registration, selected_cells

EXIT_RELEASE_INVALID, EXIT_ATTEMPTS_EXHAUSTED, EXIT_STORAGE_BUDGET_BLOCKED = 42, 43, 44
SOURCE_QUEUE_EPISODE_COUNT = 1566
MAX_IDLE_PROBE_AGE_SECONDS = 300
STOP_REQUESTED = False
STOP_GRACE_EXPIRED = False
POD_ADMISSION_SCHEMA = "sgw-01-run-admission-v2"
POD_ALLOCATION_SCHEMA = "sgw-01-external-allocation-v2"


class DeadlineExceeded(RuntimeError):
    pass


class ResourceBlocked(OSError):
    """Raised before model construction when a fixed resource gate fails."""


class Adapter(Protocol):
    def reset(self, cell: Cell, recorder: AttemptRecorder) -> dict[str, Any]: ...
    def run_episode(self, cell: Cell, recorder: AttemptRecorder, reset: dict[str, Any]) -> dict[str, Any]: ...
    def close(self) -> None: ...


ScoreFn = Callable[[Mapping[str, Any], Cell], Mapping[str, Any]]


def _stop(_signum: int, _frame: Any) -> None:
    global STOP_REQUESTED
    STOP_REQUESTED = True
    # Do not kill a completed attempt prematurely, but do not permit a hung
    # runtime to survive Kubernetes' documented 180-second termination grace.
    signal.signal(signal.SIGALRM, _grace_expired)
    signal.setitimer(signal.ITIMER_REAL, 180)


def _grace_expired(_signum: int, _frame: Any) -> None:
    global STOP_GRACE_EXPIRED
    STOP_GRACE_EXPIRED = True
    raise DeadlineExceeded("SIGTERM grace period expired")


def _run_with_deadline(seconds: int, operation: str, callback):
    if seconds <= 0:
        raise ContractError(f"{operation} deadline must be positive")
    previous = signal.getsignal(signal.SIGALRM)
    try:
        signal.signal(signal.SIGALRM, lambda _signum, _frame: (_ for _ in ()).throw(DeadlineExceeded(f"{operation} deadline exceeded")))
        signal.setitimer(signal.ITIMER_REAL, seconds)
        return callback()
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


@contextmanager
def model_lock(release: Release, model: str):
    path = release.root.parent / "locks" / f"{model}.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as stream:
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ContractError(f"global model lock held: {path}") from exc
        stream.write(json.dumps({"pid": os.getpid(), "release_id": release.release_id, "started_at_utc": utc_now()}) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def load_adapter(model: str) -> Adapter:
    """Load only the production adapter supplied by the runtime owner."""
    module_name = f"experiments.workshops.spatial_grounding_v1.adapters"
    try:
        module = importlib.import_module(module_name)
        factory = getattr(module, "load_production_adapter")
        return factory(model)
    except (ImportError, AttributeError) as exc:
        raise ContractError("production adapter is unavailable; fake adapters are tests-only") from exc


def _completion(release: Release, cell: Cell) -> bool:
    path = release.root.parent / "cells" / f"{cell.cell_id}.complete.json"
    if not path.exists():
        return False
    verify_completion_pointer(release, path)
    return True


def _receipt(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or not isinstance(value.get("path"), str) or not isinstance(value.get("sha256"), str):
        raise ResourceBlocked(f"{label} receipt is absent or unhashed")
    path = Path(value["path"])
    if not path.is_file():
        raise ResourceBlocked(f"{label} receipt is unavailable: {path}")
    from .contract import load_json, sha256_file
    try:
        if sha256_file(path) != value["sha256"]:
            raise ResourceBlocked(f"{label} receipt hash changed: {path}")
        return load_json(path, label)
    except (ContractError, OSError, UnicodeError) as exc:
        raise ResourceBlocked(f"{label} receipt is unreadable or malformed: {exc}") from exc


def _canonical_uuid(value: Any) -> bool:
    try:
        return isinstance(value, str) and str(uuid.UUID(value)) == value
    except ValueError:
        return False


def _gpu_uuid(value: Any) -> bool:
    return isinstance(value, str) and value.startswith("GPU-") and _canonical_uuid(value[4:])


def _pod_owner(value: Mapping[str, Any]) -> None:
    name = value.get("pod_name")
    if (value.get("owner_kind") != "Pod" or not _canonical_uuid(value.get("pod_uid"))
            or not isinstance(name, str) or re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?", name) is None
            or name != os.environ.get("POD_NAME") or value["pod_uid"] != os.environ.get("POD_UID")
            or any(value.get(key) is not None or os.environ.get(key.upper()) not in {None, ""}
                   for key in ("job_uid", "job_name"))):
        raise ResourceBlocked("existing Pod admission requires actual Pod name/UID and no Job identity")


def _pod_hardware_policy(binding: Mapping[str, Any], model: str) -> tuple[list[int], list[str]]:
    count_policy = binding.get("existing_pod_gpu_counts")
    name_policy = binding.get("existing_pod_gpu_names")
    declared_pool = "existing_pod_gpu_counts" in binding or "existing_pod_gpu_names" in binding
    if declared_pool:
        if not isinstance(count_policy, Mapping) or not isinstance(name_policy, Mapping):
            raise ResourceBlocked("existing Pod hardware pool requires both model-indexed count and name policies")
        counts, names = count_policy.get(model), name_policy.get(model)
    else:
        counts = [binding["model_gpu_counts"].get(model)]
        configured_names = binding.get("model_gpu_names")
        names = [configured_names.get(model)] if isinstance(configured_names, Mapping) else []
    if (not isinstance(counts, list) or not counts
            or any(type(count) is not int or count not in {1, 2, 4} for count in counts)
            or len(set(counts)) != len(counts)
            or not isinstance(names, list) or not names
            or any(not isinstance(name, str) or not name.strip() or name != name.strip()
                   or any(character in name for character in "*?[]") for name in names)
            or len(set(names)) != len(names)):
        raise ResourceBlocked("existing Pod hardware policy requires unique counts from 1/2/4 and exact GPU names")
    ceiling = binding["model_gpu_counts"].get(model)
    if type(ceiling) is not int or ceiling != max(counts):
        raise ResourceBlocked("model_gpu_counts must retain the declared maximum Pod size for conservative budgeting")
    return counts, names


def _pod_hardware_check(release: Release, model: str, value: Mapping[str, Any]) -> None:
    counts, names = _pod_hardware_policy(release.binding, model)
    if (type(value.get("allocated_gpu_count")) is not int or value["allocated_gpu_count"] not in counts
            or not isinstance(value.get("gpu_name"), str) or value["gpu_name"] not in names):
        raise ResourceBlocked("actual Pod GPU name/count is outside the immutable declared hardware policy")


def _study_root(release: Release) -> str:
    binding = release.binding
    if binding.get("allow_parallel_existing_pod_lanes") is not True:
        return binding["source_root"]
    value, mount_value = binding.get("persistent_study_root"), binding.get("pvc_mount_path")
    if (not isinstance(value, str) or not isinstance(mount_value, str)
            or not Path(value).is_absolute() or not Path(mount_value).is_absolute()):
        raise ResourceBlocked("existing Pod lanes require an absolute persistent_study_root and PVC mount")
    root, mount = Path(value), Path(mount_value)
    if (value != str(root) or mount_value != str(mount)
            or root != root.resolve() or mount != mount.resolve() or root == mount
            or not root.is_relative_to(mount) or root != release.root.parent.resolve()
            or binding.get("source_root") != str(Path(__file__).resolve().parents[3])):
        raise ResourceBlocked("persistent_study_root must be the release parent below PVC; source_root must be the code checkout")
    return str(root)


def _supervisor_process(pid: int, proc: Path = Path("/proc")) -> dict[str, Any]:
    """Read actual Linux process identity; no model/GPU probe."""
    root = proc / str(pid)
    fields = (root / "stat").read_text().rsplit(") ", 1)[1].split()
    boot = next(int(line.split()[1]) for line in (proc / "stat").read_text().splitlines() if line.startswith("btime "))
    return {"ppid": int(fields[1]), "process_start_identity": fields[19],
            "started_at_unix": boot + int(fields[19]) / os.sysconf("SC_CLK_TCK"),
            "command": (root / "cmdline").read_bytes().rstrip(b"\0").decode().split("\0"),
            "cwd": str((root / "cwd").resolve(strict=True))}


def _supervisor_check(release: Release, reference: Any) -> Mapping[str, Any]:
    return verify_existing_pod_supervisor(
        reference, source_commit=release.binding["source_commit"],
        entrypoint=release.binding.get("existing_pod_supervisor_entrypoint"),
    )


def verify_existing_pod_supervisor(reference: Any, *, source_commit: str, entrypoint: Any,
                                   environ: Mapping[str, str] | None = None) -> Mapping[str, Any]:
    """Verify a real local ancestor; shared by policy and simulator Pod lanes."""
    env = os.environ if environ is None else environ
    value = _receipt(reference, "existing Pod supervisor")
    source = Path(__file__).resolve().parents[3]
    entry = value.get("entrypoint")
    if (value.get("schema") != "sgw-01-existing-pod-supervisor-v1"
            or not _canonical_uuid(value.get("supervisor_id"))
            or value.get("pod_uid") != env.get("POD_UID") or value.get("pod_name") != env.get("POD_NAME")
            or not _gpu_uuid(value.get("gpu_uuid")) or value["gpu_uuid"] != env.get("CUDA_VISIBLE_DEVICES")
            or type(value.get("pid")) is not int or value["pid"] <= 1 or value["pid"] == os.getpid()
            or value.get("source_root") != str(source) or value.get("source_commit") != source_commit
            or not isinstance(entry, Mapping) or entry != entrypoint):
        raise ResourceBlocked("existing Pod supervisor identity/source differs from explicit binding")
    try:
        path = Path(entry["path"])
        relative = path.relative_to(source)
        from .producer import _git_revision
        if (path != path.resolve() or path.suffix != ".py"
                or _git_revision(str(source)) != value["source_commit"]
                or hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]):
            raise ValueError("supervisor entrypoint/source differs")
        committed = subprocess.run(["git", "-C", str(source), "show", f"{value['source_commit']}:{relative.as_posix()}"],
                                   check=True, capture_output=True, timeout=10).stdout
        if hashlib.sha256(committed).hexdigest() != entry["sha256"]:
            raise ValueError("supervisor is not the checked-in entrypoint")
        pid = os.getppid()
        for _ in range(64):
            process = _supervisor_process(pid)
            if pid == value["pid"]:
                break
            pid = process["ppid"]
            if pid <= 1:
                raise ValueError("supervisor is not an actual ancestor")
        else:
            raise ValueError("supervisor ancestry unavailable")
        command = process["command"]
        module = ".".join(relative.with_suffix("").parts)
        arguments = command[1:]
        while arguments and arguments[0] in {"-u", "-B"}:
            arguments = arguments[1:]
        executes_entrypoint = (arguments[:2] == ["-m", module] or
                              bool(arguments and not arguments[0].startswith("-")
                                   and (source / arguments[0]).resolve() == path))
        if (process["process_start_identity"] != value.get("process_start_identity")
                or command != value.get("command") or process["cwd"] != str(source)
                or not executes_entrypoint):
            raise ValueError("actual supervisor PID/start/command differs")
        start = datetime.fromisoformat(value["started_at_utc"].replace("Z", "+00:00"))
        deadline = datetime.fromisoformat(value["deadline_utc"].replace("Z", "+00:00"))
        seconds = value["deadline_seconds"]
        if (start.tzinfo is None or deadline.tzinfo is None or type(seconds) is not int or seconds <= 0
                or abs(start.timestamp() - process["started_at_unix"]) > 2
                or start > datetime.now(timezone.utc) or deadline != start + timedelta(seconds=seconds)
                or deadline <= datetime.now(timezone.utc)):
            raise ValueError("supervisor finite lifetime differs from actual process start")
    except (OSError, ValueError, KeyError, IndexError, TypeError, AttributeError, RuntimeError,
            StopIteration, subprocess.SubprocessError) as exc:
        raise ResourceBlocked(f"existing Pod supervisor cannot be verified: {exc}") from exc
    return value


def _run_admission(release: Release, *, model: str | None = None, family: str | None = None,
                   stage: str | None = None, block_id: str | None = None) -> Mapping[str, Any] | None:
    """Refresh expiring operational evidence without rewriting a scientific release."""
    path = os.environ.get("SGW01_RUN_ADMISSION")
    digest = os.environ.get("SGW01_RUN_ADMISSION_SHA256")
    if path is None and digest is None:
        if release.binding.get("scheduling_mode") == BLOCK_MODE:
            raise ResourceBlocked("block execution requires exact hash-bound Pod admission")
        return None
    if (release.binding.get("allow_operational_receipt_refresh") is not True
            or not path or not digest or not Path(path).is_absolute()):
        raise ResourceBlocked("run admission requires release opt-in and an absolute hash-bound receipt")
    value = _receipt({"path": path, "sha256": digest}, "run admission")
    models = {cell.model for cell in release.cells}
    stages = {cell.stage for cell in release.cells}
    job_uid, pod_uid = os.environ.get("JOB_UID"), os.environ.get("POD_UID")
    authorization = release.binding.get("operational_authorization_receipt")
    pod_lane = value.get("schema") == POD_ADMISSION_SCHEMA
    if (value.get("schema") not in {"sgw-01-run-admission-v1", POD_ADMISSION_SCHEMA}
            or value.get("status") != "approved"
            or value.get("release_id") != release.release_id
            or value.get("release_hashes") != dict(release.hashes)
            or not isinstance(value.get("model"), str)
            or models != {value["model"]} or len(stages) != 1
            or (not pod_lane and (not job_uid or not pod_uid
                or value.get("job_uid") != job_uid or value.get("pod_uid") != pod_uid))
            or value.get("resource_owner") != release.binding.get("resource_owner")
            or value.get("operational_authorization_receipt") != authorization):
        raise ResourceBlocked("run admission differs from the immutable release, owner, or current Job/Pod")
    if pod_lane:
        if (release.binding.get("allow_parallel_existing_pod_lanes") is not True
                or not isinstance(value.get("family"), str) or not isinstance(value.get("stage"), str)
                or value["family"] not in {cell.family for cell in release.cells}
                or value.get("stage") not in stages
                or any(expected is not None and value.get(key) != expected
                       for key, expected in (("model", model), ("family", family), ("stage", stage)))
                or not _gpu_uuid(value.get("selected_gpu_uuid"))
                or os.environ.get("CUDA_VISIBLE_DEVICES") != value["selected_gpu_uuid"]):
            raise ResourceBlocked("existing Pod lane lacks opt-in or exact partition/physical GPU UUID")
        _study_root(release)
        _pod_owner(value)
        _pod_hardware_check(release, value["model"], value)
        _supervisor_check(release, value.get("supervisor_identity_receipt"))
        if release.binding.get("scheduling_mode") == BLOCK_MODE:
            selected_cells(release, value["model"], value["family"], value["stage"], value.get("block_id"))
            if block_id is not None and value.get("block_id") != block_id:
                raise ResourceBlocked("run admission differs from the selected block_id")
            _protocol_runtime_check(release)
            _block_operation_check(release, value)
        elif block_id is not None or "block_id" in value:
            raise ResourceBlocked("block admission requires explicit registration")
    elif release.binding.get("allow_parallel_existing_pod_lanes") is True:
        raise ResourceBlocked("existing Pod lane opt-in requires v2 admission, never a substituted Job")
    receipts = value.get("receipts")
    allowed = {"external_allocation_receipt", "resource_budget_receipt", "storage_budget_receipt"}
    required = {"external_allocation_receipt", "resource_budget_receipt"}
    if stages != {"P"} or release.binding.get("storage_budget_receipt") is not None:
        required.add("storage_budget_receipt")
    if (not isinstance(receipts, Mapping) or not required.issubset(receipts)
            or not set(receipts).issubset(allowed)):
        raise ResourceBlocked("run admission must bind all required operational receipts, and no scientific inputs")
    for key, reference in receipts.items():
        _receipt(reference, key)
    return value


def _protocol_runtime_check(release: Release) -> None:
    from .camera_configuration import camera_configuration_identity
    from .policy_observations import policy_input_identity

    declared = protocol_runtime(release.binding)
    try:
        camera, policy = camera_configuration_identity(), policy_input_identity()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ResourceBlocked(f"active camera/input identity unavailable: {exc}") from exc
    if (declared["camera_configuration"] != camera
            or declared["policy_input_revision"] != policy.get("revision")):
        raise ResourceBlocked("active camera/input identity differs from immutable protocol_runtime")


def _block_operation_check(release: Release, admission: Mapping[str, Any]) -> None:
    root = Path(str(admission.get("operation_root", "")))
    if (not root.is_absolute() or root != root.resolve() or not root.is_dir()
            or root.parent != release.root.parent / "operations"):
        raise ResourceBlocked("block operation must have an isolated canonical cohort operation_root")
    paths = {
        "SGW01_RUNTIME_RECEIPT": "launch.json", "SGW01_SERVER_ATTESTATION": "attestation.json",
        "SGW01_TRACE_SIDECAR": "trace.jsonl", "SGW01_FUTURE_DIR": "futures",
        "SGW01_SERVER_LOG_DIR": "logs", "SGW01_NANO_OUTPUT_DIR": "native",
    }
    for variable, suffix in paths.items():
        expected = root / "runtime" / suffix
        if expected != expected.resolve() or os.environ.get(variable) != str(expected):
            raise ResourceBlocked("block runtime paths must be private to the admitted operation")
    if (os.environ.get("SGW01_NANO_PORT") != os.environ.get("SGW01_N3_PORT")
            or not str(os.environ.get("SGW01_N3_PORT", "")).isdigit()
            or not 1024 <= int(os.environ["SGW01_N3_PORT"]) <= 65535
            or os.environ.get("SGW01_N3_HOST") != "127.0.0.1"
            or os.environ.get("SGW01_NANO_HOST") != "127.0.0.1"):
        raise ResourceBlocked("block operation requires its exact local policy endpoint")
    ref = admission.get("simulator_lane_identity")
    simulator = _receipt(ref, "block simulator identity")
    if (not isinstance(ref, Mapping)
            or ref.get("path") != os.environ.get("SGW01_SIMULATOR_LANE_IDENTITY")
            or ref.get("sha256") != os.environ.get("SGW01_SIMULATOR_LANE_IDENTITY_SHA256")
            or simulator.get("schema_version") != "sgw-01-simulator-lane-v3"
            or simulator.get("model") != admission["model"]
            or simulator.get("cohort_root") != str(release.root.parent)
            or simulator.get("source_root") != release.binding["source_root"]
            or simulator.get("source_commit") != release.binding["source_commit"]
            or simulator.get("policy_pod_uid") != admission["pod_uid"]
            or simulator.get("policy_pod_name") != admission["pod_name"]
            or simulator.get("policy_owner_kind") != "Pod" or simulator.get("simulator_owner_kind") != "Pod"
            or not _canonical_uuid(simulator.get("simulator_pod_uid"))
            or simulator.get("simulator_pod_uid") == admission["pod_uid"]
            or not _gpu_uuid(simulator.get("simulator_gpu_uuid"))
            or simulator["simulator_gpu_uuid"] == admission["selected_gpu_uuid"]):
        raise ResourceBlocked("block operation must bind its distinct isolated policy/simulator pair")
    control = Path(str(simulator.get("control_root", "")))
    if (not control.is_absolute() or control != control.resolve()
            or control == release.root.parent or not control.is_relative_to(release.root.parent)):
        raise ResourceBlocked("block simulator control root is not private to this cohort")


@contextmanager
def partition_lock(release: Release, model: str, family: str, stage: str, block_id: str | None = None):
    registered = registration(release.binding, model=model)
    if registered is not None or block_id is not None:
        selected_cells(release, model, family, stage, block_id)
    if release.binding.get("allow_parallel_existing_pod_lanes") is not True:
        with model_lock(release, model):
            yield
        return
    admission = _run_admission(release, model=model, family=family, stage=stage, block_id=block_id)
    if admission is None:
        raise ResourceBlocked("existing Pod lane requires a hash-bound v2 admission before claiming")
    root = Path(_study_root(release)) / "locks" / "existing-pod-lanes"
    if root != root.resolve():
        raise ResourceBlocked("existing Pod lane lock directory must remain below the canonical persistent_study_root")
    if model not in {"N3", "E3", "F3"} or family not in {"LAT", "HEIGHT", "DIST"} or stage not in {"P", "D", "C"}:
        raise ResourceBlocked("invalid existing Pod partition lock identity")
    root.mkdir(parents=True, exist_ok=True)
    names = [f"gpu-{admission['selected_gpu_uuid']}", f"partition-{model}-{family}-{stage}"]
    if registered is not None:
        simulator = _receipt(admission["simulator_lane_identity"], "block simulator identity")
        names = [
            names[0], f"block-{block_id}",
            f"simulator-pair-{simulator['simulator_gpu_uuid']}",
            f"policy-endpoint-{admission['pod_uid']}-{os.environ['SGW01_N3_PORT']}",
            f"operation-{hashlib.sha256(admission['operation_root'].encode()).hexdigest()}",
            f"simulator-control-{hashlib.sha256(simulator['control_root'].encode()).hexdigest()}",
        ]
    with ExitStack() as stack:
        for name in names:
            stream = stack.enter_context((root / f"{name}.lock").open("a+"))
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ResourceBlocked(f"existing Pod lane lock held: {name}") from exc
            stream.write(json.dumps({"release_id": release.release_id, "pid": os.getpid(),
                                     "pod_uid": admission["pod_uid"], "selected_gpu_uuid": admission["selected_gpu_uuid"],
                                     "supervisor_identity_receipt": admission["supervisor_identity_receipt"],
                                     "started_at_utc": utc_now()}) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        yield


def _operational_reference(release: Release, field: str) -> Any:
    admission = _run_admission(release)
    return release.binding.get(field) if admission is None else admission["receipts"].get(field)


def _expiry(receipt: Mapping[str, Any], label: str) -> datetime:
    value = receipt.get("expires_at_utc")
    if not isinstance(value, str):
        raise ResourceBlocked(f"{label} receipt lacks expires_at_utc")
    try:
        expiry = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ResourceBlocked(f"{label} receipt has invalid expires_at_utc") from exc
    if expiry.tzinfo is None or expiry <= datetime.now(timezone.utc):
        raise ResourceBlocked(f"{label} receipt is expired")
    return expiry


def _unexpired(receipt: Mapping[str, Any], label: str) -> None:
    _expiry(receipt, label)


def _source_queue_hash(release: Release) -> str:
    receipt = json.loads((release.root / "release_receipt.json").read_text(encoding="utf-8"))
    value = receipt.get("source_queue_sha256")
    if not isinstance(value, str):
        raise ResourceBlocked("release lacks source queue provenance")
    return value


def _runtime_identity_sha256(release: Release) -> str:
    return runtime_identity_sha256(release.binding)


def runtime_identity_sha256(binding: Mapping[str, Any]) -> str:
    """Hash the execution identity without receipt references, avoiding a hash cycle."""
    identity = {
        "worker_image_digest": binding["worker_image_digest"],
        "source_commit": binding["source_commit"],
        "simulator_commit": binding["simulator_commit"],
        "model_code_commits": binding["model_code_commits"],
        "checkpoint_hashes": binding["checkpoint_hashes"],
        "node_gpu_type": binding["node_gpu_type"],
    }
    return hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _receipt_identity(release: Release, receipt: Mapping[str, Any], label: str) -> None:
    binding = release.binding
    expected = {
        "release_id": release.release_id,
        "source_queue_sha256": _source_queue_hash(release),
        "source_queue_episode_count": SOURCE_QUEUE_EPISODE_COUNT,
        "pvc_name": binding["pvc_name"],
        "pvc_mount_path": binding["pvc_mount_path"],
        "study_root": _study_root(release),
        "runtime_identity_sha256": _runtime_identity_sha256(release),
    }
    if any(receipt.get(field) != value for field, value in expected.items()):
        raise ResourceBlocked(f"{label} receipt is not bound to this release, PVC, study root, and runtime")


def _positive_finite_number(value: Any) -> bool:
    return type(value) in {int, float} and value > 0 and math.isfinite(value)


def _as_needed_scaling(authorization: Mapping[str, Any], constraints: Mapping[str, Any]) -> bool:
    """Only an explicit approved null-cap receipt can waive legacy aggregate caps."""
    return (
        authorization.get("budget_mode") == "existing_idle_capacity_no_aggregate_hour_cap"
        and constraints.get("allocation_scaling") == "as_needed_verified_idle_capacity"
        and "max_concurrent_model_workers" in constraints
        and "max_total_allocated_gpus" in constraints
        and constraints["max_concurrent_model_workers"] is None
        and constraints["max_total_allocated_gpus"] is None
    )


def _authorization_check(release: Release, *, model: str) -> str:
    authorization = _receipt(release.binding.get("operational_authorization_receipt"), "operational authorization")
    if authorization.get("schema_version") != "sgw-01-operational-authorization-v1" or authorization.get("status") != "approved":
        raise ResourceBlocked("operational authorization receipt is not approved")
    mode = authorization.get("budget_mode")
    if mode not in {"numeric_global_gpu_hour_cap", "existing_idle_capacity_no_aggregate_hour_cap"}:
        raise ResourceBlocked("operational authorization has an unsupported budget mode")
    scope = authorization.get("scope")
    constraints = authorization.get("constraints")
    if not isinstance(scope, Mapping) or not isinstance(constraints, Mapping):
        raise ResourceBlocked("operational authorization lacks bounded scope and constraints")
    models = scope.get("models")
    authorized_workers = constraints.get("max_concurrent_model_workers")
    authorized_gpus = constraints.get("max_total_allocated_gpus")
    as_needed = _as_needed_scaling(authorization, constraints)
    if (not isinstance(authorization.get("owner_approval_reference"), Mapping)
            or authorization.get("source_protocol_sha256") != release.hashes["protocol.json"]
            or authorization.get("source_queue_sha256") != _source_queue_hash(release)
            or scope.get("context") != release.binding["context"]
            or scope.get("namespace") != release.binding["namespace"]
            or scope.get("pvc") != release.binding["pvc_name"]
            or scope.get("persistent_study_root") != _study_root(release)
            or not isinstance(models, list) or model not in models
            or scope.get("maximum_registered_behavioral_episodes") != SOURCE_QUEUE_EPISODE_COUNT
            or scope.get("maximum_attempts_per_behavioral_cell") != 3
            or not (as_needed or (
                type(authorized_workers) is int and type(authorized_gpus) is int
                and 1 <= release.binding["max_concurrent_model_workers"] <= authorized_workers <= 2
                and 1 <= release.binding["max_total_allocated_gpus"] <= authorized_gpus <= 4
            ))
            or constraints.get("existing_authorized_cluster_capacity_only") is not True
            or constraints.get("fresh_idle_allocation_check_required") is not True
            or constraints.get("new_paid_capacity_allowed") is not False
            or constraints.get("new_cluster_provisioning_allowed") is not False
            or constraints.get("preempt_or_stop_unowned_workloads_allowed") is not False
            or constraints.get("bounded_job_deadline_required") is not True):
        raise ResourceBlocked("operational authorization does not cover this bounded existing-capacity launch")
    if mode == "numeric_global_gpu_hour_cap" and not _positive_finite_number(authorization.get("approved_global_gpu_hours")):
        raise ResourceBlocked("numeric operational authorization lacks a finite global GPU-hour cap")
    return mode


def _allocation_check(release: Release, *, model: str, minimum_runtime_seconds: int,
                      verify_idle_probe: bool = True) -> int:
    """Validate a Job reservation or explicit bare-Pod lane, not a local ledger."""
    receipt = _receipt(_operational_reference(release, "external_allocation_receipt"), "external allocation")
    pod_lane = receipt.get("schema") == POD_ALLOCATION_SCHEMA
    if receipt.get("schema") not in {"sgw-01-external-allocation-v1", POD_ALLOCATION_SCHEMA} or receipt.get("status") != "approved":
        raise ResourceBlocked("external allocation receipt is not approved")
    mode = _authorization_check(release, model=model)
    _receipt_identity(release, receipt, "external allocation")
    required_strings = ("owner_approval_reference", "reservation_id", "context", "namespace", "pod_uid", "model")
    if not pod_lane:
        required_strings += ("job_name", "job_uid")
    if any(not isinstance(receipt.get(field), str) or not receipt[field] for field in required_strings):
        raise ResourceBlocked("external allocation receipt lacks concrete reservation identity")
    if receipt["context"] != release.binding["context"] or receipt["namespace"] != release.binding["namespace"]:
        raise ResourceBlocked("external allocation receipt has a different Kubernetes scope")
    if (receipt["model"] != model or receipt["pod_uid"] != os.environ.get("POD_UID")
            or (not pod_lane and receipt["job_uid"] != os.environ.get("JOB_UID"))):
        raise ResourceBlocked("external allocation receipt does not bind this Job UID, pod UID, and model")
    if pod_lane:
        admission = _run_admission(release)
        if (release.binding.get("allow_parallel_existing_pod_lanes") is not True or admission is None
                or admission.get("schema") != POD_ADMISSION_SCHEMA
                or any(receipt.get(key) != admission.get(key) for key in (
                    "owner_kind", "pod_name", "pod_uid", "selected_gpu_uuid", "supervisor_identity_receipt",
                    "gpu_name", "allocated_gpu_count",
                ))
                or receipt.get("lane_gpu_count") != 1 or type(receipt["lane_gpu_count"]) is not int
                or receipt.get("reservation_scope") != "whole_pod"
                or any(key in receipt for key in ("activeDeadlineSeconds", "startTime"))):
            raise ResourceBlocked("existing Pod allocation differs from its explicit single-GPU lane admission")
        _pod_owner(receipt)
        pod = _receipt(receipt.get("pod_snapshot"), "actual bare Pod")
        try:
            def quantity(raw: Any) -> int:
                if type(raw) is int and raw >= 0:
                    return raw
                if isinstance(raw, str) and re.fullmatch(r"0|[1-9][0-9]*", raw):
                    return int(raw)
                raise ValueError("GPU resource quantities must be nonnegative integers")

            metadata = pod["metadata"]
            counts = [(quantity(c["resources"].get("requests", {}).get("nvidia.com/gpu", 0)),
                       quantity(c["resources"].get("limits", {}).get("nvidia.com/gpu", 0))) for c in pod["spec"]["containers"]]
            if (pod.get("kind") != "Pod" or pod.get("apiVersion") != "v1"
                    or metadata.get("name") != receipt["pod_name"] or metadata.get("uid") != receipt["pod_uid"]
                    or metadata.get("namespace") != receipt["namespace"] or metadata.get("ownerReferences")
                    or pod.get("status", {}).get("phase") != "Running"
                    or any(request != limit or request < 0 for request, limit in counts)
                    or sum(limit for _, limit in counts) != receipt["allocated_gpu_count"]):
                raise ValueError("actual bare Pod identity/resources differ")
        except (KeyError, TypeError, ValueError) as exc:
            raise ResourceBlocked(f"invalid bare Pod snapshot: {exc}") from exc
        supervisor = _supervisor_check(release, receipt["supervisor_identity_receipt"])
        active = supervisor["deadline_seconds"]
        start_value, deadline_value = supervisor["started_at_utc"], supervisor["deadline_utc"]
        if (receipt.get("deadline_utc", deadline_value) != deadline_value
                or not _positive_finite_number(receipt.get("lane_gpu_hours"))
                or abs(receipt["lane_gpu_hours"] - active / 3600) > 1e-9):
            raise ResourceBlocked("existing Pod lane GPU-hour accounting differs from supervisor lifetime")
    else:
        if release.binding.get("allow_parallel_existing_pod_lanes") is True:
            raise ResourceBlocked("existing Pod lane cannot substitute a legacy Job allocation")
        active = receipt.get("activeDeadlineSeconds")
        start_value, deadline_value = receipt.get("startTime"), receipt.get("deadline_utc")
    gpu_count = receipt.get("allocated_gpu_count")
    if (type(gpu_count) is not int or (not pod_lane and gpu_count != release.binding["model_gpu_counts"].get(model))
            or type(active) is not int or active <= 0):
        raise ResourceBlocked("external allocation receipt lacks the exact GPU allocation/deadline")
    if not isinstance(start_value, str) or not isinstance(deadline_value, str):
        raise ResourceBlocked("external allocation receipt lacks owner timing")
    try:
        start = datetime.fromisoformat(start_value.replace("Z", "+00:00"))
        deadline = datetime.fromisoformat(deadline_value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ResourceBlocked("external allocation receipt has invalid owner timing") from exc
    if (start.tzinfo is None or deadline.tzinfo is None or start > datetime.now(timezone.utc)
            or deadline != start + timedelta(seconds=active)):
        raise ResourceBlocked("external allocation receipt has invalid owner timing")
    reservation = receipt.get("reservation_gpu_hours")
    expected = gpu_count * active / 3600
    if receipt.get("budget_mode") != mode or not _positive_finite_number(reservation) or abs(reservation - expected) > 1e-9:
        raise ResourceBlocked("external allocation receipt has invalid whole-owner worst-case GPU-hour accounting")
    if mode == "numeric_global_gpu_hour_cap":
        approved = receipt.get("approved_global_gpu_hours")
        reserved = receipt.get("globally_reserved_gpu_hours")
        authorization = _receipt(release.binding["operational_authorization_receipt"], "operational authorization")
        if (not _positive_finite_number(approved) or not _positive_finite_number(reserved)
                or approved != authorization["approved_global_gpu_hours"]
                or not reservation <= reserved <= approved):
            raise ResourceBlocked("external allocation receipt has invalid capped global reservation accounting")
    if verify_idle_probe:
        gpu_names = release.binding.get("model_gpu_names")
        expected_gpu_name = receipt["gpu_name"] if pod_lane else None
        if not pod_lane and gpu_names is not None:
            if (not isinstance(gpu_names, Mapping) or not isinstance(gpu_names.get(model), str)
                    or not gpu_names[model].strip()):
                raise ResourceBlocked("runtime binding lacks the selected model's exact qualified GPU name")
            expected_gpu_name = gpu_names[model]
        idle = _receipt(receipt.get("gpu_idle_probe_receipt"), "GPU idle probe")
        allocated = receipt.get("allocated_gpu_uuids")
        observed = idle.get("observed_at_unix")
        gpus = idle.get("gpus")
        occupied = idle.get("compute_occupied_uuids")
        selected = idle.get("selected_gpu")
        now = datetime.now(timezone.utc).timestamp()
        if (idle.get("study_id") != "SGW-01"
                or idle.get("status") != "passed_idle_snapshot_only"
                or not _positive_finite_number(observed)
                or not start.timestamp() <= observed <= now
                or now - observed > MAX_IDLE_PROBE_AGE_SECONDS
                or type(idle.get("expected_visible_gpu_count")) is not int
                or idle["expected_visible_gpu_count"] != gpu_count
                or type(idle.get("model_requests")) is not int or idle["model_requests"] != 0
                or not isinstance(allocated, list) or len(allocated) != gpu_count
                or not all(isinstance(item, str) and item for item in allocated)
                or len(set(allocated)) != gpu_count
                or not isinstance(gpus, list) or not isinstance(occupied, list) or not isinstance(selected, Mapping)
                or len(gpus) != gpu_count
                or not all(isinstance(item, Mapping) and isinstance(item.get("uuid"), str) for item in gpus)
                or not all(isinstance(item, str) for item in occupied)
                or selected.get("uuid") not in allocated
                or set(allocated) != {item["uuid"] for item in gpus}
                or selected not in gpus
                or (not pod_lane and set(allocated) & set(occupied))
                or (pod_lane and (selected.get("uuid") != receipt["selected_gpu_uuid"]
                    or not all(_gpu_uuid(item) for item in allocated)))
        ):
            raise ResourceBlocked("GPU idle probe does not prove this exact pre-launch allocation")
        for gpu in gpus:
            if any(type(gpu.get(field)) is not int or gpu[field] < 0 for field in (
                "index", "memory_used_mib", "memory_free_mib", "utilization_percent",
            )):
                raise ResourceBlocked("GPU idle probe has malformed device measurements")
            if pod_lane and gpu.get("name") != expected_gpu_name:
                raise ResourceBlocked("full allocated GPU inventory differs from the admitted hardware name")
            if not pod_lane or gpu["uuid"] == receipt["selected_gpu_uuid"]:
                try:
                    select_idle([gpu], set(occupied), 1, expected_name=expected_gpu_name)
                except (ValueError, RuntimeError) as exc:
                    kind = "declared" if pod_lane else "qualified"
                    raise ResourceBlocked(f"allocated GPU failed its idle/{kind}-hardware guard: {exc}") from exc
    remaining = int((deadline - datetime.now(timezone.utc)).total_seconds())
    if remaining < minimum_runtime_seconds:
        raise ResourceBlocked("external allocation expires before one bounded operation can finish")
    return remaining


def _space_check(release: Release, *, stage: str) -> None:
    floor = 100 * 1024**3
    configured = release.binding.get("minimum_free_bytes")
    if configured is not None and (type(configured) is not int or configured < floor):
        raise ResourceBlocked("minimum_free_bytes cannot lower the immutable 100 GiB floor")
    required = max(floor, configured or floor)
    storage_ref = _operational_reference(release, "storage_budget_receipt")
    if stage in {"D", "C"} and storage_ref is None:
        raise ResourceBlocked(f"{stage} requires a measured pilot storage receipt")
    if storage_ref is not None:
        storage = _receipt(storage_ref, "storage budget")
        _unexpired(storage, "storage budget")
        if storage.get("status") != "approved":
            raise ResourceBlocked("storage budget receipt is not approved")
        _receipt_identity(release, storage, "storage budget")
        p95 = storage.get("pilot_p95_episode_bytes")
        remaining = storage.get("global_remaining_episode_count")
        if (type(p95) is not int or p95 <= 0 or type(remaining) is not int
                or remaining < SOURCE_QUEUE_EPISODE_COUNT):
            raise ResourceBlocked("storage receipt lacks conservative global remaining/pilot-P95 accounting")
        required = max(required, (3 * p95 * remaining + 1) // 2)
    free = shutil.disk_usage(release.root.parent).free
    if free < required:
        raise ResourceBlocked(f"persistent storage blocked: {free} < {required} free bytes")


def _budget_check(release: Release, *, stage: str, model: str, minimum_runtime_seconds: int) -> None:
    budget = _receipt(_operational_reference(release, "resource_budget_receipt"), "resource budget")
    expiry = _expiry(budget, "resource budget")
    if budget.get("status") != "approved":
        raise ResourceBlocked("resource budget receipt is not approved")
    _receipt_identity(release, budget, "resource budget")
    if budget.get("model") not in {model, "all_models"}:
        raise ResourceBlocked("resource budget receipt does not cover this model")
    mode = _authorization_check(release, model=model)
    approved = budget.get("approved_gpu_hours")
    estimated = budget.get("estimated_remaining_gpu_hours")
    if not _positive_finite_number(estimated):
        raise ResourceBlocked("resource budget receipt lacks a finite conservative GPU-hour estimate")
    if mode == "numeric_global_gpu_hour_cap" and (
            not _positive_finite_number(approved) or estimated > approved):
        raise ResourceBlocked("numeric resource budget receipt lacks approved conservative GPU-hour coverage")
    if mode == "numeric_global_gpu_hour_cap":
        authorization = _receipt(release.binding["operational_authorization_receipt"], "operational authorization")
        if approved > authorization["approved_global_gpu_hours"]:
            raise ResourceBlocked("resource budget exceeds the owner-approved global GPU-hour cap")
    if (expiry - datetime.now(timezone.utc)).total_seconds() < minimum_runtime_seconds:
        raise ResourceBlocked("resource budget approval expires before one bounded episode can finish")
    if stage in {"D", "C"}:
        runtime = _receipt(budget.get("measured_runtime_receipt"), "measured runtime")
        _unexpired(runtime, "measured runtime")
        if runtime.get("status") != "measured":
            raise ResourceBlocked(f"{stage} requires a measured pilot runtime receipt")
        _receipt_identity(release, runtime, "measured runtime")
        if (runtime.get("model") not in {model, "all_models"}
                or runtime.get("max_cell_attempts") != 3
                or runtime.get("request_deadline_seconds") != release.binding.get("request_deadline_seconds", 300)
                or runtime.get("episode_deadline_seconds") != release.binding.get("episode_deadline_seconds", 900)
                or not _positive_finite_number(runtime.get("estimated_remaining_gpu_hours"))):
            raise ResourceBlocked(f"{stage} runtime estimate does not cover this model, deadlines, and retry allowance")
        if estimated < runtime["estimated_remaining_gpu_hours"]:
            raise ResourceBlocked(f"{stage} budget estimate is below the measured remaining GPU-hour bound")
    workers = release.binding.get("max_concurrent_model_workers")
    total_gpus = release.binding.get("max_total_allocated_gpus")
    authorization = _receipt(release.binding["operational_authorization_receipt"], "operational authorization")
    constraints = authorization.get("constraints")
    as_needed = isinstance(constraints, Mapping) and _as_needed_scaling(authorization, constraints)
    if (type(workers) is not int or type(total_gpus) is not int or workers < 1 or total_gpus < 1
            or (not as_needed and (workers > 2 or total_gpus > 4))
            or any(type(value) is not int or value < 1 for value in release.binding["model_gpu_counts"].values())
            or sum(release.binding["model_gpu_counts"].values()) > total_gpus):
        raise ResourceBlocked("runtime binding exceeds frozen two-worker/four-GPU ceiling")


def _status(release: Release, worker_id: str, **values: Any) -> None:
    atomic_json(release.root.parent / "status" / f"{worker_id}.json", {
        "schema_version": "sgw-01-worker-status-v1", "release_id": release.release_id,
        "worker_id": worker_id, "updated_at_utc": utc_now(), **values,
    })


class _Heartbeat:
    def __init__(self, release: Release, worker_id: str, seconds: int):
        if seconds <= 0:
            raise ContractError("heartbeat interval must be positive")
        self.release = release
        self.worker_id = worker_id
        self.seconds = seconds
        self.current_cell: str | None = None
        self.valid = 0
        self.last_error: str | None = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="sgw-heartbeat", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=self.seconds + 1)

    def _run(self) -> None:
        while not self._stop.wait(self.seconds):
            _status(self.release, self.worker_id, state="running", current_cell=self.current_cell,
                    valid=self.valid, last_error=self.last_error, heartbeat=True)


def _stage_authorized(release: Release, stage: str) -> None:
    receipt = json.loads((release.root / "release_receipt.json").read_text(encoding="utf-8"))
    authorizations = validate_stage_authorizations(receipt.get("stage_authorizations"), stage)
    if stage not in authorizations:
        raise ContractError(f"stage {stage} lacks a release authorization receipt")


def _load_scorer() -> ScoreFn:
    """Resolve the scorer lazily so production cannot fall back to a fake."""
    try:
        from .scoring import FrozenScoringConfig, GoalSpec, result_payload, score_episode
    except ImportError as exc:
        raise ContractError("production scorer is unavailable") from exc

    def score(trace: Mapping[str, Any], cell: Cell) -> Mapping[str, Any]:
        goal = GoalSpec(
            family=cell.family, physical_goal_sign=int(cell.row["physical_goal_sign"]),
            form=str(cell.row["form"]),
        )
        scored = score_episode(trace, goal, FrozenScoringConfig())
        return result_payload(
            scored,
            release_id=str(trace["release_id"]),
            cell_id=cell.cell_id,
            attempt_id=str(trace["attempt_id"]),
            completed_at_utc=str(trace["completed_at_utc"]),
        )
    return score


def _canonical_outcome(outcome: Mapping[str, Any], cell: Cell, scorer: ScoreFn | None) -> dict[str, Any]:
    """Scorer, not adapter termination labels, decides every model denominator."""
    value = dict(outcome)
    if value.get("status") == "technical_invalid":
        if not isinstance(value.get("technical_cause"), str):
            raise ContractError("technical invalid execution lacks a technical cause")
        return value
    mapping = value.get("episode_mapping")
    if not isinstance(mapping, list):
        raise ContractError("nontechnical execution lacks the raw episode mapping required for scoring")
    trace = {
        "states": mapping,
        "terminal_observed": value.get("safety_terminated") is not True,
        "termination_reason": value.get("termination_reason"),
        "safety_terminated": value.get("safety_terminated") is True,
        "success_events": value.get("success_events", []),
    }
    trace.update({
        "release_id": cell.row["release_id"],
        "cell_id": cell.cell_id,
        "attempt_id": value.get("attempt_id", "pending"),
        "completed_at_utc": utc_now(),
    })
    scored = dict((scorer or _load_scorer())(trace, cell))
    status = scored.get("status")
    if status not in {"valid_success", "valid_model_failure", "censored", "technical_invalid"}:
        raise ContractError("scorer did not emit a canonical SGW status")
    # A normal 450-action endpoint is scored; censoring is only a physical
    # safety truncation, never an adapter convenience label.
    if status == "censored" and value.get("safety_terminated") is not True:
        raise ContractError("only explicit physical safety truncation may be censored")
    value.update(scored)
    value["status"] = status
    return value


def _out_of_memory(value: Any) -> bool:
    text = f"{type(value).__name__}: {value}".lower()
    return (isinstance(value, MemoryError) or getattr(value, "errno", None) == errno.ENOMEM
            or "out of memory" in text or "outofmemory" in text or re.search(r"\boom\b", text) is not None)


def run_partition(release: Release, *, model: str, family: str, stage: str, max_valid: int,
                  max_attempts: int, worker_id: str, adapter: Adapter | None = None,
                  heartbeat_seconds: int = 60, scorer: ScoreFn | None = None,
                  block_id: str | None = None) -> int:
    cells = selected_cells(release, model, family, stage, block_id)
    if block_id is not None:
        _protocol_runtime_check(release)
    if max_valid != len(cells) or max_attempts != 3:
        raise ContractError("partition limits must equal the frozen stage ceiling and three total attempts")
    _stage_authorized(release, stage)
    if block_id is not None:
        from .study_lane import stage_ready
        if not stage_ready(release.root.parent, stage, model):
            raise ContractError("per-model stage barrier is not complete")
    if release.binding.get("allow_parallel_existing_pod_lanes") is True and all(_completion(release, cell) for cell in cells):
        _status(release, worker_id, state="complete", valid=len(cells), expected=len(cells))
        return 0
    request_deadline = int(release.binding.get("request_deadline_seconds", 300))
    episode_deadline = int(release.binding.get("episode_deadline_seconds", 900))
    bounded_operation_seconds = request_deadline + episode_deadline
    valid = 0
    heartbeat = _Heartbeat(release, worker_id, heartbeat_seconds)
    heartbeat.start()
    close_registered = False
    try:
        with ExitStack() as lifetime:
            lifetime.enter_context(partition_lock(release, model, family, stage, block_id))
            pending = [cell for cell in cells if not _completion(release, cell)]
            if not pending:
                _status(release, worker_id, state="complete", valid=len(cells), expected=len(cells))
                return 0
            try:
                _space_check(release, stage=stage)
                _budget_check(release, stage=stage, model=model, minimum_runtime_seconds=bounded_operation_seconds)
                _allocation_check(release, model=model, minimum_runtime_seconds=bounded_operation_seconds)
            except ResourceBlocked as exc:
                _status(release, worker_id, state="blocked", reason=str(exc), valid=valid)
                return EXIT_STORAGE_BUDGET_BLOCKED
            # The global lock must cover model-server/factory construction, not
            # merely requests, so a duplicate Job cannot load a second policy.
            if release.binding.get("hold_on_technical_invalid") is True and fleet_is_held(release.root.parent):
                _status(release, worker_id, state="held", reason="fleet hold forbids new attempts", valid=valid)
                return EXIT_STORAGE_BUDGET_BLOCKED
            if block_id is not None:
                if STOP_REQUESTED:
                    return EXIT_ATTEMPTS_EXHAUSTED
                if len(pending) != 6 or any((release.root.parent / "attempts" / cell.cell_id).exists() for cell in cells):
                    request_fleet_hold(release.root.parent, block_id=block_id,
                                       reason="prior or partial block attempts; no automatic replay")
                    raise ContractError("prior or partial block attempts preserved; no automatic replay")
                begin_once(release.root.parent, "block-executions", block_id,
                           release_id=release.release_id, worker_id=worker_id,
                           release_hashes=dict(release.hashes))
            try:
                adapter = adapter or load_adapter(model)
            except Exception as exc:
                if release.binding.get("hold_on_technical_invalid") is True:
                    request_fleet_hold(release.root.parent, release_id=release.release_id,
                                       source_commit=release.binding["source_commit"],
                                       phase="model_construction", reason=f"{type(exc).__name__}: {exc}")
                _status(release, worker_id, state="technical_invalid", phase="model_construction",
                        reason=f"{type(exc).__name__}: {exc}", traceback=traceback.format_exc(), valid=valid)
                raise ContractError("model construction failed; partition aborted without replay") from exc
            close = getattr(adapter, "close", None)
            if callable(close):
                lifetime.callback(close)
                close_registered = True
            for cell in cells:
                heartbeat.current_cell = cell.cell_id
                heartbeat.valid = valid
                if _completion(release, cell):
                    valid += 1
                    continue
                while not STOP_REQUESTED:
                    if release.binding.get("hold_on_technical_invalid") is True and fleet_is_held(release.root.parent):
                        _status(release, worker_id, state="held", reason="fleet hold forbids new attempts", valid=valid)
                        return EXIT_STORAGE_BUDGET_BLOCKED
                    try:
                        _space_check(release, stage=stage)
                        _budget_check(release, stage=stage, model=model, minimum_runtime_seconds=bounded_operation_seconds)
                        allocation_remaining = _allocation_check(
                            release, model=model, minimum_runtime_seconds=bounded_operation_seconds,
                            verify_idle_probe=False,
                        )
                    except ResourceBlocked as exc:
                        _status(release, worker_id, state="blocked", reason=str(exc), valid=valid)
                        return EXIT_STORAGE_BUDGET_BLOCKED
                    number = next_attempt_number(release, cell)
                    if number > max_attempts:
                        _status(release, worker_id, state="blocked", cell_id=cell.cell_id,
                                reason="technical attempts exhausted", valid=valid)
                        return EXIT_ATTEMPTS_EXHAUSTED
                    recorder = AttemptRecorder(release, cell, f"attempt-{number:03d}")
                    recorder.begin()
                    admission = _run_admission(release)
                    if admission is not None:
                        atomic_json(recorder.path / "run-admission.json", admission)
                    try:
                        reset = _run_with_deadline(
                            min(request_deadline, allocation_remaining), "reset",
                            lambda: adapter.reset(cell, recorder),
                        )
                        if not isinstance(reset, dict) or not reset.get("full_reset"):
                            raise ContractError("adapter did not attest a full reset")
                        remaining_after_reset = _allocation_check(
                            release, model=model, minimum_runtime_seconds=episode_deadline,
                            verify_idle_probe=False,
                        )
                        outcome = _run_with_deadline(
                            min(episode_deadline, remaining_after_reset), "episode",
                            lambda: adapter.run_episode(cell, recorder, reset)
                        )
                        outcome = {**outcome, "attempt_id": recorder.attempt_id}
                        outcome = _canonical_outcome(outcome, cell, scorer)
                        published = recorder.complete(outcome)
                        if outcome.get("status") == "technical_invalid" and _out_of_memory(outcome.get("technical_cause")):
                            raise ContractError("policy memory exhaustion; partition aborted without replay")
                    except DeadlineExceeded as exc:
                        heartbeat.last_error = f"{type(exc).__name__}: {exc}"
                        recorder.event("technical_invalid", error_type=type(exc).__name__, error=str(exc))
                        published = recorder.complete({"status": "technical_invalid", "technical_cause": heartbeat.last_error})
                    except ContractError as exc:
                        if release.binding.get("hold_on_technical_invalid") is True:
                            request_fleet_hold(release.root.parent, release_id=release.release_id,
                                               cell_id=cell.cell_id, attempt_id=recorder.attempt_id,
                                               reason=f"{type(exc).__name__}: {exc}")
                        raise
                    except OSError as exc:
                        heartbeat.last_error = f"{type(exc).__name__}: {exc}"
                        recorder.event("technical_invalid", error_type=type(exc).__name__, error=str(exc))
                        published = recorder.complete({"status": "technical_invalid", "technical_cause": heartbeat.last_error})
                        if _out_of_memory(exc):
                            raise ContractError("policy memory exhaustion; partition aborted without replay") from exc
                    except Exception as exc:
                        from .adapters import AdapterError
                        if isinstance(exc, AdapterError) or _out_of_memory(exc):
                            cause = f"{type(exc).__name__}: {exc}"
                            heartbeat.last_error = cause
                            recorder.event("technical_invalid", error_type=type(exc).__name__, error=str(exc),
                                           traceback=traceback.format_exc())
                            recorder.complete({"status": "technical_invalid", "technical_cause": cause})
                            _status(release, worker_id, state="technical_invalid", phase="adapter_execution",
                                    current_cell=cell.cell_id, reason=cause, valid=valid, attempts=number)
                            # A disconnected response alone cannot identify the native server's failure.
                            reason = ("adapter request/reset failed" if isinstance(exc, AdapterError)
                                      else "policy memory exhaustion")
                            raise ContractError(f"{reason}; partition aborted without replay") from exc
                        recorder.event("fatal_unclassified_error", error_type=type(exc).__name__, error=str(exc))
                        if release.binding.get("hold_on_technical_invalid") is True:
                            request_fleet_hold(release.root.parent, release_id=release.release_id,
                                               cell_id=cell.cell_id, attempt_id=recorder.attempt_id,
                                               reason=f"{type(exc).__name__}: {exc}")
                        raise ContractError(f"unclassified adapter failure; attempt preserved: {type(exc).__name__}") from exc
                    _status(release, worker_id, state="running", current_cell=cell.cell_id, valid=valid,
                            attempts=number, bytes_written=sum(p.stat().st_size for p in recorder.path.rglob("*") if p.is_file()))
                    if published or _completion(release, cell):
                        valid += 1
                        break
                if STOP_REQUESTED:
                    _status(release, worker_id, state="interrupted", current_cell=cell.cell_id, valid=valid)
                    return EXIT_ATTEMPTS_EXHAUSTED
        _status(release, worker_id, state="complete", valid=valid, expected=len(cells))
        return 0
    except ResourceBlocked as exc:
        _status(release, worker_id, state="blocked", reason=str(exc), valid=valid)
        return EXIT_STORAGE_BUDGET_BLOCKED
    finally:
        heartbeat.close()
        close = getattr(adapter, "close", None) if adapter is not None and not close_registered else None
        if callable(close):
            close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--model", choices=("N3", "E3", "F3"), required=True)
    parser.add_argument("--family", choices=("LAT", "HEIGHT", "DIST"), required=True)
    parser.add_argument("--stage", choices=("P", "D", "C"), required=True)
    parser.add_argument("--block-id", help="exact intact block; requires registered six-cell-block-v1 binding")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--max-valid-episodes", type=int, required=True)
    parser.add_argument("--max-cell-attempts", type=int, default=3)
    parser.add_argument("--heartbeat-seconds", type=int, default=60)
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, _stop)
    release = load_release(args.release)
    try:
        code = run_partition(release, model=args.model, family=args.family, stage=args.stage,
                             max_valid=args.max_valid_episodes, max_attempts=args.max_cell_attempts,
                             worker_id=f"{args.model}-{args.family}-{args.stage}-{os.getpid()}",
                             heartbeat_seconds=args.heartbeat_seconds, block_id=args.block_id)
    except OSError as exc:
        print(str(exc), file=sys.stderr)
        code = EXIT_STORAGE_BUDGET_BLOCKED
    except ContractError as exc:
        print(str(exc), file=sys.stderr)
        code = EXIT_RELEASE_INVALID
    raise SystemExit(code)


if __name__ == "__main__":
    main()
