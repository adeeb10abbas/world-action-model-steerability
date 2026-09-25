"""Synthetic state-only diagnostic tests; never load learned-policy outcomes."""

import copy
import json
import math
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from experiments.workshops.spatial_grounding_v1 import failure_stages as stages
from experiments.workshops.spatial_grounding_v1.contract import sha256_file
from tools import compile_study_cohort as cohort
from tools import render_failure_stages as renderer
from test_compile_study_cohort import _index, _read, _record, _release, _rows, _update_result, _write

CALIBRATION, _ = stages.load_geometry()
GEOMETRY = {"origin": [10., 20., 30.], "root_env": [1., 2., 3.],
            "path": "/synthetic/model-blind-workspace.json", "sha256": "f" * 64}


def _state(index, *, distance=.1, joint=0., attach=False, lift=0., supported=True):
    cube = [0., 0., .2 + lift]
    quaternion = [math.sqrt(.5), 0., 0., math.sqrt(.5)]
    offset = stages._rotate_wxyz(quaternion, CALIBRATION["virtual_tcp_flange_xyz_m"])
    tcp = [cube[0] + distance, cube[1], cube[2]]
    flange = [a + b - c for a, b, c in zip(tcp, GEOMETRY["origin"], offset, strict=True)]
    bodies = {
        "root_native_body": {"position_world_xyz_m": [11., 22., 33.],
                             "quaternion_world_wxyz": [1., 0., 0., 0.]},
        "base_link": {"position_world_xyz_m": flange, "quaternion_world_wxyz": quaternion},
    }
    return {
        "action_step": index, "sim_time_s": index / 10, "cube_xyz_m": cube,
        "bowl_xyz_m": [0., -.05, .2], "plate_xyz_m": [.2, 0., .2],
        "supported": supported, "final_detached_release": not attach, "gripper_holding": attach,
        "linear_speed_m_s": 0., "angular_speed_rad_s": 0.,
        "raw_snapshot": {
            "robot_body_frames": {"bodies": bodies},
            "robot_snapshot": {
                "articulation_root_position_env_local_xyz_m": [1., 2., 3.],
                "articulation_root_quaternion_world_wxyz": [1., 0., 0., 0.],
                "body_frames": {"bodies": bodies},
                "joint_names": ["panda_joint1", "finger_joint"],
                "joint_position_rad": [0., joint],
                "asset_usd": {"available": True, **CALIBRATION["robot_asset"]},
            },
            "objects": {"rubiks_cube": {"attached_to_gripper": attach}},
        },
    }


def _episode(states=None, **updates):
    states = states if states is not None else [_state(i) for i in range(16)]
    return {
        "cell_id": "LAT-D01-N3-D-POS", "layout_id": "LAT-D01", "stage": "D",
        "model": "N3", "family": "LAT", "form": "D", "physical_goal_sign": 1,
        "release_id": "synthetic-release", "attempt_id": "attempt-001",
        "analysis_status": "complete", "status": "valid_model_failure", "failure_stage": "pick_failed",
        "requested_success": False, "terminal_step": len(states) - 1,
        "executed_action_count": len(states) - 1, "episode_mapping": states, **updates,
    }


def _diagnostics(row=None, geometry=GEOMETRY):
    return stages.episode_diagnostics(row or _episode(), CALIBRATION, geometry)


@pytest.mark.parametrize("distance,expected", [(.2, "no_approach"), (.1, "approach_no_close"),
                                               (.120001, "no_approach"), (.119999, "approach_no_close")])
def test_calibrated_approach_boundary_and_nonzero_frame_origin(distance, expected):
    result = _diagnostics(_episode([_state(i, distance=distance) for i in range(16)]))
    assert result["pick_substage"] == expected
    assert result["timeline"]["contact"]["status"] == "unobservable"


def test_closed_near_cube_without_attachment_is_not_inferred_contact():
    result = _diagnostics(_episode([_state(i, joint=stages.CLOSED_RAD) for i in range(16)]))
    assert result["pick_substage"] == "close_no_attach"
    assert result["timeline"]["gripper_close"]["step"] == 0
    assert result["timeline"]["contact"]["step"] is None
    assert result["timeline"]["attach"]["status"] == "not_observed"


