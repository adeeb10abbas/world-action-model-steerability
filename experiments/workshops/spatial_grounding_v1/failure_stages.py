"""Exploratory, downstream stage diagnostics; never a scorer or execution gate."""

from __future__ import annotations

from collections import Counter, defaultdict
import math
from pathlib import Path
from statistics import median
from typing import Any, Mapping, Sequence

from .contract import load_json, sha256_file
from .native_geometry_measurements import _rotate_wxyz
from .scoring import FrozenScoringConfig, relation_m

ROOT = Path(__file__).resolve().parents[3]
NOTE = ROOT / "docs/FAILURE_STAGE_ANALYSIS_NOTE.md"
CALIBRATION = ROOT / "artifacts/workshops/spatial_grounding_v1/controller_calibrations/lat-closed-pad-20260923.json"
CALIBRATION_SHA256 = "107442ccca01c4ac44ec6e1cb9674d51dbcd8663288a851dc54fa91a124f93d7"
REGISTRY = ROOT / "artifacts/workshops/spatial_grounding_v1/scene_package_20260924/scene-registry.json"
SCHEMA = "sgw-01-exploratory-failure-stages-v1"
STAGES = ("success", "pick_failed", "anchor_disturbance", "wrong_side",
          "release_failed", "transport_failed", "stage_unobservable")
EVENTS = ("approach", "contact", "gripper_close", "attach", "lift_30mm",
          "sustained_lift_30mm", "detach", "gripper_open", "final_stable")
GROUP_KEYS = ("stage", "model", "family", "form", "physical_goal_sign")
CLOSED_RAD = 0.785398
JOINT_TOLERANCE_RAD = 1e-4
FRAME_TOLERANCE = 1e-4
CONTACT_FORCE_N = 1.0


def _get(value: Any, path: str) -> Any:
    for key in path.split("."):
        if not isinstance(value, Mapping):
            return None
        value = value.get(key)
    return value


def _number(value: Any) -> float | None:
    return float(value) if type(value) in (int, float) and math.isfinite(value) else None


