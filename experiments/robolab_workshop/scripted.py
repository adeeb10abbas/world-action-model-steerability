"""Model-blind scripted pick-and-place controller for feasibility checks (jointpos env, DLS IK on the TCP).

Deterministic waypoint recipe per goal kind. It is not tuned per candidate; a failure rejects the candidate.
"""
from __future__ import annotations

import math

import numpy as np

from .catalog import SCENES

LIFT_Z = 0.22          # transit height of TCP above table (env-local z)
MAX_STEP_M = 0.012     # TCP position step per control tick (0.18 m/s)
CARRY_STEP_M = 0.006   # slower TCP step while the gripper is commanded closed (in-hand slip)
MAX_ROT_RAD = 0.08
LAMBDA = 0.05
NULL_GAIN = 0.01       # null-space pull toward the native home posture per tick (exact projector, no task leak)
HOME_Q = np.array([0.0, -0.628, 0.0, -2.513, 0.0, 1.885, 0.0])
LIMIT_MARGIN = 0.03
WINDUP_RAD = 0.15      # bound on |commanded - measured| joint position when integrating IK steps under load
PALM_CLEARANCE_WIDE_M = 0.025    # objects nearly as wide as the 85 mm opening hit the finger links earlier
PALM_CLEARANCE_NARROW_M = 0.05   # TCP depth below the object top when the closing width is <= 75 mm
NARROW_WIDTH_M = 0.075
FINGER_FLOOR_M = 0.028           # fingertips sit ~25 mm below the TCP; keep them just above the resting bottom
CLEAR = 0.06           # lateral goal clearance margin beyond both half-extents (>= 2 cm collision clearance)


def quat_to_mat(q):
    w, x, y, z = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def rot_err(R_des, R):
    E = R_des @ R.T
    angle = math.acos(max(-1.0, min(1.0, (np.trace(E) - 1) / 2)))
    if angle < 1e-6:
        return np.zeros(3)
    axis = np.array([E[2, 1] - E[1, 2], E[0, 2] - E[2, 0], E[1, 0] - E[0, 1]]) / (2 * math.sin(angle))
    return axis * angle


def skew(v):
    return np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])


class ScriptedController:
    def __init__(self, env) -> None:
        self.env = env
        robot = env.robot
        self.body = env._base_link_idx
        self.arm = env._arm_idx
        self.fixed_base = bool(robot.is_fixed_base)
        lim = robot.data.soft_joint_pos_limits[0].detach().cpu().numpy().astype(np.float64)[self.arm]
        self.q_lo, self.q_hi = lim[:, 0] + LIMIT_MARGIN, lim[:, 1] - LIMIT_MARGIN
        self.q_cmd = None

    def _jacobian(self):
        J = self.env.robot.root_physx_view.get_jacobians()
        idx = self.body - 1 if self.fixed_base else self.body
        J = J[0, idx, :, :].detach().cpu().numpy().astype(np.float64)
        return J[:, self.arm] if J.shape[1] > len(self.arm) + 1 else J[:, :7]

    def _pose(self):
        d = self.env.robot.data
        origin = self.env.env.scene.env_origins[0].detach().cpu().numpy()
        p = d.body_pos_w[0, self.body].detach().cpu().numpy().astype(np.float64) - origin
        R = quat_to_mat(d.body_quat_w[0, self.body].detach().cpu().numpy().astype(np.float64))
        return p, R

    def command(self, tcp_target: np.ndarray, R_des: np.ndarray, gripper: float) -> np.ndarray:
        p, R = self._pose()
        tcp = p + R @ self.env.tcp_offset
        dp = tcp_target - tcp
        n = np.linalg.norm(dp)
        step = CARRY_STEP_M if gripper > 0.5 else MAX_STEP_M
        if n > step:
            dp *= step / n
        dr = rot_err(R_des, R)
        a = np.linalg.norm(dr)
        if a > MAX_ROT_RAD:
            dr *= MAX_ROT_RAD / a
        J = self._jacobian()
        Jl = J[:3] - skew(tcp - p) @ J[3:]
        Jt = np.vstack([Jl, J[3:]])
        err = np.concatenate([dp, dr])
        Jpinv = Jt.T @ np.linalg.inv(Jt @ Jt.T + LAMBDA ** 2 * np.eye(6))
        q = self.env.robot.data.joint_pos[0].detach().cpu().numpy().astype(np.float64)[self.arm]
        null = np.eye(7) - np.linalg.pinv(Jt) @ Jt
        dq = Jpinv @ err + null @ (NULL_GAIN * (HOME_Q - q))
        # Integrate commanded joint targets (bounded windup) so the joint PD drive overcomes steady load sag.
        base = q if self.q_cmd is None else self.q_cmd
        self.q_cmd = np.clip(np.clip(base + dq, q - WINDUP_RAD, q + WINDUP_RAD), self.q_lo, self.q_hi)
        return np.concatenate([self.q_cmd, [gripper]])

    def move(self, target, R_des, gripper, max_ticks=90, tol=0.006, ticks=None):
        ticks = [] if ticks is None else ticks
        self.q_cmd = None  # windup never carries across waypoint segments
        for _ in range(max_ticks):
            ticks.append(self.env.step(self.command(target, R_des, gripper)))
            p, R = self._pose()
            if np.linalg.norm(p + R @ self.env.tcp_offset - target) < tol and np.linalg.norm(rot_err(R_des, R)) < 0.05:
                break
        return ticks

    def hold(self, gripper, n, ticks):
        p, R = self._pose()
        target = p + R @ self.env.tcp_offset
        self.q_cmd = None
        for _ in range(n):
            ticks.append(self.env.step(self.command(target, R, gripper)))
        return ticks