def test_attachment_without_lift_and_transient_lift_are_distinct():
    states_without_lift = [_state(i, attach=i > 2) for i in range(16)]
    assert _diagnostics(_episode(states_without_lift))["pick_substage"] == "attach_no_lift"
    # A single 40 mm sample is not a three-step pickup.
    transient = [_state(i, attach=i > 2, lift=.04 if i == 5 else 0) for i in range(16)]
    result = _diagnostics(_episode(transient))
    assert result["pick_substage"] == "lift_not_sustained"
    assert result["timeline"]["lift_30mm"]["step"] == 5
    assert result["timeline"]["sustained_lift_30mm"]["status"] == "not_observed"


@pytest.mark.parametrize("height,expected", [(.029999, "not_observed"), (.03, "observed"), (.030001, "observed")])
def test_exact_thirty_mm_three_step_lift_threshold(height, expected):
    row = _episode()
    for index, state in enumerate(row["episode_mapping"]):
        state["cube_xyz_m"][2] = 0. if index < 3 else height
    result = _diagnostics(row)
    assert result["timeline"]["lift_30mm"]["status"] == expected
    assert result["timeline"]["sustained_lift_30mm"]["status"] == expected
    if expected == "observed":
        assert result["timeline"]["sustained_lift_30mm"]["step"] == 3


def test_closed_only_away_is_residual_not_close_no_attach():
    states = [_state(i, distance=.2 if i < 5 else .1, joint=stages.CLOSED_RAD if i < 5 else 0)
              for i in range(16)]
    assert _diagnostics(_episode(states))["pick_substage"] == "close_away_from_cube"


def test_timeline_onsets_and_no_reset_detach_or_open_events():
    states = [_state(i, distance=.2 if i < 2 else .1,
                     joint=stages.CLOSED_RAD if 3 <= i < 8 else 0,
                     attach=4 <= i < 8, lift=.04 if i >= 5 else 0)
              for i in range(16)]
    result = _diagnostics(_episode(states, status="valid_success", failure_stage=None, requested_success=True))
    expected = {"approach": 2, "gripper_close": 3, "attach": 4, "lift_30mm": 5,
                "sustained_lift_30mm": 5, "detach": 8, "gripper_open": 8, "final_stable": 8}
    for event, step in expected.items():
        assert result["timeline"][event] == {"status": "observed", "step": step, "sim_time_s": step / 10}
    assert result["pick_substage"] == "not_applicable"
    assert _diagnostics()["timeline"]["detach"]["status"] == "not_observed"
    assert _diagnostics()["timeline"]["gripper_open"]["status"] == "not_observed"


@pytest.mark.parametrize("bad", ["missing_root", "wrong_asset", "wrong_origin", "moving_root",
                                  "ambiguous_no_agreement", "no_matching_quaternion", "bad_quaternion",
                                  "missing_flange", "missing_cube"])
def test_mapping_failures_are_unobservable_not_no_approach(bad):
    row = _episode()
    robot = row["episode_mapping"][1]["raw_snapshot"]["robot_snapshot"]
    bodies = row["episode_mapping"][1]["raw_snapshot"]["robot_body_frames"]["bodies"]
    if bad == "missing_root":
        robot.pop("articulation_root_position_env_local_xyz_m")
    elif bad == "wrong_asset":
        robot["asset_usd"] = {"sha256": "0" * 64}
    elif bad == "wrong_origin":
        bodies["root_native_body"]["position_world_xyz_m"][0] += .01
    elif bad == "moving_root":
        robot["articulation_root_position_env_local_xyz_m"][0] += .01
        bodies["root_native_body"]["position_world_xyz_m"][0] += .01
    elif bad == "ambiguous_no_agreement":
        bodies["other"] = copy.deepcopy(bodies["root_native_body"])
        bodies["other"]["position_world_xyz_m"][0] += .01
        bodies["root_native_body"]["position_world_xyz_m"][0] += .02
    elif bad == "no_matching_quaternion":
        bodies["root_native_body"]["quaternion_world_wxyz"] = [0., 1., 0., 0.]
    elif bad == "bad_quaternion":
        bodies["root_native_body"]["quaternion_world_wxyz"] = [2., 0., 0., 0.]
    elif bad == "missing_flange":
        row["episode_mapping"][0]["raw_snapshot"]["robot_body_frames"]["bodies"].pop("base_link")
    elif bad == "missing_cube":
        row["episode_mapping"][0].pop("cube_xyz_m")
    result = _diagnostics(row)
    assert result["timeline"]["approach"]["status"] == "unobservable"
    assert result["timeline"]["approach"]["step"] is None
    assert result["pick_substage"] == "unobservable"


