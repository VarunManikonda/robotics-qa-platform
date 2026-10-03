"""Turn raw run records into a plain-language picture of the robot cell.

The dashboard's job is to answer "is it okay, and what should I do?" for someone who is not standing
next to the robot. Everything here is a pure function of the rows it is given, so it is easy to test.

Vocabulary used in the output (never the raw status words):
    good    a part that went to the good bin
    defect  a part the robot correctly rejected (this is the robot doing its job, not a robot fault)
    stuck   a part the robot could not move
Robot problems come from the monitors (e.g. amr_health) and from trends such as a slowing arm.
"""

from __future__ import annotations

from statistics import mean
from typing import Any

PART_PREFIX = "part:"
RECENT_PARTS = 40

# Trend rules. Small windows keep the screen useful in a demo and in a short shift.
MIN_PARTS_FOR_TREND = 12
RECENT_WINDOW = 6
BASELINE_WINDOW = 24
SLOWDOWN_WARN = 1.15  # 15% slower than the baseline
SLOWDOWN_CRIT = 1.30
DEFECT_WINDOW = 20
MIN_PARTS_FOR_DEFECT_RATE = 10
DEFECT_WARN = 0.20
DEFECT_CRIT = 0.35

HEADLINES = {
    "idle": ("Waiting for data", "No robot has reported anything in this period yet."),
    "green": ("Running normally", "Nothing needs your attention."),
    "amber": ("Needs a look", "Nothing has stopped, but something is drifting. See the list below."),
    "red": ("Stop and check", "Something needs action before the robot keeps running."),
}


def _is_part(row: dict) -> bool:
    return row["project"] == "cobot_qa" and row["name"].startswith(PART_PREFIX)


def _result(row: dict) -> str:
    return {"pass": "good", "fail": "defect", "warn": "stuck"}[row["status"]]


def _cycle(row: dict) -> float | None:
    v = row["payload"].get("cycle_time_s", row.get("metric"))
    return float(v) if isinstance(v, (int, float)) else None


def _pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def _item(severity: str, title: str, detail: str, what_to_do: str, count: int = 1) -> dict:
    return {
        "severity": severity,
        "title": title,
        "detail": detail,
        "what_to_do": what_to_do,
        "count": count,
    }


def _part_items(parts: list[dict]) -> list[dict]:
    items: list[dict] = []
    stuck = [p for p in parts if p["status"] == "warn"]
    if stuck:
        names = ", ".join(p["name"][len(PART_PREFIX):] for p in stuck[-3:])
        items.append(
            _item(
                "warning",
                f"{len(stuck)} part{'s' if len(stuck) != 1 else ''} could not be moved",
                f"Most recent: {names}. {stuck[-1]['message']}",
                "Check the part is inside the arm's reach and the gripper or suction is working, "
                "put the part back on the table and run again.",
                len(stuck),
            )
        )

    moved = [p for p in parts if p["status"] != "warn"]
    cycles = [c for c in (_cycle(p) for p in moved) if c is not None]
    if len(cycles) >= MIN_PARTS_FOR_TREND:
        recent = cycles[-RECENT_WINDOW:]
        base = cycles[-(RECENT_WINDOW + BASELINE_WINDOW):-RECENT_WINDOW]
        if len(base) >= RECENT_WINDOW and mean(base) > 0:
            ratio = mean(recent) / mean(base)
            if ratio >= SLOWDOWN_WARN:
                sev = "critical" if ratio >= SLOWDOWN_CRIT else "warning"
                items.append(
                    _item(
                        sev,
                        f"The arm is taking {_pct(ratio - 1)} longer per part",
                        f"Average was {mean(base):.1f} s per part, the last {len(recent)} parts "
                        f"averaged {mean(recent):.1f} s.",
                        "A worn or loose joint is the usual cause. Book a maintenance check soon, "
                        "before it stops mid-shift.",
                    )
                )

    sorted_parts = [p for p in parts if p["status"] in ("pass", "fail")][-DEFECT_WINDOW:]
    if len(sorted_parts) >= MIN_PARTS_FOR_DEFECT_RATE:
        rate = sum(p["status"] == "fail" for p in sorted_parts) / len(sorted_parts)
        if rate >= DEFECT_WARN:
            sev = "critical" if rate >= DEFECT_CRIT else "warning"
            items.append(
                _item(
                    sev,
                    f"{_pct(rate)} of recent parts were defective",
                    f"{round(rate * len(sorted_parts))} of the last {len(sorted_parts)} parts were rejected.",
                    "Check the incoming batch first. If the parts look fine, the camera or lighting "
                    "may be misjudging them.",
                )
            )
    return items


