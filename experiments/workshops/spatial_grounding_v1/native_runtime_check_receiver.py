"""Native simulator lane for the explicitly registered technical check.

Use --registration PATH --registration-sha256 SHA --identity PATH
--identity-sha256 SHA. Set actual Downward API JOB_UID/POD_UID and the existing
SGW01_ENV_BINDING, SGW01_ENV_BINDING_SHA256, SGW01_SIMULATOR_DEVICE environment.
Initialize AppLauncher once; never use a RELEASED stand-in or arbitrary factory.
The coordinator must also impose a finite process/Job deadline on native hangs.
"""
from __future__ import annotations

import argparse
import importlib.metadata
import math
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys
import time
import traceback
from typing import Any

import numpy as np

from .runtime_closed_loop_check import (
    DISCLAIMER, SCOPE, Registration, append_progress, load_identity, load_registration, remaining,
)
from .simulator_mailbox import MailboxError, MailboxReceiver, _digest, _read, _write

COMPLETION_SCHEMA = "sgw-01-technical-runtime-receiver-completion-v1"


class BoundedEnvironment:
    """Additional attempt limits around the unchanged measured native environment."""
    def __init__(self, environment: Any, root: Path, deadline: float) -> None:
        self.environment, self.root, self.deadline = environment, root, deadline
        self.reset_started = self.reset_completed = self.action_started = self.executed = 0
        self.safety = False
        self.last_time: float | None = None

    def counts(self) -> dict[str, Any]:
        return {
            "physical_resets_started": self.reset_started, "physical_resets_completed": self.reset_completed,
            "action_steps_started": self.action_started, "returned_action_count": self.executed,
            "executed_action_count": self.executed if self.action_started == self.executed else None,
            "safety_terminated": self.safety,
        }

    def progress(self, event: str) -> None:
        append_progress(self.root / "physics-progress.jsonl", {**DISCLAIMER, **self.counts(), "event": event})

    def reset(self) -> Any:
        remaining(self.deadline, 1)
        if self.reset_started >= 2 or self.reset_started != self.reset_completed:
            raise MailboxError("technical receiver permits exactly two non-retried physical resets")
        self.reset_started += 1
        self.progress("physical_reset_started")
        reset = self.environment.reset()
        self.reset_completed += 1
        self.progress("physical_reset_returned")
        stamp = reset.snapshot.get("sim_time")
        if type(stamp) not in (int, float) or not math.isfinite(stamp):
            raise MailboxError("physical reset lacks finite measured sim_time")
        self.last_time = stamp
        return reset

    def step(self, action: Any) -> Any:
        remaining(self.deadline, 1)
        if (self.reset_started != 1 or self.reset_completed != 1 or self.safety
                or self.action_started >= 64 or self.action_started != self.executed):
            raise MailboxError("technical step exceeds the reset/safety/64-action boundary")
        array = np.asarray(action)
        if array.shape != (8,) or not np.isfinite(array).all():
            raise MailboxError("technical absolute action must have finite shape [8]")
        self.action_started += 1
        self.progress("action_step_started")
        result = self.environment.step(array)
        self.executed += 1
        self.safety = bool(result.get("safety_terminated"))
        self.progress("action_step_returned")
        return result

    def check_action_time(self) -> None:
        # Called only after the raw response/arrays have been durably retained.
        stamp = self.environment.snapshot().get("sim_time")
        if (type(stamp) not in (int, float) or not math.isfinite(stamp)
                or not math.isclose(stamp - self.last_time, 1 / 15, rel_tol=0, abs_tol=1e-6)):
            raise MailboxError("native action/frame correspondence is not one measured 15Hz step")
        self.last_time = stamp

    def snapshot(self) -> Any:
        return self.environment.snapshot()

    def render_viewport(self) -> Any:
        return self.environment.render_viewport()

    def policy_observation(self) -> Any:
        return self.environment.policy_observation()

    def close(self) -> None:
        self.environment.close()


