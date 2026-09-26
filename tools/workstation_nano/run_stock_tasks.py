#!/usr/bin/env python3
"""Run the prospective nine-task pilot with native RoboLab scoring and horizons."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import traceback

from common import COSMOS_COMMIT, REVISION, ROBOLAB_COMMIT, SEED, SERVER_CONFIG, dump, sha256, verify_revision
from stock_tasks import TASKS, plan


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--robolab-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--server-receipt", type=Path, required=True)
    parser.add_argument("--remote-host", default="127.0.0.1")
    parser.add_argument("--remote-port", type=int, default=18026)
    bootstrap, _ = parser.parse_known_args()
    verify_revision(bootstrap.robolab_root.resolve(), ROBOLAB_COMMIT)
    sys.path.insert(0, str(bootstrap.robolab_root.resolve()))
    import cv2  # noqa: F401 -- mandatory native import ordering
    from isaaclab.app import AppLauncher

    AppLauncher.add_app_launcher_args(parser)
    args = parser.parse_args()
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
    from openpi_client import msgpack_numpy, websocket_client_policy
    import websockets.sync.client
    from policies.cosmos3.client import Cosmos3Client
    from robolab.constants import set_output_dir
    from robolab.core.environments.runtime import create_env
    from robolab.core.task.conditionals import object_grabbed
    from robolab.core.world.world_state import get_world
    from robolab.eval.episode import run_episode
    from robolab.registrations.droid.auto_env_registrations_jointpos import auto_register_droid_envs
    from robolab.registrations.droid.camera_presets import WRIST_LEFT_RIGHT_HEAD

    if not Path(robolab.__file__).resolve().is_relative_to(args.robolab_root.resolve()):
        raise RuntimeError("Imported RoboLab is outside the requested checkout")
    robolab.constants.ENABLE_SUBTASK_PROGRESS_CHECKING = False
    robolab.constants.RECORD_IMAGE_DATA = False
    robolab.constants.VERBOSE = False
    auto_register_droid_envs(task=list(TASKS), cameras=WRIST_LEFT_RIGHT_HEAD)

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

    def snapshot(env, cfg, step):
        world = get_world(env)
        poses = {}
        for name in dict.fromkeys(["robot", *cfg.contact_object_list]):
            position, quaternion = world.get_pose(name, env_id=0)
            poses[name] = {"position_env_local_m": array(position).tolist(),
                           "quaternion_world_wxyz": array(quaternion).tolist()}
        success = cfg.terminations.success
        targets = success.params["object"]
        if isinstance(targets, str):
            targets = [targets]
        return {"step": step, "sim_time_s": step * float(env.step_dt), "poses": poses,
                "native_goal_predicate": bool(array(success.func(env, **success.params)).reshape(-1)[0]),
                "target_grabbed": {name: bool(object_grabbed(env, object=name, env_id=0))
                                   for name in targets}}

    for cell_id, (prompt, seconds) in TASKS.items():
        cell_dir = output / cell_id
        if cell_dir.exists():
            raise RuntimeError(f"Preserve existing attempt and choose a new output root: {cell_dir}")
        cell_dir.mkdir()
        native_dir = cell_dir / "native"
        native_dir.mkdir()
        set_output_dir(str(native_dir))
        step_budget = seconds * 15
        env = None
        client = None
        states = []
        steps = 0
        completed_result = None
        pose_file = (cell_dir / "poses.jsonl").open("w")

        class EvidenceClient(Cosmos3Client):
            def _connect(self):
                class LocalOffloadConnection(websocket_client_policy.WebsocketClientPolicy):
                    def _wait_for_server(self):
                        # Native inference blocks the server event loop. CPU
                        # offload can exceed the library's 20 s ping timeout.
                        # The server still bounds each request at 900 seconds.
                        connection = websockets.sync.client.connect(
                            self._uri, compression=None, max_size=None,
                            ping_interval=None, open_timeout=30,
                        )
                        return connection, msgpack_numpy.unpackb(connection.recv(timeout=30))

                return LocalOffloadConnection(self._remote_host, self._remote_port)

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
                dump(cell_dir / "transport.json", {
                    "client_keepalive_interval": None,
                    "reason": "Local CPU-offloaded inference exceeds the default 20-second keepalive timeout",
                    "server_request_timeout_seconds": 900,
                    "automatic_request_retries": 0,
                })
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
                    states.append(snapshot(env, cfg, 0))
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
            env, cfg = create_env(cell_id, device=args.device, seed=SEED, num_envs=1,
                                  policy="stock_nano_spatial", renderer="realtime",
                                  rendering_mode="balanced", instruction_type="default")
            if (cfg.instruction != prompt or env.max_episode_length != step_budget
                    or not np.isclose(float(env.step_dt), 1 / 15)):
                raise RuntimeError("Native task instruction, horizon or control rate differs from the recorded plan")
            dump(cell_dir / "task.json", {"task": cell_id, "prompt": prompt,
                 "native_horizon_seconds": seconds, "maximum_control_steps": step_budget,
                 "success_function": cfg.terminations.success.func.__name__,
                 "success_parameters": cfg.terminations.success.params,
                 "started_at_utc": datetime.now(timezone.utc).isoformat()})
            real_step = env.step

            def measured_step(action):
                nonlocal steps
                result = real_step(action)
                steps += 1
                row = snapshot(env, cfg, steps)
                states.append(row)
                pose_file.write(json.dumps(row, allow_nan=False) + "\n")
                pose_file.flush()
                return result

            env.step = measured_step
            client = EvidenceClient()
            native_results, _, timing = run_episode(
                env, cfg, 0, client, headless=True, save_videos=True, video_mode="all")
            if (not env.all_terminated or not 0 < steps <= step_budget
                    or len(native_results) != 1 or native_results[0]["success"] is None):
                raise RuntimeError(f"Episode did not reach a native terminal outcome: {native_results}")
            # Check the executed trajectory against the actions requested from Nano.
            import h5py
            with h5py.File(native_dir / "run_0.hdf5", "r") as recorded:
                executed = recorded["data/demo_0/actions"][:]
            if executed.shape != (steps, 8) or not np.array_equal(executed, np.asarray(client.actions)):
                raise RuntimeError("Native recorded actions do not match the policy trajectory")
            videos = [{"path": str(path.relative_to(cell_dir)), "bytes": path.stat().st_size}
                      for path in sorted(native_dir.glob("*.mp4"))]
            completed_result = {
                "status": "complete", "task": cell_id, "prompt": prompt, "steps": steps,
                "maximum_control_steps": step_budget, "native_results": native_results,
                "native_success": bool(native_results[0]["success"]),
                "initial_goal_satisfied": states[0]["native_goal_predicate"],
                "final_goal_satisfied": states[-1]["native_goal_predicate"],
                "initial": states[0], "final": states[-1],
                "ever_grabbed_target": any(any(row["target_grabbed"].values()) for row in states),
                "environment_seed": SEED, "policy_seed": SEED,
                "future_count": sum(row.get("future_status") == "retained" for row in client.requests),
                "request_count": len(client.requests), "timing": timing, "videos": videos,
                "native_actions_match_policy": True,
                "claim_boundary": "One episode per task, not a success-rate estimate. Check initial_goal_satisfied before attributing native success to the policy.",
                "finished_at_utc": datetime.now(timezone.utc).isoformat(),
            }
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
            print(json.dumps({key: completed_result[key] for key in
                              ("task", "native_success", "initial_goal_satisfied", "steps", "request_count")}), flush=True)
    dump(output / "summary.json", {
        "status": "complete", "plan": plan(),
        "results": [json.loads((output / task / "result.json").read_text()) for task in TASKS],
    })


if __name__ == "__main__":
    main()
