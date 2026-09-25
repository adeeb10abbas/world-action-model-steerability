"""Finite CPU-only storage guardian; never launches, retries or scores a policy."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import errno
import fcntl
import json
import os
from pathlib import Path
import re
import signal
import sys
import time

from experiments.workshops.spatial_grounding_v1.contract import sha256_file
from experiments.workshops.spatial_grounding_v1.mailbox_visibility import DirectoryRefresher
from experiments.workshops.spatial_grounding_v1.recorder import atomic_json, request_fleet_hold, utc_now
from experiments.workshops.spatial_grounding_v1.study_supervisor import process_info

MINIMUM_FREE_BYTES = 20 * 1024**4
MINIMUM_FREE_INODES = 5_000_000
HEARTBEAT_MAX_AGE_SECONDS = 120
STOP_REQUESTED = False


def capacity(path: Path) -> dict[str, int]:
    value = os.statvfs(path)
    if value.f_files <= 0 or value.f_favail < 0:
        raise ValueError("filesystem inode capacity is unavailable")
    return {
        "available_bytes": value.f_bavail * value.f_frsize,
        "available_inodes": value.f_favail,
        "total_bytes": value.f_blocks * value.f_frsize,
        "total_inodes": value.f_files,
    }


def capacity_faults(value: dict[str, int]) -> list[str]:
    faults = []
    if value["available_bytes"] < MINIMUM_FREE_BYTES:
        faults.append(f"available bytes {value['available_bytes']} below {MINIMUM_FREE_BYTES}")
    if value["available_inodes"] < MINIMUM_FREE_INODES:
        faults.append(f"available inodes {value['available_inodes']} below {MINIMUM_FREE_INODES}")
    return faults


def owner_faults(cohort: Path, index_path: Path, now: datetime, refresh) -> list[str]:
    refresh(index_path.parent)
    index = json.loads(index_path.read_text())
    roots = index["supervisor_roots"]
    if not isinstance(roots, list) or not roots or len(set(roots)) != len(roots):
        raise ValueError("storage guardian requires a distinct nonempty active-owner index")
    faults = []
    for name in roots:
        root = Path(name)
        if not root.is_absolute() or root.resolve().parent != (cohort / "supervisors").resolve():
            raise ValueError("guardian owner path is outside the cohort supervisors")
        refresh(root)
        terminal = root / "exit.json"
        if terminal.exists():
            value = json.loads(terminal.read_text())
            if value.get("returncode") != 0 or value.get("owned_descendants_remaining") != {}:
                faults.append(f"failed or undrained owner: {root.name}")
            continue
        heartbeat = root / "heartbeat.json"
        if heartbeat.exists():
            value = json.loads(heartbeat.read_text())
            timestamp = value["at_utc"]
        else:
            value = json.loads((root / "start.json").read_text())
            timestamp = value["started_at_utc"]
        age = (now - datetime.fromisoformat(timestamp.replace("Z", "+00:00"))).total_seconds()
        if age < -30 or age > HEARTBEAT_MAX_AGE_SECONDS:
            faults.append(f"owner heartbeat unavailable/stale: {root.name}, age={age:.3f}s")
    return faults


def verify_preserved_hold(cohort: Path, expected_sha256: str) -> None:
    path = cohort / "fleet-hold.json"
    if sha256_file(path) != expected_sha256:
        raise ValueError("preserved user hold changed or disappeared")
    value = json.loads(path.read_text())
    if value.get("phase") != "user_requested_stop_supersede":
        raise ValueError("capacity-only observation requires a user-stopped cohort")


def reserve_hold(path: Path) -> None:
    payload = {
        "schema_version": "sgw-01-fleet-hold-v1", "automatic_technical_invalid_threshold": 1,
        "reserved_at_utc": utc_now(), "phase": "storage_guard_control_write_failure",
        "reason": "Fail-closed storage hold; detailed hold publication failed. Inspect the guardian log.",
    }
    with path.open("xb") as stream:
        stream.write(json.dumps(payload, sort_keys=True).encode().ljust(16 * 1024, b" "))
        stream.flush()
        os.fsync(stream.fileno())


def publish_hold(cohort: Path, reserve: Path, **details) -> str:
    try:
        request_fleet_hold(cohort, phase="storage_capacity_guard", **details)
        return "ordinary_first_cause"
    except OSError as exc:
        if exc.errno not in {errno.EDQUOT, errno.ENOSPC}:
            raise
        # Reuse an allocated inode when a quota prevents a new control-file write.
        try:
            os.link(reserve, cohort / "fleet-hold.json")
        except FileExistsError:
            pass
        print(f"Hold publication hit {exc}; retained reserved-inode hold or existing hold", file=sys.stderr, flush=True)
        return "reserved_inode_or_existing_hold"


def _stop(_signum, _frame) -> None:
    global STOP_REQUESTED
    STOP_REQUESTED = True


def run(args) -> int:
    cohort = args.cohort.resolve(strict=True)
    root = args.run_root.resolve()
    preserved_hold = getattr(args, "preserved_hold_sha256", None)
    if root.parent != (cohort / "storage-guard").resolve() or not args.owners_index.resolve().is_relative_to(cohort):
        raise ValueError("guardian state and owner index must stay inside its cohort")
    if sha256_file(Path(__file__)) != args.implementation_sha256:
        raise ValueError("guardian implementation differs from the operator-pinned source")
    if preserved_hold is not None:
        verify_preserved_hold(cohort, preserved_hold)
    root.mkdir(parents=True, exist_ok=False)
    lock_path = cohort / "locks" / "storage-guardian.lock"
    with lock_path.open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        reserve = root / "hold-reserve.json"
        reserve_hold(reserve)
        info = process_info(os.getpid())
        atomic_json(root / "start.json", {
            **info, "pid": os.getpid(), "started_at_utc": utc_now(),
            "deadline_seconds": args.seconds, "poll_seconds": args.poll_seconds,
            "minimum_free_bytes": MINIMUM_FREE_BYTES, "minimum_free_inodes": MINIMUM_FREE_INODES,
            "operator_pinned_source_commit": args.source_commit,
            "implementation_sha256": args.implementation_sha256,
            "owners_index": str(args.owners_index), "cohort_root": str(cohort),
            "reserved_hold": str(reserve),
            "preserved_hold_sha256": preserved_hold,
            "observation_scope": "preserved_cohort_capacity_only" if preserved_hold else "active_owners_and_capacity",
        })
        refresh = DirectoryRefresher()
        deadline = time.monotonic() + args.seconds
        status, code = "guardian_failed_unclassified", 1
        try:
            while not STOP_REQUESTED:
                refresh(cohort)
                if preserved_hold is not None:
                    verify_preserved_hold(cohort, preserved_hold)
                elif (cohort / "fleet-hold.json").exists():
                    status, code = "existing_fleet_hold_preserved", 0
                    break
                observed = capacity(cohort)
                faults = capacity_faults(observed)
                if preserved_hold is None:
                    faults.extend(owner_faults(cohort, args.owners_index, datetime.now(timezone.utc), refresh))
                if time.monotonic() >= deadline:
                    faults.append("finite storage guardian lifetime expired")
                if faults:
                    if preserved_hold is not None:
                        atomic_json(root / "capacity-fault.json", {
                            "at_utc": utc_now(), "faults": faults, "observed_capacity": observed,
                            "preserved_hold_sha256": preserved_hold,
                        })
                    method = publish_hold(cohort, reserve, reason="; ".join(faults), observed_capacity=observed)
                    status, code = "fleet_held", 44
                    print(json.dumps({"status": status, "faults": faults, "hold_method": method}), flush=True)
                    break
                atomic_json(root / "heartbeat.json", {
                    "status": "watching_preserved_cohort" if preserved_hold else "watching",
                    "at_utc": utc_now(), **observed,
                })
                time.sleep(min(args.poll_seconds, max(0, deadline - time.monotonic())))
            if STOP_REQUESTED:
                status, code = "stopped_by_signal", 0
        except (OSError, ValueError, KeyError, TypeError) as exc:
            publish_hold(cohort, reserve, reason=f"guardian observation/write failed: {type(exc).__name__}: {exc}")
            status, code = "observation_failed_fleet_held", 44
            print(f"{status}: {exc}", file=sys.stderr, flush=True)
        finally:
            if status == "guardian_failed_unclassified":
                publish_hold(cohort, reserve, reason="storage guardian exited unexpectedly; inspect its traceback")
            try:
                atomic_json(root / "exit.json", {"status": status, "returncode": code, "at_utc": utc_now()})
            except OSError as exc:
                publish_hold(cohort, reserve, reason=f"storage guardian exit recording failed: {exc}")
                print(f"Guardian exit receipt unavailable: {exc}", file=sys.stderr, flush=True)
                code = 44
        return code


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cohort", type=Path, required=True)
    parser.add_argument("--owners-index", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--implementation-sha256", required=True)
    parser.add_argument("--preserved-hold-sha256",
                        help="Observe capacity only for this exact, already user-stopped cohort hold")
    parser.add_argument("--seconds", type=int, default=14 * 86400)
    parser.add_argument("--poll-seconds", type=int, default=60)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 14 * 86400 or not 1 <= args.poll_seconds <= 60:
        parser.error("guardian lifetime must be <=14 days and polling interval <=60 seconds")
    if re.fullmatch(r"[0-9a-f]{40}", args.source_commit) is None:
        parser.error("source commit must be a full lowercase Git SHA")
    if args.preserved_hold_sha256 is not None and re.fullmatch(r"[0-9a-f]{64}", args.preserved_hold_sha256) is None:
        parser.error("preserved hold must be a full lowercase SHA-256")
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, _stop)
    raise SystemExit(run(args))


if __name__ == "__main__":
    main()
