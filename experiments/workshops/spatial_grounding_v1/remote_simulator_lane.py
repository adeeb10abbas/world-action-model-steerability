"""One serial native simulator lane; policy actions use the existing mailbox.

Factory: SGW01_ENV_FACTORY=experiments.workshops.spatial_grounding_v1.remote_simulator_lane:create_environment
Both roles bind SGW01_SIMULATOR_LANE_IDENTITY(_SHA256), SGW01_ENV_BINDING(_SHA256)
and actual Downward API ownership. V1 uses JOB_UID/POD_UID. V2 explicitly binds a
bare policy Pod by POD_NAME/POD_UID without JOB_UID/JOB_NAME; its simulator is
still Job-owned. V3 binds both as Pods and requires the simulator's hash-bound
finite ancestor supervisor; only the simulator verifies its local PID lineage.
Lane identities additionally name
cohort_root, so neither party can redirect evidence outside the shared cohort.

The unchanged native receiver has no ready marker. The startup budget covers
publication through the first *real* reset response, never a probe/reset. Native
AppLauncher/model imports occur only in the separately executed native CLI.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import fcntl
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
import traceback
from typing import Any, Mapping
import uuid

from .adapters import AdapterError
from .mailbox_visibility import DirectoryRefresher
from .native_mailbox_receiver import verify_receiver_completion
from .producer import _git_revision
from .robolab_jointpos_environment import JointPositionBinding
from .simulator_mailbox import POD_IDENTITY_SCHEMA, MailboxClient, _digest, _read, _write, normalize_identity

SCHEMA = "sgw-01-simulator-lane-v1"
POD_SCHEMA = "sgw-01-simulator-lane-v2"
POD_SIMULATOR_SCHEMA = "sgw-01-simulator-lane-v3"
DESCRIPTOR_SCHEMA = "sgw-01-simulator-lane-request-v1"
RESULT_SCHEMA = "sgw-01-simulator-lane-result-v1"
STOP_SCHEMA = "sgw-01-simulator-lane-stop-v1"
TIMEOUTS = {"startup": 600.0, "rpc": 120.0, "finish": 120.0, "attempt": 3600.0}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AdapterError(message)


def _absolute(value: Any) -> Path:
    _require(isinstance(value, str) and bool(value) and Path(value).is_absolute(), "lane paths must be absolute")
    path = Path(value)
    _require(path == path.resolve(), "lane paths must be canonical, not symlink aliases")
    return path


def _sha(value: Any) -> str:
    _require(isinstance(value, str) and re.fullmatch("[0-9a-f]{64}", value) is not None, "lane requires a SHA256")
    return value


def _token(value: Any) -> str:
    _require(isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,159}", value) is not None
             and "--" not in value, "unsafe/ambiguous lane cell or attempt token")
    return value


def _seconds(value: Any) -> float:
    _require(type(value) in (int, float) and math.isfinite(value) and value > 0, "lane requires finite positive timeouts")
    return float(value)


def _ref(path: Path) -> dict[str, Any]:
    return {"path": str(path), "sha256": _digest(path), "bytes": path.stat().st_size}


def _bound(item: Mapping[str, Any], expected: Path) -> dict[str, Any]:
    _require(set(item) == {"path", "sha256", "bytes"} and _absolute(item["path"]) == expected,
             "lane artifact path differs from its descriptor")
    _require(_ref(expected) == item, "lane artifact hash/size differs")
    return _read(expected)


def _same_or_create(path: Path, value: Mapping[str, Any]) -> None:
    try:
        _write(path, value)
    except FileExistsError:
        _require(_read(path) == value, "existing lane control identity/result differs")


def _code_root() -> Path:
    return Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class Lane:
    path: Path
    sha256: str
    value: dict[str, Any]
    binding: JointPositionBinding

    @property
    def control(self) -> Path:
        return Path(self.value["control_root"])


def _simulator_fields(value: Mapping[str, Any]) -> dict[str, Any]:
    if value.get("schema_version") != POD_SIMULATOR_SCHEMA:
        return {"simulator_job_uid": value["simulator_job_uid"], "simulator_pod_uid": value["simulator_pod_uid"]}
    return {"identity_schema": POD_IDENTITY_SCHEMA, **{key: value[key] for key in (
        "simulator_owner_kind", "simulator_pod_name", "simulator_pod_uid", "simulator_gpu_uuid",
        "simulator_supervisor_identity_receipt", "simulator_supervisor_entrypoint",
        "simulator_renderer_gpu_index", "simulator_multi_gpu",
    )}}


def _simulator_supervisor(value: Mapping[str, Any], role: str, env: Mapping[str, str]) -> Mapping[str, Any]:
    from .worker import _gpu_uuid, verify_existing_pod_supervisor

    _require(_gpu_uuid(value["simulator_gpu_uuid"]), "simulator lane requires a physical GPU UUID")
    _require(type(value["simulator_renderer_gpu_index"]) is int and value["simulator_renderer_gpu_index"] == 0
             and value["simulator_multi_gpu"] is False,
             "only explicit single-renderer index zero is supported; other graphics mappings remain unqualified")
    reference = value["simulator_supervisor_identity_receipt"]
    entrypoint = value["simulator_supervisor_entrypoint"]
    for ref in (reference, entrypoint):
        _require(isinstance(ref, Mapping) and set(ref) == {"path", "sha256"}, "simulator supervisor reference differs")
        path = _absolute(ref["path"])
        _require(path.is_file() and _digest(path) == _sha(ref["sha256"]), "simulator supervisor artifact hash differs")
    record = _read(Path(reference["path"]))
    expected = {
        "schema": "sgw-01-existing-pod-supervisor-v1", "role": "simulator",
        "pod_name": value["simulator_pod_name"], "pod_uid": value["simulator_pod_uid"],
        "gpu_uuid": value["simulator_gpu_uuid"], "source_root": value["source_root"],
        "source_commit": value["source_commit"], "entrypoint": entrypoint,
    }
    _require(all(record.get(key) == item for key, item in expected.items()), "simulator supervisor scope differs from lane")
    try:
        start = datetime.fromisoformat(record["started_at_utc"].replace("Z", "+00:00"))
        deadline = datetime.fromisoformat(record["deadline_utc"].replace("Z", "+00:00"))
        seconds = record["deadline_seconds"]
        _require(start.tzinfo is not None and deadline.tzinfo is not None and type(seconds) is int and seconds > 0
                 and start <= datetime.now(timezone.utc) < deadline and deadline == start + timedelta(seconds=seconds),
                 "simulator supervisor has no valid finite lifetime")
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise AdapterError("simulator supervisor timing is malformed") from exc
    if role == "simulator":
        verify_existing_pod_supervisor(reference, source_commit=value["source_commit"], entrypoint=entrypoint, environ=env)
    # The policy can bind remote bytes/deadline, not attest the other Pod's PID.
    return record


def load_lane(path: Path, sha256: str, role: str, environ: Mapping[str, str] | None = None) -> Lane:
    env = os.environ if environ is None else environ
    path = _absolute(str(path))
    _require(_digest(path) == _sha(sha256), "simulator lane identity hash differs")
    value = _read(path)
    required = {"schema_version", "model", "source_root", "source_commit", "cohort_root", "control_root",
                "environment_binding", "policy_job_uid", "policy_pod_uid", "simulator_job_uid", "simulator_pod_uid"}
    pod_owner = value.get("schema_version") in {POD_SCHEMA, POD_SIMULATOR_SCHEMA}
    simulator_pod_owner = value.get("schema_version") == POD_SIMULATOR_SCHEMA
    optional = set()
    if pod_owner:
        required = required - {"policy_job_uid"} | {"policy_owner_kind", "policy_pod_name"}
        optional |= {"policy_job_uid", "policy_job_name"}
    if simulator_pod_owner:
        required = required - {"simulator_job_uid"} | {
            "simulator_owner_kind", "simulator_pod_name", "simulator_gpu_uuid",
            "simulator_supervisor_identity_receipt", "simulator_supervisor_entrypoint",
            "simulator_renderer_gpu_index", "simulator_multi_gpu",
        }
        optional |= {"simulator_job_uid", "simulator_job_name"}
    _require(required.issubset(value) and set(value).issubset(required | optional)
             and value["schema_version"] in {SCHEMA, POD_SCHEMA, POD_SIMULATOR_SCHEMA}
             and value["model"] in {"N3", "E3", "F3"} and role in {"policy", "simulator"}, "invalid simulator lane identity")
    for owner, is_pod in (("policy", pod_owner), ("simulator", simulator_pod_owner)):
        if is_pod:
            _require(value[f"{owner}_owner_kind"] == "Pod" and value.get(f"{owner}_job_uid") is None
                     and value.get(f"{owner}_job_name") is None and isinstance(value[f"{owner}_pod_name"], str)
                     and re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?", value[f"{owner}_pod_name"]) is not None,
                     "bare Pod identity cannot invent a Job owner")
    source, cohort, control = (_absolute(value[key]) for key in ("source_root", "cohort_root", "control_root"))
    _require(source == _code_root() and _git_revision(str(source)) == value["source_commit"],
             "lane does not use the clean pinned running source")
    _require(cohort.is_dir() and control != cohort and control.is_relative_to(cohort)
             and not cohort.is_relative_to(source), "lane control/evidence cohort must be outside source Git")
    for key in ("policy_job_uid", "policy_pod_uid", "simulator_job_uid", "simulator_pod_uid"):
        if (pod_owner and key == "policy_job_uid") or (simulator_pod_owner and key == "simulator_job_uid"):
            continue
        _require(isinstance(value[key], str) and str(uuid.UUID(value[key])) == value[key], "lane UIDs must be canonical")
    _require(value["policy_pod_uid"] != value["simulator_pod_uid"]
             and (pod_owner or value["policy_job_uid"] != value["simulator_job_uid"]),
             "policy and simulator must have distinct actual owners")
    if (pod_owner and role == "policy") or (simulator_pod_owner and role == "simulator"):
        _require(env.get("POD_UID") == value[f"{role}_pod_uid"] and env.get("POD_NAME") == value[f"{role}_pod_name"]
                 and env.get("JOB_UID") in {None, ""} and env.get("JOB_NAME") in {None, ""},
                 "lane differs from actual bare Pod identity")
    else:
        _require(env.get("JOB_UID") == value[f"{role}_job_uid"] and env.get("POD_UID") == value[f"{role}_pod_uid"],
                 "lane differs from actual Downward API role identity")
    _require(env.get("MODEL", value["model"]) == value["model"], "lane model differs from role environment")
    binding_ref = value["environment_binding"]
    _require(isinstance(binding_ref, dict) and set(binding_ref) == {"path", "sha256"}, "invalid lane environment binding")
    binding_path = _absolute(binding_ref["path"])
    _require(str(binding_path) == env.get("SGW01_ENV_BINDING")
             and _sha(binding_ref["sha256"]) == env.get("SGW01_ENV_BINDING_SHA256")
             and _digest(binding_path) == binding_ref["sha256"], "lane environment binding path/hash differs")
    raw_binding = _read(binding_path)
    _require(raw_binding.get("source_root") == str(source) and raw_binding.get("source_commit") == value["source_commit"],
             "native environment binding source differs from lane")
    # The native loader uses the actual process environment; CLI roles inherit it.
    binding = JointPositionBinding.load()
    _require(binding.source_root == source and binding.cells == raw_binding.get("cells"),
             "loaded native binding differs from lane source/cells")
    if simulator_pod_owner:
        _simulator_supervisor(value, role, env)
    return Lane(path, sha256, value, binding)


def _control(lane: Lane) -> None:
    lane.control.mkdir(parents=True, exist_ok=True)
    _same_or_create(lane.control / "lane.json", {"schema_version": SCHEMA, "lane_identity_sha256": lane.sha256,
                                               "identity": lane.value})
    for name in ("requests", "claims", "results", "runs"):
        (lane.control / name).mkdir(exist_ok=True)


def _stop_requested(lane: Lane, refresh: Any) -> bool:
    refresh(lane.control)
    path = lane.control / "stop.json"
    if not path.exists():
        return False
    _require(_read(path) == {"schema_version": STOP_SCHEMA, "lane_identity_sha256": lane.sha256,
                            "model": lane.value["model"]}, "stop instruction does not bind this lane")
    return True


def _paths(descriptor: dict, lane: Lane) -> tuple[Path, Path, str]:
    root = _absolute(descriptor["evidence_root"])
    cell_id, attempt_id = _token(descriptor["cell_id"]), _token(descriptor["attempt_id"])
    _require(root.is_relative_to(Path(lane.value["cohort_root"])) and root.name == "simulator"
             and root.parent.name == attempt_id and root.parent.parent.name == cell_id
             and root.parent.parent.parent.name == "attempts", "lane evidence is not inside its recorder attempt")
    _require(descriptor["mailbox_root"] == str(root / "mailbox"), "mailbox must remain inside recorder simulator evidence")
    return root, root / "lane", f"{cell_id}--{attempt_id}"


def _released_row(row: Any, lane: Lane) -> tuple[dict, str]:
    _require(isinstance(row, Mapping) and row.get("status") == "RELEASED" and row.get("model") == lane.value["model"]
             and isinstance(row.get("release_id"), str) and bool(row["release_id"]),
             "remote simulator requires a genuinely released matching model cell")
    _token(row.get("cell_id"))
    native, _ = lane.binding.cell(row)
    candidate = _sha(native.get("candidate_file_sha256"))
    for key, value in (("candidate_sha256", candidate), ("binding_sha256", lane.value["environment_binding"]["sha256"])):
        _require(key not in row or row[key] == value, "released row contradicts actual native binding")
    return dict(row), candidate


def read_descriptor(path: Path, lane: Lane) -> tuple[dict, dict, Path, Path]:
    value = _read(path)
    required = {"schema_version", "lane_identity_sha256", "cell_id", "attempt_id", "evidence_root", "mailbox_root",
                "cell", "identity", "attempt_intent", "timeouts"}
    _require(set(value) == required and value["schema_version"] == DESCRIPTOR_SCHEMA
             and value["lane_identity_sha256"] == lane.sha256, "descriptor does not bind this simulator lane")
    root, metadata, token = _paths(value, lane)
    _require(path == lane.control / "requests" / f"{token}.json" and _digest(path) == _digest(metadata / "descriptor.json"),
             "published descriptor differs from retained attempt descriptor")
    _require(set(value["timeouts"]) == set(TIMEOUTS), "descriptor timeout fields differ")
    for seconds in value["timeouts"].values():
        _seconds(seconds)
    intent = _bound(value["attempt_intent"], root.parent / "intent.json")
    row, candidate = _released_row(intent.get("cell"), lane)
    _require(intent.get("schema_version") == "sgw-01-attempt-intent-v1"
             and intent.get("cell_id") == row["cell_id"] == value["cell_id"]
             and intent.get("attempt_id") == value["attempt_id"] and intent.get("release_id") == row["release_id"],
             "descriptor differs from the existing released recorder intent")
    cell = _bound(value["cell"], metadata / "cell.json")
    expected_cell = {**row, "candidate_sha256": candidate, "binding_sha256": lane.value["environment_binding"]["sha256"]}
    _require(cell == expected_cell, "separate receiver cell differs from the unchanged released row")
    identity = _bound(value["identity"], metadata / "identity.json")
    expected_identity = {
        "release_id": row["release_id"], "cell_id": row["cell_id"], "attempt_id": value["attempt_id"],
        "candidate_sha256": candidate, "binding_sha256": expected_cell["binding_sha256"],
        **_simulator_fields(lane.value),
    }
    _require(set(identity) == {*expected_identity, "channel_nonce"}
             and all(identity[k] == v for k, v in expected_identity.items())
             and re.fullmatch("[0-9a-f]{32}", identity.get("channel_nonce", "")) is not None, "attempt receiver identity differs")
    identity = normalize_identity(identity)
    return value, identity, root, metadata


def _result(metadata: Path, descriptor_path: Path, lane: Lane, identity: dict) -> dict:
    result = _read(metadata / "result.json")
    _require(result.get("schema_version") == RESULT_SCHEMA and result.get("lane_identity_sha256") == lane.sha256
             and result.get("descriptor_sha256") == _digest(descriptor_path)
             and result.get("identity_sha256") == _digest(metadata / "identity.json"), "outer result attribution differs")
    _require(result.get("status") == "completed" and result.get("error") is None,
             f"native simulator attempt did not complete: {result.get('status')}: {result.get('error')}")
    token = descriptor_path.stem
    claim = _bound(result["claim"], lane.control / "claims" / f"{token}.json")
    started = _bound(result["child_start"], metadata / "child-start.json")
    exited = _bound(result["child_exit"], metadata / "child-exit.json")
    descriptor = _read(descriptor_path)
    _require(claim.get("descriptor_sha256") == started.get("descriptor_sha256") == exited.get("descriptor_sha256")
             == result["descriptor_sha256"] and claim.get("lane_identity_sha256") == lane.sha256
             and started.get("run_id") == claim.get("run_id") == exited.get("run_id")
             and started.get("lane_identity_sha256") == lane.sha256
             and type(started.get("pid")) is int and started["pid"] > 0
             and started["pid"] == started.get("process_group_id") == exited.get("pid")
             and started.get("process_start_identity") == exited.get("process_start_identity")
             and isinstance(started.get("process_start_identity"), str) and bool(started["process_start_identity"])
             and started.get("command") == _command(descriptor, max(1, math.ceil(_seconds(started["deadline_seconds"]))))
             and type(exited.get("returncode")) is int and exited["returncode"] == 0 and exited.get("timed_out") is False
             and exited.get("interrupted") is False and exited.get("group_drained") is True,
             "owned child exit is absent or contradicts completion")
    mailbox = metadata.parent / "mailbox"
    _require(not (metadata / "client-failure.json").exists() and not any((mailbox / "faults").iterdir()),
             "client/fault evidence contradicts native completion")
    receipt = verify_receiver_completion(mailbox, identity)
    _bound(result["receiver_completion"], mailbox / "receiver_complete.json")
    _bound(result["close_response"], mailbox / "responses" / f"{receipt['close_command_id']:04d}-close.json")
    _require(_ref(metadata / "native-child.log") == result["native_log"], "owned native log changed after exit")
    return result


class LaneMailboxClient(MailboxClient):
    def __init__(self, *, lane: Lane, descriptor_path: Path, identity: dict, root: Path, metadata: Path,
                 timeouts: dict, startup_deadline: float, refresh: Any):
        super().__init__(root=root / "mailbox", identity=identity, timeout_s=timeouts["rpc"], metadata_refresh=refresh)
        self.lane, self.descriptor_path, self.metadata = lane, descriptor_path, metadata
        self.timeouts, self.startup_deadline = timeouts, startup_deadline
        self._first_reset, self._finished, self._failure = True, None, None

    def _failed(self, error: BaseException, phase: str) -> None:
        self._closed = True
        if self._failure is None:
            self._failure = error
            _write(self.metadata / "client-failure.json", {
                "lane_identity_sha256": self.lane.sha256, "descriptor_sha256": _digest(self.descriptor_path),
                "phase": phase, "last_command_id": self.command, "error": str(error),
                "error_type": type(error).__name__, "recorded_at_unix_s": time.time(),
            })

    def reset(self) -> Any:
        _require(self._finished is None, "finished mailbox cannot be reset")
        try:
            _require(self._failure is None and self._finished is None, "finished/failed mailbox cannot be reset")
            if self._first_reset:
                self.timeout_s = _seconds(self.startup_deadline - time.monotonic())
            result = super().reset()
            self._first_reset = False
            return result
        except BaseException as exc:
            self._failed(exc, "reset")
            raise
        finally:
            self.timeout_s = self.timeouts["rpc"]

    def step(self, action: Any) -> Any:
        _require(self._finished is None, "finished mailbox cannot execute actions")
        try:
            _require(not self._first_reset and self._failure is None and self._finished is None, "step requires a live reset attempt")
            return super().step(action)
        except BaseException as exc:
            self._failed(exc, "step")
            raise

    def finish_episode(self) -> dict:
        if self._finished is not None:
            return self._finished
        _require(self._failure is None and not self._closed, "failed mailbox cannot retry episode completion")
        try:
            deadline = time.monotonic() + self.timeouts["finish"]
            self.timeout_s = min(self.timeouts["rpc"], self.timeouts["finish"])
            super().close()
            while True:
                self.metadata_refresh(self.metadata)
                if (self.metadata / "result.json").exists():
                    break
                _require(time.monotonic() < deadline, "outer native completion wait timed out; no retry")
                time.sleep(.05)
            for directory in (self.root, self.root / "responses", self.root / "faults"):
                self.metadata_refresh(directory)
            result = _result(self.metadata, self.descriptor_path, self.lane, self.identity)
            complete = verify_receiver_completion(self.root, self.identity)
            _require(complete["close_command_id"] == self.command, "outer completion differs from acknowledged close")
            finished = {"descriptor": _ref(self.descriptor_path), "outer_result": _ref(self.metadata / "result.json"),
                        "acknowledged_close_command_id": self.command, "status": result["status"]}
            _write(self.metadata / "client-finished.json", finished)
            self._finished = finished
            return self._finished
        except BaseException as exc:
            self._failed(exc, "finish_episode")
            raise

    def close(self) -> None:
        self.finish_episode()


def create_environment(*, cell: Any, evidence_root: Path) -> LaneMailboxClient:
    lane = load_lane(Path(os.environ.get("SGW01_SIMULATOR_LANE_IDENTITY", "")),
                     os.environ.get("SGW01_SIMULATOR_LANE_IDENTITY_SHA256", ""), "policy")
    row, candidate = _released_row(getattr(cell, "row", cell), lane)
    root = _absolute(str(evidence_root))
    attempt_id = _token(root.parent.name)
    descriptor = {
        "schema_version": DESCRIPTOR_SCHEMA, "lane_identity_sha256": lane.sha256, "cell_id": row["cell_id"],
        "attempt_id": attempt_id, "evidence_root": str(root), "mailbox_root": str(root / "mailbox"),
    }
    _, metadata, token = _paths(descriptor, lane)
    intent = _read(root.parent / "intent.json")
    _require(intent.get("schema_version") == "sgw-01-attempt-intent-v1" and intent.get("cell") == row
             and intent.get("cell_id") == row["cell_id"] and intent.get("attempt_id") == attempt_id
             and intent.get("release_id") == row["release_id"], "factory must bind the existing released recorder intent")
    _control(lane)
    refresh = DirectoryRefresher()
    _require(not _stop_requested(lane, refresh), "simulator lane has an explicit stop instruction")
    _require(not root.exists() or not any(root.iterdir()), "simulator evidence already exists; no attempt reuse")
    root.mkdir(exist_ok=True)
    metadata.mkdir()
    identity = {
        "release_id": row["release_id"], "cell_id": row["cell_id"], "attempt_id": attempt_id,
        "channel_nonce": uuid.uuid4().hex, "candidate_sha256": candidate,
        "binding_sha256": lane.value["environment_binding"]["sha256"],
        **_simulator_fields(lane.value),
    }
    identity = normalize_identity(identity)
    _write(metadata / "identity.json", identity)
    _write(metadata / "cell.json", {**row, "candidate_sha256": candidate, "binding_sha256": identity["binding_sha256"]})
    timeouts = {name: _seconds(float(os.environ.get(f"SGW01_SIMULATOR_LANE_{name.upper()}_TIMEOUT_SECONDS", default)))
                for name, default in TIMEOUTS.items()}
    descriptor.update(identity=_ref(metadata / "identity.json"), cell=_ref(metadata / "cell.json"),
                      attempt_intent=_ref(root.parent / "intent.json"), timeouts=timeouts)
    _write(metadata / "descriptor.json", descriptor)
    path = lane.control / "requests" / f"{token}.json"
    _write(path, descriptor)
    deadline = time.monotonic() + timeouts["startup"]
    try:
        while True:
            refresh(root)
            refresh(metadata)
            if (root / "mailbox").is_dir():
                refresh(root / "mailbox")
            _require(not _stop_requested(lane, refresh), "lane stopped during startup")
            if (metadata / "result.json").exists():
                raise AdapterError(f"native receiver exited before client startup: {_read(metadata / 'result.json').get('status')}")
            if (metadata / "child-start.json").is_file() and all((root / "mailbox" / name).is_dir()
                                                               for name in ("requests", "responses", "faults")):
                started = _read(metadata / "child-start.json")
                _require(started.get("descriptor_sha256") == _digest(path) and started.get("lane_identity_sha256") == lane.sha256,
                         "child startup attribution differs")
                break
            _require(time.monotonic() < deadline, "simulator startup timed out; no retry")
            time.sleep(.05)
        return LaneMailboxClient(lane=lane, descriptor_path=path, identity=identity, root=root, metadata=metadata,
                                 timeouts=timeouts, startup_deadline=deadline, refresh=refresh)
    except BaseException as exc:
        _write(metadata / "client-failure.json", {"lane_identity_sha256": lane.sha256, "descriptor_sha256": _digest(path),
                                                 "phase": "startup", "error": str(exc), "error_type": type(exc).__name__})
        raise


def _process_start(pid: int) -> str:
    path = Path(f"/proc/{pid}/stat")
    if path.exists():
        return path.read_text().split(") ", 1)[-1].split()[19]
    # CPU subprocess tests also run on macOS; this is an actual process query.
    result = subprocess.run(["ps", "-p", str(pid), "-o", "lstart="], capture_output=True, text=True, check=True)
    _require(bool(result.stdout.strip()), "owned child start identity unavailable")
    return result.stdout.strip()


def _group_exists(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # EPERM is not proof of absence; teardown can transiently report it.
        return True


def _drain(child: subprocess.Popen, grace: float = 30) -> tuple[int, bool]:
    """Signal only the new process group created by this exact Popen."""
    if _group_exists(child.pid):
        try:
            os.killpg(child.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    end = time.monotonic() + grace
    while time.monotonic() < end:
        child.poll()
        if not _group_exists(child.pid):
            return child.wait(), True
        time.sleep(.02)
    if _group_exists(child.pid):
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    code = child.wait(timeout=grace)
    end = time.monotonic() + grace
    while _group_exists(child.pid) and time.monotonic() < end:
        time.sleep(.02)
    return code, not _group_exists(child.pid)


def _command(descriptor: dict, seconds: int) -> list[str]:
    command = [sys.executable, "-m", "experiments.workshops.spatial_grounding_v1.native_mailbox_receiver",
            "--mailbox-root", descriptor["mailbox_root"], "--identity", descriptor["identity"]["path"],
            "--identity-sha256", descriptor["identity"]["sha256"], "--deadline-seconds", str(seconds),
            "--release-cell-json", descriptor["cell"]["path"], "--release-cell-sha256", descriptor["cell"]["sha256"]]
    identity = _read(Path(descriptor["identity"]["path"]))
    if identity.get("identity_schema") == POD_IDENTITY_SCHEMA:
        command += ["--renderer-gpu-index", str(identity["simulator_renderer_gpu_index"])]
    return command


def _publish_result(lane: Lane, path: Path, metadata: Path, value: dict) -> None:
    _write(metadata / "result.json", value)
    _same_or_create(lane.control / "results" / path.name, {
        "lane_identity_sha256": lane.sha256, "descriptor_sha256": _digest(path), "result": _ref(metadata / "result.json"),
    })


def _run_child(lane: Lane, path: Path, descriptor: dict, identity: dict, root: Path, metadata: Path,
               run_id: str, deadline: float, refresh: Any, popen: Any, environ: Mapping[str, str], grace: float) -> None:
    descriptor_sha = _digest(path)
    claim_path = lane.control / "claims" / path.name
    base = {"schema_version": RESULT_SCHEMA, "lane_identity_sha256": lane.sha256,
            "descriptor_sha256": descriptor_sha, "identity_sha256": _digest(metadata / "identity.json")}
    if claim_path.exists() or (root / "mailbox").exists() or (metadata / "child-start.json").exists():
        _publish_result(lane, path, metadata, {**base, "status": "orphan_blocked_preserve_no_replay",
                                              "error": "existing attempt has no verified terminal owned-child result"})
        raise AdapterError("orphan simulator attempt blocked; coordinator must preserve/reconcile it")
    _write(claim_path, {"lane_identity_sha256": lane.sha256, "descriptor_sha256": descriptor_sha,
                        "run_id": run_id, "supervisor_pid": os.getpid(), "claimed_at_unix_s": time.time()})
    child = None
    started = None
    timed_out = interrupted = False
    code, drained, error = None, False, None
    try:
        _require(not (metadata / "client-failure.json").exists(), "client failed before native launch")
        budget = min(_seconds(descriptor["timeouts"]["attempt"]), _seconds(deadline - time.monotonic()))
        command = _command(descriptor, max(1, math.ceil(budget)))
        child_deadline = time.monotonic() + budget
        with (metadata / "native-child.log").open("xb") as log:
            try:
                child = popen(command, cwd=lane.value["source_root"], env=dict(environ), stdout=log,
                              stderr=subprocess.STDOUT, start_new_session=True, close_fds=True)
                started = {
                    "lane_identity_sha256": lane.sha256, "descriptor_sha256": descriptor_sha, "run_id": run_id,
                    "pid": child.pid, "process_group_id": child.pid, "process_start_identity": _process_start(child.pid),
                    "started_at_unix_s": time.time(), "deadline_seconds": budget, "command": command,
                }
                _write(metadata / "child-start.json", started)
                while child.poll() is None:
                    refresh(root)
                    refresh(metadata)
                    mailbox = root / "mailbox"
                    if mailbox.is_dir():
                        refresh(mailbox)
                        if (mailbox / "requests").is_dir():
                            refresh(mailbox / "requests")
                    _require(not (metadata / "client-failure.json").exists(), "policy client failed; native child must stop")
                    if time.monotonic() >= child_deadline:
                        timed_out = True
                        raise TimeoutError("native lane child deadline elapsed")
                    time.sleep(.05)
                code = child.wait()
                settle_end = min(child_deadline, time.monotonic() + grace)
                while _group_exists(child.pid) and time.monotonic() < settle_end:
                    time.sleep(.02)
                drained = not _group_exists(child.pid)
                _require(drained, "native child exited with live descendants")
            except BaseException:
                interrupted = isinstance(sys.exc_info()[1], (KeyboardInterrupt, InterruptedError))
                if child is not None:
                    code, drained = _drain(child, grace)
                raise
            finally:
                log.flush()
                os.fsync(log.fileno())
        _require(code == 0, f"native receiver exit code {code}")
        for directory in (metadata, root / "mailbox", root / "mailbox/faults", root / "mailbox/responses"):
            refresh(directory)
        _require(not (metadata / "client-failure.json").exists(), "client failure contradicts native exit")
        _require(not any((root / "mailbox/faults").iterdir()), "native receiver has fault evidence")
        receipt = verify_receiver_completion(root / "mailbox", identity)
    except BaseException as exc:
        interrupted = interrupted or isinstance(exc, (KeyboardInterrupt, InterruptedError))
        error = traceback.format_exc()
    finally:
        if child is not None:
            _write(metadata / "child-exit.json", {
                "descriptor_sha256": descriptor_sha, "run_id": run_id, "pid": child.pid,
                "process_start_identity": started["process_start_identity"] if started else None,
                "returncode": code, "group_drained": drained, "timed_out": timed_out, "interrupted": interrupted,
                "finished_at_unix_s": time.time(),
            })
        result = {**base, "status": "failed" if error else "completed", "error": error, "claim": _ref(claim_path),
                  "child_start": _ref(metadata / "child-start.json") if (metadata / "child-start.json").exists() else None,
                  "child_exit": _ref(metadata / "child-exit.json") if child else None,
                  "native_log": _ref(metadata / "native-child.log") if (metadata / "native-child.log").exists() else None}
        if error is None:
            result.update(receiver_completion=_ref(root / "mailbox/receiver_complete.json"),
                          close_response=_ref(root / "mailbox/responses" / f"{receipt['close_command_id']:04d}-close.json"))
        _publish_result(lane, path, metadata, result)
    if error:
        raise AdapterError(f"native simulator attempt failed without replay; see {metadata / 'result.json'}")


def supervise(path: Path, sha256: str, deadline_seconds: float, *, metadata_refresh: Any = None,
              popen: Any = subprocess.Popen, environ: Mapping[str, str] | None = None, terminate_grace_seconds: float = 30) -> None:
    """Test seams can inject CPU subprocesses/refresh; the CLI cannot."""
    env = dict(os.environ if environ is None else environ)
    deadline = time.monotonic() + _seconds(deadline_seconds)
    lane = load_lane(path, sha256, "simulator", env)
    grace = _seconds(terminate_grace_seconds)
    refresh = DirectoryRefresher() if metadata_refresh is None else metadata_refresh
    _control(lane)
    if lane.value.get("schema_version") == POD_SIMULATOR_SCHEMA:
        guardian = _read(Path(lane.value["simulator_supervisor_identity_receipt"]["path"]))
        expiry = datetime.fromisoformat(guardian["deadline_utc"].replace("Z", "+00:00")).timestamp()
        deadline = min(deadline, time.monotonic() + _seconds(expiry - time.time()))
    with ExitStack() as lifetime:
        locks = [lane.control / "supervisor.lock"]
        if lane.value.get("schema_version") == POD_SIMULATOR_SCHEMA:
            root = Path(lane.value["cohort_root"]) / "locks" / "existing-pod-simulators"
            root.mkdir(parents=True, exist_ok=True)
            locks.append(root / f"{lane.value['simulator_gpu_uuid']}.lock")
            locks.append(root / f"renderer-{lane.value['simulator_pod_uid']}-0.lock")
        for lock_path in locks:
            lock = lifetime.enter_context(lock_path.open("a+b"))
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise AdapterError(f"simulator lane/GPU/renderer already has an in-flight supervisor: {lock_path.name}") from exc
        run_id = uuid.uuid4().hex
        run_root = lane.control / "runs" / run_id
        run_root.mkdir()
        _write(run_root / "start.json", {"lane_identity_sha256": lane.sha256, "pid": os.getpid(),
                                       "started_at_unix_s": time.time(), "deadline_seconds": deadline_seconds})
        completed: dict[Path, str] = {}
        try:
            while True:
                _require(time.monotonic() < deadline, "simulator lane deadline elapsed without bound stop")
                refresh(lane.control / "requests")
                requests = sorted((lane.control / "requests").glob("*.json"))
                _require(set(completed).issubset(requests), "completed lane descriptor disappeared")
                for request in requests:
                    if request in completed:
                        _require(_digest(request) == completed[request], "completed descriptor changed")
                        continue
                    descriptor, identity, root, metadata = read_descriptor(request, lane)
                    refresh(metadata)
                    if (metadata / "result.json").exists():
                        _result(metadata, request, lane, identity)
                        _same_or_create(lane.control / "results" / request.name, {
                            "lane_identity_sha256": lane.sha256, "descriptor_sha256": _digest(request),
                            "result": _ref(metadata / "result.json"),
                        })
                        completed[request] = _digest(request)
                        continue
                    _run_child(lane, request, descriptor, identity, root, metadata, run_id, deadline, refresh, popen, env, grace)
                    _result(metadata, request, lane, identity)
                    completed[request] = _digest(request)
                if _stop_requested(lane, refresh):
                    _write(run_root / "stopped.json", {"lane_identity_sha256": lane.sha256, "stop": _ref(lane.control / "stop.json"),
                                                      "finished_at_unix_s": time.time()})
                    return
                time.sleep(.1)
        except BaseException:
            _write(run_root / "failure.json", {"lane_identity_sha256": lane.sha256,
                                              "traceback": traceback.format_exc(), "finished_at_unix_s": time.time()})
            raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--lane-identity", type=Path, required=True)
    parser.add_argument("--lane-identity-sha256", required=True)
    parser.add_argument("--deadline-seconds", type=float, required=True)
    args = parser.parse_args()

    stopping = False

    def interrupted(signum: int, _frame: Any) -> None:
        nonlocal stopping
        if not stopping:
            stopping = True
            raise InterruptedError(f"simulator lane received signal {signum}")

    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    supervise(args.lane_identity, args.lane_identity_sha256, args.deadline_seconds)


if __name__ == "__main__":
    main()
