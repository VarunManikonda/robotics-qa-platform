"""Pinhole model of the overhead camera that looks straight down at the workcell.

Convention (matches the SDF pose `x y z 0 pi/2 0` used in `world.py`):

* the image "up" direction is world +x, the image "right" direction is world -y;
* pixel (u, v) is continuous, u to the right, v downwards, image centre at (W/2, H/2);
* a point at height z is at distance h = camera_z - z along the optical axis.

This orientation is derived from the Gazebo camera frame (x forward, y left, z up,
pitched 90 degrees down). It is checked on the real simulation by comparing detected
block positions with the known layout (see `detect_node`).
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Camera:
    x: float = 0.40
    y: float = 0.00
    z: float = 1.30
    width: int = 640
    height: int = 480
    hfov: float = math.radians(60.0)

    @property
    def focal_px(self) -> float:
        return (self.width / 2.0) / math.tan(self.hfov / 2.0)

    def world_to_pixel(self, x: float, y: float, z: float) -> tuple[float, float]:
        h = self.z - z
        if h <= 0:
            raise ValueError("point is at or above the camera")
        f = self.focal_px
        u = self.width / 2.0 - (y - self.y) * f / h
        v = self.height / 2.0 - (x - self.x) * f / h
        return u, v

    def pixel_to_world(self, u: float, v: float, z_plane: float) -> tuple[float, float]:
        """World (x, y) of the point on the horizontal plane z = z_plane seen at pixel (u, v)."""
        h = self.z - z_plane
        if h <= 0:
            raise ValueError("plane is at or above the camera")
        f = self.focal_px
        x = self.x + (self.height / 2.0 - v) * h / f
        y = self.y - (u - self.width / 2.0) * h / f
        return x, y

    def in_view(self, x: float, y: float, z: float, margin_px: float = 0.0) -> bool:
        u, v = self.world_to_pixel(x, y, z)
        return margin_px <= u <= self.width - margin_px and margin_px <= v <= self.height - margin_px
