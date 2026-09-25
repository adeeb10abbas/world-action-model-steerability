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
from .recorder import atomic_json, fleet_is_held, request_fleet_hold, utc_now
from .release import create_release
from .block_scheduling import MODE as BLOCK_MODE, begin_once, frozen_blocks, registration, selected_cells
from .operator_recovery import (
    INTERNAL_FIELDS, begin_recovery, claim_area, effective_release, execution_identity, load_recovery,
)

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
    _block_registration(value, binding)
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


def _block_registration(plan: Mapping[str, Any], binding: Mapping[str, Any] | None = None):
    binding = read_reference(plan["inputs"]["binding"]) if binding is None else binding
    registered = registration(binding, model=plan["model"], cohort=Path(plan["cohort_root"]),
                              protocol_sha256=plan["inputs"]["protocol"]["sha256"],
                              prompts_sha256=plan["inputs"]["prompts"]["sha256"])
    if registered is None:
        if "scheduling_mode" in plan:
            raise ContractError("plan block mode lacks binding registration")
        return None
    if (plan.get("scheduling_mode") != BLOCK_MODE or plan.get("allowed_models") != ["N3"]
            or plan.get("release_revision") != registered["release_revision"]):
        raise ContractError("plan must explicitly opt into registered r5 N3-only block scheduling")
    environment = plan.get("runtime_environment")
    declared = binding["protocol_runtime"]
    if (not isinstance(environment, Mapping)
            or environment.get("SGW01_CAMERA_REVISION") != declared["camera_configuration"]["revision"]
            or environment.get("SGW01_POLICY_INPUT_REVISION") != declared["policy_input_revision"]):
        raise ContractError("block plan must explicitly propagate its declared camera/input revisions")
    recovery = plan.get("operator_recovery")
    if recovery is not None:
        approval = load_recovery(recovery)
        if (approval["cohort_root"] != plan["cohort_root"]
                or approval["new_source"] != {"root": plan["source_root"], "commit": plan["source_commit"]}):
            raise ContractError("recovery plan differs from its approved cohort/new source")
    return registered


def release_path(cohort: Path, model: str, family: str, stage: str, revision: str = "") -> Path:
    prefix = f"release-{revision}" if revision else "release"
    return cohort / f"{prefix}-{model}-{family}-{stage}"


def partition_release_id(plan: Mapping[str, Any], family: str, stage: str) -> str:
    revision = plan.get("release_revision", "")
    return f"sgw-current-{plan['model']}-{family}-{stage}" + (f"-{revision}" if revision else "")


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
def dispatch_claim(cohort: Path, partition: str, *, wait: bool = False):
    """Hold across release creation and worker exit; never turn a crash into success."""
    directory = cohort / "dispatch-locks"
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / f"{partition}.lock").open("a+") as stream:
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | (0 if wait else fcntl.LOCK_NB))
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def verified_partition_summary(path: Path, block_id: str | None = None) -> dict[str, Any]:
    release = load_release(path)
    results = []
    cells = release.cells
    if block_id is not None:
        first = cells[0]
        cells = selected_cells(release, first.model, first.family, first.stage, block_id)
    for cell in cells:
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


