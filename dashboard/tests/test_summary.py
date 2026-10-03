import pytest

from app.summary import summarise


def part(i, status="pass", cycle=4.0, name=None):
    return {
        "id": i,
        "project": "cobot_qa",
        "name": name or f"part:block_{i}",
        "status": status,
        "metric": cycle,
        "message": "stuck at hover" if status == "warn" else "ok",
        "payload": {"cycle_time_s": cycle},
        "created_at": f"2026-10-03T08:00:{i % 60:02d}.000Z",
    }


def monitor(i, status="fail", name="velocity_tracking", project="amr_health"):
    return {
        "id": i, "project": project, "name": name, "status": status, "metric": 0.3,
        "message": "spike (z=9.0)", "payload": {}, "created_at": "2026-10-03T08:10:00.000Z",
    }


def test_no_data_is_idle_not_green():
    s = summarise([])
    assert s["status"] == "idle" and s["attention"] == []
    assert s["totals"]["parts"] == 0 and s["totals"]["avg_cycle_s"] is None


def test_healthy_cell_is_green_and_rejected_parts_are_not_a_problem():
    rows = [part(1), part(2), part(3, status="fail"), part(4)]
    s = summarise(rows)
    assert s["status"] == "green" and s["attention"] == []
    t = s["totals"]
    assert (t["parts"], t["good"], t["defects"], t["stuck"]) == (4, 3, 1, 0)
    assert t["defect_rate"] == pytest.approx(0.25)
    assert [p["result"] for p in s["recent_parts"]] == ["good", "good", "defect", "good"]


def test_stuck_part_makes_amber_with_instruction():
    s = summarise([part(1), part(2, status="warn", cycle=9.0)])
    assert s["status"] == "amber"
    item = s["attention"][0]
    assert item["severity"] == "warning" and "could not be moved" in item["title"]
    assert item["what_to_do"]
    assert s["totals"]["avg_cycle_s"] == 4.0  # the stuck part's time is not an average
    assert s["recent_parts"][1]["result"] == "stuck"


def test_slowdown_is_detected_and_graded():
    base = [part(i) for i in range(1, 25)]
    mild = base + [part(100 + i, cycle=4.8) for i in range(6)]       # +20%
    severe = base + [part(200 + i, cycle=6.0) for i in range(6)]      # +50%
    assert summarise(base)["status"] == "green"
    a, b = summarise(mild), summarise(severe)
    assert a["status"] == "amber" and "20% longer" in a["attention"][0]["title"]
    assert b["status"] == "red" and "50% longer" in b["attention"][0]["title"]


def test_slowdown_needs_enough_history():
    rows = [part(i) for i in range(1, 7)] + [part(50 + i, cycle=9.0) for i in range(3)]
    assert summarise(rows)["status"] == "green"


def test_high_defect_rate_needs_enough_parts():
    few = [part(i, status="fail") for i in range(1, 6)]
    assert summarise(few)["status"] == "green"
    many = [part(i, status="fail" if i % 3 == 0 else "pass") for i in range(1, 13)]   # 33%
    s = summarise(many)
    assert s["status"] == "amber" and "defective" in s["attention"][0]["title"]


def test_amr_anomaly_is_red_and_grouped():
    s = summarise([part(1), monitor(2), monitor(3)])
    assert s["status"] == "red"
    item = s["attention"][0]
    assert item["severity"] == "critical" and item["count"] == 2
    assert "not moving the way" in item["title"]


def test_unknown_monitor_failure_is_still_reported():
    s = summarise([monitor(1, name="imu_bias", project="other")])
    assert s["status"] == "red" and "imu_bias" in s["attention"][0]["title"]


def test_monitor_warning_is_amber():
    assert summarise([monitor(1, status="warn")])["status"] == "amber"


def test_critical_items_are_listed_first():
    s = summarise([part(1), part(2, status="warn"), monitor(3)])
    assert [i["severity"] for i in s["attention"]] == ["critical", "warning"]


def test_recent_parts_capped_to_latest():
    s = summarise([part(i) for i in range(1, 80)])
    assert len(s["recent_parts"]) == 40 and s["recent_parts"][-1]["id"] == 79
