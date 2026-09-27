"""Rescore episodes with the frozen scorer and extract the frozen baseline feature schema (feature_schema.json).

usage: python -m experiments.robolab_workshop.features --runs <root>/runs --out <file.jsonl> [--phase confirmation]
         [--calibration <analysis_calibration.json>]

Only information available at the primary request boundary (pre-request tick) and the proposed action chunk enters
the baseline features. The execution-event target comes from the mapped executed prefix via scoring.event_window.
"""
from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path

import numpy as np

from . import kinematics, scoring
from .catalog import SCENES
from .scripted import grasp_plan, place_target


def load_episode(ep_dir: Path) -> dict | None:
    marker = ep_dir / "COMPLETE.json"
    if not marker.exists():
        return None
    adir = Path(json.loads(marker.read_text())["attempt_dir"])
    result = json.loads((adir / "result.json").read_text())
    ticks = [json.loads(x) for x in gzip.open(adir / "states.jsonl.gz", "rt")]
    requests = [json.loads(x) for x in (adir / "requests.jsonl").read_text().splitlines() if x.strip()]
    actions = np.load(adir / "actions.npz")
    return {"dir": adir, "result": result, "ticks": ticks, "requests": requests,
            "postprocessed": actions["postprocessed"]}


def calibrate(episodes: list[dict], max_ticks: int = 4000) -> dict:
    q, p = [], []
    for ep in episodes:
        for k in ep["ticks"][:: max(1, len(ep["ticks"]) // 40)]:
            q.append(k["joint_pos"][:7])
            p.append(k["tcp"])
        if len(q) >= max_ticks:
            break
    return kinematics.fit_tcp(np.array(q), np.array(p))


def goal_region(tick0: dict, scene_id: str, goal_id: str) -> dict:
    mover, reference = tick0["study"][goal_id]["mover"], tick0["study"][goal_id]["reference"]
    place = place_target(tick0, scene_id, goal_id, mover, reference, grasp_plan(tick0, scene_id, mover))
    o = tick0["objects"][mover]
    half_h = (o["bbox_max"][2] - o["bbox_min"][2]) / 2
    return {"centre": [*place["mover_centre_xy"], place["bottom_z"] + half_h]}


def role(scene_id: str, goal_id: str, tick0: dict, name: str) -> str:
    st = tick0["study"][goal_id]
    return "mover" if name == st["mover"] else "reference" if name == st["reference"] else \
        "movable_other" if name in SCENES[scene_id]["movable"] else "fixed_other"


def episode_features(ep: dict, calib: dict) -> dict:
    r = ep["result"]
    scene_id, goal_id = r["scene_id"], r["goal_id"]
    ticks, reqs = ep["ticks"], ep["requests"]
    horizon = r["denominators"]["planned_actions"]
    score = scoring.score_episode(ticks, reqs, scene_id, goal_id, horizon)
    row = {k: r[k] for k in ("episode_id", "model_id", "scene_id", "goal_id", "form", "prompt_id", "state_slot",
                             "block_id", "phase", "status")}
    row.update({"stable_ever": score["stable_ever"], "stable_at_final": score["stable_at_final"],
                "stratum": score["stratum"], "study_goal_first_hit": score["study_goal_first_hit"],
                "native_matched_task": score["native_matched_task"],
                "native_matched_task_first_hit": score["native_matched_task_first_hit"],
                "native_base_task_first_hit": score["native_base_task_first_hit"],
                "failure_stage": score["failure_stage"], "lift_ever": score["lift_ever"],
                "mover_final_displacement_m": score["mover_final_displacement_m"],
                "mover_final_xy": score["mover_final_xy"], "complete_horizon": score["complete_horizon"],
                "reference_disturbed": (score["reference_disturbance"] or {}).get("disturbed"),
                "primary_window": score["primary_window"], "window_primary": score["windows"]["primary"],
                "window_request0": score["windows"]["request0"], "scorer_version": score["scorer_version"]})
    pw = score["primary_window"]
    win = score["windows"]["primary"]
    row["event"] = None if win is None else win.get("event")
    if pw is None:
        row["features"] = None
        return row
    k = pw["pre_tick"]
    tick, tick0 = ticks[k], ticks[0]
    mover, reference = score["mover"], score["reference"]
    c = lambda n, t: (np.array(t["objects"][n]["bbox_min"]) + np.array(t["objects"][n]["bbox_max"])) / 2
    rel = c(mover, tick) - c(reference, tick)
    region = goal_region(tick0, scene_id, goal_id)
    req = next(x for x in reqs if x["request_index"] == pw["request_index"])
    chunk = ep["postprocessed"][req["request_index"]]
    names = [n for n in tick["objects"] if n != "table"]
    best = (np.inf, None)
    for a in chunk:
        p = kinematics.tcp(a[:7], calib)
        for n in names:
            d = kinematics.aabb_distance(p, tick["objects"][n]["bbox_min"], tick["objects"][n]["bbox_max"])
            if d < best[0]:
                best = (d, n)
    z0 = ticks[0]["objects"][mover]["pos"][2]
    prior = ticks[: k + 1]
    row["features"] = {
        "mover_rel_ref_x_m": float(rel[0]), "mover_rel_ref_y_m": float(rel[1]), "mover_rel_ref_z_m": float(rel[2]),
        "mover_dist_to_goal_region_m": float(np.linalg.norm(c(mover, tick) - np.array(region["centre"]))),
        "goal_true_now": float(bool(tick["study"][goal_id]["goal"])),
        "gripper_closed_fraction": float(tick["gripper_closed_fraction"]),
        "chunk_fk_min_dist_m": float(best[0]),
        "chunk_fk_nearest_object_role": role(scene_id, goal_id, tick0, best[1]) if best[1] else "none",
        "prior_target_contact": float(any(t["contacts"].get(f"gripper__{mover}", {}).get("in_contact") for t in prior)),
        "prior_target_lift": float(any(t["objects"][mover]["pos"][2] - z0 >= 0.02 for t in prior)),
    }
    return row


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--phase", default=None)
    ap.add_argument("--calibration", type=Path, default=None)
    ap.add_argument("--episodes", default="")
    args = ap.parse_args()
    dirs = sorted(d for d in (args.runs / "episodes").iterdir() if d.is_dir())
    want = set(filter(None, args.episodes.split(",")))
    if want:
        dirs = [d for d in dirs if d.name in want]
    if args.phase:
        dirs = [d for d in dirs if ("-D00-" in d.name) == (args.phase == "development")]
    if args.calibration and args.calibration.exists():
        calib = json.loads(args.calibration.read_text())
    else:
        eps = [e for e in (load_episode(d) for d in dirs[:12]) if e]
        calib = calibrate(eps)
        if args.calibration:
            args.calibration.write_text(json.dumps(calib, indent=2))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with args.out.open("w") as f:
        for d in dirs:
            ep = load_episode(d)
            if ep is None:
                f.write(json.dumps({"episode_id": d.name, "status": "incomplete_no_marker"}) + "\n")
                continue
            f.write(json.dumps(episode_features(ep, calib), default=float) + "\n")
            n += 1
    print(json.dumps({"episodes": n, "calibration": calib}))


if __name__ == "__main__":
    main()
