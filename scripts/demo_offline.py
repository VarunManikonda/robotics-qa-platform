#!/usr/bin/env python3
"""End-to-end demo that needs no ROS: pushes both projects' results to a
running dashboard and saves a detection plot.

    python scripts/demo_offline.py --url http://127.0.0.1:8000 --plot docs/amr_detection.png
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "cobot_qa"), str(ROOT / "amr_health")]

from amr_health.detector import Detector  # noqa: E402
from amr_health.simulate import make_telemetry  # noqa: E402
from cobot_qa.inspector import make_synthetic_part  # noqa: E402
from cobot_qa.kinematics import fk_position_mm  # noqa: E402
from cobot_qa.mission import Part, run_mission  # noqa: E402
from cobot_qa.report_client import post_report  # noqa: E402


def post(url: str, body: dict) -> None:
    req = urllib.request.Request(
        url + "/runs", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
    )
    urllib.request.urlopen(req, timeout=5).close()


def cobot_demo(url: str) -> None:
    parts = [
        Part("P1", (0.40, 0.10, 0.10), make_synthetic_part(seed=1)),
        Part("P2", (0.35, -0.15, 0.10), make_synthetic_part(defect_pixels=300, seed=2)),
        Part("P3", (0.45, 0.00, 0.12), make_synthetic_part(seed=3)),
        Part("P4", (0.75, -0.44, 0.05), make_synthetic_part(seed=4)),  # out of reach
    ]
    report = run_mission(parts)
    sent = post_report(report, url)
    print(f"cobot_qa: {report.counts} ({sent} runs posted)")
    expected = (817.20, 232.90, 62.80)
    got = fk_position_mm([0, 0, 0, 0, 0, 0])
    err = max(abs(a - b) for a, b in zip(got, expected, strict=True))
    post(url, {"project": "cobot_qa", "name": "fk_answer_key_home", "status": "pass" if err < 0.1 else "fail",
               "metric": err, "message": f"FK home pose vs answer key, max error {err:.3f} mm"})


def amr_demo(url: str, plot: str | None) -> None:
    tele = make_telemetry(n=2000, fault="drift", fault_start=1000, magnitude=6.0, seed=7)
    det = Detector()
    alerts = [a for a in (det.update(float(v)) for v in tele.values) if a]
    first = alerts[0] if alerts else None
    if first is None:
        post(url, {"project": "amr_health", "name": "drift_demo", "status": "warn",
                   "message": "injected drift was NOT detected"})
        print("amr_health: drift not detected")
    else:
        delay = first.index - tele.fault_start
        post(url, {"project": "amr_health", "name": "drift_demo", "status": "fail",
                   "metric": float(delay),
                   "message": f"{first.kind} at sample {first.index}, {delay} samples after fault onset"})
        print(f"amr_health: {first.kind} at {first.index} (fault began {tele.fault_start})")
    if plot:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(8, 3))
        ax.plot(tele.values, lw=0.6, color="#555")
        ax.axvline(tele.fault_start, color="#9a6700", ls="--", label="fault onset")
        if first:
            ax.axvline(first.index, color="#cf222e", label=f"alert ({first.kind})")
        ax.set_xlabel("sample")
        ax.set_ylabel("tracking error (synthetic)")
        ax.legend(loc="upper left")
        fig.tight_layout()
        Path(plot).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(plot, dpi=130)
        print(f"saved {plot}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--plot", default=None)
    a = ap.parse_args()
    cobot_demo(a.url)
    amr_demo(a.url, a.plot)
