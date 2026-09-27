"""Simulator capability probe (no policy). Records API facts used by sim_env.py."""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--robolab-root", type=Path, required=True)
    parser.add_argument("--tasks", default="S1")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report: dict = {"ok": False}
    from isaaclab.app import AppLauncher

    app = AppLauncher({"headless": True, "enable_cameras": True, "device": "cuda:0"}).app
    try:
        import numpy as np
        import torch
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from experiments.robolab_workshop import sim_env

        for scene_id in args.tasks.split(","):
            t0 = time.time()
            env = sim_env.StudyEnv(scene_id, robolab_root=args.robolab_root, output_dir=args.output / f"native-{scene_id}")
            rec: dict = {"create_s": time.time() - t0}
            raw = env.env
            rec["step_dt"] = float(raw.step_dt)
            rec["physics_dt"] = float(raw.physics_dt)
            rec["max_episode_length"] = int(raw.max_episode_length)
            rec["terminations"] = list(raw.termination_manager.active_terms)
            rec["has_reset_to"] = hasattr(raw, "reset_to")
            rec["tcp_definition"] = env.tcp_definition
            rec["contact_sensors"] = sorted(env.contact_sensor_names())
            rec["robot_bodies"] = list(raw.scene["robot"].data.body_names)
            rec["robot_joints"] = list(raw.scene["robot"].data.joint_names)
            rec["frames"] = list(raw.scene["frames"].data.target_frame_names) if "frames" in raw.scene.keys() else None
            obs = env.reset_native()
            rec["obs_keys"] = {k: {kk: list(v.shape) for kk, v in obs[k].items()} for k in obs}
            s0 = env.capture_state()
            first = env.raw_observation()
            np.savez_compressed(args.output / f"{scene_id}-first.npz", **first)
            tick0 = env.tick_record()
            rec["tick0"] = tick0
            hold = env.current_joint_command()
            t1 = time.time()
            n = 30
            for i in range(n):
                action = hold.copy()
                action[:7] += 0.02 * np.sin(i / 5)
                env.step(action)
            rec["step_s_mean"] = (time.time() - t1) / n
            tick_after = env.tick_record()
            rec["tick_after"] = tick_after
            s1 = env.capture_state()
            env.restore_state(s0)
            s0b = env.capture_state()
            rec["restore_max_abs_diff"] = sim_env.state_max_abs_diff(s0, s0b)
            rec["moved_diff"] = sim_env.state_max_abs_diff(s0, s1)
            again = env.raw_observation()
            rec["restore_image_max_abs_diff"] = {k: int(np.abs(first[k].astype(int) - again[k].astype(int)).max()) for k in first}
            env.restore_state(s0)
            again2 = env.raw_observation()
            rec["restore2_vs_restore1_image_max_abs_diff"] = {k: int(np.abs(again2[k].astype(int) - again[k].astype(int)).max()) for k in first}
            rec["sim_time_after_restore"] = env.sim_time()
            report[scene_id] = rec
            (args.output / "probe.json").write_text(json.dumps(report, indent=2, default=str))
            env.close()
        report["ok"] = True
    except BaseException:
        report["error"] = traceback.format_exc()
        print(report["error"], flush=True)
    finally:
        (args.output / "probe.json").write_text(json.dumps(report, indent=2, default=str))
        app.close()


if __name__ == "__main__":
    main()
