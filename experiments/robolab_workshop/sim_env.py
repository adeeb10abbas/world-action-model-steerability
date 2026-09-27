"""Isaac-side study environment: native RoboLab scene, success termination disabled,
full-state capture/restore, per-tick physical records and pinned predicates.

Import only inside a process whose AppLauncher is already running.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np

from .catalog import SCENES, THRESHOLDS

TASK_FILES = {
    "RubiksCubeLeftOfBowlTask": "rubiks_cube_left_of_bowl.py",
    "MustardInLeftBinTask": "mustard_in_left_bin.py",
    "ButterAboveRaisinTask": "butter_above_raisin_task.py",
    "MustardAboveRaisinTask": "mustard_above_raisin_task.py",
    "BowlStackingLeftOnRightTask": "bowl_stacking_left_on_right.py",
}
POLICY_CAMERAS = ("wrist_cam", "over_shoulder_left_camera", "over_shoulder_right_camera")
RECORD_CAMERAS = POLICY_CAMERAS + ("head_camera",)
CONTACT_OBJECTS = {
    "S1": ["rubiks_cube", "banana", "bowl", "table"],
    "S2": ["table", "mustard", "grey_bin_right", "grey_bin_left"],
    "S3": ["butter", "raisin_box", "table"],
    "S4": ["mustard_bottle", "raisin_box", "table"],
    "S5": ["bowl_1", "bowl_2", "table"],
}
# Exact native success terminations (func name, params) copied from the pinned
# task sources at RoboLab 0aef241. Key = native task class.
NATIVE_SUCCESS = {
    "RubiksCubeLeftOfBowlTask": ("object_left_of", {"object": "rubiks_cube", "reference_object": "bowl", "frame_of_reference": "robot", "mirrored": False, "require_gripper_detached": True}),
    "RubiksCubeInFrontOfBowlTask": ("object_in_front_of", {"object": "rubiks_cube", "reference_object": "bowl", "frame_of_reference": "robot", "mirrored": False, "require_gripper_detached": True}),
    "RubiksCubeBehindBowlTask": ("object_behind", {"object": "rubiks_cube", "reference_object": "bowl", "frame_of_reference": "robot", "mirrored": False, "require_contact_with": "table", "require_gripper_detached": True}),
    "MustardInLeftBinTask": ("object_in_container", {"object": "mustard", "container": "grey_bin_left", "require_gripper_detached": True}),
    "MustardInRightBinTask": ("object_in_container", {"object": "mustard", "container": "grey_bin_right", "require_gripper_detached": True}),
    "ButterAboveRaisinTask": ("object_on_top", {"object": "butter", "reference_object": "raisin_box", "require_gripper_detached": True}),
    "MustardAboveRaisinTask": ("object_on_top", {"object": "mustard_bottle", "reference_object": "raisin_box", "require_gripper_detached": True}),
    "BowlStackingLeftOnRightTask": ("object_in_container", {"object": ["bowl_2"], "container": "bowl_1", "gripper_name": "gripper", "require_contact_with": True, "require_gripper_detached": True}),
    "BowlStackingRightOnLeftTask": ("object_in_container", {"object": ["bowl_1"], "container": "bowl_2", "gripper_name": "gripper", "require_contact_with": True, "require_gripper_detached": True}),
}
CONE = {"L": "left_of", "R": "right_of", "F": "in_front_of", "B": "behind"}


def _np(value: Any) -> np.ndarray:
    return np.asarray(value.detach().cpu().numpy() if hasattr(value, "detach") else value)


def state_to_numpy(state: dict) -> dict:
    return {k: state_to_numpy(v) if isinstance(v, dict) else _np(v).astype(np.float64) for k, v in state.items()}


def state_max_abs_diff(first: dict, second: dict) -> float:
    worst = 0.0
    for key, value in first.items():
        other = second[key]
        if isinstance(value, dict):
            worst = max(worst, state_max_abs_diff(value, other))
        else:
            worst = max(worst, float(np.max(np.abs(np.asarray(value) - np.asarray(other)))) if np.size(value) else 0.0)
    return worst


def flatten_state(state: dict, prefix: str = "") -> dict[str, np.ndarray]:
    out = {}
    for key, value in state.items():
        name = f"{prefix}{key}"
        if isinstance(value, dict):
            out.update(flatten_state(value, name + "/"))
        else:
            out[name] = np.asarray(value)
    return out


def unflatten_state(flat: dict[str, np.ndarray]) -> dict:
    root: dict = {}
    for key, value in flat.items():
        node = root
        parts = key.split("/")
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = np.asarray(value)
    return root


def quat_apply_inverse_np(quat_wxyz: np.ndarray, vec: np.ndarray) -> np.ndarray:
    w, x, y, z = quat_wxyz
    q = np.array([x, y, z])
    v = np.asarray(vec, dtype=np.float64)
    t = 2.0 * np.cross(-q, v)
    return v + w * t + np.cross(-q, t)


class StudyEnv:
    """One native RoboLab scene in one process; num_envs=1."""

    def __init__(self, scene_id: str, *, robolab_root: Path, output_dir: Path, device: str = "cuda:0",
                 seed: int = 1, abs_ik: bool = False, warmup_renders: int = 120) -> None:
        import robolab
        import robolab.constants
        from robolab.constants import set_output_dir
        from robolab.core.environments.config import parse_env_cfg
        from robolab.core.environments.runtime import create_env
        from robolab.registrations.droid.camera_presets import WRIST_LEFT_RIGHT_HEAD

        if not Path(robolab.__file__).resolve().is_relative_to(Path(robolab_root).resolve()):
            raise RuntimeError(f"RoboLab import {robolab.__file__} is outside {robolab_root}")
        self.scene_id = scene_id
        self.scene = SCENES[scene_id]
        self.base_task = self.scene["base_task"]
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        set_output_dir(str(output_dir))
        robolab.constants.ENABLE_SUBTASK_PROGRESS_CHECKING = False
        robolab.constants.RECORD_IMAGE_DATA = False
        robolab.constants.VERBOSE = False
        task_path = Path(robolab_root) / "robolab/tasks/benchmark" / TASK_FILES[self.base_task]
        if abs_ik:
            from robolab.registrations.droid.auto_env_registrations_abs_ik import auto_register_droid_abs_ik_envs as reg
        else:
            from robolab.registrations.droid.auto_env_registrations_jointpos import auto_register_droid_envs as reg
        reg(task=[str(task_path)], cameras=WRIST_LEFT_RIGHT_HEAD)
        cfg = parse_env_cfg(self.base_task, device=device, seed=seed, num_envs=1, use_fabric=True)
        success = getattr(cfg.terminations, "success", None)
        self.native_base_term = None if success is None else {
            "func": getattr(success.func, "__name__", str(success.func)), "params": dict(success.params)}
        cfg.terminations.success = None
        self.native_episode_length_s = float(cfg.episode_length_s)
        cfg.episode_length_s = 7200.0
        self.cfg_changes = {"terminations.success": "removed", "episode_length_s": [self.native_episode_length_s, 7200.0]}
        self.env, self.env_cfg = create_env(cfg, device=device, seed=seed, num_envs=1, policy="rws-20260926",
                                            renderer="realtime", rendering_mode="balanced", instruction_type="default")
        self.abs_ik = abs_ik
        self.step_dt = float(self.env.step_dt)
        if not math.isclose(self.step_dt, 1 / 15, abs_tol=1e-9):
            raise RuntimeError(f"step_dt {self.step_dt} != 1/15")
        self.robot = self.env.scene["robot"]
        self.contact_objects = CONTACT_OBJECTS[scene_id]
        self.named_objects = [n for n in self.contact_objects if n != "table"]
        self.movable = list(self.scene["movable"])
        self._steps = 0
        self._obs = None
        self._role_binding: dict | None = None
        body_names = list(self.robot.data.body_names)
        self._finger_idx = [body_names.index(n) for n in ("left_inner_finger", "right_inner_finger") if n in body_names]
        self._base_link_idx = body_names.index("base_link")
        joint_names = list(self.robot.data.joint_names)
        self._arm_idx = [joint_names.index(f"panda_joint{i}") for i in range(1, 8)]
        self._finger_joint_idx = joint_names.index("finger_joint")
        self._obs, _ = self.env.reset()
        self.render_only(warmup_renders)
        self.tcp_offset, self.tcp_definition = self._compute_tcp_offset()

    # ------------------------------------------------------------------ state
    def contact_sensor_names(self) -> list[str]:
        from robolab.core.sensors.contact_sensor_utils import get_contact_sensors
        return list(get_contact_sensors(self.env.scene).keys())

    def sim_time(self) -> float:
        return self._steps * self.step_dt

    def reset_native(self) -> dict:
        self.env.episode_length_buf.zero_()
        self._obs, _ = self.env.reset()
        self._steps = 0
        self.render_only(8)
        return self._obs

    def capture_state(self) -> dict:
        return state_to_numpy(self.env.scene.get_state(is_relative=True))

    def restore_state(self, state: dict, renders: int = 8) -> None:
        import torch

        self.env.episode_length_buf.zero_()
        self._obs, _ = self.env.reset()
        device = self.env.device

        def to_torch(node):
            return {k: to_torch(v) if isinstance(v, dict) else torch.as_tensor(np.asarray(v), dtype=torch.float32, device=device)
                    for k, v in node.items()}

        self.env.scene.reset_to(to_torch(state), env_ids=None, is_relative=True)
        # Joint targets: hold the restored joint positions (controller cache).
        joints = torch.as_tensor(np.asarray(state["articulation"]["robot"]["joint_position"]), dtype=torch.float32, device=device)
        self.robot.set_joint_position_target(joints)
        self.robot.set_joint_velocity_target(torch.zeros_like(joints))
        self.robot.write_data_to_sim()
        self.env.action_manager.reset()
        self.env.sim.forward()
        self.env.scene.update(dt=0.0)
        self._steps = 0
        self.render_only(renders)

    def set_object_poses(self, poses: dict[str, tuple[np.ndarray, np.ndarray]]) -> None:
        """Write env-local root poses (xyz, wxyz) and zero velocity for rigid objects."""
        import torch

        origin = self.env.scene.env_origins[0]
        for name, (pos, quat) in poses.items():
            asset = self.env.scene[name]
            pose = torch.cat([torch.as_tensor(pos, dtype=torch.float32, device=origin.device) + origin,
                              torch.as_tensor(quat, dtype=torch.float32, device=origin.device)]).reshape(1, 7)
            asset.write_root_pose_to_sim(pose)
            asset.write_root_velocity_to_sim(torch.zeros(1, 6, device=origin.device))
        self.env.sim.forward()
        self.env.scene.update(dt=0.0)

    def render_only(self, count: int) -> None:
        for _ in range(count):
            self.env.sim.render()
        for name in RECORD_CAMERAS + ("viewport_cam",):
            if name in self.env.scene.keys():
                self.env.scene[name].update(0.0, force_recompute=True)
        self._obs = self.env.observation_manager.compute()

    def settle(self, steps: int) -> list[dict]:
        hold = self.current_joint_command()
        return [self.step(hold) for _ in range(steps)]

    # ------------------------------------------------------------------ io
    def raw_observation(self) -> dict[str, np.ndarray]:
        obs = self._obs
        out = {name: _np(obs["image_obs"][name][0]).astype(np.uint8) for name in obs["image_obs"]}
        out["arm_joint_pos"] = _np(obs["proprio_obs"]["arm_joint_pos"][0]).astype(np.float64)
        out["gripper_pos"] = _np(obs["proprio_obs"]["gripper_pos"][0]).astype(np.float64)
        if "viewport_cam" in obs:
            for name, value in obs["viewport_cam"].items():
                out[f"viewport__{name}"] = _np(value[0]).astype(np.uint8)
        return out

    def current_joint_command(self) -> np.ndarray:
        q = _np(self.robot.data.joint_pos[0]).astype(np.float64)
        return np.concatenate([q[self._arm_idx], [1.0 if q[self._finger_joint_idx] / (math.pi / 4) > 0.5 else 0.0]])

    def step(self, action: np.ndarray) -> dict:
        import torch

        action = np.asarray(action, dtype=np.float64)
        if action.shape != (8,) or not np.isfinite(action).all():
            raise ValueError(f"invalid action {action.shape}")
        tensor = torch.as_tensor(action, dtype=torch.float32, device=self.env.device).reshape(1, 8)
        self._obs, _r, terminated, truncated, _info = self.env.step(tensor)
        self._steps += 1
        record = self.tick_record()
        record["command"] = action.tolist()
        record["terminated"] = bool(terminated[0])
        record["truncated"] = bool(truncated[0])
        return record

    # ------------------------------------------------------------------ measurements
    def bind_roles(self) -> dict:
        """S5: left bowl = larger robot-frame y at reset (robot frame, x forward, y left)."""
        if self.scene_id != "S5":
            self._role_binding = {"rule": "native_asset_identity"}
            return self._role_binding
        y = {name: self._robot_frame(name)[1] for name in ("bowl_1", "bowl_2")}
        left = max(y, key=y.get)
        right = min(y, key=y.get)
        self._role_binding = {"rule": "left=max_robot_frame_y_at_reset", "left_bowl": left, "right_bowl": right,
                              "robot_frame_y": y}
        return self._role_binding

    def goal_roles(self, goal_id: str) -> tuple[str, str]:
        goal = self.scene["goals"][goal_id]
        if self.scene_id == "S5":
            binding = self._role_binding or self.bind_roles()
            if goal_id == "LR":
                return binding["left_bowl"], binding["right_bowl"]
            return binding["right_bowl"], binding["left_bowl"]
        return goal["mover"], goal["reference"]

    def _robot_frame(self, name: str) -> np.ndarray:
        from robolab.core.world.world_state import get_world
        world = get_world(self.env)
        pos, _ = world.get_pose(name, env_id=0)
        rpos, rquat = world.get_pose("robot", env_id=0)
        return quat_apply_inverse_np(_np(rquat), _np(pos) - _np(rpos))

    def _compute_tcp_offset(self) -> tuple[np.ndarray, dict]:
        """Fingertip-pad centre in the Robotiq base_link frame from the pinned USD geometry (open gripper).

        The PhysX inner-finger body origins coincide with base_link in this asset, so body
        origins cannot define a TCP.  The pad centre is the midpoint of the two inner-finger
        geometry bounds expressed relative to base_link.
        """
        from pxr import Usd, UsdGeom

        stage = self.env.scene.stage
        root = stage.GetPrimAtPath("/World/envs/env_0/robot")
        base = None
        fingers = {}
        for prim in Usd.PrimRange(root):
            name = prim.GetName()
            if name == "base_link" and "Robotiq" in str(prim.GetPath()) and base is None:
                base = prim
            if name in ("left_inner_finger", "right_inner_finger") and name not in fingers:
                fingers[name] = prim
        if base is None or len(fingers) != 2:
            return np.zeros(3), {"kind": "base_link_fallback", "reason": "prims not found"}
        cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_, UsdGeom.Tokens.render,
                                                          UsdGeom.Tokens.proxy], useExtentsHint=False)
        centres = {}
        for name, prim in fingers.items():
            rng = cache.ComputeRelativeBound(prim, base).ComputeAlignedRange()
            centres[name] = np.array(rng.GetMidpoint(), dtype=np.float64)
        offset = (centres["left_inner_finger"] + centres["right_inner_finger"]) / 2
        return offset, {"kind": "inner_finger_geometry_midpoint_in_base_link", "offset_m": offset.tolist(),
                        "finger_centres": {k: v.tolist() for k, v in centres.items()},
                        "base_prim": str(base.GetPath())}

    def tcp(self) -> np.ndarray:
        origin = _np(self.env.scene.env_origins[0])
        pos = _np(self.robot.data.body_pos_w[0, self._base_link_idx]).astype(np.float64)
        quat = _np(self.robot.data.body_quat_w[0, self._base_link_idx]).astype(np.float64)
        w, x, y, z = quat
        q = np.array([x, y, z])
        t = 2.0 * np.cross(q, self.tcp_offset)
        rotated = self.tcp_offset + w * t + np.cross(q, t)
        return pos + rotated - origin

    def tick_record(self) -> dict:
        from robolab.core.world.world_state import get_world
        from robolab.core.task import predicate_logic as pl
        from robolab.core.task import conditionals as cond

        world = get_world(self.env)
        thr = THRESHOLDS["contact_force_threshold_n"]
        objects = {}
        tcp = self.tcp()
        for name in self.named_objects:
            pos, quat = world.get_pose(name, env_id=0)
            pos, quat = _np(pos).astype(np.float64), _np(quat).astype(np.float64)
            vel = _np(world.get_velocity(name, env_id=0)).astype(np.float64).reshape(-1)
            corners, centroid = world.get_bbox(name, env_id=0)
            corners = np.asarray([[c[0], c[1], c[2]] for c in corners], dtype=np.float64)
            geom = world._get_local_geometry(name)
            local = _np(geom["corners"]).astype(np.float64)
            lo, hi = local.min(axis=0), local.max(axis=0)
            p_local = quat_apply_inverse_np(quat, tcp - pos)
            gap = np.maximum(np.maximum(lo - p_local, 0.0), p_local - hi)
            objects[name] = {
                "pos": pos.tolist(), "quat": quat.tolist(), "lin_vel": vel[:3].tolist(),
                "ang_vel": vel[3:6].tolist() if vel.size >= 6 else None,
                "centroid": np.asarray(centroid, dtype=np.float64).tolist(),
                "bbox_min": corners.min(axis=0).tolist(), "bbox_max": corners.max(axis=0).tolist(),
                "local_bbox_min": lo.tolist(), "local_bbox_max": hi.tolist(),
                "robot_frame": self._robot_frame(name).tolist(),
                "tcp_obb_distance": float(np.linalg.norm(gap)),
            }
        contacts = {}
        pairs = [("gripper", o) for o in self.contact_objects] + [
            (a, b) for i, a in enumerate(self.contact_objects) for b in self.contact_objects[i + 1:]]
        for a, b in pairs:
            if True:
                try:
                    force = _np(world.get_contact_force(a, b, env_id=0)).astype(np.float64)
                    contacts[f"{a}__{b}"] = {"in_contact": bool(world.in_contact(a, b, force_threshold=thr, env_id=0)),
                                             "net_force": force.tolist()}
                except Exception as error:  # sensor absent for this pair
                    contacts[f"{a}__{b}"] = {"in_contact": None, "error": type(error).__name__}
        native = {}
        for task, (func, params) in NATIVE_SUCCESS.items():
            if task not in self._scene_native_tasks():
                continue
            native[task] = bool(getattr(cond, func)(self.env, **params, env_id=0))
        study = {}
        for goal_id in self.scene["goals"]:
            study[goal_id] = self.study_predicate(goal_id, world, pl)
        q = _np(self.robot.data.joint_pos[0]).astype(np.float64)
        qd = _np(self.robot.data.joint_vel[0]).astype(np.float64)
        base = _np(self.robot.data.body_pos_w[0, self._base_link_idx]) - _np(self.env.scene.env_origins[0])
        return {
            "t": self.sim_time(), "step": self._steps, "sim_current_time": float(self.env.sim.current_time),
            "objects": objects, "contacts": contacts, "native": native, "study": study,
            "joint_pos": q.tolist(), "joint_vel": qd.tolist(),
            "gripper_closed_fraction": float(q[self._finger_joint_idx] / (math.pi / 4)),
            "tcp": tcp.tolist(), "base_link": base.tolist(),
        }

    def _scene_native_tasks(self) -> set[str]:
        tasks = {self.base_task}
        tasks.update(g["native_task"] for g in self.scene["goals"].values() if g["native_task"])
        return tasks

    def study_predicate(self, goal_id: str, world: Any = None, pl: Any = None) -> dict:
        from robolab.core.world.world_state import get_world
        from robolab.core.task import predicate_logic as _pl

        world = world or get_world(self.env)
        pl = pl or _pl
        kind = self.scene["goals"][goal_id]["kind"]
        mover, ref = self.goal_roles(goal_id)
        thr = THRESHOLDS["contact_force_threshold_n"]
        detached = not bool(world.in_contact(mover, "gripper", force_threshold=thr, env_id=0))
        if kind.startswith("cone:"):
            relation = bool(getattr(pl, CONE[kind[5:]])(world, mover, ref, "robot", False, THRESHOLDS["cone_deg"], env_id=0))
            support = bool(world.in_contact(mover, "table", force_threshold=thr, env_id=0))
        elif kind == "container":
            relation = bool(pl.in_opentop_container(world, mover, ref, THRESHOLDS["container_tolerance_m"], env_id=0))
            support = relation
        elif kind == "on_top":
            support = bool(world.is_supported_on_surface(mover, ref, env_id=0))
            relation = bool(pl.centroid_in_footprint(world, mover, ref, THRESHOLDS["footprint_tolerance_m"], env_id=0))
        elif kind == "stacked":
            relation = bool(pl.in_opentop_container(world, mover, ref, THRESHOLDS["container_tolerance_m"], env_id=0))
            support = bool(world.in_contact(mover, ref, force_threshold=thr, env_id=0))
        else:
            raise ValueError(kind)
        return {"mover": mover, "reference": ref, "relation": relation, "support": support, "detached": detached,
                "goal": bool(relation and support and detached)}

    def close(self) -> None:
        self.env.close()