class TechnicalMailboxReceiver(MailboxReceiver):
    """Reuse physical evidence transport, but never emit its learned-policy receipt."""
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.environment_closed = False

    def close_environment(self) -> None:
        if not self.environment_close_attempted:
            self.environment_close_attempted = True
            self.environment.close()
            self.environment_closed = True

    def serve_one(self, request_path: Path) -> None:
        try:
            remaining(self.environment.deadline, 1)
            request = _read(request_path)
            command, operation = request.get("command_id"), request.get("operation")
            if (self.closed or type(command) is not int or command != self.last + 1 or command > 67
                    or request.get("identity") != self.identity or request.get("channel_nonce") != self.identity["channel_nonce"]
                    or request.get("schema") != "sgw-01-simulator-mailbox-v1"
                    or operation not in ("reset", "step", "close")
                    or request_path.name != f"{command:04d}-{operation}.json"):
                raise MailboxError("technical mailbox command identity/order/limit differs")
            if operation != "close":
                super().serve_one(request_path)
                if operation == "step":
                    self.environment.check_action_time()
                return
            if (self.environment.reset_started != self.environment.reset_completed
                    or self.environment.reset_completed not in (0, 2)):
                raise MailboxError("started technical check requires both physical resets before close")
            self.close_environment()
            response_path = self.root / "responses" / request_path.name
            _write(response_path, {
                "command_id": command, "identity": self.identity, "status": "ok",
                "data": {"reset": None, "step_result": None},
            })
            self.last, self.closed = command, True
            _write(self.root / "receiver_complete.json", {
                **DISCLAIMER, **self.environment.counts(), "schema": COMPLETION_SCHEMA, "identity": self.identity,
                "status": "closed_with_two_resets" if self.environment.reset_completed == 2 else "aborted_before_physical_reset",
                "close_command_id": command, "command_count": command, "close_response_sha256": _digest(response_path),
            })
        except BaseException as exc:
            fault = self.root / "faults" / f"{request_path.stem}.json"
            if not fault.exists():
                _write(fault, {**DISCLAIMER, "identity": self.identity, "error": str(exc),
                               "error_type": type(exc).__name__, **self.environment.counts()})
            raise


def verify_authority(registration: Registration, identity: dict[str, str]) -> None:
    if (not os.environ.get("JOB_UID") or not os.environ.get("POD_UID")
            or os.environ["JOB_UID"] != identity["simulator_job_uid"]
            or os.environ["POD_UID"] != identity["simulator_pod_uid"]):
        raise MailboxError("technical receiver differs from actual Downward API Job/Pod UIDs")
    from .robolab_jointpos_environment import JointPositionBinding
    binding = JointPositionBinding.load()
    binding.qualification_cell(registration_path=registration.path, registration_sha256=registration.sha256)


def verify_data_completion(root: Path, identity: dict[str, str], expected_actions: int,
                           *, expected_resets: int = 2) -> dict[str, Any]:
    """Check immutable receiver data independently of process-exit witnessing."""
    if (type(expected_actions) is not int or not 0 <= expected_actions <= 64
            or type(expected_resets) is not int or expected_resets not in (0, 2)
            or (expected_resets == 0 and expected_actions != 0)):
        raise MailboxError("only two-reset completion or zero-physics abort can be acknowledged")
    receipt = _read(root / "receiver_complete.json")
    if (any((root / "faults").glob("*.json")) or (root / "receiver_failure.json").exists()
            or (root / "receiver_supervisor_failure.json").exists()
            or receipt.get("schema") != COMPLETION_SCHEMA or receipt.get("attempt_scope") != SCOPE
            or receipt.get("identity") != identity or receipt.get("release_permitted") is not False
            or receipt.get("behavioral_episodes") != 0 or receipt.get("physical_resets_completed") != expected_resets
            or receipt.get("physical_resets_started") != expected_resets
            or receipt.get("status") != ("closed_with_two_resets" if expected_resets == 2 else "aborted_before_physical_reset")
            or receipt.get("executed_action_count") != expected_actions
            or receipt.get("action_steps_started") != expected_actions or not 0 <= expected_actions <= 64
            or receipt.get("command_count") != expected_actions + expected_resets + 1
            or receipt.get("close_command_id") != receipt.get("command_count")):
        raise MailboxError("technical receiver completion/cleanup/count identity differs")
    response = root / "responses" / f"{receipt['close_command_id']:04d}-close.json"
    if _digest(response) != receipt["close_response_sha256"]:
        raise MailboxError("technical receiver close-response hash mismatch")
    packet = _read(response)
    if packet != {"command_id": receipt["close_command_id"], "identity": identity, "status": "ok",
                  "data": {"reset": None, "step_result": None}}:
        raise MailboxError("technical receiver close response differs")
    return receipt


def verify_completion(root: Path, identity: dict[str, str], refresh: Any,
                      deadline: float, expected_actions: int, *, expected_resets: int = 2) -> dict[str, Any]:
    while not (root / "receiver_shutdown.json").is_file():
        remaining(deadline, 1)
        refresh(root)
        if any((root / name).is_file() for name in
               ("receiver_failure.json", "receiver_supervisor_failure.json")):
            raise MailboxError("technical receiver failed; preserve its partial evidence")
        time.sleep(.01)
    shutdown = _read(root / "receiver_shutdown.json")
    if (shutdown.get("identity") != identity or shutdown.get("cleanup_errors") != []
            or shutdown.get("environment_closed") is not True or shutdown.get("app_closed") is not True):
        raise MailboxError("technical receiver cleanup identity differs")
    return verify_data_completion(root, identity, expected_actions, expected_resets=expected_resets)


