"""Starting-state registration: canonical development starts (D00) and seeded confirmation proposals (C01-C08).

State directory layout: <state_root>/<slot>/{state.npz, first_obs.npz, receipt.json}
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
import traceback
from pathlib import Path

import numpy as np

SETTLE_STEPS = 15          # 1.0 s at 15 Hz
DRIFT_WINDOW_STEPS = 9     # last 0.5 s: 9 ticks span 8/15 = 0.533 s
DRIFT_LIMIT_M = 0.002


def save_state(slot_dir: Path, env, state: dict, first: dict, extra: dict) -> dict:
    from . import sim_env
    from .catalog import sha256_file

    slot_dir.mkdir(parents=True, exist_ok=True)
    flat = sim_env.flatten_state(state)
    np.savez_compressed(slot_dir / "state.npz", **flat)
    np.savez_compressed(slot_dir / "first_obs.npz", **first)
    receipt = {**extra, "state_sha256": sha256_file(slot_dir / "state.npz"),
               "first_obs_sha256": sha256_file(slot_dir / "first_obs.npz"),
               "first_obs_array_sha256": {k: _arr_sha(v) for k, v in first.items()}}
    (slot_dir / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True, default=str))
    return receipt


def _arr_sha(a) -> str:
    import hashlib
    a = np.ascontiguousarray(a)
    return hashlib.sha256(f"{a.dtype.str}{a.shape}".encode() + a.tobytes()).hexdigest()


def load_state(slot_dir: Path) -> tuple[dict, dict, dict]:
    from . import sim_env
    with np.load(slot_dir / "state.npz") as z:
        state = sim_env.unflatten_state({k: z[k] for k in z.files})
    with np.load(slot_dir / "first_obs.npz") as z:
        first = {k: z[k] for k in z.files}
    receipt = json.loads((slot_dir / "receipt.json").read_text())
    return state, first, receipt


def settle_and_check(env) -> tuple[bool, dict]:
    ticks = env.settle(SETTLE_STEPS)
    names = env.named_objects
    window = ticks[-DRIFT_WINDOW_STEPS:]
    drift = {n: float(np.linalg.norm(np.asarray(window[-1]["objects"][n]["pos"]) - np.asarray(window[0]["objects"][n]["pos"])))
             for n in names}
    finite = all(np.isfinite(t["objects"][n]["pos"]).all() for t in ticks for n in names)
    ok = finite and max(drift.values()) < DRIFT_LIMIT_M
    return ok, {"drift_last_0p5s_m": drift, "finite": finite, "settle_steps": SETTLE_STEPS,
                "drift_window_span_s": window[-1]["t"] - window[0]["t"]}


def register_canonical(env, scene_id: str, out: Path) -> dict:
    env.reset_native()
    ok, settle = settle_and_check(env)
    state = env.capture_state()
    env.restore_state(state)
    roles = env.bind_roles()
    tick0 = env.tick_record()
    first = env.raw_observation()
    slot = f"{scene_id}-D00"
    extra = {"slot": slot, "scene_id": scene_id, "kind": "canonical_native_start", "settle": settle, "settle_ok": ok,
             "role_binding": roles, "tick0": tick0, "tcp_definition": env.tcp_definition,
             "initial_native": tick0["native"], "initial_study": tick0["study"], "created": time.time(),
             "cfg_changes": env.cfg_changes, "native_base_term": env.native_base_term}
    return save_state(out / slot, env, state, first, extra)


JUDGE_VERSION = 3


def judge_scripted(ticks: list[dict], score: dict, scene_id: str, goal_id: str) -> tuple[bool, str | None, dict]:
    """A scripted demonstration passes when the goal is stably achieved after the mover was picked up.

    Judge v1 rejected every initially true goal outright; v2 treats those maintenance goals like the rest: the
    controller must lift the mover and re-establish the goal with a >=1 s stable dwell that starts after lift-off.
    v3 uses the scorer-v2 finite-difference mover speed.
    """
    from .scoring import THRESHOLDS, _first_dwell, arrays, mover_speed

    A = arrays(ticks, scene_id, goal_id)
    speed = mover_speed(A, A["mover"])
    stable_mask = A["study"][goal_id]["goal"] & (speed < THRESHOLDS["stable_speed_mps"])
    lift = score["lift"]
    after = _first_dwell(stable_mask, A["t"], THRESHOLDS["stable_dwell_s"], lo=lift["start_tick"]) if lift else None
    ref = score["reference_disturbance"] or {}
    ok = after is not None and not ref.get("disturbed", False)
    if ok:
        reason = None
    elif lift is None:
        reason = score["failure_stage"]
    elif after is None:
        reason = "goal_not_stable_after_lift" if A["study"][goal_id]["goal"][lift["start_tick"]:].any() else "lift_no_goal"
    else:
        reason = "reference_disturbed"
    return ok, reason, {"stable_after_lift": after, "initial_goal_true": score["initial_goal_true"],
                        "stable_at_final": score["stable_at_final"], "reference_disturbed": ref.get("disturbed")}


def rejudge(out_dir: Path, scene_id: str) -> list[dict]:
    """Re-apply the current judge to saved scripted tick logs without re-running; originals stay untouched."""
    import gzip
    from .scoring import score_episode

    rows = []
    for line in (out_dir / "scripted_attempts.jsonl").read_text().splitlines():
        rec = json.loads(line)
        path = out_dir / f"{rec['slot']}-{rec['goal_id']}-ticks.jsonl.gz"
        if not path.exists():
            continue
        with gzip.open(path, "rt") as f:
            ticks = [json.loads(x) for x in f]
        score = score_episode(ticks, [], scene_id, rec["goal_id"], len(ticks) - 1)
        ok, reason, judge = judge_scripted(ticks, score, scene_id, rec["goal_id"])
        rows.append({"slot": rec["slot"], "goal_id": rec["goal_id"], "attempt_t": rec["t"], "original_status": rec["status"],
                     "original_reason": rec["reason"], "status": "pass" if ok else "fail", "reason": reason,
                     "judge": judge, "judge_version": JUDGE_VERSION, "ticks_sha256": _file_sha(path), "t": time.time()})
    with (out_dir / "scripted_judgments.jsonl").open("a") as f:
        for r in rows:
            f.write(json.dumps(r, default=str) + "\n")
    return rows


def _file_sha(path: Path) -> str:
    from .catalog import sha256_file
    return sha256_file(path)


def scripted_checks(env, scene_id: str, slot_dir: Path, out_dir: Path, goals: list[str] | None = None,
                    budget=None, fail_fast: bool = False) -> list[dict]:
    """Try each physical goal once from the registered state with the scripted controller."""
    from .catalog import SCENES
    from .scoring import score_episode
    from . import scripted

    state, _first, receipt = load_state(slot_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    receipts = []
    for goal_id in goals or list(SCENES[scene_id]["goals"]):
        if budget is not None and not budget():
            receipts.append({"goal_id": goal_id, "status": "not_attempted_budget"})
            break
        env.restore_state(state)
        env.bind_roles()
        t0 = time.time()
        try:
            run = scripted.run_goal(env, scene_id, goal_id)
            ticks = run["ticks"]
            score = score_episode(ticks, [], scene_id, goal_id, len(ticks) - 1)
            ok, reason, judge = judge_scripted(ticks, score, scene_id, goal_id)
            rec = {"goal_id": goal_id, "status": "pass" if ok else "fail", "reason": reason,
                   "stable": score["stable"], "lift": score["lift"], "failure_stage": score["failure_stage"],
                   "native_matched_task_first_hit": score["native_matched_task_first_hit"],
                   "reference_disturbance": score["reference_disturbance"], "grasp": run["grasp"], "place": run["place"],
                   "mover": run["mover"], "reference": run["reference"], "n_ticks": len(ticks), "wall_s": time.time() - t0,
                   "final_mover_xy": score["mover_final_xy"], "judge": judge, "judge_version": JUDGE_VERSION}
            import gzip
            with gzip.open(out_dir / f"{slot_dir.name}-{goal_id}-ticks.jsonl.gz", "wt") as f:
                for tk in ticks:
                    f.write(json.dumps(tk) + "\n")
        except Exception as error:
            rec = {"goal_id": goal_id, "status": "fail", "reason": f"controller_error: {type(error).__name__}: {error}",
                   "traceback": traceback.format_exc()}
        rec.update(slot=slot_dir.name, state_sha256=receipt["state_sha256"], t=time.time(),
                   judge_version=JUDGE_VERSION)
        receipts.append(rec)
        with (out_dir / "scripted_attempts.jsonl").open("a") as f:
            f.write(json.dumps(rec, default=str) + "\n")
        print(json.dumps({k: rec.get(k) for k in ("slot", "goal_id", "status", "reason", "failure_stage")}), flush=True)
        if fail_fast and rec["status"] != "pass":
            # A failed goal rejects the candidate for all goals; remaining goals are not attempted.
            break
    return receipts


PROPOSAL_SEED = 8200
MAX_PROPOSALS = 32
XY_RANGE_M = 0.04
YAW_RANGE_DEG = 10.0
DISTINCT_M = 0.01
TARGET_ACCEPTED = 8
SCRIPTED_CAP = 140
EXTERIOR_CAMERAS = ("over_shoulder_left_camera", "over_shoulder_right_camera")


def proposal_rng(scene_id: str) -> np.random.Generator:
    return np.random.default_rng([PROPOSAL_SEED, int(scene_id[1:])])


def yaw_quat(theta: float) -> np.ndarray:
    return np.array([math.cos(theta / 2), 0.0, 0.0, math.sin(theta / 2)])


def quat_mul(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    w1, x1, y1, z1 = a
    w2, x2, y2, z2 = b
    return np.array([w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2, w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
                     w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2, w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2])


def make_proposals(scene_id: str, native_tick: dict) -> list[dict]:
    """All 32 proposals are drawn up front in a fixed order; objects are drawn in catalog `movable` order."""
    from .catalog import SCENES

    rng = proposal_rng(scene_id)
    out = []
    for i in range(MAX_PROPOSALS):
        poses = {}
        for name in SCENES[scene_id]["movable"]:
            dx, dy = rng.uniform(-XY_RANGE_M, XY_RANGE_M, size=2)
            dyaw = math.radians(rng.uniform(-YAW_RANGE_DEG, YAW_RANGE_DEG))
            pos0 = np.array(native_tick["objects"][name]["pos"])
            q0 = np.array(native_tick["objects"][name]["quat"])
            poses[name] = {"delta_xy_m": [float(dx), float(dy)], "delta_yaw_deg": math.degrees(dyaw),
                           "pos": [float(pos0[0] + dx), float(pos0[1] + dy), float(pos0[2])],
                           "quat": quat_mul(yaw_quat(dyaw), q0).tolist()}
        out.append({"proposal_id": f"{scene_id}-P{i + 1:02d}", "index": i + 1, "poses": poses})
    return out


def project_visible(env, tick: dict, names: list[str]) -> dict:
    """Object bbox centre projects inside at least one exterior policy image with positive depth (no occlusion test)."""
    origin = env.env.scene.env_origins[0].detach().cpu().numpy().astype(np.float64)
    out = {}
    for cam in EXTERIOR_CAMERAS:
        data = env.env.scene[cam].data
        c = data.pos_w[0].detach().cpu().numpy().astype(np.float64)
        from .scripted import quat_to_mat
        R = quat_to_mat(data.quat_w_ros[0].detach().cpu().numpy().astype(np.float64))
        K = data.intrinsic_matrices[0].detach().cpu().numpy().astype(np.float64)
        h, w = data.image_shape
        for n in names:
            o = tick["objects"][n]
            centre = (np.array(o["bbox_min"]) + np.array(o["bbox_max"])) / 2 + origin
            pc = R.T @ (centre - c)
            ok = pc[2] > 0.05
            u = K[0, 0] * pc[0] / pc[2] + K[0, 2] if ok else None
            v = K[1, 1] * pc[1] / pc[2] + K[1, 2] if ok else None
            inside = bool(ok and 0 <= u < w and 0 <= v < h)
            out.setdefault(n, {})[cam] = {"u": u, "v": v, "depth": float(pc[2]), "inside": inside}
    return {n: {"visible": any(v["inside"] for v in cams.values()), "cameras": cams} for n, cams in out.items()}


def evaluate_proposal(env, scene_id: str, base_state: dict, proposal: dict, previous_valid: list[dict]) -> dict:
    from .catalog import SCENES

    env.restore_state(base_state)
    env.set_object_poses({n: (np.array(p["pos"]), np.array(p["quat"])) for n, p in proposal["poses"].items()})
    t_start = env.tick_record()
    ok_settle, settle = settle_and_check(env)
    tick = env.tick_record()
    names = env.named_objects
    movable = list(SCENES[scene_id]["movable"])
    supported = {n: bool(tick["contacts"].get(f"{n}__table", tick["contacts"].get(f"table__{n}", {})).get("in_contact"))
                 for n in movable}

    def _pairs(tk):
        return {k: v.get("in_contact") for k, v in tk["contacts"].items()
                if not k.startswith("gripper__") and "table" not in k.split("__") and set(k.split("__")) & set(movable)}
    obj_pairs, pair_contact_start = _pairs(tick), _pairs(t_start)
    dz = {n: float(tick["objects"][n]["pos"][2] - t_start["objects"][n]["pos"][2]) for n in movable}
    # Native starts can include intended object-object contact (none of the five scenes do at D00); any contact
    # between task objects, or a settle height change above 5 mm, counts as unintended interpenetration.
    interpen = any(bool(v) for v in obj_pairs.values()) or any(bool(v) for v in pair_contact_start.values()) \
        or any(abs(v) > 0.005 for v in dz.values())
    visible = project_visible(env, tick, names)
    movers = sorted({g["mover"] for g in SCENES[scene_id]["goals"].values()})
    dists = {}
    for prev in previous_valid:
        dists[prev["proposal_id"]] = min(
            float(np.linalg.norm(np.array(tick["objects"][m]["pos"][:2]) - np.array(prev["settled_pos"][m][:2]))) for m in movers)
    checks = {"settle_ok": ok_settle, "supported": all(supported.values()), "no_interpenetration": not interpen,
              "visible": all(v["visible"] for v in visible.values()),
              "distinct": all(d >= DISTINCT_M for d in dists.values())}
    return {"proposal_id": proposal["proposal_id"], "index": proposal["index"], "poses": proposal["poses"],
            "valid": all(checks.values()), "checks": checks, "settle": settle, "supported": supported,
            "object_contacts": obj_pairs, "object_contacts_at_placement": pair_contact_start, "settle_dz_m": dz,
            "visibility": visible, "distinct_from_m": dists,
            "settled_pos": {n: tick["objects"][n]["pos"] for n in names}, "initial_study": tick["study"],
            "initial_native": tick["native"]}


def propose(env, scene_id: str, state_root: Path) -> list[dict]:
    """Evaluate all 32 seeded proposals in order; save every model-blind valid one as a candidate state."""
    base_state, _first, base_receipt = load_state(state_root / f"{scene_id}-D00")
    env.restore_state(base_state)
    native_tick = env.tick_record()
    proposals = make_proposals(scene_id, native_tick)
    cdir = state_root / "_candidates" / scene_id
    cdir.mkdir(parents=True, exist_ok=True)
    native_ref = {"proposal_id": f"{scene_id}-D00", "settled_pos": {n: native_tick["objects"][n]["pos"] for n in env.named_objects}}
    valid: list[dict] = []
    rows = []
    for prop in proposals:
        t0 = time.time()
        try:
            rec = evaluate_proposal(env, scene_id, base_state, prop, [native_ref] + valid)
        except Exception as error:
            rec = {"proposal_id": prop["proposal_id"], "index": prop["index"], "poses": prop["poses"], "valid": False,
                   "error": f"{type(error).__name__}: {error}", "traceback": traceback.format_exc()}
        rec["wall_s"] = time.time() - t0
        if rec["valid"]:
            state = env.capture_state()
            env.restore_state(state)
            roles = env.bind_roles()
            tick0 = env.tick_record()
            first = env.raw_observation()
            receipt = save_state(cdir / prop["proposal_id"], env, state, first, {
                "slot": None, "proposal_id": prop["proposal_id"], "scene_id": scene_id, "kind": "seeded_proposal",
                "seed": [PROPOSAL_SEED, int(scene_id[1:])], "proposal": prop, "role_binding": roles, "tick0": tick0,
                "initial_native": tick0["native"], "initial_study": tick0["study"], "tcp_definition": env.tcp_definition,
                "base_state_sha256": base_receipt["state_sha256"], "validity": {k: rec[k] for k in ("checks", "settle")},
                "camera_calibration": _cameras(env), "created": time.time()})
            rec["candidate_state_sha256"] = receipt["state_sha256"]
            rec["candidate_first_obs_sha256"] = receipt["first_obs_sha256"]
            valid.append(rec)
        rows.append(rec)
        with (cdir / "proposals.jsonl").open("a") as f:
            f.write(json.dumps(rec, default=str) + "\n")
        print(json.dumps({"proposal_id": rec["proposal_id"], "valid": rec["valid"], "checks": rec.get("checks"),
                          "error": rec.get("error")}), flush=True)
    return rows


def _cameras(env) -> dict:
    from .worker import camera_transforms
    return camera_transforms(env)


def claim_scripted_token(state_root: Path, label: str) -> str | None:
    """Global 140-attempt cap across scenes: claim the lowest free token directory atomically."""
    bdir = state_root / "_budget" / "scripted"
    bdir.mkdir(parents=True, exist_ok=True)
    for i in range(1, SCRIPTED_CAP + 1):
        path = bdir / f"{i:03d}"
        try:
            path.mkdir()
        except FileExistsError:
            continue
        (path / "label.txt").write_text(label + "\n")
        return path.name
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=("canonical", "scripted", "rejudge", "propose"))
    ap.add_argument("--out-tag", default="", help="scripted output dir suffix, e.g. _rev2 -> _scripted_rev2")
    ap.add_argument("--charge", action="store_true", help="charge each scripted attempt to the global 140 cap")
    ap.add_argument("--slot", default=None)
    ap.add_argument("--goals", default="")
    ap.add_argument("--scene", required=True)
    ap.add_argument("--state-root", type=Path, required=True)
    ap.add_argument("--robolab-root", type=Path, required=True)
    args = ap.parse_args()
    if args.mode == "rejudge":
        slot = args.slot or f"{args.scene}-D00"
        for r in rejudge(args.state_root / f"_scripted{args.out_tag}" / slot.replace("/", "__"), args.scene):
            print(json.dumps({k: r[k] for k in ("slot", "goal_id", "original_status", "status", "reason")}))
        return
    from isaaclab.app import AppLauncher

    app = AppLauncher({"headless": True, "enable_cameras": True, "device": "cuda:0"}).app
    code = 0
    try:
        from . import sim_env
        env = sim_env.StudyEnv(args.scene, robolab_root=args.robolab_root, output_dir=args.state_root / "_native" / args.scene)
        if args.mode == "canonical":
            receipt = register_canonical(env, args.scene, args.state_root)
            print(json.dumps({k: receipt[k] for k in ("slot", "settle_ok", "settle", "role_binding", "initial_study")}, default=str), flush=True)
        elif args.mode == "propose":
            propose(env, args.scene, args.state_root)
        elif args.mode == "scripted":
            slot = args.slot or f"{args.scene}-D00"
            slot_dir = args.state_root / slot
            tokens = []

            def budget() -> bool:
                if not args.charge:
                    return True
                tok = claim_scripted_token(args.state_root, f"{slot} {time.time()}")
                tokens.append(tok)
                return tok is not None
            scripted_checks(env, args.scene, slot_dir, args.state_root / f"_scripted{args.out_tag}" / slot.replace("/", "__"),
                            [g for g in args.goals.split(",") if g] or None, budget=budget,
                            fail_fast=args.charge)
        env.close()
    except BaseException:
        traceback.print_exc()
        code = 1
    finally:
        sys.stdout.flush()
        app.close()
    sys.exit(code)


if __name__ == "__main__":
    main()
