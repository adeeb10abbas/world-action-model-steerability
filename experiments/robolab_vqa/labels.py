"""Gold labels, boundary flags and visibility pre-checks from saved RWS tick records.

All physical truth comes from the saved simulator records of RWS-20260926 (pinned RoboLab 0aef241
predicates as stored per tick, plus raw poses/forces for the few quantities not stored as booleans).
Nothing here reads model outputs, episode outcomes or forecast labels.

Robot frame (pinned predicates, robolab/core/utils/geometry_utils.py::spatial_condition_check_vector_based,
frame_of_reference='robot', mirrored=False, cone 45 deg): x points away from the robot, y to the robot's
left. left_of: v=p_target-p_reference has v_y>0 within 45 deg of +y; right_of: -y; behind: +x (farther from
the robot); in_front_of: -x (closer to the robot). Positions are object root poses in the robot frame.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np

CONE_DEG = 45.0
BOUNDARY_DEG = 5.0
CENTER_MIN_M = 0.01
CONTACT_FORCE_N = 0.1
SUPPORT_CONE_DEG = 45.0
FOOTPRINT_TOL_M = 0.01
BOWL_IDENTITY_MOVE_M = 0.02
LABEL_VERSION = "rqa-gold-1"

AXES = {"left_of": (0.0, 1.0), "right_of": (0.0, -1.0), "behind": (1.0, 0.0), "in_front_of": (-1.0, 0.0)}
CONE_RELATIONS = tuple(AXES)

# Catalog object names -> RoboLab asset names (S5 roles are bound at reset and frozen).
STATIC_OBJECTS = {"rubiks_cube": "rubiks_cube", "banana": "banana", "bowl": "bowl", "butter": "butter",
                  "raisin_box": "raisin_box", "mustard_bottle": "mustard_bottle"}


def asset_name(catalog_name: str, role_binding: dict | None) -> str:
    if catalog_name == "left_bowl_at_reset":
        return role_binding["left_bowl"]
    if catalog_name == "right_bowl_at_reset":
        return role_binding["right_bowl"]
    return STATIC_OBJECTS[catalog_name]


def _contact(tick: dict, a: str, b: str) -> dict | None:
    return tick["contacts"].get(f"{a}__{b}") or tick["contacts"].get(f"{b}__{a}")


def in_contact(tick: dict, a: str, b: str) -> bool | None:
    c = _contact(tick, a, b)
    return None if c is None else c.get("in_contact")


def force_on(tick: dict, body: str, other: str) -> np.ndarray | None:
    """World force on `body` from `other` (RoboLab get_contact_force(body, other) semantics)."""
    c = tick["contacts"].get(f"{body}__{other}")
    if c is not None and c.get("net_force") is not None:
        return np.asarray(c["net_force"], dtype=np.float64)
    c = tick["contacts"].get(f"{other}__{body}")
    if c is not None and c.get("net_force") is not None:
        return -np.asarray(c["net_force"], dtype=np.float64)
    return None


def supported_on_surface(tick: dict, obj: str, surface: str) -> bool | None:
    """world_state.is_supported_on_surface: |F|>=0.1 N, Fz>0, Fz >= |F| cos 45deg (force on obj from surface)."""
    f = force_on(tick, obj, surface)
    if f is None:
        return None
    mag = float(np.linalg.norm(f))
    if mag < CONTACT_FORCE_N or f[2] <= 0:
        return False
    return bool(f[2] >= mag * math.cos(math.radians(SUPPORT_CONE_DEG)))


def centroid_in_footprint(tick: dict, obj: str, surface: str, tol: float = FOOTPRINT_TOL_M) -> bool:
    c = tick["objects"][obj]["centroid"]
    lo, hi = tick["objects"][surface]["bbox_min"], tick["objects"][surface]["bbox_max"]
    return bool(lo[0] - tol <= c[0] <= hi[0] + tol and lo[1] - tol <= c[1] <= hi[1] + tol)


def cone_geometry(tick: dict, target: str, reference: str, relation: str) -> dict:
    p = np.asarray(tick["objects"][target]["robot_frame"], dtype=np.float64)
    q = np.asarray(tick["objects"][reference]["robot_frame"], dtype=np.float64)
    v = (p - q)[:2]
    dist = float(np.linalg.norm(v))
    ax = np.asarray(AXES[relation])
    if dist <= 1e-6:
        return {"value": False, "angle_to_axis_deg": None, "boundary_margin_deg": None, "xy_distance_m": dist,
                "near_boundary": True, "centers_within_1cm": True}
    cos_t = float(np.clip(v @ ax / dist, -1.0, 1.0))
    angle = math.degrees(math.acos(cos_t))
    value = bool(float(v @ ax) > 0 and cos_t >= math.cos(math.radians(CONE_DEG)))
    margin = abs(angle - CONE_DEG)
    return {"value": value, "angle_to_axis_deg": angle, "boundary_margin_deg": margin, "xy_distance_m": dist,
            "near_boundary": bool(margin < BOUNDARY_DEG), "centers_within_1cm": bool(dist < CENTER_MIN_M)}


def stored_study(tick: dict, goal_id: str) -> dict | None:
    return (tick.get("study") or {}).get(goal_id)


def relation_truth(tick: dict, scene_id: str, goal: dict, role_binding: dict | None, relation: str,
                   target_name: str, reference_name: str, require_table: bool) -> dict:
    """Instantaneous truth of `target relation reference` (+ table support if required) with provenance.

    relation in: left_of/right_of/in_front_of/behind (pinned cone), on_top_supported (centroid in reference
    footprint + supported on reference), stacked_on (pinned open-top containment + mover/reference contact).
    """
    target = asset_name(target_name, role_binding)
    reference = asset_name(reference_name, role_binding)
    stored = stored_study(tick, goal["goal_id"])
    stored_roles_match = bool(stored and stored.get("mover") == target and stored.get("reference") == reference)
    out: dict[str, Any] = {"target_asset": target, "reference_asset": reference, "relation": relation,
                           "require_table_support": require_table, "label_version": LABEL_VERSION}
    if relation in AXES:
        geo = cone_geometry(tick, target, reference, relation)
        value = geo["value"]
        out["cone"] = geo
        out["source"] = "recomputed pinned vector cone (robot frame, 45 deg) from saved robot_frame root positions"
        if stored_roles_match and goal["relation"] == relation:
            out["stored_relation"] = bool(stored["relation"])
            out["stored_agrees"] = bool(stored["relation"]) == value
        boundary = geo["near_boundary"] or geo["centers_within_1cm"]
        out["boundary_flag"] = boundary
        out["boundary_reason"] = ("centers_within_1cm" if geo["centers_within_1cm"] else
                                  "within_5deg_of_cone_boundary" if geo["near_boundary"] else None)
    elif relation == "on_top_supported":
        footprint = centroid_in_footprint(tick, target, reference)
        support = supported_on_surface(tick, target, reference)
        value = bool(footprint and support)
        out.update({"centroid_in_footprint": footprint, "supported_on_reference": support,
                    "source": "centroid_in_footprint(tol 0.01 m) AND is_supported_on_surface(target, reference) "
                              "recomputed from saved centroid/AABB and pairwise net contact force"})
        if stored_roles_match and goal["relation"] == "on_top_supported":
            out["stored_relation"] = bool(stored["relation"])
            out["stored_support"] = bool(stored["support"])
            out["stored_agrees"] = (bool(stored["relation"]) == footprint) and (bool(stored["support"]) == bool(support))
        out["boundary_flag"] = False
        out["boundary_reason"] = None
    elif relation == "stacked_on":
        if not stored_roles_match:
            raise ValueError(f"stacked_on needs the stored S5 predicate for {goal['goal_id']}")
        contained = bool(stored["relation"])
        contact = bool(stored["support"])
        value = bool(contained and contact)
        out.update({"in_opentop_container": contained, "target_reference_contact": contact,
                    "source": "stored pinned in_opentop_container(tol 0.01 m) AND in_contact(target, reference)"})
        out["boundary_flag"] = False
        out["boundary_reason"] = None
    else:
        raise ValueError(relation)
    if require_table:
        table = in_contact(tick, target, "table")
        out["target_table_contact"] = table
        value = bool(value and table)
    out["value"] = bool(value)
    return out


def a_label(tick: dict, scene_id: str, goal: dict, role_binding: dict | None) -> dict:
    """Scene question (both subject orders share one physical predicate)."""
    return relation_truth(tick, scene_id, goal, role_binding, goal["relation"], goal["target"], goal["reference"], False)


def requires_table_support(prompt: str) -> bool:
    return "on the table" in prompt.lower()


def c_label(tick: dict, scene_id: str, goal: dict, role_binding: dict | None, item: dict) -> dict:
    """Requested arrangement of one instruction (form-specific relation from the catalog's gold_B)."""
    gold = item["gold_B"]
    return relation_truth(tick, scene_id, goal, role_binding, gold["relation"], gold["target"], gold["reference"],
                          requires_table_support(item["prompt"]))


def grasp_state(tick: dict, objects: list[str]) -> dict:
    return {o: in_contact(tick, "gripper", o) for o in objects}


def bowl_identity(tick0: dict, tick: dict, role_binding: dict) -> dict:
    moved = {}
    for name in (role_binding["left_bowl"], role_binding["right_bowl"]):
        a = np.asarray(tick0["objects"][name]["pos"], dtype=np.float64)
        b = np.asarray(tick["objects"][name]["pos"], dtype=np.float64)
        moved[name] = float(np.linalg.norm((b - a)[:2]))
    both = all(m > BOWL_IDENTITY_MOVE_M for m in moved.values())
    return {"xy_displacement_m": moved, "both_moved": both, "threshold_m": BOWL_IDENTITY_MOVE_M}


# ---------------------------------------------------------------- projection (visibility pre-check only)
def quat_wxyz_to_matrix(q) -> np.ndarray:
    w, x, y, z = [float(v) for v in q]
    n = math.sqrt(w * w + x * x + y * y + z * z)
    w, x, y, z = w / n, x / n, y / n, z / n
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def project(points_w: np.ndarray, camera: dict) -> tuple[np.ndarray, np.ndarray]:
    """ROS optical convention (x right, y down, z forward): returns pixel uv (N,2) and depth (N,)."""
    rot = quat_wxyz_to_matrix(camera["quat_w_ros"])
    c = np.asarray(camera["pos_w"], dtype=np.float64)
    pc = (np.asarray(points_w, dtype=np.float64) - c) @ rot
    k = np.asarray(camera["intrinsics"], dtype=np.float64)
    z = pc[:, 2]
    with np.errstate(divide="ignore", invalid="ignore"):
        u = k[0, 0] * pc[:, 0] / z + k[0, 2]
        v = k[1, 1] * pc[:, 1] / z + k[1, 2]
    return np.stack([u, v], axis=1), z


def bbox_corners(obj: dict) -> np.ndarray:
    lo, hi = np.asarray(obj["bbox_min"]), np.asarray(obj["bbox_max"])
    return np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])


