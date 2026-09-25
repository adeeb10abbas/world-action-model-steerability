"""Durable partition progression using the existing immutable release/worker path."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any, Mapping
import uuid

from .contract import (
    ContractError, STAGE_EPISODES, load_json, load_release, sha256_file,
    verify_completion_pointer,
)
from .recorder import atomic_json, request_fleet_hold, utc_now
from .release import create_release

MODELS = ("N3", "E3", "F3")
FAMILIES = ("LAT", "HEIGHT", "DIST")
STAGES = ("P", "D", "C")
QUEUE_SHA256 = "07a2bd6c1893e7662db0c12c01843c20d743bfeb4cb1b506f238a37ae19e068a"


def reference(path: Path) -> dict[str, Any]:
    path = path.resolve(strict=True)
    return {"path": str(path), "sha256": sha256_file(path), "bytes": path.stat().st_size}


def read_reference(value: Mapping[str, Any]) -> dict[str, Any]:
    path = Path(value["path"])
    if not path.is_absolute() or sha256_file(path) != value["sha256"]:
        raise ContractError("lane input reference is relative, absent, or changed")
    return load_json(path, "lane input")


def load_plan(path: Path, digest: str) -> dict[str, Any]:
    value = read_reference({"path": str(path), "sha256": digest})
    if value.get("schema") != "sgw-01-study-lane-plan-v1" or value.get("model") not in MODELS:
        raise ContractError("invalid study lane plan")
    if not re.fullmatch(r"[a-zA-Z0-9-]+", value.get("lane_id", "")):
        raise ContractError("invalid lane identifier")
    source, cohort = Path(value["source_root"]), Path(value["cohort_root"])
    if (not source.is_absolute() or not cohort.is_absolute() or not cohort.is_dir()
            or cohort.is_relative_to(source) or Path.cwd().resolve() != source.resolve()):
        raise ContractError("lane must run from its source with an external persistent cohort")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
    dirty = subprocess.check_output(["git", "status", "--porcelain"], cwd=source, text=True)
    if head != value["source_commit"] or dirty:
        raise ContractError("lane source must be the exact clean committed checkout")
    inputs = value["inputs"]
    if set(inputs) != {"protocol", "prompts", "queue", "fixtures", "binding", "allocation"}:
        raise ContractError("lane plan input set differs")
    for ref in inputs.values():
        if not Path(ref["path"]).is_absolute() or sha256_file(Path(ref["path"])) != ref["sha256"]:
            raise ContractError("lane plan input hash differs")
    if inputs["queue"]["sha256"] != QUEUE_SHA256:
        raise ContractError("lane requires the frozen 1566-cell queue")
    binding = read_reference(inputs["binding"])
    if (binding.get("source_root") != str(source) or binding.get("persistent_study_root") != str(cohort)
            or binding.get("source_commit") != head
            or binding.get("allow_parallel_existing_pod_lanes") is not True
            or binding.get("allow_operational_receipt_refresh") is not True):
        raise ContractError("lane binding differs from its code/cohort or lacks explicit Pod admission opt-in")
    interpreter = Path(value["model_interpreter"])
    if not interpreter.is_absolute() or not interpreter.is_file():
        raise ContractError("lane requires its existing pinned model interpreter")
    expected = {f"{family}-{stage}" for family in FAMILIES for stage in STAGES}
    assigned = value.get("partitions")
    if (not isinstance(assigned, list) or not assigned or len(set(assigned)) != len(assigned)
            or not set(assigned).issubset(expected)):
        raise ContractError("lane assignments must be distinct whole registered partitions")
    environment = value.get("runtime_environment")
    if (not isinstance(environment, dict)
            or any(not isinstance(k, str) or not isinstance(v, str) for k, v in environment.items())):
        raise ContractError("runtime environment must be explicit string pairs")
    if (type(value.get("policy_port")) is not int or not 1024 <= value["policy_port"] <= 65535
            or type(value.get("pod_gpu_count")) is not int or not 1 <= value["pod_gpu_count"] <= 4
            or not isinstance(value.get("gpu_uuid"), str) or not value["gpu_uuid"].startswith("GPU-")):
        raise ContractError("lane lacks its exact endpoint and physical GPU allocation")
    revision = value.get("release_revision", "")
    if not isinstance(revision, str) or (revision and re.fullmatch(r"[a-z][a-z0-9]{0,15}", revision) is None):
        raise ContractError("release revision must be an explicit short alphanumeric identifier")
    value["hold_on_technical_invalid"] = binding.get("hold_on_technical_invalid") is True
    return value


def release_path(cohort: Path, model: str, family: str, stage: str, revision: str = "") -> Path:
    prefix = f"release-{revision}" if revision else "release"
    return cohort / f"{prefix}-{model}-{family}-{stage}"


def assert_replacement_uncompleted(cohort: Path, model: str, family: str, stage: str) -> None:
    prior_paths = list(cohort.glob(f"release-*-{model}-{family}-{stage}"))
    original = release_path(cohort, model, family, stage)
    if original.exists():
        prior_paths.append(original)
    for prior_path in prior_paths:
        prior = load_release(prior_path)
        for cell in prior.partition(model, family, stage):
            if (cohort / "cells" / f"{cell.cell_id}.complete.json").exists():
                raise ContractError("replacement release cannot replay an already completed cell")
            for path in (cohort / "attempts" / cell.cell_id).glob("*/manifest.json"):
                manifest = load_json(path, "prior attempt manifest")
                if manifest.get("result", {}).get("status") in {"valid_success", "valid_model_failure", "censored"}:
                    raise ContractError("prior valid attempt requires completion recovery, not a replacement release")


@contextmanager
def dispatch_claim(cohort: Path, partition: str):
    """Hold across release creation and worker exit; never turn a crash into success."""
    directory = cohort / "dispatch-locks"
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / f"{partition}.lock").open("a+") as stream:
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def verified_partition_summary(path: Path) -> dict[str, Any]:
    release = load_release(path)
    results = []
    for cell in release.cells:
        pointer = path.parent / "cells" / f"{cell.cell_id}.complete.json"
        value = verify_completion_pointer(release, pointer)
        manifest_path = Path(value["manifest_path"])
        manifest = load_json(manifest_path, "completed manifest")
        intent = load_json(manifest_path.parent / "intent.json", "attempt intent")
        result = manifest["result"]
        duration = (
            datetime.fromisoformat(result["completed_at_utc"].replace("Z", "+00:00"))
            - datetime.fromisoformat(intent["created_at_utc"].replace("Z", "+00:00"))
        ).total_seconds()
        if not math.isfinite(duration) or duration <= 0:
            raise ContractError("completed episode has no measurable wall-clock duration")
        results.append({
            "cell_id": cell.cell_id, "pointer": reference(pointer),
            "manifest": reference(manifest_path), "intent": reference(manifest_path.parent / "intent.json"),
            "status": result["status"],
            "bytes": sum(record["bytes"] for record in manifest["artifacts"].values()),
            "seconds": duration,
        })
    return {
        "schema": "sgw-01-partition-completion-v1", "status": "complete",
        "release_id": release.release_id, "release_path": str(path),
        "release_hashes": dict(release.hashes), "episodes": results,
        "completed_at_utc": utc_now(),
    }


def read_partition_summary(cohort: Path, model: str, family: str, stage: str):
    path = cohort / "partition-completions" / f"{model}-{family}-{stage}.json"
    if not path.exists():
        return None
    value = load_json(path, "partition completion")
    release_root = Path(value.get("release_path", ""))
    if not release_root.is_absolute() or release_root.resolve().parent != cohort.resolve():
        raise ContractError("partition completion must reference an immutable release in this cohort")
    release = load_release(release_root)
    cells = release.partition(model, family, stage)
    episodes = value.get("episodes", [])
    if (len(cells) != STAGE_EPISODES[stage] or value.get("status") != "complete" or value.get("release_id") != release.release_id
            or value.get("release_hashes") != dict(release.hashes)
            or len(episodes) != len(cells)
            or {episode["cell_id"] for episode in episodes} != {cell.cell_id for cell in cells}):
        raise ContractError("partition summary differs from immutable released cells")
    # Completion was fully verified once at publication. Barrier polling checks
    # only these small pinned manifests/pointers, never rereads raw videos.
    for episode in episodes:
        pointer = read_reference(episode["pointer"])
        manifest = read_reference(episode["manifest"])
        intent = read_reference(episode["intent"])
        duration = (
            datetime.fromisoformat(manifest["result"]["completed_at_utc"].replace("Z", "+00:00"))
            - datetime.fromisoformat(intent["created_at_utc"].replace("Z", "+00:00"))
        ).total_seconds()
        if (pointer.get("release_id") != release.release_id or pointer.get("cell_id") != episode["cell_id"]
                or manifest.get("cell_id") != episode["cell_id"]
                or episode["status"] != manifest["result"]["status"]
                or episode["bytes"] != sum(record["bytes"] for record in manifest["artifacts"].values())
                or episode["seconds"] != duration):
            raise ContractError("partition summary changed measured result/bytes/timing evidence")
    return value


def stage_ready(cohort: Path, stage: str) -> bool:
    if stage == "P":
        return True
    previous = STAGES[STAGES.index(stage) - 1]
    return all(read_partition_summary(cohort, model, family, previous) is not None
               for model in MODELS for family in FAMILIES)


def measured_pilots(cohort: Path) -> dict[str, Any]:
    summaries = [read_partition_summary(cohort, model, family, "P")
                 for model in MODELS for family in FAMILIES]
    if any(summary is None for summary in summaries):
        raise ContractError("all nine complete pilot partitions are required for measured budgeting")
    episodes = [episode for summary in summaries for episode in summary["episodes"]]
    if len(episodes) != 54 or len({episode["cell_id"] for episode in episodes}) != 54:
        raise ContractError("pilot budget evidence must contain exactly 54 unique completed cells")
    # Native server-side arrays remain outside the attempt manifests. Include
    # the largest measured per-episode pilot operation overhead.
    overheads = []
    for summary in summaries:
        operation = Path(summary["operation"]).resolve(strict=True)
        if not operation.is_relative_to((cohort / "operations").resolve()):
            raise ContractError("pilot operation is outside the persistent cohort")
        total = sum(path.stat().st_size for path in operation.rglob("*") if path.is_file())
        overheads.append(math.ceil(total / len(summary["episodes"])))
    overhead = max(overheads)
    rank = math.ceil(0.95 * len(episodes)) - 1
    return {
        "status": "measured", "episodes": episodes,
        "pilot_p95_episode_bytes": sorted(e["bytes"] for e in episodes)[rank] + overhead,
        "pilot_p95_episode_seconds": sorted(e["seconds"] for e in episodes)[rank],
        "maximum_pilot_operation_bytes_per_episode": overhead,
    }


def receipt_identity(plan: Mapping[str, Any], binding: Mapping[str, Any], release_id: str):
    from .worker import runtime_identity_sha256

    return {
        "release_id": release_id, "source_queue_sha256": QUEUE_SHA256,
        "source_queue_episode_count": 1566, "pvc_name": binding["pvc_name"],
        "pvc_mount_path": binding["pvc_mount_path"],
        "study_root": binding.get("persistent_study_root", binding["source_root"]),
        "runtime_identity_sha256": runtime_identity_sha256(binding),
    }


def prepare_operation(plan: Mapping[str, Any], family: str, stage: str, root: Path):
    binding = read_reference(plan["inputs"]["binding"])
    allocation = read_reference(plan["inputs"]["allocation"])
    supervisor_path = Path(os.environ["SGW01_SUPERVISOR_RECEIPT"])
    supervisor_ref = reference(supervisor_path)
    supervisor = read_reference(supervisor_ref)
    release_id = f"sgw-current-{plan['model']}-{family}-{stage}"
    identity = receipt_identity(plan, binding, release_id)
    idle_path = root / "idle.json"
    subprocess.run([
        sys.executable, "-m", "experiments.workshops.spatial_grounding_v1.gpu_idle_probe",
        "--expected-count", str(plan["pod_gpu_count"]), "--expected-name", plan["gpu_name"],
        "--select-uuid", plan["gpu_uuid"], "--output", str(idle_path),
    ], check=True)
    allocation.update({
        **identity, "gpu_idle_probe_receipt": reference(idle_path),
        "supervisor_identity_receipt": supervisor_ref, "pod_snapshot": plan["pod_receipt"],
        "owner_kind": "Pod", "pod_name": os.environ["POD_NAME"], "pod_uid": os.environ["POD_UID"],
        "selected_gpu_uuid": plan["gpu_uuid"], "gpu_name": plan["gpu_name"],
        "allocated_gpu_count": plan["pod_gpu_count"], "allocated_gpu_uuids": plan["allocated_gpu_uuids"],
        "lane_gpu_count": 1, "reservation_scope": "whole_pod",
        "lane_gpu_hours": supervisor["deadline_seconds"] / 3600,
        "reservation_gpu_hours": plan["pod_gpu_count"] * supervisor["deadline_seconds"] / 3600,
        "deadline_utc": supervisor["deadline_utc"],
    })
    atomic_json(root / "allocation.json", allocation)
    bound_seconds = binding["request_deadline_seconds"] + binding["episode_deadline_seconds"]
    estimated_hours = 1566 * 3 * bound_seconds * 2 / 3600
    budget = {
        **identity, "status": "approved", "model": plan["model"],
        "expires_at_utc": supervisor["deadline_utc"],
        "estimated_remaining_gpu_hours": estimated_hours,
        "estimate_basis": "all1566 cells, three total attempts, policy+simulator, full configured deadlines",
    }
    if stage != "P":
        pilots = measured_pilots(Path(plan["cohort_root"]))
        runtime = {
            **identity, **pilots, "model": "all_models",
            "expires_at_utc": supervisor["deadline_utc"], "max_cell_attempts": 3,
            "request_deadline_seconds": binding["request_deadline_seconds"],
            "episode_deadline_seconds": binding["episode_deadline_seconds"],
            "estimated_remaining_gpu_hours": max(
                estimated_hours, pilots["pilot_p95_episode_seconds"] * 1566 * 3 * 2 / 3600,
            ),
        }
        atomic_json(root / "measured-runtime.json", runtime)
        budget["measured_runtime_receipt"] = reference(root / "measured-runtime.json")
        budget["estimated_remaining_gpu_hours"] = runtime["estimated_remaining_gpu_hours"]
        storage = {
            **identity, "status": "approved", "expires_at_utc": supervisor["deadline_utc"],
            "pilot_p95_episode_bytes": pilots["pilot_p95_episode_bytes"],
            "global_remaining_episode_count": 1566,
            "pilot_evidence": reference(root / "measured-runtime.json"),
        }
        atomic_json(root / "storage.json", storage)
        binding["storage_budget_receipt"] = reference(root / "storage.json")
    atomic_json(root / "budget.json", budget)
    binding["external_allocation_receipt"] = reference(root / "allocation.json")
    binding["resource_budget_receipt"] = reference(root / "budget.json")
    atomic_json(root / "binding.json", binding)
    return binding


def worker_environment(plan: Mapping[str, Any], root: Path) -> dict[str, str]:
    environment = {**os.environ, **plan["runtime_environment"]}
    port = str(plan["policy_port"])
    module = ("nano_wrapper_entrypoint" if plan["model"] == "N3" else "checkpoint_wrapper_entrypoint")
    server = [
        plan["model_interpreter"], "-m", f"experiments.workshops.spatial_grounding_v1.{module}",
    ]
    if plan["model"] != "N3":
        server.append(plan["model"])
    environment.update({
        "MODEL": plan["model"], "USER": "ali", "LOGNAME": "ali",
        "CUDA_VISIBLE_DEVICES": plan["gpu_uuid"],
        "SGW01_POLICY_CUDA_VISIBLE_DEVICES": plan["gpu_uuid"],
        f"SGW01_{plan['model']}_HOST": "127.0.0.1",
        f"SGW01_{plan['model']}_PORT": port,
        "SGW01_NANO_HOST": "127.0.0.1", "SGW01_NANO_PORT": port,
        "SGW01_RUNTIME_RECEIPT": str(root / "runtime" / "launch.json"),
        "SGW01_SERVER_ATTESTATION": str(root / "runtime" / "attestation.json"),
        "SGW01_TRACE_SIDECAR": str(root / "runtime" / "trace.jsonl"),
        "SGW01_FUTURE_DIR": str(root / "runtime" / "futures"),
        "SGW01_SERVER_LOG_DIR": str(root / "runtime" / "logs"),
        "SGW01_NANO_OUTPUT_DIR": str(root / "runtime" / "native"),
        "SGW01_E3_OUTPUT_DIR": str(root / "runtime" / "native"),
        "SGW01_SERVER_ARGV": json.dumps(server),
        "SGW01_RUNTIME_FACTORY": "experiments.workshops.spatial_grounding_v1.runtime:create_runtime",
        "SGW01_ENV_FACTORY": "experiments.workshops.spatial_grounding_v1.remote_simulator_lane:create_environment",
        "SGW01_NANO_BACKEND_FACTORY": "experiments.workshops.spatial_grounding_v1.nano_backend:build_pinned_nano_backend",
    })
    return environment


def stop_remote_lane(plan: Mapping[str, Any]) -> None:
    environment = plan["runtime_environment"]
    digest = environment["SGW01_SIMULATOR_LANE_IDENTITY_SHA256"]
    identity = read_reference({"path": environment["SGW01_SIMULATOR_LANE_IDENTITY"], "sha256": digest})
    if identity["model"] != plan["model"]:
        raise ContractError("cannot stop another model's simulator lane")
    path = Path(identity["control_root"]) / "stop.json"
    value = {
        "schema_version": "sgw-01-simulator-lane-stop-v1",
        "lane_identity_sha256": digest, "model": plan["model"],
    }
    if path.exists():
        if load_json(path, "simulator stop") != value:
            raise ContractError("existing simulator stop belongs to another identity")
        return
    atomic_json(path, value)


def run_one(plan: Mapping[str, Any], family: str, stage: str) -> int:
    cohort = Path(plan["cohort_root"])
    root = cohort / "operations" / f"{plan['lane_id']}-{family}-{stage}-{uuid.uuid4().hex}"
    root.mkdir(parents=True, exist_ok=False)
    binding = prepare_operation(plan, family, stage, root)
    revision = plan.get("release_revision", "")
    path = release_path(cohort, plan["model"], family, stage, revision)
    inputs = plan["inputs"]
    if not path.exists():
        if revision:
            assert_replacement_uncompleted(cohort, plan["model"], family, stage)
        create_release(
            output=path, release_id=f"sgw-current-{plan['model']}-{family}-{stage}" + (f"-{revision}" if revision else ""),
            protocol=Path(inputs["protocol"]["path"]), prompts=Path(inputs["prompts"]["path"]),
            planned_queue=Path(inputs["queue"]["path"]), fixtures=Path(inputs["fixtures"]["path"]),
            runtime_binding=root / "binding.json", resource_owner=binding["resource_owner"],
            stage=stage, model=plan["model"], family=family,
        )
    release = load_release(path)
    for key, filename in (("protocol", "protocol.json"), ("prompts", "prompts.json"), ("fixtures", "fixtures.json")):
        if release.hashes[filename] != inputs[key]["sha256"]:
            raise ContractError("existing release differs from the lane's scientific inputs")
    if release.binding["source_commit"] != plan["source_commit"]:
        raise ContractError("resume must retain the original released executable source")
    receipts = {key: binding[key] for key in (
        "external_allocation_receipt", "resource_budget_receipt", "storage_budget_receipt",
    ) if key in binding}
    admission = {
        "schema": "sgw-01-run-admission-v2", "status": "approved",
        "release_id": release.release_id, "release_hashes": dict(release.hashes),
        "model": plan["model"], "family": family, "stage": stage,
        "gpu_name": plan["gpu_name"], "allocated_gpu_count": plan["pod_gpu_count"],
        "selected_gpu_uuid": plan["gpu_uuid"], "resource_owner": binding["resource_owner"],
        "operational_authorization_receipt": binding["operational_authorization_receipt"],
        "receipts": receipts, "owner_kind": "Pod",
        "pod_uid": os.environ["POD_UID"], "pod_name": os.environ["POD_NAME"],
        "job_uid": None, "job_name": None,
        "supervisor_identity_receipt": reference(Path(os.environ["SGW01_SUPERVISOR_RECEIPT"])),
    }
    atomic_json(root / "admission.json", admission)
    environment = worker_environment(plan, root)
    environment["SGW01_RUN_ADMISSION"] = str(root / "admission.json")
    environment["SGW01_RUN_ADMISSION_SHA256"] = sha256_file(root / "admission.json")
    with (root / "worker.log").open("xb", buffering=0) as log:
        completed = subprocess.run([
            sys.executable, "-u", "-m", "experiments.workshops.spatial_grounding_v1.worker",
            "--release", str(path), "--model", plan["model"], "--family", family, "--stage", stage,
            "--resume", "--max-valid-episodes", str(STAGE_EPISODES[stage]), "--max-cell-attempts", "3",
        ], env=environment, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
    atomic_json(root / "exit.json", {"returncode": completed.returncode, "at_utc": utc_now()})
    if completed.returncode != 0:
        return completed.returncode
    summary = verified_partition_summary(path)
    summary["operation"] = str(root)
    atomic_json(cohort / "partition-completions" / f"{plan['model']}-{family}-{stage}.json", summary)
    return 0


def run(plan: Mapping[str, Any]) -> int:
    from .mailbox_visibility import DirectoryRefresher

    cohort = Path(plan["cohort_root"])
    (cohort / "partition-completions").mkdir(parents=True, exist_ok=True)
    refresh = DirectoryRefresher()
    status_path = cohort / "lane-status" / f"{plan['lane_id']}.json"
    while True:
        refresh(cohort)
        if (cohort / "fleet-hold.json").exists():
            stop_remote_lane(plan)
            atomic_json(status_path, {"status": "held_no_new_claims", "at_utc": utc_now(), "model": plan["model"]})
            return 44
        refresh(cohort / "partition-completions")
        remaining = []
        for stage in STAGES:
            for family in FAMILIES:
                if f"{family}-{stage}" not in plan["partitions"]:
                    continue
                if read_partition_summary(cohort, plan["model"], family, stage) is None:
                    remaining.append((family, stage))
        if not remaining:
            stop_remote_lane(plan)
            atomic_json(status_path, {"status": "complete", "at_utc": utc_now(), "model": plan["model"]})
            return 0
        dispatched = False
        for family, stage in remaining:
            refresh(cohort)
            if (cohort / "fleet-hold.json").exists():
                break
            if not stage_ready(cohort, stage):
                continue
            partition = f"{plan['model']}-{family}-{stage}"
            with dispatch_claim(cohort, partition) as acquired:
                if not acquired or read_partition_summary(cohort, plan["model"], family, stage) is not None:
                    continue
                atomic_json(status_path, {"status": "running", "partition": partition, "at_utc": utc_now()})
                result = run_one(plan, family, stage)
                if result != 0:
                    if plan.get("hold_on_technical_invalid") is True:
                        request_fleet_hold(cohort, lane_id=plan["lane_id"], partition=partition,
                                           reason=f"worker exited {result}; no automatic retry")
                    atomic_json(status_path, {
                        "status": "blocked_preserve_no_automatic_retry", "partition": partition,
                        "returncode": result, "at_utc": utc_now(),
                    })
                    return result
                dispatched = True
        if not dispatched:
            atomic_json(status_path, {"status": "waiting_for_stage_or_partition", "at_utc": utc_now()})
            time.sleep(30)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--plan-sha256", required=True)
    args = parser.parse_args()
    plan = load_plan(args.plan, args.plan_sha256)
    try:
        raise SystemExit(run(plan))
    except Exception as exc:
        if plan.get("hold_on_technical_invalid") is True:
            request_fleet_hold(Path(plan["cohort_root"]), lane_id=plan["lane_id"],
                               reason=f"{type(exc).__name__}: {exc}")
        atomic_json(Path(plan["cohort_root"]) / "lane-status" / f"{plan['lane_id']}.json", {
            "status": "failed_preserve_no_automatic_retry", "at_utc": utc_now(),
            "error_type": type(exc).__name__, "error": str(exc),
        })
        raise


if __name__ == "__main__":
    main()
