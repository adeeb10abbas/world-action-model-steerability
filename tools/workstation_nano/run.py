#!/usr/bin/env python3
"""Run selected matched wording cells on the unchanged stock left-task scene."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import traceback

from common import COSMOS_COMMIT, PROMPTS, REVISION, ROBOLAB_COMMIT, SEED, SERVER_CONFIG, STEPS, dump, plan, sha256, verify_revision


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--robolab-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--server-receipt", type=Path, required=True)
    parser.add_argument("--remote-host", default="127.0.0.1")
    parser.add_argument("--remote-port", type=int, default=18026)
    parser.add_argument("--cells", nargs="+", choices=list(PROMPTS), default=list(PROMPTS))
    parser.add_argument("--resume-completed", action="store_true")
    bootstrap, _ = parser.parse_known_args()
    verify_revision(bootstrap.robolab_root.resolve(), ROBOLAB_COMMIT)
    sys.path.insert(0, str(bootstrap.robolab_root.resolve()))
    import cv2  # noqa: F401 -- mandatory native import ordering
    from isaaclab.app import AppLauncher

    AppLauncher.add_app_launcher_args(parser)
    args = parser.parse_args()
    if len(args.cells) != len(set(args.cells)):
        parser.error("A cell may only appear once per invocation")
    args.headless = True
    args.enable_cameras = True
    receipt = json.loads(args.server_receipt.read_text())
    if (receipt.get("source_commit") != COSMOS_COMMIT or receipt.get("checkpoint_revision") != REVISION
            or any(receipt.get("config", {}).get(key) != value for key, value in SERVER_CONFIG.items())):
        raise RuntimeError("Server receipt does not match the pinned deterministic Nano configuration")
    output = args.output_root.resolve()
    output.mkdir(parents=True, exist_ok=True)
    current_plan = plan()
    plan_file = output / "plan.json"
    if plan_file.exists() and json.loads(plan_file.read_text()) != current_plan:
        raise RuntimeError("Output directory contains a different plan")
    dump(plan_file, current_plan)
    launcher = AppLauncher(args)
    try:
        run_cells(args, output, receipt)
    finally:
        launcher.app.close()


def run_cells(args, output: Path, receipt: dict) -> None:
    import numpy as np
    import robolab
    import robolab.constants
    from policies.cosmos3.client import Cosmos3Client
    from robolab.constants import set_output_dir
    from robolab.core.environments.config import parse_env_cfg
    from robolab.core.environments.runtime import create_env
    from robolab.core.task.conditionals import object_grabbed, object_left_of, object_right_of
    from robolab.core.world.world_state import get_world
    from robolab.eval.episode import run_episode
    from robolab.registrations.droid.auto_env_registrations_jointpos import auto_register_droid_envs
    from robolab.registrations.droid.camera_presets import WRIST_LEFT_RIGHT_HEAD

    if not Path(robolab.__file__).resolve().is_relative_to(args.robolab_root.resolve()):
        raise RuntimeError("Imported RoboLab is outside the requested checkout")
    robolab.constants.ENABLE_SUBTASK_PROGRESS_CHECKING = False
    robolab.constants.RECORD_IMAGE_DATA = False
    robolab.constants.VERBOSE = False
    auto_register_droid_envs(task=["RubiksCubeLeftOfBowlTask"], cameras=WRIST_LEFT_RIGHT_HEAD)

    def array(value):
        if hasattr(value, "detach"):
            value = value.detach().cpu().numpy()
        return np.asarray(value)

    def flatten(value, prefix=""):
        if isinstance(value, dict):
            result = {}
            for key, item in value.items():
                result.update(flatten(item, f"{prefix}/{key}" if prefix else key))
            return result
        return {prefix: array(value)}

    def snapshot(env, step):
        world = get_world(env)
        poses = {}
        for name in ("robot", "rubiks_cube", "bowl", "banana", "table"):
            position, quaternion = world.get_pose(name, env_id=0)
            poses[name] = {"position_env_local_m": array(position).tolist(), "quaternion_world_wxyz": array(quaternion).tolist()}
        cube = array(world.get_pose("rubiks_cube", env_id=0)[0])
        bowl = array(world.get_pose("bowl", env_id=0)[0])
        robot_matrix = array(world.get_pose("robot", as_matrix=True, env_id=0))
        delta_robot = robot_matrix[:3, :3].T @ (cube - bowl)
        kwargs = dict(object="rubiks_cube", reference_object="bowl", frame_of_reference="robot",
                      mirrored=False, require_gripper_detached=True, env_id=0)
        return {"step": step, "sim_time_s": step * float(env.step_dt), "poses": poses,
                "cube_minus_bowl_robot_xyz_m": delta_robot.tolist(),
                "left_predicate": bool(object_left_of(env, **kwargs)),
                "right_predicate": bool(object_right_of(env, **kwargs)),
                "cube_grabbed": bool(object_grabbed(env, object="rubiks_cube", env_id=0))}

    for cell_id in args.cells:
        cell_dir = output / cell_id
        if cell_dir.exists():
            if args.resume_completed and (cell_dir / "result.json").is_file():
                previous = json.loads((cell_dir / "result.json").read_text())
                if previous.get("status") == "complete" and previous.get("steps") == STEPS:
                    continue
            raise RuntimeError(f"Preserve existing attempt and choose a new output root: {cell_dir}")
        cell_dir.mkdir()
        native_dir = cell_dir / "native"
        native_dir.mkdir()
        set_output_dir(str(native_dir))
        prompt = PROMPTS[cell_id]
        cfg = parse_env_cfg("RubiksCubeLeftOfBowlTask", device=args.device, seed=SEED, num_envs=1)
        cfg.instruction = prompt
        cfg.terminations.success = None
        cfg.episode_length_s = 30.0
        env = None
        client = None
        states = []
        steps = 0
        completed_result = None
        pose_file = (cell_dir / "poses.jsonl").open("w")

        class EvidenceClient(Cosmos3Client):
            def __init__(self):
                super().__init__(remote_host=args.remote_host, remote_port=args.remote_port)
                self.requests = []
                self.actions = []
                self.started = False
                self.pending_raw = None
                metadata_method = getattr(self.client, "get_server_metadata", None)
                if not callable(metadata_method):
                    raise RuntimeError("Native WebSocket client lacks get_server_metadata")
                observed = metadata_method()
                if observed != receipt:
                    raise RuntimeError("Connected server metadata differs from the launch receipt")
                dump(cell_dir / "server_receipt.json", observed)
                reset_ack = self.client.infer({"_workstation_control": "reset"})
                if (reset_ack.get("status") != "reset" or reset_ack.get("policy_seed") != SEED
                        or reset_ack.get("history_length") != 1):
                    raise RuntimeError(f"Distributed server reset was not acknowledged: {reset_ack}")
                dump(cell_dir / "server_reset.json", reset_ack)

            def close(self):
                # The pinned OpenPI client has no public close method. Its
                # inspected synchronous WebSocket owns this close operation.
                self.client._ws.close()

            def infer(self, obs, instruction, *, env_id=0):
                if instruction != prompt or env_id != 0:
                    raise RuntimeError("Cell instruction or environment changed")
                if not self.started:
                    # Native run_episode calls reset twice. This is the actual
                    # observation and state used by the first policy request.
                    initial = flatten(env.scene.get_state(is_relative=True))
                    np.savez(cell_dir / "initial_state.npz", **initial)
                    baseline = output / "paired_initial_state.npz"
                    if baseline.exists():
                        with np.load(baseline, allow_pickle=False) as saved:
                            matching = set(saved.files) == set(initial)
                            differences = {}
                            for key in initial:
                                if key not in saved.files or saved[key].shape != initial[key].shape:
                                    differences[key] = {"same_shape": False}
                                    matching = False
                                else:
                                    delta = float(np.max(np.abs(saved[key] - initial[key]))) if initial[key].size else 0.0
                                    differences[key] = {"max_absolute_difference": delta}
                                    matching = matching and bool(np.allclose(saved[key], initial[key], atol=1e-5, rtol=0))
                            dump(cell_dir / "reset_match.json", {"matched": matching, "baseline": str(baseline),
                                                                "absolute_tolerance": 1e-5, "differences": differences})
                            if not matching:
                                raise RuntimeError("Physical reset differs from the first cell (absolute state tolerance 1e-5)")
                    else:
                        np.savez(baseline, **initial)
                        dump(cell_dir / "reset_match.json", {"matched": True, "baseline_established_by": cell_id,
                                                            "baseline": str(baseline), "absolute_tolerance": 1e-5})
                    states.append(snapshot(env, 0))
                    pose_file.write(json.dumps(states[-1], allow_nan=False) + "\n")
                    pose_file.flush()
                    self.started = True
                if self._needs_refresh(env_id):
                    self.pending_raw = flatten({"image_obs": obs["image_obs"], "proprio_obs": obs["proprio_obs"]})
                result = super().infer(obs, instruction, env_id=env_id)
                self.actions.append(np.asarray(result["action"], dtype=np.float32).copy())
                return result

            def _query_server(self, request):
                index = len(self.requests)
                stem = f"request_{index:03d}"
                raw_path = cell_dir / f"{stem}_raw_observation.npz"
                np.savez(raw_path, **self.pending_raw)
                packed_path = cell_dir / f"{stem}_packed_input.npz"
                np.savez(packed_path, **{key: value for key, value in request.items() if key != "prompt"})
                record = {"request_index": index, "action_step_start": len(self.actions),
                          "prompt": request["prompt"], "policy_seed": SEED,
                          "raw_observation": raw_path.name, "raw_observation_sha256": sha256(raw_path),
                          "packed_input": packed_path.name, "packed_input_sha256": sha256(packed_path)}
                self.requests.append(record)
                dump(cell_dir / "requests.json", self.requests)
                # No transport retry: preserve an ambiguous request as a partial
                # attempt rather than silently generating another sample.
                response = self.client.infer(request)
                action = np.asarray(response["action"])
                if action.shape != (32, 8) or not np.isfinite(action).all():
                    raise RuntimeError(f"Invalid native action chunk: {action.shape}")
                action_path = cell_dir / f"{stem}_returned_actions.npy"
                np.save(action_path, action, allow_pickle=False)
                record.update(returned_actions=action_path.name, returned_actions_sha256=sha256(action_path))
                if "video" in response:
                    future = np.asarray(response["video"])
                    if future.ndim != 4 or future.shape[0] != 33 or future.shape[-1] != 3 or future.dtype != np.uint8:
                        raise RuntimeError(f"Invalid exposed native future: {future.shape} {future.dtype}")
                    future_path = cell_dir / f"{stem}_future.npy"
                    np.save(future_path, future, allow_pickle=False)
                    record.update(future_status="retained", future=future_path.name, future_sha256=sha256(future_path), future_shape=list(future.shape))
                else:
                    record["future_status"] = "unavailable"
                dump(cell_dir / "requests.json", self.requests)
                return response

        try:
            env, cfg = create_env(cfg, device=args.device, seed=SEED, num_envs=1,
                                  policy="stock_nano_wording", renderer="realtime", rendering_mode="balanced")
            if env.max_episode_length != STEPS or not np.isclose(float(env.step_dt), 1 / 15):
                raise RuntimeError("Expected exactly 450 actions at 15 Hz")
            real_step = env.step

            def measured_step(action):
                nonlocal steps
                result = real_step(action)
                steps += 1
                row = snapshot(env, steps)
                states.append(row)
                pose_file.write(json.dumps(row, allow_nan=False) + "\n")
                pose_file.flush()
                return result

            env.step = measured_step
            client = EvidenceClient()
            run_episode(env, cfg, 0, client, headless=True, save_videos=True, video_mode="all")
            if steps != STEPS:
                raise RuntimeError(f"Episode ended after {steps}, expected {STEPS}")
            relation = cell_id.split("-")[1]
            grasp_indices = [i for i, row in enumerate(states) if row["cube_grabbed"]]
            released_after_grasp = bool(grasp_indices) and any(not row["cube_grabbed"] for row in states[grasp_indices[0] + 1:])
            cube_start = np.asarray(states[0]["poses"]["rubiks_cube"]["position_env_local_m"])
            cube_end = np.asarray(states[-1]["poses"]["rubiks_cube"]["position_env_local_m"])
            completed_result = {"status": "complete", "cell_id": cell_id, "prompt": prompt, "steps": steps,
                      "environment_seed": SEED, "policy_seed": SEED, "initial": states[0], "final": states[-1],
                      "endpoint_requested_relation": states[-1][f"{relation}_predicate"],
                      "initial_requested_relation": states[0][f"{relation}_predicate"],
                      "ever_grabbed": any(row["cube_grabbed"] for row in states),
                      "release_after_grasp_observed": released_after_grasp,
                      "cube_endpoint_displacement_m": float(np.linalg.norm(cube_end - cube_start)),
                      "future_count": sum(row.get("future_status") == "retained" for row in client.requests),
                      "request_count": len(client.requests),
                      "claim_boundary": "Endpoint predicates can hold at reset; this is a fixed-scene wording diagnostic, not an independent-trial success estimate.",
                      "finished_at_utc": datetime.now(timezone.utc).isoformat()}
        except BaseException as error:
            dump(cell_dir / "partial.json", {"status": "partial", "cell_id": cell_id, "steps": steps,
                                            "error": repr(error), "traceback": traceback.format_exc()})
            raise
        finally:
            pose_file.close()
            if client is not None:
                for request in client.requests:
                    request["executed_control_steps"] = max(0, min(32, steps - request["action_step_start"]))
                dump(cell_dir / "requests.json", client.requests)
                np.save(cell_dir / "requested_step_actions.npy", np.asarray(client.actions, dtype=np.float32), allow_pickle=False)
                client.close()
            if env is not None:
                env.close()
        if completed_result is not None:
            dump(cell_dir / "result.json", completed_result)


if __name__ == "__main__":
    main()
