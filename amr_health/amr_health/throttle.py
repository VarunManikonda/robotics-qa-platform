"""Rate limiter so a persistent fault posts a few alerts, not one every sample."""

from __future__ import annotations

import time
from typing import Callable


class RateLimiter:
    """`allow()` is True at most once per `min_interval_s`; `suppressed` counts the ones it blocked."""

    def __init__(self, min_interval_s: float, clock: Callable[[], float] = time.monotonic) -> None:
        if min_interval_s < 0:
            raise ValueError("min_interval_s must be >= 0")
        self._gap, self._clock = min_interval_s, clock
        self._last: float | None = None
        self.suppressed = 0

    def allow(self) -> bool:
        now = self._clock()
        if self._last is None or now - self._last >= self._gap:
            self._last = now
            return True
        self.suppressed += 1
        return False
