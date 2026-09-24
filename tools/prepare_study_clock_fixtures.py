"""Derive behavior-only release receipts from consumed native evidence; no inference."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from experiments.workshops.spatial_grounding_v1.contract import ContractError, load_json
from experiments.workshops.spatial_grounding_v1.recorder import atomic_json
from experiments.workshops.spatial_grounding_v1.study_lane import reference


def observed_clock(path: Path) -> dict:
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    actions = [row for row in rows if "global_action_index" in row]
    resets = [row for row in rows if "global_action_index" not in row]
    if (len(actions) != 64 or len(resets) != 2
            or any(type(row["global_action_index"]) is not int for row in actions)
            or [row["global_action_index"] for row in actions] != list(range(64))
            or any(type(row["sim_time"]) not in (float, int) or not math.isfinite(row["sim_time"])
                   or abs(row["sim_time"]) > 1e-9 for row in resets)):
        raise ContractError("clock receipt requires the existing two resets and64 unique executed steps")
    errors = []
    for index, row in enumerate(actions):
        before, after = row["before_sim_time"], row["sim_time"]
        if (type(before) not in (float, int) or type(after) not in (float, int)
                or not math.isfinite(before) or not math.isfinite(after)
                or abs(before - (actions[index - 1]["sim_time"] if index else 0)) > 1e-9):
            raise ContractError("recorded executed-action clock is nonfinite or discontinuous")
        errors.append(abs((after - before) - 1 / 15))
    if max(errors) > 1e-6:
        raise ContractError("recorded action transitions do not meet the existing15Hz contract")
    return {
        "observations": reference(path), "verified_action_transitions": 64,
        "verified_resets": 2, "physical_step_dt_s": 1 / 15,
        "maximum_step_dt_error_s": max(errors),
    }


def prepare(*, source: Path, cohort: Path, materialization: Path, output: Path) -> Path:
    if output.exists():
        raise FileExistsError("derived qualification output already exists; never overwrite evidence")
    physical_path = materialization / "physical-fixtures.json"
    physical = load_json(physical_path, "physical fixtures")
    if physical.get("status") != "physical_qualified_runtime_pending" or len(physical.get("layouts", {})) != 87:
        raise ContractError("expected the completed87-layout current physical package")
    handoff = source / "handoff" / "cluster-execution-20260924"
    results, clocks = {}, {}
    for model, suffix in (("N3", "b"), ("E3", "b"), ("F3", "c")):
        fixed_path = handoff / f"{model.lower()}-fixed-input-result.json"
        fixed = load_json(fixed_path, "consumed fixed-input evidence")
        if (fixed.get("model_requests", fixed.get("model_requests_completed")) != 6
                or fixed.get("behavioral_episodes") != 0 or fixed.get("executed_actions") != 0
                or fixed.get("release_permitted") is not False):
            raise ContractError("fixed-input evidence is incomplete or misclassified")
        live_path = handoff / ("n3-live-external-witness.json" if model == "N3" else f"{model.lower()}-live-result.json")
        live = load_json(live_path, "consumed live evidence")
        if model == "N3":
            passed = (live.get("data_plane_contract_verified") is True
                      and live.get("simulator_process_termination_observed") is True
                      and live.get("requests_consumed") == 2
                      and live.get("receiver_executed_actions_verified") == 64
                      and live.get("physical_resets_verified") == 2)
        else:
            passed = (live.get("status") == "technical_check_completed"
                      and live.get("model_requests_completed") == 2
                      and live.get("executed_action_count") == 64
                      and live.get("physical_resets_completed") == 2)
        if (not passed or live.get("physical_forecast_alignment_qualified") is not False
                or live.get("behavioral_episodes") != 0 or live.get("release_permitted") is not False):
            raise ContractError("live evidence is incomplete or falsely promotes forecast/study status")
        observation_path = cohort / f"closed-loop-{model}-{suffix}" / "policy" / "evidence" / "observations.jsonl"
        clock = observed_clock(observation_path)
        results[model] = {"fixed_input": reference(fixed_path), "live": reference(live_path)}
        clocks[model] = {
            "schema": "sgw-01-observed-execution-clock-v1", "status": "passed", "model": model,
            "scope": "executed actions and observed simulator frames only",
            **clock, "native_evidence": results[model],
            "forecast_camera_mapping": None, "forecast_time_mapping": None,
            "physical_forecast_alignment_qualified": False, "prediction_scoring_allowed": False,
            "forecast_status": "decoded_unmapped", "additional_model_requests": 0,
            "limitation": "This measured execution clock is not an alignment of generated future pixels or exposures.",
        }
    output.mkdir(parents=True, exist_ok=False)
    time_maps = {}
    for model, clock in clocks.items():
        path = output / f"{model}-observed-clock.json"
        atomic_json(path, clock)
        time_maps[model] = reference(path)["sha256"]
    atomic_json(output / "fixtures.json", {
        "schema_version": "sgw-01-behavioral-fixtures-v1", "status": "qualified",
        "qualification_scope": "registered physical scenes, native input/action contract, observed execution clock",
        "physical_source": reference(physical_path), "layouts": physical["layouts"], "time_maps": time_maps,
        "forecast_camera_mapping": None, "forecast_time_mapping": None,
        "prediction_scoring_allowed": False, "additional_model_requests": 0,
        "original_native_failures_preserved": True,
    })
    atomic_json(output / "fixed-input-gate.json", {
        "schema": "sgw-01-consumed-fixed-input-gate-v1", "status": "passed",
        "evidence": results, "native_requests_consumed": 18, "additional_model_requests": 0,
    })
    atomic_json(output / "technical-stage-gate.json", {
        "schema": "sgw-01-behavioral-technical-stage-gate-v1", "status": "accepted",
        "stages": ["P", "D", "C"], "evidence": results,
        "progression": "all54 P completions and measured budgets before D; all216 D completions before C",
        "behavioral_performance_gate": False, "prediction_scoring_allowed": False,
        "forecast_camera_mapping": None, "forecast_time_mapping": None,
        "additional_model_requests": 0,
    })
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--cohort", type=Path, required=True)
    parser.add_argument("--materialization", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(prepare(source=args.source, cohort=args.cohort, materialization=args.materialization, output=args.output))


if __name__ == "__main__":
    main()
