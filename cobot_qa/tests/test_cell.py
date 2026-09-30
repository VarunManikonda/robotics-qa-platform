import itertools
import math
import xml.etree.ElementTree as ET

import pytest

from cobot_qa.cell import BLOCK_MASS, BLOCK_SIZE, BLOCKS, PAD_SIZE, PADS, all_models, block_sdf, pad_sdf
from cobot_qa.kinematics import reachable
from cobot_qa.spawn_cell import build_remove_commands, build_spawn_commands


def test_names_are_unique():
    names = [b.name for b in BLOCKS] + [p.name for p in PADS]
    assert len(names) == len(set(names))


@pytest.mark.parametrize("block", BLOCKS, ids=lambda b: b.name)
def test_every_block_is_within_reach(block):
    assert reachable((block.x, block.y, block.z))


@pytest.mark.parametrize("pad", PADS, ids=lambda p: p.name)
def test_every_pad_centre_is_within_reach(pad):
    assert reachable((pad.x, pad.y, 0.05))


def test_blocks_do_not_touch_each_other():
    for a, b in itertools.combinations(BLOCKS, 2):
        # centres must be further apart than one edge plus a 5 cm gripper clearance
        assert math.hypot(a.x - b.x, a.y - b.y) >= BLOCK_SIZE + 0.05, (a.name, b.name)


def test_blocks_are_off_the_pads():
    half = PAD_SIZE / 2 + BLOCK_SIZE
    for b in BLOCKS:
        for p in PADS:
            assert max(abs(b.x - p.x), abs(b.y - p.y)) > half, (b.name, p.name)


def test_blocks_clear_the_robot_base():
    for b in BLOCKS:
        assert math.hypot(b.x, b.y) > 0.25, b.name  # base plate radius + margin


def test_exactly_one_defective_block_and_it_is_not_red():
    bad = [b for b in BLOCKS if b.defective]
    assert len(bad) == 1
    r, g, blue = bad[0].rgb
    assert blue > r  # blue, unlike the red nominal parts


@pytest.mark.parametrize("block", BLOCKS, ids=lambda b: b.name)
def test_block_sdf_is_valid_xml_with_expected_physics(block):
    root = ET.fromstring(block_sdf(block))
    assert root.tag == "sdf"
    model = root.find("model")
    assert model.get("name") == block.name
    assert float(model.find("link/inertial/mass").text) == BLOCK_MASS
    ixx = float(model.find("link/inertial/inertia/ixx").text)
    assert ixx == pytest.approx(BLOCK_MASS * BLOCK_SIZE**2 / 6, rel=1e-3)
    size = model.find("link/collision/geometry/box/size").text.split()
    assert [float(s) for s in size] == [BLOCK_SIZE] * 3


@pytest.mark.parametrize("pad", PADS, ids=lambda p: p.name)
def test_pad_sdf_is_static_and_has_no_collision(pad):
    root = ET.fromstring(pad_sdf(pad))
    model = root.find("model")
    assert model.find("static").text == "true"
    assert model.find("link/collision") is None


def test_spawn_commands_cover_every_object():
    cmds = build_spawn_commands("empty")
    assert len(cmds) == len(BLOCKS) + len(PADS) == len(all_models())
    for c in cmds:
        assert c[:4] == ["ros2", "run", "ros_gz_sim", "create"]
        assert c[c.index("-world") + 1] == "empty"
        z = float(c[c.index("-z") + 1])
        assert 0.0 < z < 0.1


def test_blocks_spawn_just_above_the_floor_so_they_settle():
    z_by_name = {n: z for n, _, _, _, z in all_models()}
    for b in BLOCKS:
        assert z_by_name[b.name] == pytest.approx(BLOCK_SIZE / 2, abs=0.002)


def test_remove_commands_target_the_same_names():
    spawned = {c[c.index("-name") + 1] for c in build_spawn_commands("empty")}
    removed = {c[-1].split('"')[1] for c in build_remove_commands("empty")}
    assert spawned == removed


def test_blocks_have_gravity_off_so_teleport_carry_cannot_build_up_speed():
    from cobot_qa.cell import block_sdf

    for b in BLOCKS:
        assert "<gravity>false</gravity>" in block_sdf(b), b.name
