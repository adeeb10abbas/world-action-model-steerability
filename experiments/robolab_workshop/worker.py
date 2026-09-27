"""Simulator lane worker: one scene env, one policy server, whole blocks in plan order. Zero retries.

Episode layout: <out>/episodes/<episode_id>/attempts/<attempt_id>/... ; <out>/episodes/<episode_id>/COMPLETE.json
(written last, atomically, only after validation). Attempts without COMPLETE.json are partial/quarantined.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import socket
import sys
import time
import traceback
from pathlib import Path

import numpy as np

SEED = 6100
FPS = 15


def arr_sha(a) -> str:
    a = np.ascontiguousarray(a)
    return hashlib.sha256(f"{a.dtype.str}{a.shape}".encode() + a.tobytes()).hexdigest()


def file_sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def camera_transforms(env) -> dict:
    out = {}
    for name in ("wrist_cam", "over_shoulder_left_camera", "over_shoulder_right_camera", "head_camera"):
        try:
            data = env.env.scene[name].data
            out[name] = {"pos_w": data.pos_w[0].detach().cpu().numpy().tolist(),
                         "quat_w_ros": data.quat_w_ros[0].detach().cpu().numpy().tolist(),
                         "intrinsics": data.intrinsic_matrices[0].detach().cpu().numpy().tolist()}
        except Exception as error:
            out[name] = {"error": type(error).__name__}
    return out


class InfraError(RuntimeError):
    pass


class Worker:
    def __init__(self, args) -> None:
        from . import sim_env
        from .client import HttpPolicy

        self.args = args
        self.out = args.out
        self.env = sim_env.StudyEnv(args.scene, robolab_root=args.robolab_root,
                                    output_dir=Path(f"/tmp/rws-native-{socket.gethostname()}-{os.getpid()}"))
        self.policy = HttpPolicy(args.url)
        self.server_info = self.policy.info()
        if self.server_info.get("model") != args.model:
            raise RuntimeError(f"server model {self.server_info.get('model')} != {args.model}")
        self.lane = {"lane_id": args.lane_id, "host": socket.gethostname(), "pid": os.getpid(),
                     "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"), "url": args.url,
                     "server_pid": self.server_info.get("pid"), "server_host": self.server_info.get("host"),
                     "tcp_definition": self.env.tcp_definition}

    # ---------------------------------------------------------------- episode
    def run_episode(self, row: dict, state: dict, first: dict, state_receipt: dict) -> str:
        from . import client as C
        from .recording import LosslessStream, write_json_atomic
        from .scoring import score_episode
        from . import sim_env

        eid = row["episode_id"]
        edir = self.out / "episodes" / eid
        if (edir / "COMPLETE.json").exists():
            return "already_complete"
        attempt_id = f"{eid}.{time.strftime('%Y%m%dT%H%M%S')}.{socket.gethostname()}.{os.getpid()}"
        adir = edir / "attempts" / attempt_id
        (adir / "requests").mkdir(parents=True, exist_ok=True)
        (adir / "futures").mkdir(parents=True, exist_ok=True)
        write_json_atomic(adir / "intent.json", {"episode_id": eid, "attempt_id": attempt_id, "row": row,
                                                  "lane": self.lane, "t": time.time()})
        streams = {}
        ticks: list[dict] = []
        requests: list[dict] = []
        try:
            t_start = time.time()
            self.env.restore_state(state)
            restored = self.env.capture_state()
            restore_diff = sim_env.state_max_abs_diff(state, restored)
            roles = self.env.bind_roles()
            frozen = state_receipt.get("role_binding", {})
            if self.env.scene_id == "S5" and (roles.get("left_bowl") != frozen.get("left_bowl")):
                raise InfraError(f"role binding changed {roles} vs {frozen}")
            ticks.append(self.env.tick_record())
            reset = self.policy.reset(SEED, eid, attempt_id)
            obs0 = self.env.raw_observation()
            comp_shape = (540, 640)
            streams = {"composite": LosslessStream(adir / "exec_composite.mkv", *comp_shape),
                       "head_camera": LosslessStream(adir / "exec_head_camera.mkv", *obs0["head_camera"].shape[:2])}
            vp = [k for k in obs0 if k.startswith("viewport__")]
            if vp:
                streams["viewport"] = LosslessStream(adir / "exec_viewport.mkv", *obs0[vp[0]].shape[:2])

            def record_frames(raw):
                streams["composite"].write(C.request_from_raw(raw)["image"])
                streams["head_camera"].write(raw["head_camera"])
                if vp:
                    streams["viewport"].write(raw[vp[0]])

            record_frames(obs0)
            max_actions = int(row["maximum_control_actions"])
            max_requests = int(row["maximum_requests"])
            returned_all, post_all = [], []
            for r in range(max_requests):
                pre = len(ticks) - 1
                remaining = max_actions - pre
                if remaining <= 0:
                    break
                raw = first if r == 0 else self.env.raw_observation()
                req = C.request_from_raw(raw)
                header = {"prompt": row["prompt"], "prompt_sha256": row["prompt_sha256"], "seed": SEED,
                          "episode_id": eid, "request_index": r, "attempt_id": attempt_id,
                          "future_path": str(adir / "futures" / f"r{r:02d}.npz")}
                cams = camera_transforms(self.env)
                np.savez_compressed(adir / "requests" / f"r{r:02d}_input.npz", composite=req["image"],
                                    joint_position=req["joint_position"], gripper_position=req["gripper_position"],
                                    **{k: raw[k] for k in C.VIEW_KEYS})
                t0 = time.time()
                try:
                    action, meta, rtt = self.policy.infer(req, header)
                except Exception as error:
                    raise InfraError(f"policy request {r} failed: {error}") from error
                post = C.postprocess_chunk(action)
                n = min(32, remaining)
                executed = post[:n]
                for i in range(n):
                    rec = self.env.step(executed[i])
                    if rec["terminated"] or rec["truncated"]:
                        raise InfraError(f"simulator terminated at tick {len(ticks)} (invalid state?)")
                    if not all(np.isfinite(o["pos"]).all() for o in rec["objects"].values()):
                        raise InfraError("non-finite object state")
                    ticks.append(rec)
                    record_frames(self.env.raw_observation())
                returned_all.append(action)
                post_all.append(post)
                t_req0 = ticks[pre]["t"]
                requests.append({
                    "episode_id": eid, "attempt_id": attempt_id, "request_index": r,
                    "prompt_sha256": row["prompt_sha256"], "effective_prompt": meta.get("effective_prompt"),
                    "effective_seed": meta.get("effective_seed"), "seed": SEED,
                    "input_source": "cached_first_observation" if r == 0 else "live_render",
                    "input_sha256": meta.get("input_sha256"), "composite_sha256": arr_sha(req["image"]),
                    "joint_position": req["joint_position"].tolist(), "gripper_position": req["gripper_position"].tolist(),
                    "pre_tick": pre, "n_executed": n, "t_start": t_req0, "t_end": ticks[pre + n]["t"],
                    "returned_sha256": arr_sha(action), "postprocessed_sha256": arr_sha(post),
                    "executed_sha256": arr_sha(executed), "infer_s": meta.get("infer_s"), "rtt_s": rtt,
                    "wall_s": time.time() - t0, "peak_cuda_mem_bytes": meta.get("peak_cuda_mem_bytes"),
                    "camera_transforms": cams, "future": meta.get("future"), "future_status": meta.get("future_status"),
                    "future_missing_reason": None if meta.get("future") else (meta.get("future_status") or "not_exposed"),
                    "future_frame_times": [t_req0 + k / FPS for k in range(33)],
                    "future_executed_frames": list(range(0, n + 1)),
                    "sampling_kwargs": meta.get("sampling_kwargs"), "server_served_index": meta.get("served_index"),
                })
                with open(adir / "requests.jsonl", "a") as f:
                    f.write(json.dumps(requests[-1], default=str) + "\n")
            stream_receipts = {k: s.close() for k, s in streams.items()}
            streams = {}
            with gzip.open(adir / "states.jsonl.gz", "wt") as f:
                for rec in ticks:
                    f.write(json.dumps(rec) + "\n")
            np.savez_compressed(adir / "actions.npz", returned=np.stack(returned_all), postprocessed=np.stack(post_all),
                                executed=np.array([t["command"] for t in ticks[1:]], dtype=np.float64))
            np.savez_compressed(adir / "first_observation.npz", **first)
            (adir / "initial_state.json").write_text(json.dumps({"state_slot": row["state_slot"],
                                                                "state_sha256": state_receipt.get("state_sha256"),
                                                                "first_obs_sha256": state_receipt.get("first_obs_sha256"),
                                                                "restore_max_abs_diff": restore_diff,
                                                                "role_binding": roles}, indent=2))
            horizon = max_actions
            score = score_episode(ticks, requests, self.env.scene_id, row["goal_id"], horizon)
            if not score["complete_horizon"]:
                raise InfraError(f"incomplete horizon {len(ticks) - 1}/{horizon}")
            artifacts = {}
            for p in sorted(adir.rglob("*")):
                if p.is_file() and p.name not in ("result.json",):
                    artifacts[str(p.relative_to(adir))] = file_sha(p)
            result = {"status": "valid", "episode_id": eid, "attempt_id": attempt_id, "model_id": row["model_id"],
                      "phase": row["phase"], "block_id": row["block_id"], "scene_id": row["scene_id"],
                      "state_slot": row["state_slot"], "goal_id": row["goal_id"], "prompt_id": row["prompt_id"],
                      "form": row["form"], "prompt_sha256": row["prompt_sha256"],
                      "denominators": {"requests": len(requests), "executed_actions": len(ticks) - 1,
                                       "futures_saved": sum(1 for q in requests if q["future"] and q["future"].get("uri")),
                                       "planned_actions": max_actions, "planned_requests": max_requests},
                      "score": score, "server_reset": reset, "lane": self.lane, "streams": {
                          k: {kk: vv for kk, vv in v.items() if kk != "frame_sha256"} for k, v in stream_receipts.items()},
                      "restore_max_abs_diff": restore_diff, "wall_s": time.time() - t_start, "artifacts": artifacts}
            (adir / "stream_frame_hashes.json").write_text(json.dumps(stream_receipts))
            write_json_atomic(adir / "result.json", result)
            ok = self.validate(adir, result, requests, ticks, row)
            if not ok:
                raise InfraError("validation failed")
            write_json_atomic(edir / "COMPLETE.json", {"episode_id": eid, "attempt_id": attempt_id,
                                                        "attempt_dir": str(adir), "result_sha256": file_sha(adir / "result.json"),
                                                        "stable_ever": score["stable_ever"], "t": time.time()})
            return "valid"
        except BaseException as error:
            for s in streams.values():
                try:
                    s.close()
                except Exception:
                    pass
            kind = "infrastructure" if isinstance(error, (InfraError, OSError)) else "implementation_error"
            write_json_atomic(adir / "PARTIAL.json", {"episode_id": eid, "attempt_id": attempt_id, "kind": kind,
                                                       "error": f"{type(error).__name__}: {error}",
                                                       "traceback": traceback.format_exc(), "ticks": len(ticks),
                                                       "requests": len(requests), "t": time.time()})
            if ticks:
                with gzip.open(adir / "partial_states.jsonl.gz", "wt") as f:
                    for rec in ticks:
                        f.write(json.dumps(rec) + "\n")
            if isinstance(error, KeyboardInterrupt):
                raise
            return f"partial:{kind}"

    def validate(self, adir: Path, result: dict, requests: list, ticks: list, row: dict) -> bool:
        exp_req = -(-int(row["maximum_control_actions"]) // 32)
        checks = [len(requests) == exp_req, len(ticks) == int(row["maximum_control_actions"]) + 1,
                  sum(q["n_executed"] for q in requests) == len(ticks) - 1,
                  all(q["prompt_sha256"] == row["prompt_sha256"] for q in requests),
                  all(result["streams"][k]["frames"] == len(ticks) for k in result["streams"])]
        return all(checks)


def claim(out: Path, block_id: str, lane: dict) -> bool:
    cdir = out / "claims" / block_id
    try:
        cdir.mkdir(parents=True)
    except FileExistsError:
        return False
    (cdir / "owner.json").write_text(json.dumps(lane))
    return True


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--scene", required=True)
    ap.add_argument("--url", required=True)
    ap.add_argument("--lane-id", required=True)
    ap.add_argument("--blocks", required=True, help="comma-separated block ids in execution order")
    ap.add_argument("--episodes", default="", help="optional comma-separated episode-id filter")
    ap.add_argument("--state-root", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--robolab-root", type=Path, required=True)
    ap.add_argument("--rows", type=Path, default=None, help="bound plan rows jsonl (default: spec planned_episodes)")
    args = ap.parse_args()
    from isaaclab.app import AppLauncher

    app = AppLauncher({"headless": True, "enable_cameras": True, "device": "cuda:0"}).app
    code = 0
    try:
        from .catalog import load_planned_episodes
        from .states import load_state

        rows = [json.loads(l) for l in args.rows.read_text().splitlines() if l.strip()] if args.rows else load_planned_episodes()
        wanted = set(filter(None, args.episodes.split(",")))
        worker = Worker(args)
        log = args.out / "lanes" / f"{args.lane_id}.jsonl"
        log.parent.mkdir(parents=True, exist_ok=True)
        for block_id in args.blocks.split(","):
            brows = sorted((r for r in rows if r["block_id"] == block_id and r["model_id"] == args.model
                            and (not wanted or r["episode_id"] in wanted)), key=lambda r: r["order_in_block"])
            if not brows:
                continue
            if any(r["scene_id"] != args.scene for r in brows):
                raise RuntimeError(f"block {block_id} not in scene {args.scene}")
            if not claim(args.out, block_id + (f"__{'_'.join(sorted(wanted))[:80]}" if wanted else ""), worker.lane):
                print(f"skip claimed {block_id}", flush=True)
                continue
            if any(r["phase"] == "confirmation" and not r.get("physical_state_bound") for r in brows):
                raise RuntimeError(f"{block_id}: confirmation rows must come from the release-bound plan (--rows)")
            state, first, receipt = load_state(args.state_root / brows[0]["state_slot"])
            want = brows[0].get("state_snapshot_sha256")
            if want and want != receipt.get("state_sha256"):
                raise RuntimeError(f"{block_id}: state hash {receipt.get('state_sha256')} != released {want}")
            for row in brows:
                t0 = time.time()
                status = worker.run_episode(row, state, first, receipt)
                entry = {"t": time.time(), "episode_id": row["episode_id"], "status": status, "wall_s": time.time() - t0}
                with log.open("a") as f:
                    f.write(json.dumps(entry) + "\n")
                print(json.dumps(entry), flush=True)
        worker.env.close()
    except BaseException:
        traceback.print_exc()
        code = 1
    finally:
        sys.stdout.flush()
        app.close()
    sys.exit(code)


if __name__ == "__main__":
    main()