def run(registration_path: Path, registration_sha256: str, identity_path: Path, identity_sha256: str,
        *, metadata_refresh: Any = None, app_factory: Any = None, environment_factory: Any = None,
        supervised: bool = False) -> dict[str, Any]:
    """Callbacks are CPU-test seams only; the CLI exposes no factory injection."""
    registration = load_registration(registration_path, registration_sha256)
    deadline = time.monotonic() + registration.value["deadline_seconds"]
    root = registration.root
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    for name in ("requests", "responses", "faults"):
        (root / name).mkdir()
    identity = app = environment = receiver = bounded = None
    failure = None
    cleanup_errors: list[str] = []
    environment_closed = app_closed = False
    try:
        identity = load_identity(identity_path, identity_sha256, registration)
        verify_authority(registration, identity)
        if metadata_refresh is None:
            from .mailbox_visibility import DirectoryRefresher
            metadata_refresh = DirectoryRefresher()
        if app_factory is None:
            from isaaclab.app import AppLauncher
            app_factory = lambda: AppLauncher({"headless": True, "enable_cameras": True}).app
        if environment_factory is None:
            from .robolab_jointpos_environment import create_qualification_environment
            environment_factory = create_qualification_environment
        remaining(deadline, 1)
        app = app_factory()
        remaining(deadline, 1)
        environment = environment_factory(registration_path=registration.path, registration_sha256=registration.sha256,
                                          evidence_root=root / "evidence")
        bounded = BoundedEnvironment(environment, root, deadline)
        receiver = TechnicalMailboxReceiver(root=root, identity=identity, environment=bounded)
        versions = {}
        for name in ("numpy", "torch", "isaaclab", "isaacsim"):
            try:
                versions[name] = importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:
                versions[name] = "not_available_as_distribution"
        _write(root / "receiver_ready.json", {
            **DISCLAIMER, "identity": identity, "registration_sha256": registration.sha256,
            "binding": _read(registration.binding_path), "pid": os.getpid(), "python": platform.python_version(),
            "versions": versions, "physical_resets_completed": 0, "executed_action_count": 0,
            "metadata_transport": "DirectoryRefresher STATX_FORCE_SYNC", "app_launcher_count": 1,
        })
        while not receiver.closed:
            remaining(deadline, 1)
            metadata_refresh(root / "requests")
            for request in sorted((root / "requests").glob("*.json")):
                if int(request.name[:4]) > receiver.last:
                    receiver.serve_one(request)
            time.sleep(.01)
    except BaseException:
        failure = traceback.format_exc()
        _write(root / "receiver_failure.json", {
            **DISCLAIMER, "identity": identity, "traceback": failure,
            "counts": bounded.counts() if bounded else None,
        })
    finally:
        try:
            if receiver is not None:
                receiver.close_environment()
                environment_closed = receiver.environment_closed
            elif environment is not None:
                environment.close()
                environment_closed = True
        except BaseException:
            cleanup_errors.append(traceback.format_exc())
        _write(root / "receiver_cleanup_started.json", {
            **DISCLAIMER, "identity": identity, "native_pid": os.getpid(),
            "environment_closed": environment_closed, "cleanup_errors": cleanup_errors,
            "app_close_started": app is not None,
            "counts": bounded.counts() if bounded else None,
        })
        try:
            if app is not None:
                app.close()
                app_closed = True
        except BaseException:
            cleanup_errors.append(traceback.format_exc())
        shutdown_name = "receiver_child_shutdown.json" if supervised else "receiver_shutdown.json"
        _write(root / shutdown_name, {
            **DISCLAIMER, "identity": identity, "environment_closed": environment_closed,
            "app_closed": app_closed, "cleanup_errors": cleanup_errors,
            "counts": bounded.counts() if bounded else None,
        })
    if failure or cleanup_errors:
        raise RuntimeError(f"technical receiver failed; partial evidence retained at {root}")
    return _read(root / "receiver_complete.json")


