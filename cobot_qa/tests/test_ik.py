import numpy as np
import pytest

from cobot_qa.cell import BLOCKS, PADS
from cobot_qa.ik import LIMITS, MIN_JOINT_HEIGHT, Q_NOM, joint_heights, solve
from cobot_qa.kinematics import fk
from cobot_qa.sorter import (
    PARK_JOINTS,
    READY_XYZ,
    SLOT_OFFSETS_Y,
    Z_CARRY,
    Z_GRASP,
    Z_HOVER,
    Z_PLACE,
    slot_xy,
)


def all_poses():
    poses = {"ready": READY_XYZ}
    for b in BLOCKS:
        for label, z in (("hover", Z_HOVER), ("grasp", Z_GRASP), ("carry", Z_CARRY)):
            poses[f"{b.name} {label}"] = (b.x, b.y, z)
    for pad in PADS:
        for i in range(len(SLOT_OFFSETS_Y)):
            x, y = slot_xy(pad, i)
            poses[f"{pad.name}{i} carry"] = (x, y, Z_CARRY)
            poses[f"{pad.name}{i} place"] = (x, y, Z_PLACE)
    return poses


POSES = all_poses()


@pytest.mark.parametrize("name", POSES)
def test_every_cell_pose_is_solved_accurately_with_the_tool_pointing_down(name):
    x, y, z = POSES[name]
    q = solve(x, y, z)
    assert q is not None, name
    T = fk(q)
    assert np.linalg.norm(T[:3, 3] - np.array([x, y, z])) < 5e-4  # under half a millimetre
    assert T[2, 2] == pytest.approx(-1.0, abs=1e-4)  # tool z axis straight down


@pytest.mark.parametrize("name", POSES)
def test_solutions_respect_joint_limits_and_keep_the_arm_off_the_floor(name):
    q = solve(*POSES[name])
    assert all(abs(a) <= lim + 1e-9 for a, lim in zip(q, LIMITS, strict=True))
    assert min(joint_heights(q)[2:5]) >= MIN_JOINT_HEIGHT


def test_every_pose_uses_the_same_arm_configuration():
    """The bug this module fixes: MoveIt gave 2.94 rad and 1.91 rad moves to the same waypoint."""
    qs = np.array([solve(*p) for p in POSES.values()])
    assert np.ptp(qs[:, 4]) < 0.05 and np.ptp(qs[:, 5]) < 0.05  # wrist 2 and wrist 3 never flip
    assert qs[:, 2].min() > 1.5 and qs[:, 2].max() < 2.8  # elbow always bent the same way
    assert qs[:, 1].max() < -0.9  # shoulder always leaning the same way


def test_the_answer_depends_only_on_the_pose():
    a, b = solve(0.4, 0.138, 0.25), solve(0.4, 0.138, 0.25)
    assert a == b
    _ = solve(0.3, -0.4, 0.114)  # solving something else in between changes nothing
    assert solve(0.4, 0.138, 0.25) == a


def test_moves_between_neighbouring_poses_are_small():
    def gap(p, q):
        return max(abs(a - b) for a, b in zip(solve(*p), solve(*q), strict=True))

    for b in BLOCKS:
        assert gap(READY_XYZ, (b.x, b.y, Z_HOVER)) < 1.0, b.name
        assert gap((b.x, b.y, Z_HOVER), (b.x, b.y, Z_GRASP)) < 0.8, b.name
        assert gap((b.x, b.y, Z_GRASP), (b.x, b.y, Z_CARRY)) < 1.0, b.name
    for pad in PADS:
        x, y = slot_xy(pad, 1)
        assert gap((x, y, Z_CARRY), (x, y, Z_PLACE)) < 0.8
    # the biggest swing in a cycle: from a block to the far pad
    assert gap((BLOCKS[0].x, BLOCKS[0].y, Z_CARRY), (*slot_xy(PADS[1], 2), Z_CARRY)) < 2.6


def test_park_to_ready_is_a_moderate_move():
    q = solve(*READY_XYZ)
    assert max(abs(a - b) for a, b in zip(q, PARK_JOINTS, strict=True)) < 2.5


def test_unreachable_and_underground_targets_return_none():
    assert solve(2.0, 0.0, 0.3) is None  # far outside the reach
    assert solve(0.4, 0.0, -0.3) is None  # below the floor


def test_nominal_configuration_points_down():
    assert fk(Q_NOM)[2, 2] == pytest.approx(-1.0, abs=1e-6)