def object_visibility(tick: dict, obj: str, cameras: dict, image_hw: dict) -> dict:
    """Projected-centre and AABB-overlap pre-check per view (no occlusion test; not a human review)."""
    rec = tick["objects"][obj]
    out = {}
    for view, cam in cameras.items():
        h, w = image_hw[view]
        native_h, native_w = 720, 1280
        sx, sy = w / native_w, h / native_h
        uv_c, z_c = project(np.asarray([rec["centroid"]]), cam)
        uv, z = project(bbox_corners(rec), cam)
        centre_in = bool(z_c[0] > 0 and 0 <= uv_c[0, 0] < native_w and 0 <= uv_c[0, 1] < native_h)
        if (z > 0).all():
            u0, v0 = uv[:, 0].min(), uv[:, 1].min()
            u1, v1 = uv[:, 0].max(), uv[:, 1].max()
            area = max(u1 - u0, 0) * max(v1 - v0, 0)
            iu0, iv0, iu1, iv1 = max(u0, 0), max(v0, 0), min(u1, native_w), min(v1, native_h)
            inter = max(iu1 - iu0, 0) * max(iv1 - iv0, 0)
            frac = float(inter / area) if area > 0 else 0.0
            px = float(math.sqrt(inter) * math.sqrt(sx * sy))
        else:
            frac, px = 0.0, 0.0
        out[view] = {"centre_in_image": centre_in, "bbox_fraction_in_image": frac,
                     "approx_visible_extent_px_at_presented_resolution": px,
                     "centre_uv_native": [float(uv_c[0, 0]), float(uv_c[0, 1])], "centre_depth_m": float(z_c[0])}
    return out
