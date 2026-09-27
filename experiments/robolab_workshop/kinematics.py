"""Frozen analysis kinematics: Franka Panda forward kinematics plus a fitted fixed flange->TCP offset.

The TCP offset and robot base translation are fitted once by linear least squares on recorded ticks (measured
joint positions vs. the simulator's TCP), then frozen in `analysis_calibration.json`. Used only to evaluate the
*proposed* action chunk geometrically (baseline feature); never to replace measured simulator state.
"""
from __future__ import annotations

import math

import numpy as np

# Craig (modified) DH parameters for the Panda arm: (a_{i-1}, d_i, alpha_{i-1})
_DH = [(0.0, 0.333, 0.0), (0.0, 0.0, -math.pi / 2), (0.0, 0.316, math.pi / 2), (0.0825, 0.0, math.pi / 2),
       (-0.0825, 0.384, -math.pi / 2), (0.0, 0.0, math.pi / 2), (0.088, 0.0, math.pi / 2)]
_FLANGE_D = 0.107


def _tf(a, d, alpha, theta):
    ca, sa, ct, st = math.cos(alpha), math.sin(alpha), math.cos(theta), math.sin(theta)
    return np.array([[ct, -st, 0, a], [st * ca, ct * ca, -sa, -d * sa], [st * sa, ct * sa, ca, d * ca], [0, 0, 0, 1]])


def flange(q) -> tuple[np.ndarray, np.ndarray]:
    T = np.eye(4)
    for (a, d, alpha), th in zip(_DH, q[:7]):
        T = T @ _tf(a, d, alpha, float(th))
    T = T @ _tf(0.0, _FLANGE_D, 0.0, 0.0)
    return T[:3, 3], T[:3, :3]


def fit_tcp(joint_positions: np.ndarray, tcps: np.ndarray) -> dict:
    """Solve tcp = base + p_f(q) + R_f(q) @ offset for (base, offset) by least squares."""
    A, b = [], []
    for q, tcp in zip(joint_positions, tcps):
        p, R = flange(q)
        A.append(np.hstack([np.eye(3), R]))
        b.append(np.asarray(tcp) - p)
    x, *_ = np.linalg.lstsq(np.vstack(A), np.concatenate(b), rcond=None)
    pred = np.array([x[:3] + flange(q)[0] + flange(q)[1] @ x[3:] for q in joint_positions])
    res = np.linalg.norm(pred - tcps, axis=1)
    return {"base": x[:3].tolist(), "offset": x[3:].tolist(), "residual_max_m": float(res.max()),
            "residual_mean_m": float(res.mean()), "n": int(len(tcps))}


def tcp(q, calib: dict) -> np.ndarray:
    p, R = flange(q)
    return np.asarray(calib["base"]) + p + R @ np.asarray(calib["offset"])


def aabb_distance(point: np.ndarray, lo, hi) -> float:
    d = np.maximum(np.maximum(np.asarray(lo) - point, 0.0), point - np.asarray(hi))
    return float(np.linalg.norm(d))
