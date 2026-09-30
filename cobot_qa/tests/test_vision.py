import ast
import math
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pytest

from cobot_qa.camera import Camera
from cobot_qa.cell import BLOCK_SIZE, BLOCKS, PAD_SIZE, PADS
from cobot_qa.detector import colour_masks, components, detect_blocks, match_to_layout
from cobot_qa.world import CAMERA, build_world_sdf

SIM = Path(__file__).resolve().parents[1] / "sim"
FLOOR = (181, 181, 181)  # measured in real Gazebo


def washed(rgb):
    """Gazebo's ambient light lifts colours: fitted to samples from the real camera image,
    e.g. (200,40,40) -> (211,101,101) and the orange pad (230,128,26) -> about (225,173,82)."""
    return tuple(min(255.0, 73.5 + 0.6875 * c) for c in rgb)


# ---------------------------------------------------------------- camera geometry
def test_round_trip_pixel_world():
    cam = Camera()
    for x, y, z in [(0.4, 0.0, 0.05), (0.3, 0.4, 0.004), (0.55, -0.3, 0.05)]:
        u, v = cam.world_to_pixel(x, y, z)
        assert cam.pixel_to_world(u, v, z) == pytest.approx((x, y), abs=1e-9)


def test_image_axes_follow_the_documented_convention():
    cam = Camera()
    u0, v0 = cam.world_to_pixel(0.4, 0.0, 0.05)
    assert (u0, v0) == pytest.approx((320.0, 240.0))  # directly below the camera
    _, v_far = cam.world_to_pixel(0.5, 0.0, 0.05)
    assert v_far < v0  # +x is image "up"
    u_left, _ = cam.world_to_pixel(0.4, 0.1, 0.05)
    assert u_left < u0  # +y is image "left"


def test_camera_rejects_points_at_or_above_it():
    with pytest.raises(ValueError):
        Camera().world_to_pixel(0.4, 0.0, 1.3)


def test_everything_in_the_cell_is_well_inside_the_image():
    cam = CAMERA
    for b in BLOCKS:
        assert cam.in_view(b.x, b.y, BLOCK_SIZE, margin_px=40), b.name
    for p in PADS:
        for dx, dy in [(-1, -1), (-1, 1), (1, -1), (1, 1)]:
            assert cam.in_view(p.x + dx * PAD_SIZE / 2, p.y + dy * PAD_SIZE / 2, 0.004, margin_px=10), p.name


def test_a_block_is_large_enough_to_detect():
    edge_px = BLOCK_SIZE * CAMERA.focal_px / (CAMERA.z - BLOCK_SIZE)
    assert edge_px > 15  # at least ~225 px area, comfortably above min_area


# ---------------------------------------------------------------- world file
def test_committed_world_matches_generator():
    assert (SIM / "qa_cell.sdf").read_text() == build_world_sdf()


def test_world_has_required_systems_camera_and_all_models():
    w = ET.fromstring(build_world_sdf()).find("world")
    assert w.get("name") == "empty"
    plugins = {p.get("name") for p in w.findall("plugin")}
    for needed in ("Physics", "UserCommands", "SceneBroadcaster", "Sensors"):
        assert f"gz::sim::systems::{needed}" in plugins
    models = {m.get("name") for m in w.findall("model")}
    assert {"ground_plane", "overhead_camera"} <= models
    assert {b.name for b in BLOCKS} | {p.name for p in PADS} <= models


def test_world_camera_looks_straight_down_from_the_configured_pose():
    w = ET.fromstring(build_world_sdf()).find("world")
    cam = w.find("model[@name='overhead_camera']")
    x, y, z, roll, pitch, yaw = (float(v) for v in cam.find("pose").text.split())
    assert (x, y, z) == pytest.approx((CAMERA.x, CAMERA.y, CAMERA.z))
    assert roll == 0 and yaw == 0
    assert pitch == pytest.approx(math.pi / 2, abs=1e-5)
    sensor = cam.find("link/sensor")
    assert sensor.get("type") == "camera"
    assert sensor.find("topic").text == "overhead/image"
    assert int(sensor.find("camera/image/width").text) == CAMERA.width
    assert int(sensor.find("camera/image/height").text) == CAMERA.height
    assert float(sensor.find("camera/horizontal_fov").text) == pytest.approx(CAMERA.hfov, abs=1e-5)