def _vector(value: Any, size: int = 3) -> list[float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != size:
        return None
    if any(_number(item) is None for item in value):
        return None
    return [float(item) for item in value]


def _quaternion(value: Any) -> list[float] | None:
    result = _vector(value, 4)
    return result if result is not None and abs(math.hypot(*result) - 1) <= FRAME_TOLERANCE else None


def _inventory(value: Any, prefix: str = "") -> set[str]:
    paths: set[str] = set()
    if isinstance(value, Mapping):
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else key
            paths.add(path)
            paths.update(_inventory(item, path))
    return paths


def load_geometry(workspaces: Sequence[Path] = ()) -> tuple[dict[str, Any], dict[str, Any]]:
    """Only registry-hash-bound, existing model-blind workspaces are accepted."""
    if sha256_file(CALIBRATION) != CALIBRATION_SHA256:
        raise ValueError("failure-stage calibration differs from pre-analysis note")
    calibration = load_json(CALIBRATION, "grasp calibration")
    registry = load_json(REGISTRY, "scene registry")
    expected = {entry["regenerate_scene"]["workspace_sha256"] for entry in registry["layouts"].values()}
    loaded: dict[str, Any] = {}
    for path in workspaces:
        digest = sha256_file(path)
        if digest not in expected or digest in loaded:
            raise ValueError("failure workspace is unregistered or repeated")
        value = load_json(path, "model-blind workspace")
        if value.get("model_request_count") != 0 or value.get("behavioral_episode_count") != 0:
            raise ValueError("failure workspace must be a recorded zero-model workspace")
        robot = value.get("robot_snapshot", value.get("robot", {}))
        loaded[digest] = {
            "origin": value.get("environment_origin_world_xyz_m"),
            "root_env": robot.get("articulation_root_position_env_local_xyz_m",
                                  robot.get("base_position_env_local_xyz_m")),
            "path": str(path.resolve()), "sha256": digest,
        }
    layouts = {
        layout: loaded[entry["regenerate_scene"]["workspace_sha256"]]
        for layout, entry in registry["layouts"].items()
        if entry["regenerate_scene"]["workspace_sha256"] in loaded
    }
    return calibration, layouts


def _approach(states: Sequence[Mapping[str, Any]], geometry: Mapping[str, Any] | None,
              calibration: Mapping[str, Any]) -> tuple[list[bool | None], str | None]:
    unavailable = [None] * len(states)
    if geometry is None:
        return unavailable, "registered layout workspace not supplied"
    origin, qualified_root = _vector(geometry.get("origin")), _vector(geometry.get("root_env"))
    if origin is None or qualified_root is None:
        return unavailable, "workspace lacks environment origin or env-local robot root"
    offset = _vector(calibration.get("virtual_tcp_flange_xyz_m"))
    radius = _number(calibration.get("lift_height_m"))
    if offset is None or radius is None:
        return unavailable, "calibration lacks measured TCP or approach offset"
    first_root = None
    first_origin = None
    values: list[bool | None] = []
    for state in states:
        robot = _get(state, "raw_snapshot.robot_snapshot")
        if not isinstance(robot, Mapping):
            return unavailable, "missing raw_snapshot.robot_snapshot"
        if (_get(robot, "asset_usd.available") is not True
                or _get(robot, "asset_usd.sha256") != _get(calibration, "robot_asset.sha256")):
            return unavailable, "recorded robot asset differs from calibrated asset"
        root = _vector(robot.get("articulation_root_position_env_local_xyz_m"))
        rotation = _quaternion(robot.get("articulation_root_quaternion_world_wxyz"))
        bodies = _get(state, "raw_snapshot.robot_body_frames.bodies")
        if not isinstance(bodies, Mapping):
            bodies = _get(robot, "body_frames.bodies")
        if root is None or rotation is None or not isinstance(bodies, Mapping):
            return unavailable, "missing or malformed root/body-frame coordinates"
        matches = []
        for frame in bodies.values():
            quaternion = _quaternion(_get(frame, "quaternion_world_wxyz"))
            position = _vector(_get(frame, "position_world_xyz_m"))
            if quaternion is not None and position is not None and min(
                math.dist(quaternion, rotation), math.dist(quaternion, [-v for v in rotation]),
            ) <= FRAME_TOLERANCE:
                matches.append([a - b for a, b in zip(position, root, strict=True)])
        if not matches:
            return unavailable, "no recorded body matches root quaternion"
        if len(matches) == 1:
            derived = matches[0]
            if math.dist(derived, origin) > FRAME_TOLERANCE:
                return unavailable, "derived origin differs from registered workspace"
        else:
            if math.dist(root, qualified_root) > FRAME_TOLERANCE or not any(
                math.dist(candidate, origin) <= FRAME_TOLERANCE for candidate in matches
            ):
                return unavailable, "ambiguous root frames fail workspace root/origin check"
            derived = origin
        if first_root is not None and (math.dist(root, first_root) > FRAME_TOLERANCE
                                       or math.dist(derived, first_origin) > FRAME_TOLERANCE):
            return unavailable, "robot root or environment origin changes within episode"
        if first_root is None:
            first_root, first_origin = root, derived
        flange = bodies.get("base_link")
        position = _vector(_get(flange, "position_world_xyz_m"))
        quaternion = _quaternion(_get(flange, "quaternion_world_wxyz"))
        cube = _vector(state.get("cube_xyz_m"))
        if position is None or quaternion is None or cube is None:
            values.append(None)
            continue
        rotated = _rotate_wxyz(quaternion, offset)
        tcp = [p + delta - o for p, delta, o in zip(position, rotated, derived, strict=True)]
        values.append(math.dist(tcp, cube) <= radius)
    return values, None if all(value is not None for value in values) else "missing flange/TCP/cube coordinates"


def _joint(state: Mapping[str, Any]) -> float | None:
    robot = _get(state, "raw_snapshot.robot_snapshot")
    names, positions = _get(robot, "joint_names"), _get(robot, "joint_position_rad")
    if (not isinstance(names, list) or not all(isinstance(name, str) for name in names)
            or len(set(names)) != len(names) or names.count("finger_joint") != 1
            or not isinstance(positions, list) or len(positions) != len(names)):
        return None
    value = _number(positions[names.index("finger_joint")])
    return value if value is not None and -JOINT_TOLERANCE_RAD <= value <= CLOSED_RAD + JOINT_TOLERANCE_RAD else None


def _attachment(state: Mapping[str, Any]) -> bool | None:
    values = [state.get("gripper_holding"), _get(state, "raw_snapshot.objects.rubiks_cube.attached_to_gripper")]
    present = [value for value in values if value is not None]
    if not present or any(type(value) is not bool for value in present) or len(set(present)) != 1:
        return None
    return present[0]


def _contact(state: Mapping[str, Any]) -> bool | None:
    record = _get(state, "raw_snapshot.robot_snapshot.gripper_contact_forces.gripper__rubiks_cube")
    if not isinstance(record, Mapping) or record.get("available") is not True:
        return None
    vectors: list[list[float]] = []

    def collect(value: Any) -> bool:
        vector = _vector(value)
        if vector is not None:
            vectors.append(vector)
            return True
        return isinstance(value, list) and bool(value) and all(collect(item) for item in value)

    if not collect(record.get("force_matrix_world_n")):
        return None
    return any(math.hypot(*vector) >= CONTACT_FORCE_N for vector in vectors)


def _after(first: Sequence[bool | None], second: Sequence[bool | None]) -> list[bool | None]:
    seen = False
    unknown = False
    result: list[bool | None] = []
    for before, after in zip(first, second, strict=True):
        result.append(after if seen else None if unknown else False)
        seen = seen or before is True
        unknown = unknown or before is None
    return result


def _event(values: Sequence[bool | None], states: Sequence[Mapping[str, Any]], reason: str) -> dict[str, Any]:
    found = next((index for index, value in enumerate(values) if value is True), None)
    prefix = values if found is None else values[:found + 1]
    if any(value is None for value in prefix):
        return {"status": "unobservable", "step": None, "sim_time_s": None, "reason": reason}
    if found is None:
        return {"status": "not_observed", "step": None, "sim_time_s": None}
    return {"status": "observed", "step": states[found]["action_step"], "sim_time_s": states[found]["sim_time_s"]}


def _stable(state: Mapping[str, Any], row: Mapping[str, Any], cfg: FrozenScoringConfig) -> bool | None:
    supported, detached = state.get("supported"), state.get("final_detached_release")
    linear, angular = _number(state.get("linear_speed_m_s")), _number(state.get("angular_speed_rad_s"))
    cube, bowl, plate = (_vector(state.get(f"{name}_xyz_m")) for name in ("cube", "bowl", "plate"))
    if (type(supported) is not bool or type(detached) is not bool or linear is None or angular is None
            or linear < 0 or angular < 0
            or cube is None or bowl is None or (row["family"] == "DIST" and plate is None)):
        return None
    return (supported and detached and 0 <= linear < cfg.linear_speed_limit_m_s
            and 0 <= angular < cfg.angular_speed_limit_rad_s
            and int(row["physical_goal_sign"]) * relation_m(row["family"], cube, bowl, plate) >= cfg.relation_margin_m)


def episode_diagnostics(row: Mapping[str, Any], calibration: Mapping[str, Any],
                        geometry: Mapping[str, Any] | None = None) -> dict[str, Any]:
    states = row.get("episode_mapping")
    states = states if isinstance(states, list) else []
    fields: set[str] = set()
    for state in states:
        fields.update(_inventory(state))
    result: dict[str, Any] = {
        "available_state_fields": sorted(fields),
        "state_source": row.get("failure_state_source", "result.episode_mapping"),
        "geometry": dict(geometry) if geometry else None,
    }
    end = row.get("executed_action_count", row.get("terminal_step"))
    valid = (type(end) is int and end > 0 and len(states) == end + 1
             and all(isinstance(state, Mapping) and type(state.get("action_step")) is int
                     and state["action_step"] == index and _number(state.get("sim_time_s")) is not None
                     for index, state in enumerate(states)))
    if not valid or any(b["sim_time_s"] <= a["sim_time_s"] for a, b in zip(states, states[1:])):
        reason = "missing/malformed contiguous reset-to-executed-endpoint state/time sequence"
        result.update(pick_substage="unobservable" if row.get("failure_stage") == "pick_failed" else "not_applicable",
                      substage_reason=reason, timeline={
                          event: {"status": "unobservable", "step": None, "sim_time_s": None, "reason": reason}
                          for event in EVENTS})
        return result
    cfg = FrozenScoringConfig()
    approach, approach_reason = _approach(states, geometry, calibration)
    joints = [_joint(state) for state in states]
    closed = [None if joint is None else abs(joint - CLOSED_RAD) <= JOINT_TOLERANCE_RAD for joint in joints]
    opened = [None if joint is None else abs(joint) <= JOINT_TOLERANCE_RAD for joint in joints]
    attached = [_attachment(state) for state in states]
    detached = [state.get("final_detached_release") if type(state.get("final_detached_release")) is bool else None
                for state in states]
    # Both native fields describe the same predicate, so contradictory flags are not evidence.
    for index, (holding, release) in enumerate(zip(attached, detached, strict=True)):
        if holding is not None and release is not None and holding == release:
            attached[index] = detached[index] = None
    cubes = [_vector(state.get("cube_xyz_m")) for state in states]
    lifted = [None if cube is None or cubes[0] is None else cube[2] - cubes[0][2] >= cfg.pickup_height_m
              for cube in cubes]
    sustained: list[bool | None] = []
    for index in range(len(states)):
        window = lifted[index:index + cfg.pickup_consecutive_steps]
        sustained.append(False if index == 0 or len(window) < cfg.pickup_consecutive_steps else
                         None if None in window else all(window))
    predicates = {
        "approach": approach, "contact": [_contact(state) for state in states],
        "gripper_close": closed, "attach": attached, "lift_30mm": lifted,
        "sustained_lift_30mm": sustained, "detach": _after(attached, detached),
        "gripper_open": _after(closed, opened),
    }
    timeline = {name: _event(values, states, f"missing/inconsistent fields for {name}")
                for name, values in predicates.items()}
    if approach_reason and timeline["approach"]["status"] == "unobservable":
        timeline["approach"]["reason"] = approach_reason
    stable = [_stable(state, row, cfg) if release is not None else None
              for state, release in zip(states, detached, strict=True)]
    start = len(states)
    while start and stable[start - 1] is True:
        start -= 1
    final_values: list[bool | None] = [False] * len(states)
    if start < len(states) and states[-1]["sim_time_s"] - states[start]["sim_time_s"] >= cfg.final_stability_seconds - 1e-9:
        final_values[start] = None if start and stable[start - 1] is None else True
    elif start and None in stable[start - 1:]:
        final_values[-1] = None
    timeline["final_stable"] = _event(final_values, states, "terminal stable suffix is not fully observable")
    if (row.get("status") in {"censored", "technical_invalid"} or row.get("safety_censored") is True
            or row.get("terminal_step") != end):
        timeline["final_stable"] = {
            "status": "unobservable", "step": None, "sim_time_s": None,
            "reason": "no uncensored terminal endpoint; earlier stability is not final stability",
        }
    result["timeline"] = timeline
    result["pick_substage"], result["substage_reason"] = _substage(row, predicates)
    return result


def _substage(row: Mapping[str, Any], values: Mapping[str, Sequence[bool | None]]) -> tuple[str, str]:
    if row.get("failure_stage") != "pick_failed":
        return "not_applicable", "primary stage is not pick_failed"
    attached, lifted = values["attach"], values["lift_30mm"]
    if True in values["sustained_lift_30mm"]:
        return "unobservable", "sustained lift conflicts with recorded primary pick_failed"
    if True in lifted:
        if None in values["sustained_lift_30mm"]:
            return "unobservable", "sustained lift coverage is incomplete"
        return "lift_not_sustained", "30 mm crossing without three consecutive action steps"
    if True in attached:
        return ("unobservable", "lift coverage is incomplete") if None in lifted else (
            "attach_no_lift", "attachment observed without a 30 mm crossing")
    if None in attached:
        return "unobservable", "attachment coverage is incomplete or inconsistent"
    approach, closed = values["approach"], values["gripper_close"]
    if None in approach:
        return "unobservable", "approach coverage or coordinate mapping unavailable"
    if True not in approach:
        return "no_approach", "TCP never within scripted approach distance"
    if None in closed:
        return "unobservable", "gripper closure coverage is incomplete"
    if True not in closed:
        return "approach_no_close", "approach observed without entering calibrated closed band"
    if any(near and shut for near, shut in zip(approach, closed, strict=True)):
        return "close_no_attach", "closed near cube but attachment never observed"
    return "close_away_from_cube", "closed band observed only outside approach distance"


def _category(row: Mapping[str, Any]) -> str:
    if row.get("analysis_status") == "not_run":
        return "not_run"
    if row.get("status") == "technical_invalid" or row.get("analysis_status") == "incomplete":
        return "technical_invalid"
    if row.get("status") == "censored" or row.get("safety_censored") is True:
        return "safety_censored"
    if row.get("status") == "valid_success" and "failure_stage" in row and row["failure_stage"] is None:
        return "success"
    if row.get("status") == "valid_model_failure" and row.get("failure_stage") in STAGES[1:-1]:
        return row["failure_stage"]
    return "stage_unobservable"


def compile_failure_stages(rows: Sequence[Mapping[str, Any]], *, calibration: Mapping[str, Any],
                           geometry: Mapping[str, Mapping[str, Any]] | None = None) -> dict[str, Any]:
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    layouts: dict[tuple[Any, ...], dict[str, Any]] = defaultdict(dict)
    episodes = []
    for row in rows:
        category = _category(row)
        episode = {key: row.get(key) for key in (*GROUP_KEYS, "cell_id", "layout_id", "release_id", "attempt_id")}
        episode.update(category=category, primary_failure_stage=row.get("failure_stage"))
        if category != "not_run":
            episode.update(episode_diagnostics(row, calibration, (geometry or {}).get(row["layout_id"])))
            if category not in STAGES:
                episode["pick_substage"] = "not_applicable"
                episode["substage_reason"] = "technical/censored episode, not a valid model-failure category"
        else:
            episode.update(pick_substage="not_applicable", timeline={})
        episodes.append(episode)
        groups[tuple(row[key] for key in GROUP_KEYS)].append(episode)
        layout_key = tuple(row[key] for key in ("stage", "model", "family", "layout_id", "physical_goal_sign"))
        if row["form"] in layouts[layout_key]:
            raise ValueError("duplicate form in paired failure-stage layout")
        layouts[layout_key][row["form"]] = {"cell_id": row["cell_id"], "category": category,
                                           "failure_stage": row.get("failure_stage")}
    summary = []
    for key, group in sorted(groups.items()):
        counts = Counter(row["category"] for row in group)
        valid = sum(counts[stage] for stage in STAGES)
        medians = {}
        for name in EVENTS:
            events = [row["timeline"][name] for row in group if row["category"] in STAGES]
            observed = [event for event in events if event["status"] == "observed"]
            medians[name] = {
                "eligible": valid, "observed": len(observed),
                "not_observed": sum(event["status"] == "not_observed" for event in events),
                "unobservable": sum(event["status"] == "unobservable" for event in events),
                "median_step": median(event["step"] for event in observed) if observed else None,
                "median_sim_time_s": median(event["sim_time_s"] for event in observed) if observed else None,
            }
        substages = dict(sorted(Counter(row["pick_substage"] for row in group
                                        if row["category"] == "pick_failed").items()))
        summary.append({
            **dict(zip(GROUP_KEYS, key, strict=True)), "planned": len(group), "valid_model": valid,
            "counts": {name: counts[name] for name in (*STAGES, "not_run", "technical_invalid", "safety_censored")},
            "stage_proportions": {
                name: {"numerator": counts[name], "denominator": valid,
                       "proportion": counts[name] / valid if valid else None} for name in STAGES
            },
            "pick_substage_counts": substages,
            "pick_substage_proportions": {
                name: {"numerator": count, "denominator": counts["pick_failed"],
                       "proportion": count / counts["pick_failed"]} for name, count in substages.items()
            },
            "pick_substage_denominator": counts["pick_failed"], "median_timelines": medians,
        })
    transitions = []
    for key, forms in sorted(layouts.items()):
        pairs = []
        for first, second in (("D", "C"), ("D", "I"), ("C", "I")):
            left, right = forms.get(first), forms.get(second)
            available = left is not None and right is not None and all(
                item["category"] in STAGES[:-1] for item in (left, right))
            pairs.append({"from_form": first, "to_form": second, "status": "paired" if available else "unavailable",
                          "from_stage": left["category"] if left else "not_run",
                          "to_stage": right["category"] if right else "not_run"})
        transitions.append({**dict(zip(("stage", "model", "family", "layout_id", "physical_goal_sign"), key, strict=True)),
                            "forms": forms, "pairs": pairs})
    return {
        "schema_version": SCHEMA, "exploratory": True, "primary_scoring_unchanged": True,
        "definition": {"note": str(NOTE.relative_to(ROOT)), "note_sha256": sha256_file(NOTE),
                       "source_sha256": sha256_file(Path(__file__)), "registry_sha256": sha256_file(REGISTRY),
                       "calibration_sha256": CALIBRATION_SHA256, "approach_distance_m": calibration["lift_height_m"],
                       "closed_joint_rad": CLOSED_RAD, "open_joint_rad": 0,
                       "joint_tolerance_rad": JOINT_TOLERANCE_RAD, "frame_tolerance": FRAME_TOLERANCE,
                       "contact_force_n": CONTACT_FORCE_N},
        "groups": summary, "paired_layout_transitions": transitions, "episodes": episodes,
    }