def test_mapping_ambiguous_rotation_requires_qualified_root_and_position_match():
    row = _episode()
    for state in row["episode_mapping"]:
        bodies = state["raw_snapshot"]["robot_body_frames"]["bodies"]
        bodies["same_quaternion_other_position"] = {
            "position_world_xyz_m": [12., 22., 33.], "quaternion_world_wxyz": [-1., 0., 0., 0.]}
    assert _diagnostics(row)["timeline"]["approach"]["status"] == "observed"
    wrong = {**GEOMETRY, "root_env": [0., 0., 0.]}
    assert _diagnostics(row, wrong)["timeline"]["approach"]["status"] == "unobservable"


def test_cumulative_root_drift_is_not_allowed_by_per_step_tolerance():
    row = _episode()
    for i, state in enumerate(row["episode_mapping"]):
        robot = state["raw_snapshot"]["robot_snapshot"]
        robot["articulation_root_position_env_local_xyz_m"][0] += i * .00002
        state["raw_snapshot"]["robot_body_frames"]["bodies"]["root_native_body"]["position_world_xyz_m"][0] += i * .00002
    assert _diagnostics(row)["timeline"]["approach"]["status"] == "unobservable"


def test_no_workspace_no_ee_invention_and_exact_available_fields():
    result = _diagnostics(geometry=None)
    assert result["pick_substage"] == "unobservable"
    assert result["timeline"]["approach"]["reason"] == "registered layout workspace not supplied"
    assert "raw_snapshot.robot_body_frames.bodies.base_link.position_world_xyz_m" in result["available_state_fields"]
    assert not any("end_effector" in field for field in result["available_state_fields"])
    assert result["timeline"]["gripper_close"]["status"] == "not_observed"


@pytest.mark.parametrize("joint,closed,opened", [
    (0., False, True), (.00011, False, False), (.4, False, False),
    (stages.CLOSED_RAD, True, False), (stages.CLOSED_RAD - .00009, True, False),
    (stages.CLOSED_RAD - .00011, False, False),
])
def test_calibrated_open_closed_bands(joint, closed, opened):
    row = _episode([_state(i, joint=joint) for i in range(16)])
    timeline = _diagnostics(row)["timeline"]
    assert (timeline["gripper_close"]["status"] == "observed") == closed
    # Initial open is not an open-after-close event.
    assert timeline["gripper_open"]["status"] == "not_observed"
    assert (abs(joint) <= stages.JOINT_TOLERANCE_RAD) == opened


@pytest.mark.parametrize("bad", ["missing_joint", "duplicate_joint", "nan", "out_of_range", "missing_positions"])
def test_missing_or_invalid_closure_evidence_is_unobservable(bad):
    row = _episode()
    robot = row["episode_mapping"][0]["raw_snapshot"]["robot_snapshot"]
    if bad == "missing_joint":
        robot["joint_names"] = ["panda_joint1", "not_finger"]
    elif bad == "duplicate_joint":
        robot["joint_names"] = ["finger_joint", "finger_joint"]
    elif bad == "nan":
        robot["joint_position_rad"][1] = float("nan")
    elif bad == "out_of_range":
        robot["joint_position_rad"][1] = 10.
    else:
        robot.pop("joint_position_rad")
    result = _diagnostics(row)
    assert result["pick_substage"] == "unobservable"
    assert result["timeline"]["gripper_close"]["status"] == "unobservable"


