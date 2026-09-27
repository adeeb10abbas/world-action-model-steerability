"""Pure scoring over per-tick physical records (no simulator import).

Tick 0 is the restored start (t=0, before the first action); tick i is the state after executed action i.
Request r starts at tick `pre_tick` and its executed prefix covers ticks pre_tick+1 .. pre_tick+n_executed.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from .catalog import ALTERNATIVES, SCENES, THRESHOLDS

EPS = 1e-9


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """Inclusive index runs where mask is true."""
    runs, start = [], None
    for i, v in enumerate(mask):
        if v and start is None:
            start = i
        elif not v and start is not None:
            runs.append((start, i - 1))
            start = None
    if start is not None:
        runs.append((start, len(mask) - 1))
    return runs


def _first_dwell(mask: np.ndarray, t: np.ndarray, dwell: float, lo: int = 0, hi: int | None = None) -> dict | None:
    """First run inside [lo, hi] whose timestamp span reaches dwell. Returns start/complete indices and times."""
    hi = len(mask) - 1 if hi is None else hi
    sub = mask[lo:hi + 1]
    for a, b in _runs(sub):
        a, b = a + lo, b + lo
        span = t[b] - t[a]
        if span + EPS >= dwell:
            done = a + int(np.searchsorted(t[a:b + 1] - t[a], dwell - EPS))
            return {"start_tick": int(a), "start_t": float(t[a]), "complete_tick": int(done),
                    "complete_t": float(t[done]), "run_end_tick": int(b), "run_span_s": float(span)}
    return None


def _first_true(mask: np.ndarray, t: np.ndarray) -> float | None:
    idx = np.flatnonzero(mask)
    return float(t[idx[0]]) if idx.size else None


def arrays(ticks: list[dict], scene_id: str, goal_id: str) -> dict[str, Any]:
    scene = SCENES[scene_id]
    t = np.array([k["t"] for k in ticks], dtype=np.float64)
    names = list(ticks[0]["objects"].keys())
    pos = {n: np.array([k["objects"][n]["pos"] for k in ticks]) for n in names}
    vel = {n: np.array([k["objects"][n]["lin_vel"] for k in ticks]) for n in names}
    grip = {n: np.array([bool(k["contacts"].get(f"gripper__{n}", {}).get("in_contact")) for k in ticks]) for n in names}
    study = {g: {f: np.array([bool(k["study"][g][f]) for k in ticks]) for f in ("relation", "support", "detached", "goal")}
             for g in scene["goals"]}
    mover = ticks[0]["study"][goal_id]["mover"]
    reference = ticks[0]["study"][goal_id]["reference"]
    tcp_dist = {n: np.array([k["objects"][n]["tcp_obb_distance"] for k in ticks]) for n in names}
    native = {task: np.array([bool(k["native"].get(task)) for k in ticks]) for task in ticks[0]["native"]}
    return {"t": t, "names": names, "pos": pos, "vel": vel, "grip": grip, "study": study, "mover": mover,
            "reference": reference, "tcp_dist": tcp_dist, "native": native}


SCORER_VERSION = 2
SPEED_DEFINITION = ("backward finite difference of the mover root position between consecutive 15 Hz ticks "
                    "(|p_i - p_(i-1)| / (t_i - t_(i-1))); tick 0 uses 0. PhysX-reported rigid-body velocities of "
                    "resting objects keep solver jitter of 1-3 cm/s at constant pose, so they are recorded but not used.")


def mover_speed(A: dict, name: str) -> np.ndarray:
    p, t = A["pos"][name], A["t"]
    speed = np.zeros(len(t))
    if len(t) > 1:
        speed[1:] = np.linalg.norm(np.diff(p, axis=0), axis=1) / np.maximum(np.diff(t), EPS)
    return speed


def score_episode(ticks: list[dict], requests: list[dict], scene_id: str, goal_id: str, horizon_ticks: int) -> dict:
    scene = SCENES[scene_id]
    goal = scene["goals"][goal_id]
    A = arrays(ticks, scene_id, goal_id)
    t, mover, reference = A["t"], A["mover"], A["reference"]
    th = THRESHOLDS
    complete = len(ticks) == horizon_ticks + 1
    goal_mask = A["study"][goal_id]["goal"]
    speed = mover_speed(A, mover)
    stable_mask = goal_mask & (speed < th["stable_speed_mps"])
    stable = _first_dwell(stable_mask, t, th["stable_dwell_s"])
    final_run = None
    if stable_mask[-1]:
        start = len(stable_mask) - 1
        while start > 0 and stable_mask[start - 1]:
            start -= 1
        final_run = {"start_tick": start, "span_s": float(t[-1] - t[start])}
    stable_final = bool(final_run and final_run["span_s"] + EPS >= th["stable_dwell_s"])
    z0 = A["pos"][mover][0, 2]
    lift_mask = A["pos"][mover][:, 2] - z0 >= th["lift_m"]
    lift = _first_dwell(lift_mask, t, th["lift_dwell_s"])
    disturbance = {}
    for n in A["names"]:
        if n == mover:
            continue
        d = np.linalg.norm(A["pos"][n] - A["pos"][n][0], axis=1)
        disturbance[n] = {"max_displacement_m": float(d.max()), "disturbed": bool(d.max() > th["reference_disturbance_m"])}
    mover_contact = A["grip"][mover]
    initially_true = bool(goal_mask[0])
    native_base = A["native"].get(scene["base_task"])
    matched = goal["native_task"]
    if scene_id == "S5":
        # Native bowl tasks are asset-named; the matched task follows the frozen reset role binding.
        left_on_right = "BowlStackingLeftOnRightTask" if mover == "bowl_2" else "BowlStackingRightOnLeftTask"
        matched = left_on_right
    failure_stage = ("stable" if stable else "goal_unstable" if goal_mask.any() else "lift_no_goal" if lift
                     else "contact_no_lift" if mover_contact.any() else "no_mover_contact")
    primary = primary_window(A, requests, scene)
    windows = {"primary": event_window(A, requests, primary["request_index"], scene_id, goal_id) if primary else None,
               "request0": event_window(A, requests, 0, scene_id, goal_id) if requests else None}
    return {
        "scorer_version": SCORER_VERSION, "complete_horizon": complete, "n_ticks": len(ticks), "horizon_ticks": horizon_ticks,
        "mover": mover, "reference": reference,
        "initial_goal_true": initially_true, "stratum": "maintenance" if initially_true else "achievement",
        "native_base_task": scene["base_task"],
        "native_base_task_first_hit": _first_true(native_base, t) if native_base is not None else None,
        "native_matched_task": matched,
        "native_matched_task_first_hit": (_first_true(A["native"][matched], t) if matched in A["native"] else None) if matched else None,
        "study_goal_first_hit": _first_true(goal_mask, t),
        "study_relation_first_hit": _first_true(A["study"][goal_id]["relation"], t),
        "stable_ever": stable is not None, "stable": stable,
        "stable_at_final": stable_final, "final_goal_true": bool(goal_mask[-1]), "final_stable_run": final_run,
        "lift": lift, "lift_ever": lift is not None,
        "mover_contact_ever": bool(mover_contact.any()),
        "mover_final_displacement_m": float(np.linalg.norm(A["pos"][mover][-1] - A["pos"][mover][0])),
        "mover_final_xy": A["pos"][mover][-1][:2].tolist(),
        "reference_disturbance": disturbance.get(reference), "other_disturbance": disturbance,
        "failure_stage": failure_stage,
        "primary_window": primary, "windows": windows,
    }


def primary_window(A: dict, requests: list[dict], scene: dict) -> dict | None:
    if not requests:
        return None
    movable = [n for n in scene["movable"] if n in A["tcp_dist"]]
    for req in requests:
        k = req["pre_tick"]
        d = {n: float(A["tcp_dist"][n][k]) for n in movable}
        if min(d.values()) <= THRESHOLDS["primary_window_tcp_distance_m"] + EPS:
            return {"request_index": req["request_index"], "fallback": False, "pre_tick": k,
                    "nearest_object": min(d, key=d.get), "distance_m": min(d.values())}
    k = requests[0]["pre_tick"]
    d = {n: float(A["tcp_dist"][n][k]) for n in movable}
    return {"request_index": requests[0]["request_index"], "fallback": True, "pre_tick": k,
            "nearest_object": min(d, key=d.get), "distance_m": min(d.values())}


def event_window(A: dict, requests: list[dict], request_index: int, scene_id: str, goal_id: str) -> dict:
    req = next(r for r in requests if r["request_index"] == request_index)
    lo, n = req["pre_tick"], req["n_executed"]
    hi = lo + n
    t = A["t"]
    if n <= 0 or hi >= len(t):
        return {"request_index": request_index, "event": None, "reason": "execution_interval_unavailable",
                "pre_tick": lo, "n_executed": n}
    th = THRESHOLDS
    mover = A["mover"]
    # 1. wrong-object manipulation
    wrong = []
    for o in A["names"]:
        if o == mover:
            continue
        run = _first_dwell(A["grip"][o], t, th["wrong_object_contact_s"], lo, hi)
        if run is None:
            continue
        p = A["pos"][o][lo:hi + 1]
        moved = float(np.linalg.norm(p - p[0], axis=1).max())
        rose = float((p[:, 2] - p[0, 2]).max())
        if moved >= th["wrong_object_move_m"] - EPS or rose >= th["wrong_object_move_m"] - EPS:
            wrong.append({"object": o, "contact_run": run, "moved_m": moved, "rose_m": rose})
    # 2. contradictory released placement
    contradictory = []
    alternatives = ALTERNATIVES[scene_id][goal_id]
    contact = A["grip"][mover]
    releases = [i for i in range(lo + 1, hi + 1) if contact[i - 1] and not contact[i]]
    if releases and alternatives:
        intended = A["study"][goal_id]["relation"]
        alt_true = {a: A["study"][a]["relation"] & A["study"][a]["support"] & A["study"][a]["detached"] for a in alternatives}
        n_alt = np.sum([alt_true[a] for a in alternatives], axis=0)
        for a in alternatives:
            mask = alt_true[a] & ~intended & (n_alt == 1)
            run = _first_dwell(mask, t, th["contradictory_support_s"], releases[0], hi)
            if run is not None:
                contradictory.append({"alternative": a, "release_tick": releases[0], "run": run})
    event = 1 if (wrong or contradictory) else 0
    any_contact = any(A["grip"][o][lo + 1:hi + 1].any() for o in A["names"])
    any_move = any(float(np.linalg.norm(A["pos"][o][lo:hi + 1] - A["pos"][o][lo], axis=1).max()) >= th["wrong_object_move_m"]
                   for o in A["names"])
    mover_contact = bool(contact[lo + 1:hi + 1].any())
    lifted_then_dropped = bool(releases) and bool((A["pos"][mover][releases[0]:hi + 1, 2] - A["pos"][mover][lo, 2] >= th["lift_m"]).any()) \
        and not bool(A["study"][goal_id]["goal"][hi])
    return {"request_index": request_index, "pre_tick": lo, "n_executed": n, "t_start": float(t[lo]), "t_end": float(t[hi]),
            "event": event, "wrong_object": wrong, "contradictory_release": contradictory,
            "neutral_no_decision": bool(event == 0 and not any_contact and not any_move),
            "goal_consistent_interaction": bool(event == 0 and mover_contact),
            "physical_failure": bool(event == 0 and lifted_then_dropped)}
