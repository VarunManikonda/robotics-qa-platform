"""Turn one navigation goal into a dashboard run, and post it. Standard library only.

A dashboard problem must never stop the robot, so `post_run` returns False instead of raising.
"""

from __future__ import annotations

import json
import urllib.request

PROJECT = "amr_health"
NAME = "nav_goal"


def build_run(outcome: str, seconds: float, x: float, y: float) -> dict:
    """outcome: 'succeeded' | 'aborted' | 'rejected' | 'timeout' | 'canceled'."""
    ok = outcome == "succeeded"
    return {
        "project": PROJECT,
        "name": NAME,
        "status": "pass" if ok else "warn",
        "metric": round(seconds, 1),
        "message": (
            f"reached ({x:.2f}, {y:.2f}) in {seconds:.1f} s"
            if ok
            else f"goal ({x:.2f}, {y:.2f}) {outcome} after {seconds:.1f} s"
        ),
        "payload": {
            "outcome": outcome,
            "goal_xy_m": [round(x, 2), round(y, 2)],
            "duration_s": round(seconds, 1),
        },
    }


def post_run(run: dict, base_url: str, timeout: float = 3.0) -> bool:
    try:
        req = urllib.request.Request(
            base_url.rstrip("/") + "/runs",
            data=json.dumps(run).encode(),
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=timeout).close()
        return True
    except Exception:
        return False
