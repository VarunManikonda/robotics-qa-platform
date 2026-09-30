"""Colour-based part inspection.

The inspector classifies a part image as PASS or FAIL from simple, explainable
features (mean colour and a defect-pixel ratio), the same style of HSV
approach used in Sia-Cobot's block detectors. It works on plain numpy arrays,
so it is testable without a camera or ROS.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Inspection:
    passed: bool
    defect_ratio: float
    reason: str


def make_synthetic_part(
    size: int = 64,
    base_rgb: tuple[int, int, int] = (200, 40, 40),
    defect_pixels: int = 0,
    seed: int = 0,
) -> np.ndarray:
    """Solid-colour part with `defect_pixels` dark pixels and mild sensor noise."""
    rng = np.random.default_rng(seed)
    img = np.empty((size, size, 3), dtype=np.float64)
    img[:] = base_rgb
    img += rng.normal(0, 3, img.shape)
    if defect_pixels:
        idx = rng.choice(size * size, size=defect_pixels, replace=False)
        ys, xs = np.divmod(idx, size)
        img[ys, xs] = (20, 20, 20)
    return np.clip(img, 0, 255).astype(np.uint8)


def inspect(
    img: np.ndarray,
    expected_rgb: tuple[int, int, int] = (200, 40, 40),
    colour_tol: float = 40.0,
    max_defect_ratio: float = 0.02,
) -> Inspection:
    if img.ndim != 3 or img.shape[2] != 3:
        raise ValueError("expected an HxWx3 image")
    if img.size == 0:
        raise ValueError("empty image")
    pix = img.reshape(-1, 3).astype(np.float64)
    dist = np.linalg.norm(pix - np.asarray(expected_rgb, dtype=np.float64), axis=1)
    defect_ratio = float(np.mean(dist > colour_tol))
    if defect_ratio > max_defect_ratio:
        return Inspection(False, defect_ratio, f"defect ratio {defect_ratio:.3f} > {max_defect_ratio}")
    return Inspection(True, defect_ratio, "ok")
