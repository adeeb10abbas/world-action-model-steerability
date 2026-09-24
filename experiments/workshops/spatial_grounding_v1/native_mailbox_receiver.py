"""A40-side entrypoint for one bounded SGW native simulator mailbox attempt."""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import time
import traceback
from typing import Any

from .adapters import AdapterError
from .simulator_mailbox import LEGACY_IDENTITY_FIELDS, POD_IDENTITY_SCHEMA, MailboxReceiver, _write, normalize_identity


GRAPHICS_SOURCES = {
    "isaaclab": "https://github.com/isaac-sim/IsaacLab/blob/46dff135f44683f031edf346e544fcfd8456b2bb/source/isaaclab/isaaclab/app/app_launcher.py#L642-L690",
    "isaacsim": "https://github.com/isaac-sim/IsaacSim/blob/1791e14867bc9f269cf6c430a2bff5a1fb43ca66/source/extensions/isaacsim.simulation_app/isaacsim/simulation_app/simulation_app.py#L65-L71",
}


def _graphics_plan(identity: dict[str, Any], renderer_index: int | None) -> dict[str, Any] | None:
    if identity.get("identity_schema") != POD_IDENTITY_SCHEMA:
        if renderer_index is not None:
            raise AdapterError("renderer pin must be in an explicit hash-bound Pod identity")
        return None
    identity = normalize_identity(identity)
    if (type(renderer_index) is not int or renderer_index != identity["simulator_renderer_gpu_index"]
            or os.environ.get("SGW01_SIMULATOR_DEVICE") != "cuda:0"):
        raise AdapterError("bare simulator requires matching renderer index zero and CUDA-local cuda:0")
    return {
        "schema": "sgw-01-graphics-launch-v1",
        "configured_cuda_gpu_uuid": identity["simulator_gpu_uuid"],
        "renderer_index_space": "kit_vulkan_adapter_index_not_cuda_uuid",
        "physical_gpu_uuid_correspondence": "unqualified",
        "source_references": GRAPHICS_SOURCES,
        # Lab 2.2 overwrites active_gpu/physics_gpu from device. Only the
        # matching zero-index configuration is supported, not a guessed remap.
        "launcher_args": {"headless": True, "enable_cameras": True, "device": "cuda:0",
                          "active_gpu": 0, "physics_gpu": 0, "multi_gpu": False},
    }


def _observe_graphics(app: Any, settings: Any) -> dict[str, Any]:
    config = getattr(app, "config", {})
    resolved = {key: config.get(key) for key in ("active_gpu", "physics_gpu", "multi_gpu")}
    kit = {key: settings.get(path) for key, path in {
        "active_gpu": "/renderer/activeGpu", "physics_gpu": "/physics/cudaDevice",
        "multi_gpu": "/renderer/multiGpu/enabled",
    }.items()}
    valid = all(type(value["active_gpu"]) is int and value["active_gpu"] == 0
                and type(value["physics_gpu"]) is int and value["physics_gpu"] == 0
                and value["multi_gpu"] is False for value in (resolved, kit))
    return {
        "schema": "sgw-01-graphics-observation-v1",
        "status": "configured_settings_verified" if valid else "mismatch",
        "simulation_app_config": resolved, "kit_settings": kit,
        "physical_gpu_uuid_correspondence": "unqualified",
        "graphics_isolation_qualified": False,
    }