def read_partition_summary(cohort: Path, model: str, family: str, stage: str, block_id: str | None = None):
    path = (cohort / "partition-completions" / f"{model}-{family}-{stage}.json" if block_id is None
            else cohort / "block-completions" / f"{block_id}.json")
    if not path.exists():
        return None
    value = load_json(path, "partition completion")
    release_root = Path(value.get("release_path", ""))
    if not release_root.is_absolute() or release_root.resolve().parent != cohort.resolve():
        raise ContractError("partition completion must reference an immutable release in this cohort")
    release = load_release(release_root)
    cells = (release.partition(model, family, stage) if block_id is None
             else selected_cells(release, model, family, stage, block_id))
    episodes = value.get("episodes", [])
    if (value.get("status") != "complete" or value.get("release_id") != release.release_id
            or (block_id is not None and value.get("block_id") != block_id)
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


def lane_completion_state(plan: Mapping[str, Any]) -> dict[str, Any]:
    """Inspect published, pointer-backed claim units, never infer success from exit.

    A block with missing publication is not resumable merely because some of its
    cells completed. The existing worker deliberately rejects partial blocks.
    """
    from .contract import Cell
    from .mailbox_visibility import DirectoryRefresher
    from .release import _queue_rows

    cohort, model = Path(plan["cohort_root"]), plan["model"]
    block_mode = plan.get("scheduling_mode") == BLOCK_MODE
    _block_registration(plan)
    queue = plan["inputs"]["queue"]
    if queue["sha256"] != QUEUE_SHA256 or sha256_file(Path(queue["path"])) != QUEUE_SHA256:
        raise ContractError("supervisor completion requires the frozen planned queue")
    assigned = plan.get("partitions")
    expected = {f"{family}-{stage}" for family in FAMILIES for stage in STAGES}
    if (model not in MODELS or not isinstance(assigned, list) or not assigned
            or len(set(assigned)) != len(assigned) or not set(assigned).issubset(expected)):
        raise ContractError("supervisor completion requires explicit registered partitions")
    rows = _queue_rows(Path(queue["path"]))
    refresh = DirectoryRefresher()
    refresh(cohort)
    for name in ("cells", "attempts", "block-claims", "block-executions", "block-completions", "partition-completions"):
        if (cohort / name).is_dir():
            refresh(cohort / name)
    completed, owned, pending, unsafe = [], [], [], []
    for partition in assigned:
        family, stage = partition.split("-")
        cells = tuple(Cell(row) for row in rows
                      if (row["model"], row["family"], row["stage"]) == (model, family, stage))
        units = frozen_blocks(cells) if block_mode else {f"{model}-{partition}": cells}
        for unit, unit_cells in units.items():
            claim_path = cohort / "block-claims" / f"{unit}.json"
            expected_root = release_path(cohort, model, family, stage, plan.get("release_revision", ""))
            if block_mode and plan.get("operator_recovery") is not None and expected_root.exists():
                effective = effective_release(load_release(expected_root), plan["operator_recovery"])
                if effective.binding.get("operator_recovery") is not None:
                    claim_path = cohort / claim_area(effective, "dispatch") / f"{unit}.json"
            claim = load_json(claim_path, "block claim") if block_mode and claim_path.exists() else None
            mine = claim is not None and claim.get("lane_id") == plan["lane_id"]
            summary = read_partition_summary(cohort, model, family, stage, unit if block_mode else None)
            if summary is None:
                pending.append(unit)
                attempted = any((cohort / "attempts" / cell.cell_id).exists()
                                or (cohort / "cells" / f"{cell.cell_id}.complete.json").exists()
                                for cell in unit_cells)
                execution = (cohort / "block-executions" / f"{unit}.json").exists()
                if mine or (claim is None and (attempted or execution)):
                    unsafe.append(unit)
                continue
            root = release_path(cohort, model, family, stage, plan.get("release_revision", ""))
            if (summary["release_path"] != str(root)
                    or summary["release_id"] != partition_release_id(plan, family, stage)):
                raise ContractError("completed queue unit belongs to a different planned release")
            release = effective_release(load_release(root), plan.get("operator_recovery"))
            if (release.binding["source_commit"] != plan["source_commit"]
                    or any(release.hashes[filename] != plan["inputs"][key]["sha256"] for key, filename in (
                        ("protocol", "protocol.json"), ("prompts", "prompts.json"), ("fixtures", "fixtures.json")))):
                raise ContractError("completed queue unit differs from the planned source/scientific inputs")
            # Publication already verified raw artifacts. Recheck the small
            # immutable pointer/manifest/result chain rather than reread videos.
            for episode in summary["episodes"]:
                pointer = read_reference(episode["pointer"])
                manifest = read_reference(episode["manifest"])
                if (episode["pointer"]["path"] != str(cohort / "cells" / f"{episode['cell_id']}.complete.json")
                        or pointer.get("manifest_path") != episode["manifest"]["path"]
                        or pointer.get("manifest_sha256") != episode["manifest"]["sha256"]
                        or manifest.get("complete") is not True
                        or manifest.get("release_id") != release.release_id
                        or manifest.get("release_hashes") != dict(release.hashes)
                        or manifest.get("result") != read_reference(pointer["result"])
                        or manifest["result"].get("status") not in {"valid_success", "valid_model_failure", "censored"}):
                    raise ContractError("queue completion lacks its immutable valid completion pointer")
            completed.append(unit)
            if mine or not block_mode:
                owned.append(unit)
    return {
        "complete": not pending, "completed_units": sorted(completed),
        "owned_completed_units": sorted(owned), "pending_units": sorted(pending),
        "unsafe_owned_units": sorted(unsafe), "held": fleet_is_held(cohort),
    }


def stage_ready(cohort: Path, stage: str, model: str | None = None) -> bool:
    if stage == "P":
        return True
    previous = STAGES[STAGES.index(stage) - 1]
    models = MODELS if model is None else (model,)
    stages = (previous,) if model is None else STAGES[:STAGES.index(stage)]
    return all(read_partition_summary(cohort, candidate, family, prior) is not None
               for candidate in models for family in FAMILIES for prior in stages)


def measured_pilots(cohort: Path, model: str | None = None) -> dict[str, Any]:
    models = MODELS if model is None else (model,)
    summaries = [read_partition_summary(cohort, model, family, "P")
                 for model in models for family in FAMILIES]
    if any(summary is None for summary in summaries):
        raise ContractError("all required model/family pilot partitions are needed for measured budgeting")
    episodes = [episode for summary in summaries for episode in summary["episodes"]]
    count = 18 * len(models)
    if len(episodes) != count or len({episode["cell_id"] for episode in episodes}) != count:
        raise ContractError(f"pilot budget evidence must contain exactly {count} unique completed cells")
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
    identity = receipt_identity(plan, binding, partition_release_id(plan, family, stage))
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
        pilots = (measured_pilots(Path(plan["cohort_root"]), plan["model"])
                  if plan.get("scheduling_mode") == BLOCK_MODE else measured_pilots(Path(plan["cohort_root"])))
        runtime = {
            **identity, **pilots, "model": plan["model"] if plan.get("scheduling_mode") == BLOCK_MODE else "all_models",
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
    if plan.get("operator_recovery") is not None:
        environment["SGW01_OPERATOR_RECOVERY"] = plan["operator_recovery"]["path"]
        environment["SGW01_OPERATOR_RECOVERY_SHA256"] = plan["operator_recovery"]["sha256"]
    else:
        environment.pop("SGW01_OPERATOR_RECOVERY", None)
        environment.pop("SGW01_OPERATOR_RECOVERY_SHA256", None)
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


def run_one(plan: Mapping[str, Any], family: str, stage: str, block_id: str | None = None) -> int:
    cohort = Path(plan["cohort_root"])
    revision = plan.get("release_revision", "")
    path = release_path(cohort, plan["model"], family, stage, revision)
    block_mode = plan.get("scheduling_mode") == BLOCK_MODE
    if block_mode:
        _block_registration(plan)
        if block_id not in planned_blocks(plan, family, stage):
            raise ContractError("dispatch must select a whole frozen layout block")
        if fleet_is_held(cohort):
            return 44
        if not stage_ready(cohort, stage, plan["model"]):
            raise ContractError("per-model stage barrier is not complete")
        recovery_release = (effective_release(load_release(path), plan["operator_recovery"])
                            if plan.get("operator_recovery") is not None and path.exists() else None)
        if recovery_release is not None and recovery_release.binding.get("operator_recovery") is not None:
            begin_recovery(recovery_release, block_id, "dispatch", lane_id=plan["lane_id"])
        else:
            begin_once(cohort, "block-claims", block_id, lane_id=plan["lane_id"],
                       release_id=partition_release_id(plan, family, stage))
    elif block_id is not None:
        raise ContractError("block dispatch requires explicit registration")
    root = cohort / "operations" / f"{plan['lane_id']}-{family}-{stage}-{uuid.uuid4().hex}"
    root.mkdir(parents=True, exist_ok=False)
    binding = prepare_operation(plan, family, stage, root)
    inputs = plan["inputs"]
    # Publication is serialized briefly, not for the worker lifetime. Every
    # block keeps the same authoritative full-partition release and cell IDs.
    with dispatch_claim(cohort, f"release-{plan['model']}-{family}-{stage}", wait=True):
        if block_mode:
            from .mailbox_visibility import DirectoryRefresher
            DirectoryRefresher()(cohort)
        if not path.exists():
            if revision:
                assert_replacement_uncompleted(cohort, plan["model"], family, stage)
            create_release(
                output=path, release_id=partition_release_id(plan, family, stage),
                protocol=Path(inputs["protocol"]["path"]), prompts=Path(inputs["prompts"]["path"]),
                planned_queue=Path(inputs["queue"]["path"]), fixtures=Path(inputs["fixtures"]["path"]),
                runtime_binding=root / "binding.json", resource_owner=binding["resource_owner"],
                stage=stage, model=plan["model"], family=family,
            )
        release = effective_release(load_release(path), plan.get("operator_recovery"))
    for key, filename in (("protocol", "protocol.json"), ("prompts", "prompts.json"), ("fixtures", "fixtures.json")):
        if release.hashes[filename] != inputs[key]["sha256"]:
            raise ContractError("existing release differs from the lane's scientific inputs")
    if release.binding["source_commit"] != plan["source_commit"]:
        raise ContractError("resume must retain the original released executable source")
    if block_mode:
        selected_cells(release, plan["model"], family, stage, block_id)
        operational = {"external_allocation_receipt", "resource_budget_receipt", "storage_budget_receipt"} | INTERNAL_FIELDS
        if ({k: v for k, v in release.binding.items() if k not in operational}
                != {k: v for k, v in binding.items() if k not in operational}):
            raise ContractError("parallel block operation changed the immutable runtime binding")
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
    if block_mode:
        admission.update(block_id=block_id, operation_root=str(root),
                         simulator_lane_identity={
                             "path": plan["runtime_environment"]["SGW01_SIMULATOR_LANE_IDENTITY"],
                             "sha256": plan["runtime_environment"]["SGW01_SIMULATOR_LANE_IDENTITY_SHA256"],
                         })
    if release.binding.get("operator_recovery") is not None:
        admission["execution_identity"] = execution_identity(release)
    atomic_json(root / "admission.json", admission)
    environment = worker_environment(plan, root)
    environment["SGW01_RUN_ADMISSION"] = str(root / "admission.json")
    environment["SGW01_RUN_ADMISSION_SHA256"] = sha256_file(root / "admission.json")
    with (root / "worker.log").open("xb", buffering=0) as log:
        completed = subprocess.run([
            sys.executable, "-u", "-m", "experiments.workshops.spatial_grounding_v1.worker",
            "--release", str(path), "--model", plan["model"], "--family", family, "--stage", stage,
            "--resume", "--max-valid-episodes", str(6 if block_mode else STAGE_EPISODES[stage]),
            "--max-cell-attempts", "3", *([] if block_id is None else ["--block-id", block_id]),
        ], env=environment, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
    atomic_json(root / "exit.json", {"returncode": completed.returncode, "at_utc": utc_now()})
    if completed.returncode != 0:
        return completed.returncode
    summary = verified_partition_summary(path, block_id)
    summary["operation"] = str(root)
    if block_mode:
        summary.update(schema="sgw-01-block-completion-v1", block_id=block_id)
        if release.binding.get("operator_recovery") is not None:
            summary["execution_identity"] = execution_identity(release)
        atomic_json(cohort / "block-completions" / f"{block_id}.json", summary)
        publish_block_partition(cohort, release, plan["model"], family, stage)
    else:
        atomic_json(cohort / "partition-completions" / f"{plan['model']}-{family}-{stage}.json", summary)
    return 0


def planned_blocks(plan: Mapping[str, Any], family: str, stage: str) -> tuple[str, ...]:
    from .contract import Cell
    from .release import _queue_rows

    ref = plan["inputs"]["queue"]
    if ref["sha256"] != QUEUE_SHA256 or sha256_file(Path(ref["path"])) != QUEUE_SHA256:
        raise ContractError("block plan queue changed")
    cells = tuple(Cell(row) for row in _queue_rows(Path(ref["path"]))
                  if (row["model"], row["family"], row["stage"]) == (plan["model"], family, stage))
    if len(cells) != STAGE_EPISODES[stage]:
        raise ContractError("block plan requires the whole frozen partition")
    return tuple(frozen_blocks(cells))


def publish_block_partition(cohort, release, model, family, stage):
    from .mailbox_visibility import DirectoryRefresher

    for name in ("block-completions", "partition-completions"):
        (cohort / name).mkdir(parents=True, exist_ok=True)
    with dispatch_claim(cohort, f"publish-{model}-{family}-{stage}", wait=True):
        refresh = DirectoryRefresher()
        refresh(cohort / "block-completions")
        refresh(cohort / "partition-completions")
        if read_partition_summary(cohort, model, family, stage) is not None:
            return
        blocks = frozen_blocks(release.partition(model, family, stage))
        summaries = [read_partition_summary(cohort, model, family, stage, block) for block in blocks]
        if any(summary is None for summary in summaries):
            return
        if any(summary["release_hashes"] != dict(release.hashes) for summary in summaries):
            raise ContractError("block completion releases differ within a partition")
        value = {
            **summaries[0], "schema": "sgw-01-partition-completion-v1",
            "episodes": [episode for summary in summaries for episode in summary["episodes"]],
            "blocks": [reference(cohort / "block-completions" / f"{block}.json") for block in blocks],
            "operations": [summary["operation"] for summary in summaries], "completed_at_utc": utc_now(),
        }
        value.pop("block_id")
        atomic_json(cohort / "partition-completions" / f"{model}-{family}-{stage}.json", value)


def run_blocks(plan: Mapping[str, Any]) -> int:
    from .mailbox_visibility import DirectoryRefresher

    _block_registration(plan)
    cohort, model = Path(plan["cohort_root"]), plan["model"]
    for name in ("block-completions", "partition-completions"):
        (cohort / name).mkdir(parents=True, exist_ok=True)
    refresh = DirectoryRefresher()
    status_path = cohort / "lane-status" / f"{plan['lane_id']}.json"
    assignments = [(family, stage, block) for stage in STAGES for family in FAMILIES
                   if f"{family}-{stage}" in plan["partitions"]
                   for block in planned_blocks(plan, family, stage)]
    while True:
        if fleet_is_held(cohort):
            stop_remote_lane(plan)
            atomic_json(status_path, {"status": "held_no_new_claims", "at_utc": utc_now(), "model": model})
            return 44
        refresh(cohort / "block-completions")
        # Recover publication only, never execution, if a controller died after
        # publishing the last complete block but before the partition summary.
        for family, stage in dict.fromkeys((f, s) for f, s, _ in assignments):
            blocks = [b for f, s, b in assignments if (f, s) == (family, stage)]
            if all((cohort / "block-completions" / f"{block}.json").exists() for block in blocks):
                release = load_release(release_path(cohort, model, family, stage, plan["release_revision"]))
                publish_block_partition(cohort, release, model, family, stage)
        remaining = [(f, s, b) for f, s, b in assignments if read_partition_summary(cohort, model, f, s, b) is None]
        if not remaining:
            stop_remote_lane(plan)
            atomic_json(status_path, {"status": "complete", "at_utc": utc_now(), "model": model})
            return 0
        dispatched = False
        for family, stage, block in remaining:
            if fleet_is_held(cohort):
                break
            refresh(cohort / "partition-completions")
            if not stage_ready(cohort, stage, model):
                continue
            with dispatch_claim(cohort, block) as acquired:
                if not acquired:
                    continue
                refresh(cohort / "block-completions")
                if read_partition_summary(cohort, model, family, stage, block) is not None:
                    continue
                if fleet_is_held(cohort):
                    break
                atomic_json(status_path, {"status": "running", "block_id": block, "at_utc": utc_now()})
                try:
                    result = run_one(plan, family, stage, block)
                except Exception as exc:
                    request_fleet_hold(cohort, lane_id=plan["lane_id"], block_id=block,
                                       reason=f"{type(exc).__name__}: {exc}; no automatic retry")
                    stop_remote_lane(plan)
                    raise
                if result != 0:
                    request_fleet_hold(cohort, lane_id=plan["lane_id"], block_id=block,
                                       reason=f"worker exited {result}; no automatic retry")
                    stop_remote_lane(plan)
                    atomic_json(status_path, {"status": "blocked_preserve_no_automatic_retry",
                                             "block_id": block, "returncode": result, "at_utc": utc_now()})
                    return result
                dispatched = True
        if not dispatched:
            atomic_json(status_path, {"status": "waiting_for_stage_or_block", "at_utc": utc_now()})
            time.sleep(30)


def run(plan: Mapping[str, Any]) -> int:
    from .mailbox_visibility import DirectoryRefresher

    if "scheduling_mode" in plan:
        return run_blocks(plan)
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
                        stop_remote_lane(plan)
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
