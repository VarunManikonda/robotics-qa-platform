"""Inspection-and-sort mission logic, independent of ROS.

`run_mission` takes part poses, runs the pre-flight safety checks, inspects
each part and returns a per-part record. The ROS 2 node in `ros_node.py` is a
thin wrapper that feeds this from topics and publishes the results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Sequence

import numpy as np

from .inspector import Inspection, inspect
from .kinematics import reachable


@dataclass
class Part:
    part_id: str
    position_m: tuple[float, float, float]
    image: np.ndarray


@dataclass
class PartResult:
    part_id: str
    status: str  # pass | fail | warn
    bin: str  # good | reject | skipped
    message: str
    defect_ratio: float | None = None


@dataclass
class MissionReport:
    results: list[PartResult] = field(default_factory=list)

    @property
    def counts(self) -> dict[str, int]:
        c = {"pass": 0, "fail": 0, "warn": 0}
        for r in self.results:
            c[r.status] += 1
        return c


def run_mission(
    parts: Sequence[Part],
    inspector: Callable[[np.ndarray], Inspection] = inspect,
) -> MissionReport:
    report = MissionReport()
    for p in parts:
        if not reachable(p.position_m):
            report.results.append(
                PartResult(p.part_id, "warn", "skipped", "target outside arm envelope")
            )
            continue
        res = inspector(p.image)
        report.results.append(
            PartResult(
                p.part_id,
                "pass" if res.passed else "fail",
                "good" if res.passed else "reject",
                res.reason,
                res.defect_ratio,
            )
        )
    return report