@pytest.mark.parametrize("force,expected", [(.999, "not_observed"), (1., "observed"), (1.001, "observed")])
def test_optional_measured_contact_threshold_not_inferred_from_joint(force, expected):
    row = _episode()
    for state in row["episode_mapping"]:
        state["raw_snapshot"]["robot_snapshot"]["gripper_contact_forces"] = {
            "gripper__rubiks_cube": {"available": True, "force_matrix_world_n": [[[[0., force, 0.]]]]}}
    assert _diagnostics(row)["timeline"]["contact"]["status"] == expected


def test_missing_before_first_event_does_not_claim_exact_first_step():
    row = _episode([_state(i, joint=stages.CLOSED_RAD if i > 3 else 0) for i in range(16)])
    row["episode_mapping"][1]["raw_snapshot"]["robot_snapshot"].pop("joint_names")
    assert _diagnostics(row)["timeline"]["gripper_close"]["status"] == "unobservable"


def test_missing_after_first_event_preserves_known_first_time():
    row = _episode([_state(i, joint=stages.CLOSED_RAD) for i in range(16)])
    row["episode_mapping"][-1]["raw_snapshot"]["robot_snapshot"].pop("joint_names")
    result = _diagnostics(row)
    assert result["timeline"]["gripper_close"]["step"] == 0
    assert result["pick_substage"] == "unobservable"


@pytest.mark.parametrize("bad", ["gap", "time", "endpoint", "empty", "not_list"])
def test_missing_sequence_coverage_is_unobservable(bad):
    row = _episode()
    if bad == "gap":
        row["episode_mapping"].pop(2)
    elif bad == "time":
        row["episode_mapping"][2]["sim_time_s"] = row["episode_mapping"][1]["sim_time_s"]
    elif bad == "endpoint":
        row.pop("executed_action_count")
        row.pop("terminal_step")
    elif bad == "empty":
        row["episode_mapping"] = []
    else:
        row["episode_mapping"] = {}
    result = _diagnostics(row)
    assert all(event["status"] == "unobservable" and event["step"] is None for event in result["timeline"].values())


def test_contradictory_native_attachment_flags_do_not_become_no_grasp():
    row = _episode()
    row["episode_mapping"][0]["raw_snapshot"]["objects"]["rubiks_cube"]["attached_to_gripper"] = True
    assert _diagnostics(row)["pick_substage"] == "unobservable"


def test_contradictory_detachment_is_not_a_final_stable_observation():
    row = _episode()
    for state in row["episode_mapping"]:
        state["gripper_holding"] = True
        state["raw_snapshot"]["objects"]["rubiks_cube"]["attached_to_gripper"] = True
        state["final_detached_release"] = True
    assert _diagnostics(row)["timeline"]["final_stable"]["status"] == "unobservable"


def test_sustained_lift_contradiction_does_not_rewrite_primary_stage():
    row = _episode([_state(i, attach=i > 1, lift=.04 if i > 3 else 0) for i in range(16)])
    result = _diagnostics(row)
    assert result["pick_substage"] == "unobservable"
    assert "conflicts" in result["substage_reason"]
    assert row["failure_stage"] == "pick_failed"


@pytest.mark.parametrize("change", [
    {"supported": False}, {"final_detached_release": False},
    {"linear_speed_m_s": .02}, {"angular_speed_rad_s": .2},
    {"bowl_xyz_m": [0., 0., .2]},
])
def test_final_stable_requires_unchanged_frozen_predicate(change):
    row = _episode(status="valid_model_failure", failure_stage="transport_failed")
    row["episode_mapping"][-1].update(change)
    assert _diagnostics(row)["timeline"]["final_stable"]["status"] != "observed"


def test_final_stability_missing_fields_and_short_window_do_not_become_zero():
    row = _episode([_state(i, supported=i >= 12) for i in range(16)])
    assert _diagnostics(row)["timeline"]["final_stable"]["status"] == "not_observed"
    row["episode_mapping"][-1].pop("linear_speed_m_s")
    assert _diagnostics(row)["timeline"]["final_stable"]["status"] == "unobservable"


