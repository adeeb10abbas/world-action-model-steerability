from datetime import datetime, timedelta, timezone
import errno
import json

import pytest

from tools import watch_study_storage as guard


def test_capacity_thresholds_are_strict_and_independent():
    value = {"available_bytes": guard.MINIMUM_FREE_BYTES, "available_inodes": guard.MINIMUM_FREE_INODES}
    assert guard.capacity_faults(value) == []
    assert len(guard.capacity_faults({**value, "available_bytes": value["available_bytes"] - 1})) == 1
    assert len(guard.capacity_faults({**value, "available_inodes": value["available_inodes"] - 1})) == 1
    assert len(guard.capacity_faults({"available_bytes": 0, "available_inodes": 0})) == 2


@pytest.mark.parametrize("failure", [errno.EDQUOT, errno.ENOSPC])
def test_quota_failure_uses_reserved_inode_without_deleting_data(tmp_path, monkeypatch, failure):
    reserve = tmp_path / "reserve.json"
    guard.reserve_hold(reserve)
    original = reserve.read_bytes()

    def fail(*args, **kwargs):
        raise OSError(failure, "synthetic storage exhaustion")

    monkeypatch.setattr(guard, "request_fleet_hold", fail)
    assert guard.publish_hold(tmp_path, reserve, reason="synthetic") == "reserved_inode_or_existing_hold"
    held = tmp_path / "fleet-hold.json"
    assert held.stat().st_ino == reserve.stat().st_ino
    assert held.read_bytes() == original
    assert json.loads(held.read_text())["phase"] == "storage_guard_control_write_failure"


def test_existing_first_cause_is_never_overwritten(tmp_path):
    reserve = tmp_path / "reserve.json"
    guard.reserve_hold(reserve)
    held = tmp_path / "fleet-hold.json"
    held.write_text('{"reason":"first cause"}')
    guard.publish_hold(tmp_path, reserve, reason="later cause")
    assert held.read_text() == '{"reason":"first cause"}'


def test_owner_observation_accepts_clean_exit_and_rejects_stale_or_failed_owner(tmp_path):
    owner = tmp_path / "supervisors" / "owner"
    owner.mkdir(parents=True)
    index = tmp_path / "owners.json"
    index.write_text(json.dumps({"supervisor_roots": [str(owner)]}))
    now = datetime.now(timezone.utc)
    heartbeat = owner / "heartbeat.json"
    heartbeat.write_text(json.dumps({"at_utc": now.isoformat()}))
    assert guard.owner_faults(tmp_path, index, now, lambda path: None) == []
    assert guard.owner_faults(tmp_path, index, now + timedelta(seconds=121), lambda path: None)
    (owner / "exit.json").write_text('{"returncode":0,"owned_descendants_remaining":{}}')
    assert guard.owner_faults(tmp_path, index, now, lambda path: None) == []
    (owner / "exit.json").write_text('{"returncode":44,"owned_descendants_remaining":{}}')
    assert guard.owner_faults(tmp_path, index, now, lambda path: None)


def test_owner_index_cannot_monitor_unrelated_paths(tmp_path):
    index = tmp_path / "owners.json"
    index.write_text(json.dumps({"supervisor_roots": [str(tmp_path / "unrelated")]}))
    with pytest.raises(ValueError, match="outside"):
        guard.owner_faults(tmp_path, index, datetime.now(timezone.utc), lambda path: None)