def test_launch_file_forwards_world_and_bridges_the_image():
    src = (SIM / "arm_cell.launch.py").read_text()
    ast.parse(src)  # valid Python
    assert '"world_file": world_file' in src  # the argument ur_sim_moveit.launch.py drops
    assert "ur_sim_control.launch.py" in src and "ur_moveit.launch.py" in src
    assert "/overhead/image@sensor_msgs/msg/Image[gz.msgs.Image" in src
    assert "/world/empty/set_pose@ros_gz_interfaces/srv/SetEntityPose" in src


# ---------------------------------------------------------------- detection
def render(cam=CAMERA, blocks=BLOCKS, brightness=1.0, noise=2.0, seed=0, shift_px=(0, 0)):
    """Synthetic overhead image: grey floor, coloured pads, and top faces of blocks."""
    rng = np.random.default_rng(seed)
    img = np.empty((cam.height, cam.width, 3), dtype=np.float64)
    img[:] = FLOOR

    def paint(cx, cy, z, half, rgb):
        u0, v0 = cam.world_to_pixel(cx + half, cy + half, z)  # +x up, +y left
        u1, v1 = cam.world_to_pixel(cx - half, cy - half, z)
        img[int(round(v0)) : int(round(v1)), int(round(u0)) : int(round(u1))] = rgb

    for p in PADS:
        paint(p.x, p.y, 0.004, PAD_SIZE / 2, washed(tuple(255 * c for c in p.rgb)))
    for b in blocks:
        paint(b.x, b.y, BLOCK_SIZE, BLOCK_SIZE / 2, washed(tuple(255 * c for c in b.rgb)))
    img *= brightness
    img += rng.normal(0, noise, img.shape)
    return np.clip(img, 0, 255).astype(np.uint8)


def test_detects_every_block_within_a_few_millimetres():
    dets = detect_blocks(render())
    assert sorted(d.colour for d in dets) == ["blue", "red", "red", "red"]
    for name, err in match_to_layout(dets, BLOCKS):
        assert err is not None, name
        assert err < 3.0, (name, err)  # limited by pixel size (~2.4 mm/px), not by the method


@pytest.mark.parametrize("brightness", [0.6, 0.8, 1.2])
def test_robust_to_lighting_changes(brightness):
    dets = detect_blocks(render(brightness=brightness, seed=3))
    assert sorted(d.colour for d in dets) == ["blue", "red", "red", "red"]
    assert all(e is not None and e < 4.0 for _, e in match_to_layout(dets, BLOCKS))


def test_orange_pad_is_not_mistaken_for_a_red_block():
    dets = detect_blocks(render())
    pad = next(p for p in PADS if p.name == "pad_reject")
    assert all(np.hypot(d.x - pad.x, d.y - pad.y) > 0.1 for d in dets)


def test_missing_block_is_reported_as_missing():
    dets = detect_blocks(render(blocks=BLOCKS[:-1]))  # blue block removed
    result = dict(match_to_layout(dets, BLOCKS))
    assert result["block_blue_1"] is None
    assert all(result[b.name] is not None for b in BLOCKS[:-1])


def test_noise_specks_are_ignored():
    img = render()
    img[10:13, 10:13] = (211, 101, 101)  # 9-pixel red speck
    assert len(detect_blocks(img)) == 4


def test_oversized_blob_is_rejected():
    img = render()
    img[0:100, 500:600] = (211, 101, 101)  # 10,000 px red region
    assert len(detect_blocks(img)) == 4