def _analysis(rows):
    return stages.compile_failure_stages(rows, calibration=CALIBRATION, geometry={"LAT-D01": GEOMETRY})


def test_exact_denominators_status_separation_and_matched_form_transitions():
    rows = [
        _episode(cell_id="d", form="D"),
        _episode(cell_id="c", form="C", status="valid_success", failure_stage=None, requested_success=True),
        _episode(cell_id="i", form="I", status="censored", failure_stage="safety_censored", safety_censored=True),
        _episode(cell_id="t", form="D", layout_id="LAT-D02", status="technical_invalid", analysis_status="incomplete"),
        _episode(cell_id="m", form="D", layout_id="LAT-D03", analysis_status="not_run"),
        _episode(cell_id="u", form="D", layout_id="LAT-D04", failure_stage=None),
    ]
    result = _analysis(rows)
    direct = next(group for group in result["groups"] if group["form"] == "D")
    assert direct["planned"] == 4 and direct["valid_model"] == 2
    assert direct["counts"]["pick_failed"] == direct["counts"]["stage_unobservable"] == 1
    assert direct["counts"]["technical_invalid"] == direct["counts"]["not_run"] == 1
    assert direct["stage_proportions"]["pick_failed"] == {"numerator": 1, "denominator": 2, "proportion": .5}
    inverted = next(group for group in result["groups"] if group["form"] == "I")
    assert inverted["valid_model"] == 0 and inverted["counts"]["safety_censored"] == 1
    assert inverted["stage_proportions"]["pick_failed"]["proportion"] is None
    first = next(row for row in result["paired_layout_transitions"] if row["layout_id"] == "LAT-D01")
    assert first["pairs"][0] == {"from_form": "D", "to_form": "C", "status": "paired",
                                 "from_stage": "pick_failed", "to_stage": "success"}
    assert first["pairs"][1]["status"] == first["pairs"][2]["status"] == "unavailable"
    assert len(result["episodes"]) == 6


def test_grouping_never_pools_family_sign_or_execution_stage():
    rows = [_episode(cell_id=str(i), family=family, physical_goal_sign=sign, stage=stage)
            for i, (family, sign, stage) in enumerate([
                ("LAT", 1, "D"), ("LAT", -1, "D"), ("HEIGHT", 1, "D"), ("LAT", 1, "C")])]
    assert len(_analysis(rows)["groups"]) == 4


def test_conditional_medians_keep_missing_nonoccurrence_and_censor_counts():
    rows = [
        _episode(cell_id="a", layout_id="LAT-D01",
                 episode_mapping=[_state(i, attach=i >= 4) for i in range(16)]),
        _episode(cell_id="b", layout_id="LAT-D02"),
        _episode(cell_id="c", layout_id="LAT-D03", episode_mapping=[]),
        _episode(cell_id="d", layout_id="LAT-D04", status="censored", safety_censored=True),
    ]
    metric = _analysis(rows)["groups"][0]["median_timelines"]["attach"]
    assert metric == {"eligible": 3, "observed": 1, "not_observed": 1, "unobservable": 1,
                      "median_step": 4, "median_sim_time_s": .4}


def test_censored_prefix_keeps_observed_events_but_no_final_stability_or_failure_class():
    row = _episode(status="censored", safety_censored=True, terminal_step=None,
                   episode_mapping=[_state(i, attach=3 <= i < 5) for i in range(16)])
    result = _analysis([row])
    episode = result["episodes"][0]
    assert episode["timeline"]["attach"]["step"] == 3
    assert episode["timeline"]["final_stable"]["status"] == "unobservable"
    assert episode["pick_substage"] == "not_applicable"
    assert result["groups"][0]["valid_model"] == 0
    assert result["groups"][0]["median_timelines"]["attach"]["median_step"] is None


def test_absent_primary_label_is_not_silently_success():
    row = _episode(status="valid_success", requested_success=True)
    row.pop("failure_stage")
    assert _analysis([row])["episodes"][0]["category"] == "stage_unobservable"


