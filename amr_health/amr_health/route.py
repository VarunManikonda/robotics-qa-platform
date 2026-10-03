"""The patrol route for the AMR demo, in the map frame of the Nav2 TurtleBot3 world.

The robot spawns at HOME. The other points are the gaps between the pillars. If a point is too close to
an obstacle Nav2 rejects it; the goal runner logs that and moves on, so a bad point never stops the demo.
"""

from __future__ import annotations

import math

HOME = (-2.0, -0.5, 0.0)
WAYPOINTS: list[tuple[float, float, float]] = [
    (0.55, -0.55, 0.0),
    (0.55, 0.55, math.pi / 2),
    (-0.55, 0.55, math.pi),
    (-0.55, -0.55, -math.pi / 2),
    HOME,
]


def yaw_to_quat(yaw: float) -> tuple[float, float]:
    """(z, w) of a rotation about the vertical axis."""
    return math.sin(yaw / 2.0), math.cos(yaw / 2.0)


def goals(laps: int) -> list[tuple[float, float, float]]:
    if laps < 1:
        raise ValueError("laps must be >= 1")
    return WAYPOINTS * laps
