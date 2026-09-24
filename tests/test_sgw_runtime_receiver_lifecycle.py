"""CPU-only process-exit witnesses; no Isaac, GPU, or model construction."""
import json
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from experiments.workshops.spatial_grounding_v1 import native_runtime_check_receiver as receiver
from experiments.workshops.spatial_grounding_v1.simulator_mailbox import MailboxError, _digest, _read, _write


IDENTITY = {"attempt_id": "cpu-only-abort", "channel_nonce": "unique-cpu-channel"}
COUNTS = {
    "executed_action_count": 0, "returned_action_count": 0, "action_steps_started": 0,
    "physical_resets_started": 0, "physical_resets_completed": 0, "safety_terminated": False,
}


def completion(root):
    root.mkdir()
    for name in ("responses", "requests", "faults"):
        (root / name).mkdir()
    response = root / "responses/0001-close.json"
    _write(response, {"command_id": 1, "identity": IDENTITY, "status": "ok",
                      "data": {"reset": None, "step_result": None}})
    _write(root / "receiver_complete.json", {
        **receiver.DISCLAIMER, **COUNTS, "schema": receiver.COMPLETION_SCHEMA,
        "identity": IDENTITY, "status": "aborted_before_physical_reset",
        "command_count": 1, "close_command_id": 1, "close_response_sha256": _digest(response),
    })


def cleanup_started(root, pid=123):
    _write(root / "receiver_cleanup_started.json", {
        **receiver.DISCLAIMER, "identity": IDENTITY, "native_pid": pid,
        "environment_closed": True, "app_close_started": True,
        "cleanup_errors": [], "counts": COUNTS,
    })


def test_real_fast_exit_is_witnessed_outside_unreachable_native_finally(tmp_path):
    root = tmp_path / "mailbox"
    completion(root)
    script = """
import json, os, sys
from pathlib import Path
from experiments.workshops.spatial_grounding_v1.simulator_mailbox import _write
root = Path(sys.argv[1])
marker = json.loads(sys.argv[2])
marker["native_pid"] = os.getpid()
_write(root / "receiver_cleanup_started.json", marker)
try:
    os._exit(0)
finally:
    _write(root / "unreachable-native-post-close.json", {})
"""
    marker = {"identity": IDENTITY, "environment_closed": True, "app_close_started": True,
              "cleanup_errors": [], "counts": COUNTS}
    started = time.time()
    child = subprocess.Popen([sys.executable, "-c", script, str(root), json.dumps(marker)])
    code = child.wait(timeout=10)
    assert code == 0
    assert not (root / "unreachable-native-post-close.json").exists()
    assert not (root / "receiver_shutdown.json").exists()
    receiver.witness_owned_exit(root, IDENTITY, native_pid=child.pid, exit_code=code, started_at=started)
    shutdown = _read(root / "receiver_shutdown.json")
    assert shutdown["app_close_return_observed"] is False
    assert shutdown["receiver_process_exit_sha256"] == _digest(root / "receiver_process_exit.json")
    checked = receiver.verify_completion(root, IDENTITY, lambda _: None, time.monotonic() + 1,
                                         0, expected_resets=0)
    assert checked["executed_action_count"] == 0
    assert checked["behavioral_episodes"] == 0
    assert checked["study_ready"] is False


@pytest.mark.parametrize("contradiction", (
    "nonzero_exit", "timed_out", "interrupted", "missing_pre_close", "wrong_pid",
    "receiver_failure", "fault", "child_cleanup_error", "corrupt_close_response",
))
def test_exit_zero_cannot_hide_missing_or_contradictory_evidence(tmp_path, contradiction):
    root = tmp_path / "mailbox"
    completion(root)
    if contradiction != "missing_pre_close":
        cleanup_started(root, 456 if contradiction == "wrong_pid" else 123)
    if contradiction == "receiver_failure":
        _write(root / "receiver_failure.json", {"error": "native Python failure before exit zero"})
    if contradiction == "fault":
        _write(root / "faults/0001-close.json", {"error": "close fault"})
    if contradiction == "child_cleanup_error":
        _write(root / "receiver_child_shutdown.json", {
            "identity": IDENTITY, "environment_closed": True,
            "app_closed": False, "cleanup_errors": ["native close raised"],
        })
    if contradiction == "corrupt_close_response":
        (root / "responses/0001-close.json").write_text("{}\n")
    with pytest.raises(MailboxError):
        receiver.witness_owned_exit(
            root, IDENTITY, native_pid=123, exit_code=1 if contradiction == "nonzero_exit" else 0,
            started_at=time.time(), timed_out=contradiction == "timed_out",
            interrupted=contradiction == "interrupted",
        )
    assert not (root / "receiver_shutdown.json").exists()
    assert (root / "receiver_process_exit.json").is_file()
    assert (root / "receiver_supervisor_failure.json").is_file()
    with pytest.raises(MailboxError, match="technical receiver failed"):
        receiver.verify_completion(root, IDENTITY, lambda _: None, time.monotonic() + 1,
                                   0, expected_resets=0)


def test_normal_child_return_is_not_published_before_process_exit(tmp_path):
    root = tmp_path / "mailbox"
    completion(root)
    cleanup_started(root)
    _write(root / "receiver_child_shutdown.json", {
        "identity": IDENTITY, "environment_closed": True,
        "app_closed": True, "cleanup_errors": [],
    })
    assert not (root / "receiver_shutdown.json").exists()
    receiver.witness_owned_exit(root, IDENTITY, native_pid=123, exit_code=0, started_at=time.time())
    assert _read(root / "receiver_shutdown.json")["app_close_return_observed"] is True


def test_supervisor_launches_exactly_one_finite_native_child(monkeypatch, tmp_path):
    root = tmp_path / "mailbox"
    registration = SimpleNamespace(root=root, value={"deadline_seconds": 17})
    monkeypatch.setattr(receiver, "load_registration", lambda *_: registration)
    monkeypatch.setattr(receiver, "load_identity", lambda *_: IDENTITY)
    monkeypatch.setattr(receiver, "verify_authority", lambda *_: None)
    commands, waits = [], []

    class Child:
        pid = 123

        def wait(self, *, timeout):
            waits.append(timeout)
            return 0

    def launch(command, *, start_new_session):
        assert start_new_session is True
        commands.append(command)
        completion(root)
        cleanup_started(root)
        return Child()

    monkeypatch.setattr(receiver.subprocess, "Popen", launch)
    receiver.supervise(tmp_path / "registration.json", "a" * 64, tmp_path / "identity.json", "b" * 64)
    assert len(commands) == 1
    assert commands[0][:4] == [
        sys.executable, "-m",
        "experiments.workshops.spatial_grounding_v1.native_runtime_check_receiver", "--native-child",
    ]
    assert waits == [137]
    assert (root / "receiver_shutdown.json").exists()
    with pytest.raises(MailboxError, match="attempts cannot be replayed"):
        receiver.supervise(tmp_path / "registration.json", "a" * 64, tmp_path / "identity.json", "b" * 64)
    assert len(commands) == 1