def test_geometry_loader_matches_registered_hash_not_user_supplied_origin(tmp_path, monkeypatch):
    workspace = _write(tmp_path / "workspace.json", {
        "model_request_count": 0, "behavioral_episode_count": 0,
        "environment_origin_world_xyz_m": GEOMETRY["origin"],
        "robot": {"base_position_env_local_xyz_m": GEOMETRY["root_env"]},
    })
    registry = _write(tmp_path / "registry.json", {"layouts": {
        "LAT-D01": {"regenerate_scene": {"workspace_sha256": sha256_file(workspace)}}}})
    monkeypatch.setattr(stages, "REGISTRY", registry)
    _, layouts = stages.load_geometry([workspace])
    assert layouts["LAT-D01"]["origin"] == GEOMETRY["origin"]
    with pytest.raises(ValueError, match="repeated"):
        stages.load_geometry([workspace, workspace])
    workspace.write_text("{}")
    with pytest.raises(ValueError, match="unregistered"):
        stages.load_geometry([workspace])


def test_cohort_reads_hash_bound_state_file_fallback_and_preserves_primary(tmp_path):
    root, entry = _release(tmp_path / "cohort")
    row = _rows(root)[0]
    pointer, manifest_path = _record(root, row)
    _update_result(pointer, {"failure_stage": "pick_failed", "executed_action_count": 15, "terminal_step": 15})
    manifest = _read(manifest_path)
    for index in range(16):
        name = "states/reset.json" if index == 0 else f"states/state-{index:04d}.json"
        path = _write(manifest_path.parent / name, {
            "state": _state(index, attach=index >= 3), "sim_time_s": index / 10, "action_index": index})
        manifest["artifacts"][name] = {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
    _write(manifest_path, manifest)
    raw = _read(pointer)
    raw["manifest_sha256"] = sha256_file(manifest_path)
    _write(pointer, raw)
    report = cohort.compile_study_cohort(cohort.SPEC / "planned_cells.csv", _index(tmp_path, [entry]))
    episode = next(item for item in report["failure_stage_analysis"]["episodes"] if item["cell_id"] == row["cell_id"])
    assert episode["pick_substage"] == "attach_no_lift"
    assert episode["state_source"] == "manifest_bound_state_files"
    original = next(item for item in report["ledger"] if item["cell_id"] == row["cell_id"])
    assert original["failure_stage"] == "pick_failed" and original["S"] == 0
    assert report["coverage"]["observed"] == 1 and not report["complete"]
    assert "episode_mapping" not in original


def test_svg_outputs_show_stage_selection_and_unobservable_without_zero_markers(tmp_path):
    report = {"cohort_id": "synthetic <not results>", "complete": False,
              "schema_version": "sgw-01-cohort-analysis-v1",
              "failure_stage_analysis": _analysis([_episode()])}
    figures = renderer.render_figures(report, stage="D", report_sha256="a" * 64)
    assert set(figures) == {"stage-proportions.svg", "median-timelines.svg"}
    ns = {"s": "http://www.w3.org/2000/svg"}
    for text in figures.values():
        svg = ET.fromstring(text)
        assert "INCOMPLETE CHECKPOINT" in "".join(svg.itertext())
        assert "synthetic <not results>" in "".join(svg.itertext())
        assert len(svg.findall(".//s:g[@data-family]", ns)) == 6
    timeline = ET.fromstring(figures["median-timelines.svg"])
    assert not timeline.findall(".//s:circle[@data-event='contact']", ns)
    stage = ET.fromstring(figures["stage-proportions.svg"])
    bars = stage.findall(".//s:rect[@data-stage='pick_failed']", ns)
    assert len(bars) == 1 and float(bars[0].get("width")) == 510.
    report_path = _write(tmp_path / "report.json", report)
    args = ["--report", str(report_path), "--report-sha256", sha256_file(report_path),
            "--stage", "D", "--output-dir", str(tmp_path / "figures")]
    assert renderer.main(args) == 0
    assert (tmp_path / "figures" / "stage-proportions.svg").is_file()
    with pytest.raises(SystemExit):
        renderer.main(args)
    args[3] = "0" * 64
    with pytest.raises(SystemExit):
        renderer.main(args)
