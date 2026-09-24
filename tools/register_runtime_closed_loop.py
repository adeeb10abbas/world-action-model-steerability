"""Bind a bounded technical check to current inputs and actual simulator UIDs.

No cluster API, model, simulator or release is invoked. Prepare before creating
the finite simulator Job; bind its identity after reading its actual Job/Pod UIDs.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import uuid

from experiments.workshops.spatial_grounding_v1.paper_engineering import record
from experiments.workshops.spatial_grounding_v1.runtime_closed_loop_check import (
    LIMITS, example, load_identity, load_registration,
)
from experiments.workshops.spatial_grounding_v1.simulator_mailbox import _write


def prepare(*, model: str, materialized: Path, output: Path, authorization: Path) -> dict:
    handoff_path = materialized / "handoff.json"
    handoff = json.loads(handoff_path.read_text())
    authority = json.loads(authorization.read_text())
    if (authority.get("schema_version") != "sgw-current-launch-instruction-v1"
            or authority.get("status") != "approved"
            or authority.get("authorization_source") != "current_user_instruction"
            or model not in authority.get("scope", {}).get("models", [])
            or authority.get("source_protocol_sha256") != handoff["frozen_sources"]["protocol.json"]["sha256"]
            or authority.get("source_queue_sha256") != handoff["frozen_sources"]["planned_cells.csv"]["sha256"]):
        raise ValueError("current user instruction does not bind this model and frozen study")
    cohort = authority.get("scope", {}).get("persistent_cohort_parent")
    if not isinstance(cohort, str) or not Path(cohort).is_absolute() or not output.resolve().is_relative_to(Path(cohort)):
        raise ValueError("qualification output differs from the authorized persistent cohort")
    if output.resolve().is_relative_to(Path(handoff["source_root"]).resolve()):
        raise ValueError("qualification outputs must remain outside the clean source checkout")
    rows = [json.loads(line) for line in (materialized / "bound-cells.jsonl").read_text().splitlines()]
    selected = [row for row in rows if row["model"] == model and row["layout_id"] == "LAT-P01"
                and row["prompt_id"] == "LAT-D-POS"]
    if len(selected) != 1:
        raise ValueError("exactly one frozen direct-positive LAT-P01 cell is required")
    output.mkdir(parents=True, exist_ok=False)
    value = example(model)["registration"]
    value.update(
        qualification_id=output.name, attempt_id=f"{output.name}-{model}-attempt-001",
        cell_id=selected[0]["cell_id"], mailbox_root=str((output / "simulator/mailbox").resolve()),
        materialization=record(handoff_path),
        environment_binding=record(materialized / "environment-binding.json"),
        bound_cells=record(materialized / "bound-cells.jsonl"),
        prompts=record(Path(handoff["frozen_sources"]["prompts.json"]["path"])),
    )
    launch = {key: value[key] for key in ("scope", "qualification_id", "attempt_id", "model", "cell_id", *LIMITS)}
    launch.update(
        schema_version="sgw-01-runtime-check-launch-v1",
        current_user_instruction=record(authorization),
        instruction="Execute the separately bounded live runtime check under the current hash-bound user instruction: "
                    "two static direct-positive requests, at most 64 native absolute actions and two physical resets. "
                    "No study episode, scene revision, scripted goal trial, extra sample or automatic retry.",
    )
    _write(output / "launch-instruction.json", launch)
    value["launch_instruction"] = record(output / "launch-instruction.json")
    path = output / "registration.json"
    _write(path, value)
    result = record(path)
    load_registration(path, result["sha256"])
    _write(output / "registration-record.json", result)
    return result


def bind_identity(*, registration: Path, registration_sha256: str, identity: Path,
                  simulator_job_uid: str, simulator_pod_uid: str) -> dict:
    uuid.UUID(simulator_job_uid)
    uuid.UUID(simulator_pod_uid)
    bound = load_registration(registration, registration_sha256)
    digest_path = identity.with_suffix(".sha256")
    if identity.exists() or digest_path.exists():
        raise FileExistsError("technical identity and readiness digest are immutable")
    value = {key: bound.value[key] for key in ("scope", "qualification_id", "attempt_id", "cell_id")}
    value.update(
        registration_sha256=bound.sha256,
        candidate_sha256=bound.binding_record["candidate_file_sha256"],
        binding_sha256=bound.value["environment_binding"]["sha256"],
        channel_nonce=uuid.uuid4().hex,
        simulator_job_uid=simulator_job_uid, simulator_pod_uid=simulator_pod_uid,
    )
    _write(identity, value)
    result = record(identity)
    load_identity(identity, result["sha256"], bound)
    with digest_path.open("x") as stream:
        stream.write(result["sha256"] + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("prepare")
    prep.add_argument("--model", choices=("N3", "E3", "F3"), required=True)
    prep.add_argument("--materialized", type=Path, required=True)
    prep.add_argument("--output", type=Path, required=True)
    prep.add_argument("--authorization", type=Path, required=True)
    bind = commands.add_parser("bind-identity")
    bind.add_argument("--registration", type=Path, required=True)
    bind.add_argument("--registration-sha256", required=True)
    bind.add_argument("--identity", type=Path, required=True)
    bind.add_argument("--simulator-job-uid", required=True)
    bind.add_argument("--simulator-pod-uid", required=True)
    args = vars(parser.parse_args())
    command = args.pop("command")
    print(json.dumps((prepare if command == "prepare" else bind_identity)(**args), sort_keys=True))


if __name__ == "__main__":
    main()