@pytest.mark.parametrize("unsafe", [False, True])
def test_finite_guard_observes_and_holds_without_any_model_calls(tmp_path, monkeypatch, unsafe):
    from argparse import Namespace
    from pathlib import Path

    (tmp_path / "locks").mkdir()
    owner = tmp_path / "supervisors" / "owner"
    owner.mkdir(parents=True)
    (owner / "heartbeat.json").write_text(json.dumps({"at_utc": datetime.now(timezone.utc).isoformat()}))
    index = tmp_path / "owners.json"
    index.write_text(json.dumps({"supervisor_roots": [str(owner)]}))
    monkeypatch.setattr(guard, "STOP_REQUESTED", False)
    monkeypatch.setattr(guard, "process_info", lambda pid: {"process_start_identity": "synthetic"})
    monkeypatch.setattr(guard, "DirectoryRefresher", lambda: lambda path: None)
    monkeypatch.setattr(guard, "capacity", lambda path: {
        "available_bytes": guard.MINIMUM_FREE_BYTES - int(unsafe),
        "available_inodes": guard.MINIMUM_FREE_INODES,
    })
    monkeypatch.setattr(guard.time, "sleep", lambda seconds: setattr(guard, "STOP_REQUESTED", True))
    root = tmp_path / "storage-guard" / "synthetic"
    args = Namespace(cohort=tmp_path, run_root=root, owners_index=index, seconds=60,
                     poll_seconds=1, source_commit="a" * 40,
                     implementation_sha256=guard.sha256_file(Path(guard.__file__)))
    assert guard.run(args) == (44 if unsafe else 0)
    assert (tmp_path / "fleet-hold.json").exists() is unsafe
    assert json.loads((root / "exit.json").read_text())["status"] == (
        "fleet_held" if unsafe else "stopped_by_signal")
    assert not (tmp_path / "attempts").exists()


@pytest.mark.parametrize("unsafe", [False, True])
def test_preserved_user_hold_monitors_capacity_without_reclassifying_retired_owners(tmp_path, monkeypatch, unsafe):
    from argparse import Namespace
    from pathlib import Path

    (tmp_path / "locks").mkdir()
    hold = tmp_path / "fleet-hold.json"
    hold.write_text('{"phase":"user_requested_stop_supersede","reason":"explicit user stop"}')
    original = hold.read_bytes()
    monkeypatch.setattr(guard, "STOP_REQUESTED", False)
    monkeypatch.setattr(guard, "process_info", lambda pid: {"process_start_identity": "synthetic"})
    monkeypatch.setattr(guard, "DirectoryRefresher", lambda: lambda path: None)
    monkeypatch.setattr(guard, "owner_faults", lambda *args: pytest.fail("retired owners must not be monitored"))
    monkeypatch.setattr(guard, "capacity", lambda path: {
        "available_bytes": guard.MINIMUM_FREE_BYTES - int(unsafe),
        "available_inodes": guard.MINIMUM_FREE_INODES,
    })
    monkeypatch.setattr(guard.time, "sleep", lambda seconds: setattr(guard, "STOP_REQUESTED", True))
    root = tmp_path / "storage-guard" / "preserved"
    args = Namespace(cohort=tmp_path, run_root=root, owners_index=tmp_path / "owners.json",
                     seconds=60, poll_seconds=1, source_commit="a" * 40,
                     implementation_sha256=guard.sha256_file(Path(guard.__file__)),
                     preserved_hold_sha256=guard.sha256_file(hold))
    assert guard.run(args) == (44 if unsafe else 0)
    assert hold.read_bytes() == original
    assert (root / "capacity-fault.json").exists() is unsafe
    if not unsafe:
        assert json.loads((root / "heartbeat.json").read_text())["status"] == "watching_preserved_cohort"
    assert not (tmp_path / "attempts").exists()


def test_preserved_hold_rejects_wrong_phase_and_changed_identity(tmp_path):
    hold = tmp_path / "fleet-hold.json"
    hold.write_text('{"phase":"technical_failure"}')
    with pytest.raises(ValueError, match="user-stopped"):
        guard.verify_preserved_hold(tmp_path, guard.sha256_file(hold))
    hold.write_text('{"phase":"user_requested_stop_supersede"}')
    digest = guard.sha256_file(hold)
    guard.verify_preserved_hold(tmp_path, digest)
    hold.write_text('{"phase":"user_requested_stop_supersede","changed":true}')
    with pytest.raises(ValueError, match="changed"):
        guard.verify_preserved_hold(tmp_path, digest)
