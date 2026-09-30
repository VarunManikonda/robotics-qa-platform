import pytest

from cobot_qa.camera import Camera
from cobot_qa.cell import BLOCK_SIZE, BLOCKS, PAD_THICKNESS, PADS
from cobot_qa.detector import detect_blocks
from cobot_qa.kinematics import reachable
from cobot_qa.sorter import (
    BLOCK_REST_Z,
    SLOT_OFFSETS_Y,
    TCP_OFFSET,
    Z_CARRY,
    Z_GRASP,
    Z_HOVER,
    Z_PLACE,
    carried_block_pose,
    destination,
    expected_block_area_px,
    name_for_detection,
    next_on_table,
    on_any_pad,
    only_fully_visible,
    pad_load,
    slot_xy,
)

from .test_vision import render

GOOD, REJECT = PADS


def det(colour, x, y, area=490):
    return {"colour": colour, "x": x, "y": y, "area_px": area}


def test_heights_are_consistent():
    assert Z_GRASP == pytest.approx(BLOCK_SIZE + TCP_OFFSET)
    assert Z_PLACE == pytest.approx(PAD_THICKNESS + BLOCK_SIZE + TCP_OFFSET)
    assert BLOCK_REST_Z == pytest.approx(PAD_THICKNESS + BLOCK_SIZE / 2)
    assert Z_GRASP < Z_HOVER < Z_CARRY


def test_block_hangs_exactly_at_its_original_position_at_grasp():
    """No visible jump when suction turns on: block centre == tool z - cup - half block == BLOCKS z."""
    x, y, z = carried_block_pose((0.4, 0.14, Z_GRASP))
    assert (x, y) == (0.4, 0.14)
    assert z == pytest.approx(BLOCK_SIZE / 2)


def test_destination_red_good_blue_reject():
    assert destination("red") is GOOD
    assert destination("blue") is REJECT


def test_slots_are_distinct_fit_on_the_pad_and_do_not_touch():
    xs = [slot_xy(GOOD, i) for i in range(len(SLOT_OFFSETS_Y))]
    ys = sorted(y for _, y in xs)
    assert all(b - a >= BLOCK_SIZE + 0.005 for a, b in zip(ys, ys[1:], strict=False))
    assert all(abs(y - GOOD.y) + BLOCK_SIZE / 2 <= 0.10 for _, y in xs)
    with pytest.raises(ValueError):
        slot_xy(GOOD, len(SLOT_OFFSETS_Y))


def test_every_pad_slot_pose_is_within_arm_reach():
    for pad in PADS:
        for i in range(len(SLOT_OFFSETS_Y)):
            x, y = slot_xy(pad, i)
            for z in (Z_CARRY, Z_PLACE):
                assert reachable((x, y, z)), (pad.name, i, z)


def test_every_block_grasp_pose_is_within_arm_reach():
    for b in BLOCKS:
        for z in (Z_HOVER, Z_GRASP):
            assert reachable((b.x, b.y, z)), b.name


def test_partly_hidden_blobs_are_dropped():
    full = expected_block_area_px()
    assert 400 < full < 600
    dets = [det("red", 0.4, 0.1, area=int(full)), det("red", 0.4, -0.1, area=int(full * 0.6))]
    assert only_fully_visible(dets) == dets[:1]


def test_expected_area_matches_what_the_renderer_produces():
    dets = detect_blocks(render())
    assert all(abs(d.area_px - expected_block_area_px()) < 0.15 * expected_block_area_px() for d in dets)


def test_blocks_on_pads_are_not_picked_again():
    on_good = det("red", GOOD.x, GOOD.y - 0.06)
    assert on_any_pad(on_good)
    assert next_on_table([on_good]) is None
    table = det("red", 0.40, 0.14)
    assert next_on_table([on_good, table]) == table


def test_next_on_table_is_deterministic_and_skips_hidden():
    a, b, hidden = det("red", 0.49, -0.03), det("blue", 0.31, 0.06), det("red", 0.30, 0.0, area=200)
    assert next_on_table([a, b, hidden]) == b  # smallest x among fully visible
    assert next_on_table([]) is None


def test_pad_load_counts_blocks_already_on_the_pad():
    dets = [det("red", GOOD.x, GOOD.y), det("red", GOOD.x, GOOD.y + 0.06), det("blue", REJECT.x, REJECT.y),
            det("red", 0.4, 0.1)]
    assert pad_load(dets, GOOD) == 2
    assert pad_load(dets, REJECT) == 1


def test_name_for_detection_matches_layout_by_colour_and_position():
    assert name_for_detection(det("blue", 0.311, 0.059)) == "block_blue_1"
    assert name_for_detection(det("red", 0.489, -0.030)) == "block_red_2"
    assert name_for_detection(det("red", 0.311, 0.059)) is None  # right place, wrong colour
    assert name_for_detection(det("red", 0.9, 0.9)) is None


def test_full_pipeline_from_synthetic_image_to_target_and_name():
    dets = [{"colour": d.colour, "x": d.x, "y": d.y, "area_px": d.area_px} for d in detect_blocks(render())]
    target = next_on_table(dets)
    assert target["colour"] == "blue"  # x = 0.31 is the smallest
    assert name_for_detection(target) == "block_blue_1"
    assert destination(target["colour"]) is REJECT


def test_camera_default_is_used_for_area():
    assert expected_block_area_px(Camera()) == expected_block_area_px()
