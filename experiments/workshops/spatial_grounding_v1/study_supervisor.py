"""Detach one finite, source-pinned study process tree inside an allocated Pod."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import ctypes
from datetime import datetime, timedelta, timezone
import os
import fcntl
from pathlib import Path
import signal
import subprocess
import sys
import time
from typing import Any
import uuid

from .contract import ContractError, sha256_file
from .recorder import atomic_json, utc_now
from .study_lane import read_reference, reference

STOP = False


def sample_memory(previous_peak: int = 0, root: Path = Path("/sys/fs/cgroup")) -> dict[str, Any]:
    current = int((root / "memory.current").read_text().strip())
    maximum = (root / "memory.max").read_text().strip()
    events = dict(line.split() for line in (root / "memory.events").read_text().splitlines())
    peak_path = root / "memory.peak"
    return {
        "current_bytes": current, "limit_bytes": None if maximum == "max" else int(maximum),
        "sampled_peak_bytes": max(previous_peak, current), "sampling_interval_seconds": 0.2,
        "kernel_peak_bytes": int(peak_path.read_text().strip()) if peak_path.exists() else None,
        "events": {key: int(value) for key, value in events.items()},
    }


def process_info(pid: int, proc: Path = Path("/proc")) -> dict[str, Any]:
    from .worker import _supervisor_process

    return _supervisor_process(pid, proc)


def descendants(parent: int, proc: Path = Path("/proc")) -> dict[int, str]:
    processes = {}
    for path in proc.iterdir():
        if not path.name.isdigit():
            continue
        try:
            fields = (path / "stat").read_text().rsplit(") ", 1)[1].split()
        except FileNotFoundError:
            continue
        processes[int(path.name)] = (int(fields[1]), fields[19], fields[0])
    owned = {parent}
    while True:
        found = {pid for pid, (ppid, _, _) in processes.items() if ppid in owned}
        if found.issubset(owned):
            break
        owned |= found
    return {pid: processes[pid][1] for pid in owned - {parent}
            if processes[pid][2] != "Z"}


def signal_owned(processes: dict[int, str], signum: int) -> None:
    for pid, start in processes.items():
        try:
            if process_info(pid)["process_start_identity"] == start:
                os.kill(pid, signum)
        except ProcessLookupError:
            continue
        except FileNotFoundError:
            continue


def stop_tree(child: subprocess.Popen, *, grace: float = 180) -> None:
    deadline = time.monotonic() + grace
    known = descendants(os.getpid())
    signal_owned(known, signal.SIGTERM)
    while time.monotonic() < deadline:
        child.poll()
        current = descendants(os.getpid())
        if not current:
            break
        new = {pid: start for pid, start in current.items() if known.get(pid) != start}
        signal_owned(new, signal.SIGTERM)
        known.update(new)
        time.sleep(0.2)
    signal_owned(descendants(os.getpid()), signal.SIGKILL)
    child.wait(timeout=30)
    deadline = time.monotonic() + 30
    while descendants(os.getpid()) and time.monotonic() < deadline:
        time.sleep(0.1)
    if descendants(os.getpid()):
        raise RuntimeError("owned descendants remain after bounded shutdown")
    while True:
        try:
            pid, _ = os.waitpid(-1, os.WNOHANG)
        except ChildProcessError:
            break
        if pid == 0:
            break


def _stop(_signum, _frame) -> None:
    global STOP
    STOP = True


def validate_launch(plan: dict[str, Any]) -> None:
    source = Path(plan["source_root"]).resolve(strict=True)
    if source != Path(__file__).resolve().parents[3] or Path.cwd().resolve() != source:
        raise ContractError("supervisor is outside the pinned source")
    if subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip() != plan["source_commit"]:
        raise ContractError("supervisor source commit differs")
    if subprocess.check_output(["git", "status", "--porcelain"], text=True):
        raise ContractError("supervisor requires a clean committed source checkout")
    if os.getuid() != 816149040 or os.getgid() != 2518800:
        raise ContractError("supervisor UID/GID differs from the authorized PVC owner")
    pod = read_reference(plan["pod_receipt"])
    if (pod["metadata"]["name"] != plan["pod_name"] or pod["metadata"]["uid"] != plan["pod_uid"]
            or os.environ.get("HOSTNAME") != plan["pod_name"]
            or pod["metadata"].get("ownerReferences")
            or pod["status"]["phase"] != "Running"):
        raise ContractError("supervisor requires the inspected existing bare Pod identity")
    containers = pod["spec"]["containers"]
    if len(containers) != 1 or str(containers[0]["resources"]["limits"].get("nvidia.com/gpu")) != str(plan["pod_gpu_count"]):
        raise ContractError("supervisor visible GPU count differs from the actual Pod allocation")
    volumes = {v["name"] for v in pod["spec"]["volumes"]
               if v.get("persistentVolumeClaim", {}).get("claimName") == "211247-prod-pvc"}
    if not any(v["name"] in volumes and v["mountPath"] == "/data" for v in containers[0]["volumeMounts"]):
        raise ContractError("authorized persistent PVC is not mounted at /data")
    if not Path(plan["cohort_root"]).resolve(strict=True).is_relative_to("/data/users/ali/sgw-01"):
        raise ContractError("study outputs must remain in the authorized persistent study root")


@contextmanager
def simulator_gpu_lease(plan, role):
    if role != "simulator":
        yield
        return
    root = Path(plan["cohort_root"]) / "locks" / "existing-pod-lanes"
    root.mkdir(parents=True, exist_ok=True)
    with (root / f"gpu-{plan['gpu_uuid']}.lock").open("a+") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def run(args) -> int:
    plan = read_reference({"path": str(args.plan), "sha256": args.plan_sha256})
    validate_launch(plan)
    if not args.run_root.resolve().is_relative_to(Path(plan["cohort_root"]).resolve()):
        raise ContractError("supervisor receipt/log root must remain inside the study cohort")
    with simulator_gpu_lease(plan, args.role):
        return run_owned(args, plan)


def run_owned(args, plan) -> int:
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER retains orphaned owned servers.
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))
    for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(signum, _stop)
    info = process_info(os.getpid())
    started = datetime.fromtimestamp(info["started_at_unix"], timezone.utc)
    deadline = started + timedelta(seconds=args.seconds)
    entry = reference(Path(__file__))
    receipt = {
        "schema": "sgw-01-existing-pod-supervisor-v1", "supervisor_id": args.supervisor_id,
        "pid": os.getpid(), "process_start_identity": info["process_start_identity"],
        "command": info["command"], "source_root": plan["source_root"],
        "source_commit": plan["source_commit"], "pod_name": plan["pod_name"], "pod_uid": plan["pod_uid"],
        "entrypoint": {"path": entry["path"], "sha256": entry["sha256"]},
        "started_at_utc": started.isoformat(), "deadline_utc": deadline.isoformat(),
        "deadline_seconds": args.seconds, "role": args.role, "gpu_uuid": plan["gpu_uuid"],
        "plan": {"path": str(args.plan), "sha256": args.plan_sha256},
    }
    start_path = args.run_root / "start.json"
    if start_path.exists():
        raise FileExistsError("supervisor start receipt already exists; do not replay")
    atomic_json(start_path, receipt)
    environment = {**os.environ, **plan["runtime_environment"]}
    for key in ("JOB_UID", "JOB_NAME"):
        environment.pop(key, None)
    environment.update({
        "POD_UID": plan["pod_uid"], "POD_NAME": plan["pod_name"],
        "USER": "ali", "LOGNAME": "ali", "PYTHONUNBUFFERED": "1",
        "CUDA_VISIBLE_DEVICES": plan["gpu_uuid"],
        "SGW01_SUPERVISOR_RECEIPT": str(start_path),
        "SGW01_SUPERVISOR_RECEIPT_SHA256": sha256_file(start_path),
    })
    remaining = int((deadline - datetime.now(timezone.utc)).total_seconds())
    if remaining <= 0:
        raise ContractError("supervisor lifetime already expired")
    if args.role == "policy":
        command = [
            sys.executable, "-m", "experiments.workshops.spatial_grounding_v1.study_lane",
            "--plan", str(args.plan), "--plan-sha256", args.plan_sha256,
        ]
    else:
        idle = args.run_root / "idle.json"
        subprocess.run([
            sys.executable, "-m", "experiments.workshops.spatial_grounding_v1.gpu_idle_probe",
            "--expected-count", str(plan["pod_gpu_count"]), "--expected-name", plan["gpu_name"],
            "--select-uuid", plan["gpu_uuid"], "--output", str(idle),
        ], env=environment, check=True)
        identity = read_reference(plan["lane_identity_template"])
        if (identity["simulator_pod_uid"] != plan["pod_uid"]
                or identity["simulator_pod_name"] != plan["pod_name"]
                or identity["simulator_gpu_uuid"] != plan["gpu_uuid"]
                or identity["source_commit"] != plan["source_commit"]
                or identity["source_root"] != plan["source_root"]):
            raise ContractError("simulator identity template differs from its actual supervisor")
        identity["simulator_supervisor_identity_receipt"] = {
            "path": str(start_path), "sha256": sha256_file(start_path),
        }
        identity["simulator_supervisor_entrypoint"] = receipt["entrypoint"]
        identity_path = args.run_root / "lane-identity.json"
        atomic_json(identity_path, identity)
        identity_ref = {"path": str(identity_path), "sha256": sha256_file(identity_path)}
        atomic_json(args.run_root / "lane-identity-reference.json", identity_ref)
        environment["SGW01_SIMULATOR_LANE_IDENTITY"] = str(identity_path)
        environment["SGW01_SIMULATOR_LANE_IDENTITY_SHA256"] = identity_ref["sha256"]
        command = [
            sys.executable, "-m", "experiments.workshops.spatial_grounding_v1.remote_simulator_lane",
            "--lane-identity", str(identity_path),
            "--lane-identity-sha256", identity_ref["sha256"],
            "--deadline-seconds", str(remaining),
        ]
    child = None
    try:
        with (args.run_root / "child.log").open("xb", buffering=0) as log:
            child = subprocess.Popen(command, env=environment, stdin=subprocess.DEVNULL,
                                     stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            atomic_json(args.run_root / "child-start.json", {
                "pid": child.pid, "command": command,
                "process_start_identity": process_info(child.pid)["process_start_identity"],
            })
            last_heartbeat = 0.0
            memory = sample_memory()
            while child.poll() is None and not STOP and datetime.now(timezone.utc) < deadline:
                memory = sample_memory(memory["sampled_peak_bytes"])
                if time.monotonic() - last_heartbeat >= 60:
                    atomic_json(args.run_root / "heartbeat.json", {
                        "at_utc": utc_now(), "status": "supervising", "child_pid": child.pid,
                        "deadline_utc": receipt["deadline_utc"],
                        "host_memory": memory,
                    })
                    last_heartbeat = time.monotonic()
                time.sleep(0.2)
            code = child.poll()
            leftover = descendants(os.getpid())
            if code is None or leftover:
                stop_tree(child)
                if code is None or code == 0:
                    code = 124 if datetime.now(timezone.utc) >= deadline else 125
            atomic_json(args.run_root / "exit.json", {
                "at_utc": utc_now(), "returncode": code, "child_returncode": child.returncode,
                "interrupted": STOP, "owned_descendants_remaining": descendants(os.getpid()),
                "status": "complete" if code == 0 else "failed_preserve_no_automatic_retry",
                "host_memory": sample_memory(memory["sampled_peak_bytes"]),
            })
            return code
    except BaseException as exc:
        if child is not None:
            stop_tree(child)
        atomic_json(args.run_root / "failure.json", {
            "at_utc": utc_now(), "error_type": type(exc).__name__, "error": str(exc),
        })
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("launch", "run"))
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--plan-sha256", required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--supervisor-id", required=True)
    parser.add_argument("--seconds", type=int, required=True)
    parser.add_argument("--role", choices=("policy", "simulator"), required=True)
    args = parser.parse_args()
    if (str(uuid.UUID(args.supervisor_id)) != args.supervisor_id
            or not 1 <= args.seconds <= 14 * 86400 or not args.run_root.is_absolute()):
        parser.error("require a canonical supervisor UUID, absolute run root, and finite lifetime up to14 days")
    if args.command == "launch":
        plan = read_reference({"path": str(args.plan), "sha256": args.plan_sha256})
        validate_launch(plan)
        if not args.run_root.resolve().is_relative_to(Path(plan["cohort_root"]).resolve()):
            raise ContractError("supervisor receipt/log root must remain inside the study cohort")
        args.run_root.mkdir(parents=True, exist_ok=False)
        with (args.run_root / "supervisor.log").open("xb", buffering=0) as log:
            child = subprocess.Popen([
                sys.executable, "-m", "experiments.workshops.spatial_grounding_v1.study_supervisor",
                "run", "--plan", str(args.plan), "--plan-sha256", args.plan_sha256,
                "--run-root", str(args.run_root), "--supervisor-id", args.supervisor_id,
                "--seconds", str(args.seconds), "--role", args.role,
            ], stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if child.poll() is not None:
                raise RuntimeError(f"detached supervisor exited {child.returncode}; see {args.run_root}")
            if (args.run_root / "child-start.json").exists():
                print(str(args.run_root / "start.json"), flush=True)
                return
            time.sleep(0.1)
        raise TimeoutError(f"supervisor did not publish child start; inspect preserved {args.run_root}")
    raise SystemExit(run(args))


if __name__ == "__main__":
    main()