def test_empty_scene_gives_no_detections():
    img = np.full((CAMERA.height, CAMERA.width, 3), FLOOR, dtype=np.uint8)
    assert detect_blocks(img) == []


@pytest.mark.parametrize("bad", [np.zeros((10, 10)), np.zeros((10, 10, 4))])
def test_rejects_wrong_image_shape(bad):
    with pytest.raises(ValueError):
        detect_blocks(bad)


def test_components_labels_separate_blobs_and_uses_4_connectivity():
    m = np.zeros((6, 6), dtype=bool)
    m[0:2, 0:2] = True  # blob A (4 px)
    m[3, 3] = True
    m[4, 4] = True  # diagonal neighbours are NOT connected under 4-connectivity
    sizes = sorted(len(c) for c in components(m))
    assert sizes == [1, 1, 4]


def test_colour_masks_are_disjoint_for_pure_colours():
    img = np.zeros((2, 2, 3), dtype=np.uint8)
    img[0, 0] = (211, 101, 101)
    img[0, 1] = (101, 101, 211)
    m = colour_masks(img)
    assert m["red"][0, 0] and not m["blue"][0, 0]
    assert m["blue"][0, 1] and not m["red"][0, 1]
    assert not (m["red"] & m["blue"]).any()


def test_orange_colour_is_rejected_by_the_colour_rule_itself():
    """Not just by the blob-size filter: the pad colour must not classify as red at any brightness."""
    for k in (0.6, 1.0, 1.2):
        img = np.zeros((1, 1, 3), dtype=np.uint8)
        orange = washed(tuple(255 * v for v in PADS[1].rgb))  # pad_reject
        img[0, 0] = tuple(min(255, int(c * k)) for c in orange)
        m = colour_masks(img)
        assert not m["red"][0, 0] and not m["blue"][0, 0], k


def test_layout_is_not_symmetric_about_the_camera_axes():
    from cobot_qa.cell import Block

    def mirrored_y(b):
        return Block(b.name, b.rgb, b.x, -b.y)

    def mirrored_x(b):
        return Block(b.name, b.rgb, 2 * CAMERA.x - b.x, b.y)

    for mirror in (mirrored_y, mirrored_x):
        moved = tuple(mirror(b) for b in BLOCKS)
        missing = [n for n, e in match_to_layout(list_detections(moved), BLOCKS) if e is None]
        assert missing, mirror.__name__


def list_detections(blocks):
    return detect_blocks(render(blocks=blocks))


def test_layout_check_notices_a_left_right_flipped_image():
    dets = detect_blocks(np.ascontiguousarray(render()[:, ::-1]))
    assert any(e is None for _, e in match_to_layout(dets, BLOCKS))


def test_layout_check_notices_an_upside_down_image():
    dets = detect_blocks(np.ascontiguousarray(render()[::-1]))
    assert any(e is None for _, e in match_to_layout(dets, BLOCKS))



def test_colours_measured_in_real_gazebo_are_classified_correctly():
    """Pixel values sampled from the real /overhead/image (ambient light washes colours out)."""
    real = {"red": (211, 101, 101), "blue": (101, 101, 211)}
    not_blocks = {"orange pad": (225, 173, 82), "green pad": (99, 188, 114), "floor": (181, 181, 181)}
    for want, rgb in real.items():
        m = colour_masks(np.array([[rgb]], dtype=np.uint8))
        assert m[want][0, 0] and not m["red" if want == "blue" else "blue"][0, 0], want
    for name, rgb in not_blocks.items():
        m = colour_masks(np.array([[rgb]], dtype=np.uint8))
        assert not m["red"][0, 0] and not m["blue"][0, 0], name


def test_detection_reports_bounding_box_size():
    dets = detect_blocks(render())
    edge = BLOCK_SIZE * CAMERA.focal_px / (CAMERA.z - BLOCK_SIZE)
    for d in dets:
        assert abs(d.w_px - edge) <= 2 and abs(d.h_px - edge) <= 2
