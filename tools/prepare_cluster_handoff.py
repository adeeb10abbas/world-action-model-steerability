"""Prepare offline SGW partitions; optionally disable a concrete reviewed Job.

This tool performs no network calls, inference, simulator work, or submission.
It does not create release receipts or invent cluster resource identities.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import copy
import csv
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.validate_standalone_sgw import validate

SPEC = ROOT / "experiments/workshops/spatial_grounding_v1/spec"
ENTRYPOINT = "experiments.workshops.spatial_grounding_v1.native_worker_entrypoint"
STAGE_COUNTS = {"P": 6, "D": 24, "C": 144}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def prepare_partitions() -> dict:
    validate(check_imports=False)
    with (SPEC / "planned_cells.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    partitions = []
    for stage, expected_count in STAGE_COUNTS.items():
        for model in ("N3", "D1"):
            for family in ("LAT", "HEIGHT", "DIST"):
                selected = [r for r in rows if (r["stage"], r["model"], r["family"]) == (stage, model, family)]
                require(len(selected) == expected_count, "Partition differs from native worker ceiling")
                grouped: dict[str, list] = defaultdict(list)
                for row in selected:
                    grouped[row["block_id"]].append(row)
                blocks = []
                for block_id, cells in grouped.items():
                    cells = sorted(cells, key=lambda r: int(r["within_block_order"]))
                    require(len(cells) == 6, "A matched block must remain intact")
                    require(len({c["layout_id"] for c in cells}) == 1
                            and len({c["environment_seed"] for c in cells}) == 1
                            and len({c["effective_policy_seed"] for c in cells}) == 1,
                            "Matched block must retain its layout and seeds")
                    blocks.append({"block_id": block_id, "layout_id": cells[0]["layout_id"], "cells": cells})
                partitions.append({
                    "partition_id": f"{model}-{family}-{stage}",
                    "model": model, "family": family, "stage": stage,
                    "status": "PLANNED_NOT_RELEASED", "episode_count": len(selected),
                    "matched_block_count": len(blocks), "blocks": blocks,
                    "native_worker_selection": {
                        "model": model, "family": family, "stage": stage,
                        "max_valid_episodes": expected_count, "max_cell_attempts": 3,
                        "heartbeat_seconds": 60,
                    },
                })
    return {
        "schema": "sgw-offline-cluster-handoff-v1", "study_id": "SGW-01",
        "status": "PLANNING_ONLY_NO_LAUNCH_AUTHORIZED",
        "learned_policy_launch_authorized": False, "execution_location": "cluster_only",
        "release_namespace_policy": {
            "cohort": "proposed_separate_clean_scene_cohort",
            "new_release_namespace_required": True,
            "preserve_original_cell_ids_within_new_namespace": True,
            "reuse_other_cohort_completion_pointers": False,
            "release_created": False,
        },
        "queue_path": str((SPEC / "planned_cells.csv").relative_to(ROOT)),
        "queue_sha256": hashlib.sha256((SPEC / "planned_cells.csv").read_bytes()).hexdigest(),
        "prompt_sha256": hashlib.sha256((SPEC / "prompts.json").read_bytes()).hexdigest(),
        "total_cells": len(rows), "total_matched_blocks": 174, "partition_count": len(partitions),
        "stage_cell_counts": dict(Counter(r["stage"] for r in rows)),
        "partition_unit": "one complete model/family/stage selection; no arbitrary subpartition support",
        "concurrency": "Existing shared-parent worker locks permit one active worker per model. Partition count is not simultaneous worker count.",
        "native_entrypoint": ENTRYPOINT, "partitions": partitions,
    }


def disabled_job(job: dict, partitions: dict) -> tuple[dict, str]:
    """Preserve supplied concrete runtime/resource values; disable all pod creation."""
    require(job.get("apiVersion") == "batch/v1" and job.get("kind") == "Job", "Expected one batch/v1 Job")
    require("${" not in json.dumps(job), "Unresolved template substitutions are not accepted")
    metadata = job.get("metadata", {})
    require(isinstance(metadata.get("namespace"), str) and bool(metadata["namespace"])
            and isinstance(metadata.get("name"), str) and bool(metadata["name"]),
            "Use a concrete reviewed Job name and namespace")
    spec = job.get("spec", {})
    require("status" not in job and "uid" not in metadata and "resourceVersion" not in metadata,
            "Supply a reviewed manifest, not a live API object")
    require(type(spec.get("activeDeadlineSeconds")) is int and spec["activeDeadlineSeconds"] > 0,
            "Reviewed Job needs a finite existing deadline")
    pod = spec.get("template", {}).get("spec", {})
    containers = pod.get("containers", [])
    require(len(containers) == 1 and not pod.get("initContainers"),
            "Only the reviewed single native-worker container is supported")
    container = containers[0]
    require(re.fullmatch(r"[^\s<>]+@sha256:[0-9a-f]{64}", str(container.get("image", ""))) is not None,
            "Use the concrete reviewed image digest")
    command = container.get("command", [])
    require(len(command) == 3 and re.fullmatch(r"python(?:3(?:\.\d+)?)?", Path(command[0]).name) is not None
            and command[1:] == ["-m", ENTRYPOINT],
            "Job must directly invoke the existing native_worker_entrypoint; shell/legacy launchers are unsupported")
    args = container.get("args", [])
    require(isinstance(args, list) and all(isinstance(v, str) for v in args), "Worker arguments must be strings")

    def arg(flag: str) -> str:
        require(args.count(flag) == 1, f"Expected one {flag} argument")
        index = args.index(flag)
        require(index + 1 < len(args) and not args[index + 1].startswith("--"), f"Missing value for {flag}")
        return args[index + 1]

    model, family, stage = (arg(flag) for flag in ("--model", "--family", "--stage"))
    identity = f"{model}-{family}-{stage}"
    selected = next((p for p in partitions["partitions"] if p["partition_id"] == identity), None)
    require(selected is not None, "Job must select a registered complete partition")
    require(arg("--max-valid-episodes") == str(selected["episode_count"])
            and arg("--max-cell-attempts") == "3", "Job ceilings differ from the native partition contract")
    require(Path(arg("--release")).is_absolute(), "Use a concrete absolute release path")
    require(Path(str(container.get("workingDir", ""))).is_absolute(), "Use a concrete absolute source workingDir")
    pvcs = [v for v in pod.get("volumes", []) if "persistentVolumeClaim" in v]
    require(bool(pvcs) and all(v["persistentVolumeClaim"].get("claimName") for v in pvcs),
            "Use the actual reviewed persistent volume claim")
    mounts = {v.get("name") for v in container.get("volumeMounts", [])}
    require(all(v.get("name") in mounts for v in pvcs), "Persistent claims must be mounted by the worker")
    require(pod.get("restartPolicy") == "Never", "Reviewed worker must use restartPolicy Never")
    result = copy.deepcopy(job)
    result["spec"].update(suspend=True, parallelism=0, completions=1, backoffLimit=0)
    annotations = result["metadata"].setdefault("annotations", {})
    annotations["sgw-handoff-state"] = "planning-only-no-launch-authorized"
    annotations["sgw-disabled-controls"] = "suspend=true;parallelism=0"
    return result, identity


def write_handoff(output: Path, reviewed_job: Path | None = None) -> dict:
    partitions = prepare_partitions()
    job, identity = (None, None)
    if reviewed_job is not None:
        job, identity = disabled_job(json.loads(reviewed_job.read_text()), partitions)
    summary = {
        "status": "PLANNING_ONLY_NO_LAUNCH_AUTHORIZED", "model_requests": 0, "simulator_trials": 0,
        "planned_cells": 1044, "matched_blocks": 174, "partitions": 18,
        "suspended_job_generated": job is not None,
        "job_note": ("Supplied concrete manifest copied with suspend=true and parallelism=0; no native qualification asserted."
                     if job is not None else "No concrete reviewed image/PVC/namespace/runtime Job was supplied; no executable or placeholder Job generated."),
    }
    output.mkdir(parents=True, exist_ok=False)
    for name, value in (("partitions.json", partitions), ("preparation.json", summary)):
        (output / name).write_text(json.dumps(value, indent=2) + "\n")
    if job is not None:
        (output / f"job-{identity.lower()}-suspended.json").write_text(json.dumps(job, indent=2) + "\n")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New handoff directory; existing outputs are preserved")
    parser.add_argument("--reviewed-job-json", type=Path, help="Optional concrete native-worker Job; never applied")
    args = parser.parse_args()
    print(json.dumps(write_handoff(args.output, args.reviewed_job_json), indent=2))
