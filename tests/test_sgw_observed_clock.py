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


def test_prospective_gate_requires_selected_stock_inputs_and_all_three_captures(tmp_path, monkeypatch):
    from pathlib import Path
    from experiments.workshops.spatial_grounding_v1.camera_configuration import STOCK_REVISION, camera_configuration_identity
    from experiments.workshops.spatial_grounding_v1.policy_observations import OFFICIAL_INPUT_REVISION, policy_input_identity
    from experiments.workshops.spatial_grounding_v1.study_lane import reference
    from tools.prepare_study_clock_fixtures import revision_evidence

    monkeypatch.setenv("SGW01_CAMERA_REVISION", STOCK_REVISION)
    monkeypatch.setenv("SGW01_POLICY_INPUT_REVISION", OFFICIAL_INPUT_REVISION)
    original = Path(__file__).resolve().parents[1] / "artifacts/workshops/spatial_grounding_v1/camera_checks_20260925/front-side-candidates/receipt.json"
    captures = {}
    for layout in ("LAT-P01", "HEIGHT-P01", "DIST-P01"):
        # Synthetic contract fixtures, not new physical reset evidence.
        capture = json.loads(original.read_text())
        capture["layout_id"] = layout
        path = tmp_path / f"{layout}.json"
        path.write_text(json.dumps(capture))
        captures[layout] = reference(path)
    packing = tmp_path / "packing.json"
    packing.write_text(json.dumps({
        "status": "passed", "camera_configuration": camera_configuration_identity(),
        "policy_input": policy_input_identity(), "native_reset_inputs": 1, "model_requests": 0,
    }))
    gate = {
        "schema": "sgw-stock-camera-rerun-gates-v1", "status": "passed",
        "allowed_models": ["N3"], "camera_configuration": camera_configuration_identity(),
        "policy_input": policy_input_identity(), "layouts": ["LAT-P01", "HEIGHT-P01", "DIST-P01"],
        "model_requests": 0, "reset_captures": captures, "packing": reference(packing),
    }
    path = tmp_path / "gates.json"
    path.write_text(json.dumps(gate))
    assert revision_evidence(path) == gate
    del gate["reset_captures"]["DIST-P01"]
    path.write_text(json.dumps(gate))
    with pytest.raises(ContractError, match="all three reset captures"):
        revision_evidence(path)