def _failure(path: Path, error: BaseException, identity: dict[str, Any] | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        payload = {"error_type": type(error).__name__, "error": str(error), "identity": identity,
                   "traceback": "".join(traceback.format_exception(error))}
        with path.open("x") as stream:
            stream.write(json.dumps(payload, sort_keys=True) + "\n")
            stream.flush()
            import os
            os.fsync(stream.fileno())


def _load_identity(path: Path, expected_sha256: str) -> dict[str, Any]:
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected_sha256:
        raise AdapterError("receiver identity record is absent or hash-mismatched")
    value = json.loads(path.read_text())
    if isinstance(value, dict) and ("identity_schema" in value or value.get("simulator_owner_kind") == "Pod"):
        return normalize_identity(value)
    required = LEGACY_IDENTITY_FIELDS
    if not isinstance(value, dict) or any(not isinstance(value.get(key), str) or not value[key] for key in required):
        raise AdapterError("receiver identity record is incomplete")
    return {key: value[key] for key in required}


def verify_receiver_completion(root: Path, identity: dict[str, Any]) -> dict[str, Any]:
    """Validate a completed learned-policy receiver from a separate process."""
    root = Path(root)
    identity = normalize_identity(identity)
    complete = root / "receiver_complete.json"
    failures = ("receiver_failure.json", "receiver_cleanup_failure.json", "receiver_app_cleanup_failure.json")
    if any((root / name).exists() for name in failures) or any((root / "faults").glob("*.json")) or not complete.is_file():
        raise AdapterError("receiver has no clean completion receipt")
    try:
        receipt = json.loads(complete.read_text())
        if (receipt.get("schema") != "sgw-01-mailbox-receiver-completion-v1"
                or receipt.get("attempt_scope") != "learned_policy_remote_simulator"
                or receipt.get("identity") != identity
                or type(receipt.get("close_command_id")) is not int
                or receipt["close_command_id"] < 1
                or receipt.get("close_command_id") != receipt.get("command_count")):
            raise ValueError("completion fields do not bind the learned attempt")
        response = root / "responses" / f"{receipt['close_command_id']:04d}-close.json"
        if not response.is_file() or hashlib.sha256(response.read_bytes()).hexdigest() != receipt.get("close_response_sha256"):
            raise ValueError("close response is absent or hash-mismatched")
        payload = json.loads(response.read_text())
        if (payload.get("status") != "ok" or payload.get("identity") != identity
                or payload.get("command_id") != receipt["close_command_id"]
                or payload.get("data") != {"reset": None, "step_result": None}):
            raise ValueError("close response is invalid")
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise AdapterError("receiver completion receipt is malformed") from exc
    return receipt


def _load_bound_cell(path: Path, expected_sha256: str, identity: dict[str, Any]) -> dict[str, Any]:
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected_sha256:
        raise AdapterError("receiver release-cell binding is absent or hash-mismatched")
    try:
        cell = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise AdapterError("receiver release-cell JSON is malformed") from exc
    if not isinstance(cell, dict) or any(cell.get(key) != identity[key] for key in
                                        ("cell_id", "candidate_sha256", "binding_sha256")):
        raise AdapterError("receiver identity does not bind the actual release-cell bytes")
    return cell


def _verify_native_authority(cell: dict[str, Any], identity: dict[str, Any]) -> float | None:
    """Bind mailbox labels to the exact native binding before AppLauncher."""
    job_uid, pod_uid = os.environ.get("JOB_UID"), os.environ.get("POD_UID")
    identity = normalize_identity(identity)
    pod_owner = identity.get("identity_schema") == POD_IDENTITY_SCHEMA
    if pod_owner:
        if (pod_uid != identity["simulator_pod_uid"] or os.environ.get("POD_NAME") != identity["simulator_pod_name"]
                or job_uid not in {None, ""} or os.environ.get("JOB_NAME") not in {None, ""}
                or os.environ.get("CUDA_VISIBLE_DEVICES") != identity["simulator_gpu_uuid"]):
            raise AdapterError("receiver mailbox identity differs from actual bare simulator Pod/GPU")
    elif (not isinstance(job_uid, str) or not job_uid or not isinstance(pod_uid, str) or not pod_uid or job_uid == pod_uid
            or identity["simulator_job_uid"] != job_uid or identity["simulator_pod_uid"] != pod_uid):
        raise AdapterError("receiver mailbox identity differs from Downward API Job/pod identity")
    from .robolab_jointpos_environment import JointPositionBinding, _sha256
    binding_path = Path(os.environ.get("SGW01_ENV_BINDING", "")).resolve()
    if not binding_path.is_file():
        raise AdapterError("receiver has no concrete joint-position binding path")
    binding = JointPositionBinding.load()
    if _sha256(binding_path) != identity["binding_sha256"]:
        raise AdapterError("mailbox identity binding hash differs from actual joint-position binding")
    record, _candidate = binding.cell(cell)
    if record.get("candidate_file_sha256") != identity["candidate_sha256"]:
        raise AdapterError("mailbox identity candidate hash differs from actual selected native candidate")
    if pod_owner:
        from .worker import verify_existing_pod_supervisor
        value = json.loads(binding_path.read_text())
        supervisor = verify_existing_pod_supervisor(
            identity["simulator_supervisor_identity_receipt"], source_commit=value["source_commit"],
            entrypoint=identity["simulator_supervisor_entrypoint"],
        )
        if supervisor.get("role") != "simulator":
            raise AdapterError("native simulator must have its own simulator-role supervisor")
        return datetime.fromisoformat(supervisor["deadline_utc"].replace("Z", "+00:00")).timestamp()
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mailbox-root", type=Path, required=True)
    parser.add_argument("--identity", type=Path, required=True)
    parser.add_argument("--identity-sha256", required=True)
    parser.add_argument("--deadline-seconds", type=int, required=True)
    parser.add_argument("--release-cell-json", type=Path, required=True)
    parser.add_argument("--release-cell-sha256", required=True)
    parser.add_argument("--renderer-gpu-index", type=int)
    args = parser.parse_args()
    if args.deadline_seconds <= 0 or args.mailbox_root.exists():
        raise AdapterError("receiver requires a new mailbox root and finite positive deadline")
    identity = _load_identity(args.identity, args.identity_sha256)
    cell = _load_bound_cell(args.release_cell_json, args.release_cell_sha256, identity)
    supervisor_deadline = _verify_native_authority(cell, identity)
    wall_deadline = None
    if supervisor_deadline is not None:
        remaining = min(args.deadline_seconds, supervisor_deadline - time.time())
        if remaining <= 0:
            raise AdapterError("simulator supervisor deadline has expired before native startup")
        wall_deadline = time.monotonic() + remaining
    args.mailbox_root.mkdir(mode=0o700)
    for name in ("requests", "responses", "faults"):
        (args.mailbox_root / name).mkdir()
    environment: Any = None
    receiver: MailboxReceiver | None = None
    app: Any = None
    failure = args.mailbox_root / "receiver_failure.json"
    try:
        graphics = _graphics_plan(identity, args.renderer_gpu_index)
        if graphics is not None:
            _write(args.mailbox_root / "graphics_launch.json", {**graphics, "identity_sha256": args.identity_sha256})
            versions = {name: importlib.metadata.version(name) for name in ("isaaclab", "isaacsim")}
            _write(args.mailbox_root / "graphics_versions.json", versions)
            if versions != {"isaaclab": "2.2.0", "isaacsim": "5.0.0.0"}:
                raise AdapterError("renderer pin requires the registered Isaac Lab 2.2.0 / Isaac Sim 5.0.0.0 runtime")
        # Imports and initialization remain inside the failure guard because
        # AppLauncher cleanup can terminate an otherwise propagating process.
        from isaaclab.app import AppLauncher
        from .robolab_jointpos_environment import create_environment
        app = AppLauncher(graphics["launcher_args"] if graphics else {
            "headless": True, "enable_cameras": True, "device": "cuda:0", "multi_gpu": False,
        }).app
        environment = create_environment(cell=cell, evidence_root=args.mailbox_root / "evidence")
        if graphics is not None:
            import carb.settings
            observed = _observe_graphics(app, carb.settings.get_settings())
            _write(args.mailbox_root / "graphics_observed.json", observed)
            if observed["status"] != "configured_settings_verified":
                raise AdapterError("native renderer settings differ from the bound single-GPU pin")
        receiver = MailboxReceiver(root=args.mailbox_root, identity=identity, environment=environment)
        deadline = wall_deadline if wall_deadline is not None else time.monotonic() + args.deadline_seconds
        while not receiver.closed and time.monotonic() < deadline:
            for request in sorted((args.mailbox_root / "requests").glob("*.json")):
                if int(request.name[:4]) > receiver.last:
                    receiver.serve_one(request)
            time.sleep(.01)
        if not receiver.closed:
            raise AdapterError("receiver deadline elapsed before close")
    except BaseException as exc:
        _failure(failure, exc, identity)
        raise
    finally:
        try:
            if receiver is not None:
                receiver.close_environment()
            elif environment is not None:
                environment.close()
        except BaseException as exc:
            _failure(args.mailbox_root / "receiver_cleanup_failure.json", exc, identity)
            raise
        finally:
            try:
                if app is not None:
                    app.close()
            except BaseException as exc:
                _failure(args.mailbox_root / "receiver_app_cleanup_failure.json", exc, identity)
                raise


if __name__ == "__main__":
    main()