def down_rotation(yaw: float) -> np.ndarray:
    """base_link orientation with +x (approach) pointing down and +y (finger closing) along yaw in the table plane."""
    x = np.array([0.0, 0.0, -1.0])
    y = np.array([math.cos(yaw), math.sin(yaw), 0.0])
    z = np.cross(x, y)
    return np.stack([x, y, z], axis=1)


def object_frame(tick: dict, name: str) -> dict:
    o = tick["objects"][name]
    lo, hi = np.array(o["bbox_min"]), np.array(o["bbox_max"])
    R = quat_to_mat(np.array(o["quat"]))
    return {"centre": (lo + hi) / 2, "lo": lo, "hi": hi, "R": R, "pos": np.array(o["pos"])}


def grasp_plan(tick: dict, scene_id: str, mover: str) -> dict:
    f = object_frame(tick, mover)
    c, lo, hi = f["centre"], f["lo"], f["hi"]
    o = tick["objects"][mover]
    if scene_id == "S5":
        # Rim point on the far side along the robot-base-to-bowl direction; fingers close radially across the rim.
        ext = hi - lo
        radius = min(ext[0], ext[1]) / 2
        u = c[:2] / max(np.linalg.norm(c[:2]), 1e-9)
        point = np.array([c[0] + u[0] * (radius - 0.012), c[1] + u[1] * (radius - 0.012), hi[2] - 0.02])
        yaw = math.atan2(u[1], u[0])
        return {"point": point, "yaw": yaw, "height_above_bottom": point[2] - lo[2], "rule": "far_rim_radial"}
    # Close the fingers across the narrower horizontal axis of the world-frame bounding box (starts vary yaw by
    # at most 10 degrees; the USD local geometry frames are not consistently aligned with the root quaternion).
    ext = hi - lo
    close_axis = 0 if ext[0] <= ext[1] else 1
    yaw = 0.0 if close_axis == 0 else math.pi / 2
    depth = PALM_CLEARANCE_NARROW_M if ext[close_axis] <= NARROW_WIDTH_M else PALM_CLEARANCE_WIDE_M
    z = max(lo[2] + FINGER_FLOOR_M, hi[2] - depth)
    return {"point": np.array([c[0], c[1], z]), "yaw": yaw, "height_above_bottom": z - lo[2],
            "rule": "narrow_world_aabb_axis", "depth_below_top_m": depth, "closing_width_m": float(ext[close_axis]),
            "other_width_m": float(ext[1 - close_axis])}


