"""Turn one sorted part into a dashboard run, and post it. Standard library only.

A dashboard problem must never stop the robot, so `post_run` returns False instead of raising.
"""

from __future__ import annotations

import json
import math
import urllib.error
import urllib.request

from .cell import BLOCKS

PROJECT = "cobot_qa"


def layout_error_mm(det: dict, block_name: str) -> float | None:
    """Distance between where the camera saw a block and where the cell layout put it, in mm."""
    for b in BLOCKS:
        if b.name == block_name:
            return math.hypot(det["x"] - b.x, det["y"] - b.y) * 1000.0
    return None


def build_run(
    block_name: str,
    det: dict,
    pad_name: str,
    slot: int,
    cycle_s: float,
    ok: bool = True,
    reason: str = "",
) -> dict:
    """Body for POST /runs.

    Rule of the demo cell: red is the nominal part, blue is the defective one. A part that was sorted
    correctly is "pass" if it went to the good pad and "fail" (correctly rejected) if it went to the
    reject pad; a part the robot could not move is "warn".
    """
    err = layout_error_mm(det, block_name)
    payload = {
        "bin": "good" if pad_name == "pad_good" else "reject",
        "pad": pad_name,
        "slot": slot,
        "colour": det["colour"],
        "detected_xy_m": [round(det["x"], 4), round(det["y"], 4)],
        "layout_error_mm": None if err is None else round(err, 1),
        "cycle_time_s": round(cycle_s, 1),
    }
    if not ok:
        return {
            "project": PROJECT,
            "name": f"part:{block_name}",
            "status": "warn",
            "metric": round(cycle_s, 1),
            "message": f"pick-and-place failed: {reason}" if reason else "pick-and-place failed",
            "payload": {**payload, "bin": "skipped"},
        }
    rejected = pad_name != "pad_good"
    return {
        "project": PROJECT,
        "name": f"part:{block_name}",
        "status": "fail" if rejected else "pass",
        "metric": round(cycle_s, 1),
        "message": (
            f"{det['colour']} part {'rejected to' if rejected else 'sorted to'} {pad_name} slot {slot} "
            f"in {cycle_s:.1f} s"
        ),
        "payload": payload,
    }


def post_run(run: dict, base_url: str = "http://127.0.0.1:8000", timeout: float = 3.0) -> bool:
    try:  # building the request can raise too (malformed URL), and that must not stop the robot
        req = urllib.request.Request(
            f"{base_url.rstrip('/')}/runs",
            data=json.dumps(run).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 201
    except (urllib.error.URLError, OSError, ValueError):
        return False
