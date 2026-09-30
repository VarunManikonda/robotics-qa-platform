"""Target selection and hover pose for the pick-and-place cycle. Pure Python, unit-tested.

The tool points straight down: tool0's z axis is world -z, which is a 180 degree rotation about
the x axis, quaternion (x, y, z, w) = (1, 0, 0, 0). The hover point is `z_clear` metres above
the floor, in the robot base frame (== world frame in this cell).
"""

from __future__ import annotations

from .kinematics import reachable

DOWN_QUAT = (1.0, 0.0, 0.0, 0.0)
Z_CLEAR = 0.25  # tool0 height above the floor at the hover point, metres


def select_target(detections: list[dict], colour: str, index: int = 0) -> dict | None:
    """The `index`-th detection of `colour`, ordered by (x, y) so the choice is deterministic."""
    same = sorted((d for d in detections if d.get("colour") == colour), key=lambda d: (d["x"], d["y"]))
    return same[index] if 0 <= index < len(same) else None


def hover_position(det: dict, z_clear: float = Z_CLEAR) -> tuple[float, float, float]:
    return (float(det["x"]), float(det["y"]), z_clear)


def hover_is_reachable(det: dict, z_clear: float = Z_CLEAR) -> bool:
    return reachable(hover_position(det, z_clear))