def _monitor_items(others: list[dict]) -> list[dict]:
    items: list[dict] = []
    fails = [r for r in others if r["status"] == "fail"]
    warns = [r for r in others if r["status"] == "warn"]
    by_name: dict[str, list[dict]] = {}
    for r in fails:
        by_name.setdefault(r["name"], []).append(r)
    for name, rs in by_name.items():
        if name == "velocity_tracking":
            items.append(
                _item(
                    "critical",
                    "The mobile robot is not moving the way it was told to",
                    f"{len(rs)} alert{'s' if len(rs) != 1 else ''}. Latest: {rs[-1]['message']}.",
                    "Pause new missions, check the wheels, brakes and floor for slipping or dragging, "
                    "then restart.",
                    len(rs),
                )
            )
        else:
            items.append(
                _item(
                    "critical",
                    f"A check failed: {name}",
                    f"{len(rs)} time{'s' if len(rs) != 1 else ''}. "
                    f"Latest: {rs[-1]['message'] or 'no details'}.",
                    "Open the table below and look at the latest entries for this check.",
                    len(rs),
                )
            )
    nav_warns = [r for r in warns if r["name"] == "nav_goal"]
    warns = [r for r in warns if r["name"] != "nav_goal"]
    if nav_warns:
        items.append(
            _item(
                "warning",
                f"The mobile robot failed {len(nav_warns)} "
                f"navigation goal{'s' if len(nav_warns) != 1 else ''}",
                f"Latest: {nav_warns[-1]['message']}.",
                "Check the route is clear and the map is up to date, then send the goal again.",
                len(nav_warns),
            )
        )
    if warns:
        items.append(
            _item(
                "warning",
                f"{len(warns)} monitor warning{'s' if len(warns) != 1 else ''}",
                f"Latest: {warns[-1]['name']} - {warns[-1]['message'] or 'no details'}.",
                "Open the table below and look at the latest entries for these checks.",
                len(warns),
            )
        )
    return items


def summarise(rows: list[dict], hours: int = 24) -> dict[str, Any]:
    """`rows` must be oldest-first and already limited to the time window."""
    parts = [r for r in rows if _is_part(r)]
    others = [r for r in rows if not _is_part(r) and r["project"] != "cobot_qa"]

    attention = _part_items(parts) + _monitor_items(others)
    order = {"critical": 0, "warning": 1, "info": 2}
    attention.sort(key=lambda i: order[i["severity"]])

    if not rows:
        status = "idle"
    elif any(i["severity"] == "critical" for i in attention):
        status = "red"
    elif attention:
        status = "amber"
    else:
        status = "green"
    headline, advice = HEADLINES[status]

    good = sum(p["status"] == "pass" for p in parts)
    defects = sum(p["status"] == "fail" for p in parts)
    stuck = sum(p["status"] == "warn" for p in parts)
    cycles = [c for c in (_cycle(p) for p in parts if p["status"] != "warn") if c is not None]
    handled = good + defects
    goals = [r for r in others if r["project"] == "amr_health" and r["name"] == "nav_goal"]
    goal_secs = [r["metric"] for r in goals if r["status"] == "pass" and r["metric"] is not None]

    recent = [
        {
            "id": p["id"],
            "part": p["name"][len(PART_PREFIX):],
            "result": _result(p),
            "cycle_s": _cycle(p),
            "at": p["created_at"],
        }
        for p in parts[-RECENT_PARTS:]
    ]

    return {
        "window_hours": hours,
        "status": status,
        "headline": headline,
        "advice": advice,
        "totals": {
            "parts": len(parts),
            "good": good,
            "defects": defects,
            "stuck": stuck,
            "defect_rate": (defects / handled) if handled else None,
            "avg_cycle_s": round(mean(cycles), 1) if cycles else None,
            "to_check": len(attention),
            "goals": len(goals),
            "goals_reached": sum(r["status"] == "pass" for r in goals),
            "avg_goal_s": round(mean(goal_secs), 1) if goal_secs else None,
        },
        "attention": attention,
        "recent_parts": recent,
    }
