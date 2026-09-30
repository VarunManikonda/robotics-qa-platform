"""Deterministic inverse kinematics for the UR5e, tool pointing straight down.

Why not just MoveIt's /compute_ik: it returned different arm configurations for the same pose on
different calls (a 2.94 rad and a 1.91 rad move to the same waypoint), and one of them stalled the
arm. Here the answer for a pose depends only on the pose: a damped least-squares solver always starts
from the same nominal "elbow up, tool down" configuration Q_NOM and is pulled towards it, so every
pose is reached in the same arm configuration and neighbouring poses need only small joint moves.

Pure numpy on top of the verified forward kinematics, so it is unit-tested without ROS.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

from .kinematics import ALPHA, A, D, _dh, fk

DOWN = np.array([0.0, 0.0, -1.0])
# joint limits of the UR5e model in simulation: +/- 2 pi, except the elbow at +/- pi
LIMITS = (2 * math.pi, 2 * math.pi, math.pi, 2 * math.pi, 2 * math.pi, 2 * math.pi)
Q_NOM = (0.3, -1.6, 1.9, -1.87, -1.5708, 0.0)  # elbow up, tool down, over the middle of the table
POS_TOL = 1e-4  # metres
ANG_TOL = 1e-3  # radians (tool z axis vs straight down)
MIN_JOINT_HEIGHT = 0.12  # metres; elbow and wrist joints must stay this far above the floor


def _residual(q: np.ndarray, target: np.ndarray) -> np.ndarray:
    T = fk(q)
    return np.concatenate([T[:3, 3] - target, T[:3, 2] - DOWN])


def _jacobian(q: np.ndarray, target: np.ndarray, r0: np.ndarray) -> np.ndarray:
    J = np.zeros((6, 6))
    h = 1e-6
    for i in range(6):
        dq = q.copy()
        dq[i] += h
        J[:, i] = (_residual(dq, target) - r0) / h
    return J


def joint_heights(q: Sequence[float]) -> list[float]:
    """Height above the floor of each joint frame origin (frames 1..6: shoulder, elbow, wrists, flange)."""
    T = np.diag([-1.0, -1.0, 1.0, 1.0])
    out = []
    for i in range(6):
        T = T @ _dh(A[i], ALPHA[i], D[i], q[i])
        out.append(float(T[2, 3]))
    return out


def _refine(
    target: np.ndarray, q: np.ndarray, mu: float, iters: int, pos_tol: float, ang_tol: float
) -> np.ndarray:
    q_nom = np.array(Q_NOM, dtype=float)
    lim = np.array(LIMITS)
    for _ in range(iters):
        r = _residual(q, target)
        if np.linalg.norm(r[:3]) < pos_tol and np.linalg.norm(r[3:]) < ang_tol:
            break
        J = _jacobian(q, target, r)
        # least squares on the task, gently pulled towards Q_NOM (fixes the configuration and the free spin)
        H = J.T @ J + (mu + 1e-4) * np.eye(6)
        g = J.T @ r + mu * (q - q_nom)
        q = np.clip(q - np.linalg.solve(H, g), -lim, lim)
    return q


def solve(x: float, y: float, z: float, mu: float = 1e-6, steps: int = 12) -> list[float] | None:
    """Joint angles putting tool0 at (x, y, z) with its z axis pointing down, or None.

    The target is approached from the pose of Q_NOM in `steps` small moves, each solved from the previous
    answer. Solving directly from Q_NOM jumped to a different arm configuration for far targets (elbow
    down, wrist flipped); walking there keeps the solution on the same branch.
    """
    target = np.array([x, y, z], dtype=float)
    start = fk(Q_NOM)[:3, 3]
    q = np.array(Q_NOM, dtype=float)
    for k in range(1, steps + 1):
        wp = start + (target - start) * (k / steps)
        last = k == steps
        q = _refine(wp, q, mu, 60, POS_TOL if last else 1e-3, ANG_TOL if last else 1e-2)
    r = _residual(q, target)
    if np.linalg.norm(r[:3]) >= POS_TOL * 5 or np.linalg.norm(r[3:]) >= ANG_TOL * 5:
        return None
    if min(joint_heights(q)[2:5]) < MIN_JOINT_HEIGHT:  # elbow / wrist joints too close to the floor
        return None
    return [float(v) for v in q]
