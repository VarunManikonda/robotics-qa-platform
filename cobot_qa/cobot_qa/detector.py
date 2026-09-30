"""Colour-based block detection from the overhead RGB image. Pure numpy, no OpenCV.

Steps: classify pixels as "red" or "blue" by channel ratios (robust to brightness changes),
group them into 4-connected blobs, drop blobs of implausible size, and convert each blob
centroid to world coordinates on the plane of the block's top face.

Ratios rather than absolute RGB keep the orange drop pad (G/R about 0.55) separate from the
red blocks (G/R about 0.2), and tolerate lighting that scales all channels.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .camera import Camera
from .cell import BLOCK_SIZE, Block

MIN_CHANNEL = 60  # ignore very dark pixels
RATIO = 0.6  # other channels must be below 60% of the dominant one (Gazebo washes cubes out to ~48%)


@dataclass(frozen=True)
class Detection:
    colour: str  # "red" | "blue"
    u: float
    v: float
    area_px: int
    x: float  # world coordinates of the block's top-face centre, metres
    y: float


def colour_masks(img: np.ndarray) -> dict[str, np.ndarray]:
    if img.ndim != 3 or img.shape[2] != 3:
        raise ValueError("expected an HxWx3 RGB image")
    r = img[..., 0].astype(np.int32)
    g = img[..., 1].astype(np.int32)
    b = img[..., 2].astype(np.int32)
    red = (r > MIN_CHANNEL) & (g * 10 < r * RATIO * 10) & (b * 10 < r * RATIO * 10)
    blue = (b > MIN_CHANNEL) & (r * 10 < b * RATIO * 10) & (g * 10 < b * RATIO * 10)
    return {"red": red, "blue": blue}


def components(mask: np.ndarray) -> list[np.ndarray]:
    """4-connected components of a boolean mask, each as an (n, 2) array of (row, col)."""
    h, w = mask.shape
    seen = np.zeros_like(mask, dtype=bool)
    blobs = []
    for y0, x0 in zip(*np.nonzero(mask), strict=True):
        if seen[y0, x0]:
            continue
        stack = [(int(y0), int(x0))]
        seen[y0, x0] = True
        pts = []
        while stack:
            y, x = stack.pop()
            pts.append((y, x))
            for ny, nx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True
                    stack.append((ny, nx))
        blobs.append(np.array(pts))
    return blobs


def detect_blocks(
    img: np.ndarray,
    camera: Camera | None = None,
    z_top: float = BLOCK_SIZE,
    min_area: int = 150,
    max_area: int = 2500,
) -> list[Detection]:
    cam = camera or Camera()
    out = []
    for colour, mask in colour_masks(img).items():
        for pts in components(mask):
            if not (min_area <= len(pts) <= max_area):
                continue
            # centroid of pixel centres; pixel i covers [i, i+1) so its centre is i + 0.5
            v = float(pts[:, 0].mean()) + 0.5
            u = float(pts[:, 1].mean()) + 0.5
            x, y = cam.pixel_to_world(u, v, z_top)
            out.append(Detection(colour, u, v, int(len(pts)), x, y))
    return sorted(out, key=lambda d: (d.colour, d.x, d.y))


def match_to_layout(
    detections: list[Detection], blocks: tuple[Block, ...], max_dist_m: float = 0.06
) -> list[tuple[str, float | None]]:
    """For each expected block, the position error in millimetres of the nearest same-colour
    detection (None if nothing within `max_dist_m`). Each detection is used at most once."""
    used: set[int] = set()
    result: list[tuple[str, float | None]] = []
    for blk in blocks:
        want = "blue" if blk.rgb[2] > blk.rgb[0] else "red"
        best, best_d = None, max_dist_m
        for i, d in enumerate(detections):
            if i in used or d.colour != want:
                continue
            dist = math.hypot(d.x - blk.x, d.y - blk.y)
            if dist <= best_d:
                best, best_d = i, dist
        if best is None:
            result.append((blk.name, None))
        else:
            used.add(best)
            result.append((blk.name, best_d * 1000.0))
    return result
