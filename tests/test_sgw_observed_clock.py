"""Recorded executed clocks never qualify generated forecast pixels."""

import json

import pytest

from experiments.workshops.spatial_grounding_v1.contract import ContractError
from tools.prepare_study_clock_fixtures import observed_clock


def rows():
    return [{"sim_time": 0, "label": "initial_reset"}] + [
        {"global_action_index": index, "before_sim_time": index / 15, "sim_time": (index + 1) / 15}
        for index in range(64)
    ] + [{"sim_time": 0, "label": "final_reset"}]


def write_rows(path, values):
    path.write_text("".join(json.dumps(row) + "\n" for row in values))


def test_measured_clock_is_64_contiguous_15hz_steps(tmp_path):
    path = tmp_path / "observations.jsonl"
    write_rows(path, rows())
    result = observed_clock(path)
    assert result["verified_action_transitions"] == 64
    assert result["maximum_step_dt_error_s"] < 1e-12
    assert result["verified_resets"] == 2
    assert "forecast_time_mapping" not in result


@pytest.mark.parametrize("defect", ["count", "duplicate", "clock", "gap", "nan", "reset", "nan_reset", "initial_gap"])
def test_incomplete_or_inconsistent_clock_rejected(tmp_path, defect):
    values = rows()
    if defect == "count":
        values.pop(2)
    elif defect == "duplicate":
        values[2]["global_action_index"] = 0
    elif defect == "clock":
        values[2]["sim_time"] += 1
    elif defect == "gap":
        values[2]["before_sim_time"] += 1
    elif defect == "nan":
        values[2]["sim_time"] = float("nan")
    elif defect == "reset":
        values[-1]["sim_time"] = 1
    elif defect == "nan_reset":
        values[-1]["sim_time"] = float("nan")
    elif defect == "initial_gap":
        values[1]["before_sim_time"] = 1
    path = tmp_path / "observations.jsonl"
    write_rows(path, values)
    with pytest.raises(ContractError):
        observed_clock(path)
