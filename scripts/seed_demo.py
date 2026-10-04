#!/usr/bin/env python3
"""Fill a running dashboard with realistic sorted-part data so the screen can be shown without a robot.

    python3 scripts/seed_demo.py --scenario healthy
    python3 scripts/seed_demo.py --scenario slowing      # arm gets slower: amber / red banner
    python3 scripts/seed_demo.py --scenario defects      # a bad batch arrives
    python3 scripts/seed_demo.py --scenario stuck        # the arm fails to pick a part
    python3 scripts/seed_demo.py --scenario amr          # mobile robot tracking alerts

Standard library only. The part records have the same shape the real sorter posts.
"""

from __future__ import annotations

import argparse
import json
import random
import urllib.request

SCENARIOS = ("healthy", "slowing", "defects", "stuck", "amr")


def post(url: str, body: dict) -> None:
    req = urllib.request.Request(
        url + "/runs", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
    )
    urllib.request.urlopen(req, timeout=5).close()


def part(n: int, defect: bool, cycle: float, ok: bool = True) -> dict:
    colour = "blue" if defect else "red"
    name = f"block_{colour}_{n}"
    payload = {
        "bin": "reject" if defect else "good",
        "pad": "pad_reject" if defect else "pad_good",
        "slot": n % 3,
        "colour": colour,
        "layout_error_mm": round(random.uniform(0.8, 2.8), 1),
        "cycle_time_s": round(cycle, 1),
    }
    if not ok:
        return {"project": "cobot_qa", "name": f"part:{name}", "status": "warn", "metric": round(cycle, 1),
                "message": "pick-and-place failed: no inverse-kinematics solution",
                "payload": {**payload, "bin": "skipped"}}
    return {"project": "cobot_qa", "name": f"part:{name}", "status": "fail" if defect else "pass",
            "metric": round(cycle, 1),
            "message": f"{colour} part {'rejected to pad_reject' if defect else 'sorted to pad_good'} "
                       f"in {cycle:.1f} s",
            "payload": payload}


def seed(url: str, scenario: str, seed_value: int = 7) -> int:
    random.seed(seed_value)
    sent = 0
    for n in range(1, 31):                                   # a normal stretch of work
        bad = n in (7, 19)                                   # an ordinary defect rate (~7%)
        post(url, part(n, bad, random.gauss(4.0, 0.12)))
        sent += 1
    if scenario == "slowing":
        for n in range(31, 39):
            post(url, part(n, False, random.gauss(5.8, 0.15)))
            sent += 1
    elif scenario == "defects":
        for n in range(31, 43):
            post(url, part(n, random.random() < 0.6, random.gauss(4.0, 0.12)))
            sent += 1
    elif scenario == "stuck":
        post(url, part(31, False, 9.0, ok=False))
        sent += 1
    elif scenario == "amr":
        for z in (7.2, 8.9, 11.4):
            post(url, {"project": "amr_health", "name": "velocity_tracking", "status": "fail",
                       "metric": 0.31, "message": f"spike (z={z})", "payload": {"cmd": 0.5, "odom": 0.19}})
            sent += 1
    return sent


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--scenario", choices=SCENARIOS, default="healthy")
    a = ap.parse_args()
    print(f"posted {seed(a.url, a.scenario)} runs for scenario '{a.scenario}' to {a.url}")


if __name__ == "__main__":
    main()
