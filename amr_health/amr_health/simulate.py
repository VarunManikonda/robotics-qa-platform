"""Synthetic telemetry with labelled faults, for testing and demos.

The signal stands in for a per-wheel motor load or velocity-tracking error.
Faults are injected at a known sample index so detection delay can be measured.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

FaultKind = Literal["none", "step", "drift", "spike"]


@dataclass(frozen=True)
class Telemetry:
    values: np.ndarray
    fault: FaultKind
    fault_start: int | None


def make_telemetry(
    n: int = 2000,
    fault: FaultKind = "none",
    fault_start: int = 1000,
    magnitude: float = 4.0,
    baseline: float = 1.5,
    noise_sd: float = 0.1,
    seed: int = 0,
) -> Telemetry:
    """`magnitude` is in units of noise_sd (a 4.0 step is a 4-sigma shift)."""
    rng = np.random.default_rng(seed)
    x = baseline + rng.normal(0.0, noise_sd, n)
    if fault == "step":
        x[fault_start:] += magnitude * noise_sd
    elif fault == "drift":
        ramp = np.arange(n - fault_start) / max(1, n - fault_start)
        x[fault_start:] += magnitude * noise_sd * ramp
    elif fault == "spike":
        x[fault_start : fault_start + 3] += magnitude * noise_sd
    elif fault != "none":
        raise ValueError(f"unknown fault {fault!r}")
    return Telemetry(x, fault, None if fault == "none" else fault_start)