def place_target(tick: dict, scene_id: str, goal_id: str, mover: str, reference: str, grasp: dict) -> dict:
    kind = SCENES[scene_id]["goals"][goal_id]["kind"]
    m = object_frame(tick, mover)
    r = object_frame(tick, reference)
    mh = (m["hi"] - m["lo"]) / 2
    rh = (r["hi"] - r["lo"]) / 2
    rc = r["centre"]
    table_z = min(m["lo"][2], r["lo"][2])
    if kind.startswith("cone:"):
        d = kind[5:]
        direction = {"L": (0, 1), "R": (0, -1), "F": (-1, 0), "B": (1, 0)}[d]
        axis = 0 if direction[0] else 1
        dist = rh[axis] + mh[axis] + CLEAR
        xy = np.array([rc[0] + direction[0] * dist, rc[1] + direction[1] * dist])
        bottom = table_z + 0.01
    elif kind == "container":
        xy = rc[:2].copy()
        bottom = r["hi"][2] + 0.03
    elif kind == "on_top":
        xy = rc[:2].copy()
        bottom = r["hi"][2] + 0.01
    elif kind == "stacked":
        xy = rc[:2].copy()
        bottom = r["lo"][2] + 0.02
    else:
        raise ValueError(kind)
    # keep the same grasp offset relative to the mover centre
    offset_xy = grasp["point"][:2] - m["centre"][:2]
    point = np.array([xy[0] + offset_xy[0], xy[1] + offset_xy[1], bottom + grasp["height_above_bottom"]])
    return {"point": point, "mover_centre_xy": xy.tolist(), "bottom_z": bottom}


def fold_yaw(yaw: float, centre: float = 0.0) -> float:
    """The parallel gripper is symmetric under a half turn; use the equivalent yaw within +-pi/2 of the start
    posture's closing yaw so the last wrist joint stays away from its limits."""
    return (yaw - centre + math.pi / 2) % math.pi - math.pi / 2 + centre


def run_goal(env, scene_id: str, goal_id: str) -> dict:
    """Execute one scripted pick-and-place from the current (restored) state. Returns ticks and plan."""
    ctl = ScriptedController(env)
    tick0 = env.tick_record()
    mover, reference = env.goal_roles(goal_id)
    grasp = grasp_plan(tick0, scene_id, mover)
    place = place_target(tick0, scene_id, goal_id, mover, reference, grasp)
    ticks = [tick0]
    grasp["yaw_raw"] = grasp["yaw"]
    _, R0 = ctl._pose()
    grasp["start_closing_yaw"] = float(math.atan2(R0[1, 1], R0[0, 1]))
    grasp["yaw"] = fold_yaw(grasp["yaw"], grasp["start_closing_yaw"])
    R_g = down_rotation(grasp["yaw"])
    above = grasp["point"].copy()
    above[2] = LIFT_Z
    ctl.move(above, R_g, 0.0, 120, ticks=ticks)
    ctl.move(grasp["point"], R_g, 0.0, 90, tol=0.004, ticks=ticks)
    ctl.hold(1.0, 20, ticks)
    lift = grasp["point"].copy()
    lift[2] = LIFT_Z
    ctl.move(lift, R_g, 1.0, 120, ticks=ticks)
    over = place["point"].copy()
    over[2] = LIFT_Z
    ctl.move(over, R_g, 1.0, 200, ticks=ticks)
    # Closed-loop correction for in-hand slip: re-aim so the measured mover centre lands on the planned centre.
    hf = object_frame(ticks[-1], mover)
    held = hf["centre"][:2]
    tcp_now = np.array(ticks[-1]["tcp"])
    target_xy = np.array(place["mover_centre_xy"]) - (held - tcp_now[:2])
    target_z = place["bottom_z"] + (tcp_now[2] - hf["lo"][2])
    place["slip_corrected_point"] = [float(target_xy[0]), float(target_xy[1]), float(target_z)]
    over = np.array([target_xy[0], target_xy[1], LIFT_Z])
    ctl.move(over, R_g, 1.0, 60, tol=0.004, ticks=ticks)
    down = np.array(place["slip_corrected_point"])
    ctl.move(down, R_g, 1.0, 120, tol=0.004, ticks=ticks)
    ctl.hold(0.0, 15, ticks)
    retreat = np.array(place["slip_corrected_point"])
    retreat[2] = LIFT_Z
    ctl.move(retreat, R_g, 0.0, 60, ticks=ticks)
    ctl.hold(0.0, 30, ticks)
    return {"ticks": ticks, "grasp": {k: (v.tolist() if isinstance(v, np.ndarray) else v) for k, v in grasp.items()},
            "place": {k: (v.tolist() if isinstance(v, np.ndarray) else v) for k, v in place.items()},
            "mover": mover, "reference": reference}
