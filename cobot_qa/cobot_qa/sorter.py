"""Pure planning helpers for the sort cycle (no ROS, unit-tested).

Geometry of the "virtual suction cup": tool0 hovers TCP_OFFSET above the surface it touches, i.e.
tool0 is at z = 0.05 (block top) + 0.06 = 0.11 m when grasping. While carried, the block hangs straight
below tool0 (its centre BLOCK_SIZE/2 below the cup). Red blocks are good parts and go to the green
pad, blue is the defective part and goes to the orange reject pad.
"""

from __future__ import annotations

import math

from .camera import Camera
from .cell import BLOCK_SIZE, BLOCKS, PAD_SIZE, PAD_THICKNESS, PADS, Pad

TCP_OFFSET = 0.06  # virtual suction cup length below tool0, metres
Z_HOVER = 0.25  # tool0 height when moving over the table
Z_CARRY = 0.30  # tool0 height while carrying, clears the other blocks
Z_GRASP = BLOCK_SIZE + TCP_OFFSET  # tool0 height when touching the top of a block
BLOCK_REST_Z = PAD_THICKNESS + BLOCK_SIZE / 2  # centre of a block lying on a pad
Z_PLACE = BLOCK_REST_Z + BLOCK_SIZE / 2 + TCP_OFFSET  # tool0 height when setting a block on a pad
PARK_JOINTS = (1.5708, -1.5708, 0.0, -1.5708, 0.0, 0.0)  # arm out of the camera's view
READY_XYZ = (0.40, 0.0, 0.40)  # waypoint above the table centre; every long swing goes through it
SLOT_OFFSETS_Y = (-0.06, 0.0, 0.06)  # three slots per pad, 6 cm apart (blocks are 5 cm)
FULL_BLOB_FRACTION = 0.85  # a blob smaller than this share of a whole block is partly hidden


def expected_block_area_px(cam: Camera | None = None) -> float:
    cam = cam or Camera()
    edge = BLOCK_SIZE * cam.focal_px / (cam.z - BLOCK_SIZE)
    return edge * edge


def only_fully_visible(dets: list[dict], cam: Camera | None = None) -> list[dict]:
    """Drop blobs that are partly hidden (by the arm), whose centroid would be off."""
    need = FULL_BLOB_FRACTION * expected_block_area_px(cam)
    return [d for d in dets if d.get("area_px", 0) >= need]


def on_pad(det: dict, pad: Pad) -> bool:
    return abs(det["x"] - pad.x) <= PAD_SIZE / 2 and abs(det["y"] - pad.y) <= PAD_SIZE / 2


def on_any_pad(det: dict) -> bool:
    return any(on_pad(det, p) for p in PADS)


def pad_load(dets: list[dict], pad: Pad, cam: Camera | None = None) -> int:
    """How many blocks already sit on this pad (= the next free slot index).

    Counted by blob area, not blob number: cubes in neighbouring slots are only 1 cm apart and can
    merge into a single blob, which counting blobs would report as one block.
    """
    area = sum(d.get("area_px", 0) for d in dets if on_pad(d, pad))
    return round(area / expected_block_area_px(cam))


def next_on_table(dets: list[dict], cam: Camera | None = None) -> dict | None:
    """The next block to sort: fully visible, not already on a pad, ordered by (x, y)."""
    todo = [d for d in only_fully_visible(dets, cam) if not on_any_pad(d)]
    return min(todo, key=lambda d: (d["x"], d["y"])) if todo else None


def destination(colour: str) -> Pad:
    good = next(p for p in PADS if p.name == "pad_good")
    reject = next(p for p in PADS if p.name == "pad_reject")
    return good if colour == "red" else reject


def slot_xy(pad: Pad, index: int) -> tuple[float, float]:
    if not 0 <= index < len(SLOT_OFFSETS_Y):
        raise ValueError(f"{pad.name} is full (slot {index})")
    return pad.x, pad.y + SLOT_OFFSETS_Y[index]


def name_for_detection(det: dict, max_dist_m: float = 0.06) -> str | None:
    """Gazebo model name of the block at a detection (nearest same-colour block of the initial layout)."""
    want = det["colour"]
    best, best_d = None, max_dist_m
    for b in BLOCKS:
        colour = "blue" if b.rgb[2] > b.rgb[0] else "red"
        d = math.hypot(det["x"] - b.x, det["y"] - b.y)
        if colour == want and d <= best_d:
            best, best_d = b.name, d
    return best


def carried_block_pose(tool_xyz: tuple[float, float, float]) -> tuple[float, float, float]:
    x, y, z = tool_xyz
    return (x, y, z - TCP_OFFSET - BLOCK_SIZE / 2)
