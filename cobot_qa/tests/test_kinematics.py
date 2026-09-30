import math

import numpy as np
import pytest

from cobot_qa.kinematics import fk, fk_position_mm, reachable, within_joint_limits

# Answer key computed for the UR5e in ROS (base_link -> tool0), order
# pan/lift/elbow/wrist1/wrist2/wrist3, degrees, result in mm.
ANSWER_KEY = [
    ([0, 0, 0, 0, 0, 0], (817.20, 232.90, 62.80)),
    ([30, 0, 0, 0, 0, 0], (591.27, 610.30, 62.80)),
    ([0, -60, 60, 0, 0, 0], (604.70, 232.90, 430.86)),
    ([45, -60, 75, -30, 40, 0], (331.90, 628.32, 349.32)),
]


@pytest.mark.parametrize("joints_deg, expected", ANSWER_KEY)
def test_fk_matches_answer_key(joints_deg, expected):
    got = fk_position_mm(joints_deg)
    assert got == pytest.approx(expected, abs=0.1)


def test_fk_is_rigid_transform():
    T = fk([0.3, -1.1, 1.4, -0.5, 0.9, 0.2])
    R = T[:3, :3]
    assert np.allclose(R @ R.T, np.eye(3), atol=1e-9)
    assert np.linalg.det(R) == pytest.approx(1.0)


def test_wrist3_rotation_does_not_move_tool_origin():
    base = fk_position_mm([10, -50, 70, -20, 30, 0])
    spun = fk_position_mm([10, -50, 70, -20, 30, 170])
    assert spun == pytest.approx(base, abs=1e-6)


def test_fk_rejects_bad_input():
    with pytest.raises(ValueError):
        fk([0, 0, 0])
    with pytest.raises(ValueError):
        fk([0, 0, 0, 0, 0, math.nan])


def test_joint_limits():
    assert within_joint_limits([0] * 6)
    assert not within_joint_limits([0, 0, 0, 0, 0, 7.0])


def test_reachability_rejects_far_target():
    # the failure seen in Sia-Cobot: a block ~0.87 m radially from the base
    assert not reachable((0.75, -0.44, 0.05))


def test_reachability_accepts_near_target():
    assert reachable((0.4, 0.1, 0.1))
