"""Forward kinematics and reachability for the Universal Robots UR5e.

Uses the published UR DH parameters. The ROS `base_link` frame is the DH base
frame rotated 180 degrees about Z, so `fk(..., ros_base=True)` matches what
`tf2_echo base_link tool0` prints.
"""

from __future__ import annotations

import math
from typing import Sequence

import numpy as np

# UR5e DH parameters (metres / radians)
D = (0.1625, 0.0, 0.0, 0.1333, 0.0997, 0.0996)
A = (0.0, -0.425, -0.3922, 0.0, 0.0, 0.0)
ALPHA = (math.pi / 2, 0.0, 0.0, math.pi / 2, -math.pi / 2, 0.0)

JOINT_LIMIT = 2 * math.pi  # UR5e joints are +/- 360 deg
MAX_REACH = 0.85  # UR datasheet nominal reach, metres


def _dh(a: float, alpha: float, d: float, theta: float) -> np.ndarray:
    ct, st = math.cos(theta), math.sin(theta)
    ca, sa = math.cos(alpha), math.sin(alpha)
    return np.array(
        [
            [ct, -st * ca, st * sa, a * ct],
            [st, ct * ca, -ct * sa, a * st],
            [0.0, sa, ca, d],
            [0.0, 0.0, 0.0, 1.0],
        ]
    )


def fk(joints: Sequence[float], ros_base: bool = True) -> np.ndarray:
    """4x4 pose of the tool flange for six joint angles in radians."""
    if len(joints) != 6:
        raise ValueError(f"expected 6 joint angles, got {len(joints)}")
    if any(not math.isfinite(q) for q in joints):
        raise ValueError("joint angles must be finite")
    T = np.eye(4)
    for i in range(6):
        T = T @ _dh(A[i], ALPHA[i], D[i], joints[i])
    if ros_base:
        T = np.diag([-1.0, -1.0, 1.0, 1.0]) @ T
    return T


def fk_position_mm(joints_deg: Sequence[float]) -> tuple[float, float, float]:
    T = fk([math.radians(q) for q in joints_deg])
    return tuple(float(v) * 1000.0 for v in T[:3, 3])  # type: ignore[return-value]


def within_joint_limits(joints: Sequence[float]) -> bool:
    return all(abs(q) <= JOINT_LIMIT for q in joints)


def reachable(point_m: Sequence[float], margin: float = 0.05) -> bool:
    """Conservative check: is a target inside the arm's spherical work envelope?

    A sphere test is only a necessary condition, so a `True` here does not
    guarantee IK will succeed (wrist geometry, orientation and collisions all
    matter). A `False` is a reliable rejection, which is what makes it a cheap
    pre-flight test for mission targets.
    """
    x, y, z = point_m
    shoulder_z = D[0]
    r = math.sqrt(x * x + y * y + (z - shoulder_z) ** 2)
    return r <= (MAX_REACH - margin)


def nearest_equivalent(q: Sequence[float], ref: Sequence[float], limit: float = JOINT_LIMIT) -> list[float]:
    """Each angle shifted by whole turns to the value closest to `ref` that stays within +/- limit.

    IK solvers may return an angle a full turn (2 pi) away from the current one; the arm pose is
    identical, but moving there would spin the joint all the way round.
    """
    out = []
    for a, r in zip(q, ref, strict=True):
        best = a
        for k in range(-2, 3):
            cand = a + k * 2 * math.pi
            if abs(cand) <= limit and abs(cand - r) < abs(best - r):
                best = cand
        out.append(best)
    return out
