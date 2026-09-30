import numpy as np
import pytest

from cobot_qa.cell import BLOCKS
from cobot_qa.hover import DOWN_QUAT, Z_CLEAR, hover_is_reachable, hover_position, select_target
from cobot_qa.kinematics import MAX_REACH

DETS = [
    {"colour": "red", "x": 0.49, "y": -0.03},
    {"colour": "blue", "x": 0.31, "y": 0.06},
    {"colour": "red", "x": 0.40, "y": 0.14},
    {"colour": "red", "x": 0.41, "y": -0.13},
]


def test_select_target_orders_by_x_then_y():
    assert select_target(DETS, "red", 0)["x"] == 0.40
    assert select_target(DETS, "red", 1)["x"] == 0.41
    assert select_target(DETS, "red", 2)["x"] == 0.49


def test_select_target_filters_by_colour_and_handles_missing():
    assert select_target(DETS, "blue")["y"] == 0.06
    assert select_target(DETS, "green") is None
    assert select_target(DETS, "red", 3) is None
    assert select_target(DETS, "red", -1) is None
    assert select_target([], "red") is None


def test_hover_position_uses_detection_xy_and_clearance():
    assert hover_position({"x": 0.3, "y": -0.1}) == (0.3, -0.1, Z_CLEAR)
    assert hover_position({"x": 0.3, "y": -0.1}, 0.4)[2] == 0.4


def test_down_quaternion_points_tool_z_at_the_floor():
    x, y, z, w = DOWN_QUAT
    assert x * x + y * y + z * z + w * w == pytest.approx(1.0)
    # rotate the tool z axis (0,0,1) by the quaternion
    R = np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])
    assert (R @ np.array([0, 0, 1.0])) == pytest.approx([0, 0, -1.0])


def test_every_block_hover_point_is_reachable():
    for b in BLOCKS:
        det = {"colour": "x", "x": b.x, "y": b.y}
        assert hover_is_reachable(det), b.name


def test_far_target_is_reported_unreachable():
    assert not hover_is_reachable({"x": MAX_REACH, "y": 0.5})
