"""Post mission results to the dashboard. Uses only the standard library."""

from __future__ import annotations

import json
import urllib.request

from .mission import MissionReport


def post_report(
    report: MissionReport,
    base_url: str = "http://127.0.0.1:8000",
    project: str = "cobot_qa",
) -> int:
    sent = 0
    for r in report.results:
        body = json.dumps(
            {
                "project": project,
                "name": f"part:{r.part_id}",
                "status": r.status,
                "metric": r.defect_ratio,
                "message": r.message,
                "payload": {"bin": r.bin},
            }
        ).encode()
        req = urllib.request.Request(
            f"{base_url}/runs", data=body, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 201:
                sent += 1
    return sent
