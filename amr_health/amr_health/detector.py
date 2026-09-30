"""Streaming anomaly detector for robot health signals.

Design
------
* Learn a baseline (mean, std) from the first `warmup` samples, then freeze it.
  Freezing matters: an adaptive baseline slowly "absorbs" a drifting fault and
  never raises it.
* Two checks on the standardised value z:
    - spike: |z| > z_spike            (sudden events, e.g. a stall or a hit)
    - CUSUM: cumulative sum of (|z| - k) exceeds h   (step changes and slow
      drift, e.g. wheel wear or rising motor load)
* Non-finite samples are counted and skipped, never propagated into the state.

Limitations (deliberate, documented in docs/ARCHITECTURE.md): the baseline is
assumed stationary. After maintenance, or a legitimate change of duty cycle,
call `reset()` so it relearns.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Alert:
    index: int
    kind: str  # "spike" | "cusum_high" | "cusum_low"
    z: float


class Detector:
    def __init__(
        self,
        warmup: int = 200,
        z_spike: float = 6.0,
        k: float = 1.0,
        h: float = 8.0,
        min_std: float = 1e-3,
    ) -> None:
        if warmup < 10:
            raise ValueError("warmup must be >= 10")
        if min_std <= 0:
            raise ValueError("min_std must be > 0")
        self.warmup, self.z_spike, self.k, self.h, self.min_std = warmup, z_spike, k, h, min_std
        self.reset()

    def reset(self) -> None:
        self._n = 0  # finite samples seen
        self._index = 0  # all samples seen (including skipped)
        self._mean = 0.0
        self._m2 = 0.0
        self._sd = self.min_std
        self._s_hi = 0.0
        self._s_lo = 0.0
        self.skipped = 0

    @property
    def ready(self) -> bool:
        return self._n >= self.warmup

    @property
    def baseline(self) -> tuple[float, float]:
        return self._mean, self._sd

    def update(self, x: float) -> Optional[Alert]:
        idx = self._index
        self._index += 1
        if not math.isfinite(x):
            self.skipped += 1
            return None

        if self._n < self.warmup:  # Welford running mean/variance
            self._n += 1
            d = x - self._mean
            self._mean += d / self._n
            self._m2 += d * (x - self._mean)
            if self._n == self.warmup:
                var = self._m2 / (self._n - 1)
                self._sd = max(math.sqrt(var), self.min_std)
            return None

        z = (x - self._mean) / self._sd
        if abs(z) > self.z_spike:
            return Alert(idx, "spike", z)

        self._s_hi = max(0.0, self._s_hi + z - self.k)
        self._s_lo = max(0.0, self._s_lo - z - self.k)
        if self._s_hi > self.h:
            self._s_hi = 0.0
            return Alert(idx, "cusum_high", z)
        if self._s_lo > self.h:
            self._s_lo = 0.0
            return Alert(idx, "cusum_low", z)
        return None