def witness_owned_exit(root: Path, identity: dict[str, str], *, native_pid: int,
                       exit_code: int, started_at: float, timed_out: bool = False,
                       interrupted: bool = False) -> None:
    """Survive Isaac's normal fast-shutdown exit; exit zero alone is insufficient."""
    _write(root / "receiver_process_exit.json", {
        **DISCLAIMER, "identity": identity, "supervisor_pid": os.getpid(),
        "native_pid": native_pid, "exit_code": exit_code, "timed_out": timed_out,
        "interrupted": interrupted,
        "started_at_unix_s": started_at, "finished_at_unix_s": time.time(),
    })
    try:
        started = _read(root / "receiver_cleanup_started.json")
        counts = started.get("counts")
        if (exit_code != 0 or timed_out or interrupted or started.get("identity") != identity
                or started.get("native_pid") != native_pid or started.get("cleanup_errors") != []
                or started.get("environment_closed") is not True or started.get("app_close_started") is not True
                or not isinstance(counts, dict)):
            raise MailboxError("native exit lacks clean identity-bound pre-close evidence")
        receipt = verify_data_completion(root, identity, counts.get("executed_action_count"),
                                         expected_resets=counts.get("physical_resets_completed"))
        child_shutdown = root / "receiver_child_shutdown.json"
        if child_shutdown.exists():
            shutdown = _read(child_shutdown)
            if (shutdown.get("identity") != identity or shutdown.get("cleanup_errors") != []
                    or shutdown.get("environment_closed") is not True or shutdown.get("app_closed") is not True):
                raise MailboxError("native post-close receipt contradicts clean process exit")
        _write(root / "receiver_shutdown.json", {
            **DISCLAIMER, "identity": identity, "environment_closed": True, "app_closed": True,
            "cleanup_errors": [], "counts": counts,
            "witness": "owned_native_subprocess_exit_after_complete_data_and_pre_close_evidence",
            "app_close_return_observed": child_shutdown.exists(),
            "receiver_complete_sha256": _digest(root / "receiver_complete.json"),
            "receiver_cleanup_started_sha256": _digest(root / "receiver_cleanup_started.json"),
            "receiver_process_exit_sha256": _digest(root / "receiver_process_exit.json"),
            "command_count": receipt["command_count"],
        })
    except BaseException:
        _write(root / "receiver_supervisor_failure.json", {
            **DISCLAIMER, "identity": identity, "traceback": traceback.format_exc(),
            "native_pid": native_pid, "exit_code": exit_code,
        })
        raise


def _stop_owned_child(child: subprocess.Popen) -> int:
    if child.poll() is None:
        try:
            os.killpg(child.pid, signal.SIGTERM)
        except ProcessLookupError:
            return child.wait()
        try:
            return child.wait(timeout=30)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGKILL)
    return child.wait()


def supervise(registration_path: Path, registration_sha256: str,
              identity_path: Path, identity_sha256: str) -> None:
    registration = load_registration(registration_path, registration_sha256)
    identity = load_identity(identity_path, identity_sha256, registration)
    verify_authority(registration, identity)
    if registration.root.exists():
        raise MailboxError("native supervisor requires a new mailbox; attempts cannot be replayed")
    command = [
        sys.executable, "-m", "experiments.workshops.spatial_grounding_v1.native_runtime_check_receiver",
        "--native-child",
        "--registration", str(registration_path), "--registration-sha256", registration_sha256,
        "--identity", str(identity_path), "--identity-sha256", identity_sha256,
    ]
    started_at = time.time()
    child = subprocess.Popen(command, start_new_session=True)
    timed_out = False
    try:
        exit_code = child.wait(timeout=registration.value["deadline_seconds"] + 120)
    except subprocess.TimeoutExpired:
        timed_out = True
        exit_code = _stop_owned_child(child)
    except BaseException:
        exit_code = _stop_owned_child(child)
        witness_owned_exit(registration.root, identity, native_pid=child.pid, exit_code=exit_code,
                           started_at=started_at, interrupted=True)
        raise
    witness_owned_exit(registration.root, identity, native_pid=child.pid, exit_code=exit_code,
                       started_at=started_at, timed_out=timed_out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--registration", type=Path, required=True)
    parser.add_argument("--registration-sha256", required=True)
    parser.add_argument("--identity", type=Path, required=True)
    parser.add_argument("--identity-sha256", required=True)
    parser.add_argument("--native-child", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.native_child:
        run(args.registration, args.registration_sha256, args.identity, args.identity_sha256, supervised=True)
    else:
        def interrupted(signum: int, _frame: Any) -> None:
            raise InterruptedError(f"native supervisor received signal {signum}")

        signal.signal(signal.SIGTERM, interrupted)
        supervise(args.registration, args.registration_sha256, args.identity, args.identity_sha256)


if __name__ == "__main__":
    main()
