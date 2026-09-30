import numpy as np
import pytest

from cobot_qa.inspector import inspect, make_synthetic_part
from cobot_qa.mission import Part, run_mission


def test_good_part_passes():
    res = inspect(make_synthetic_part(seed=1))
    assert res.passed and res.defect_ratio == 0.0


def test_defective_part_fails():
    res = inspect(make_synthetic_part(defect_pixels=200, seed=2))
    assert not res.passed
    assert res.defect_ratio == pytest.approx(200 / 64**2, abs=0.005)


def test_wrong_colour_fails():
    res = inspect(make_synthetic_part(base_rgb=(40, 40, 200), seed=3))
    assert not res.passed


def test_threshold_boundary():
    # 2% of 4096 px is ~82 pixels: just under passes, well over fails
    assert inspect(make_synthetic_part(defect_pixels=60, seed=4)).passed
    assert not inspect(make_synthetic_part(defect_pixels=120, seed=4)).passed


@pytest.mark.parametrize("bad", [np.zeros((4, 4)), np.zeros((4, 4, 4))])
def test_inspect_rejects_bad_shapes(bad):
    with pytest.raises(ValueError):
        inspect(bad)


def test_mission_sorts_and_skips_unreachable():
    parts = [
        Part("A", (0.4, 0.1, 0.1), make_synthetic_part(seed=1)),
        Part("B", (0.4, -0.1, 0.1), make_synthetic_part(defect_pixels=300, seed=2)),
        Part("C", (0.75, -0.44, 0.05), make_synthetic_part(seed=3)),
    ]
    report = run_mission(parts)
    by_id = {r.part_id: r for r in report.results}
    assert (by_id["A"].status, by_id["A"].bin) == ("pass", "good")
    assert (by_id["B"].status, by_id["B"].bin) == ("fail", "reject")
    assert (by_id["C"].status, by_id["C"].bin) == ("warn", "skipped")
    assert report.counts == {"pass": 1, "fail": 1, "warn": 1}


def test_unreachable_part_is_never_inspected():
    calls = []

    def spy(img):
        calls.append(1)
        return inspect(img)

    run_mission([Part("far", (2.0, 0, 0), make_synthetic_part())], inspector=spy)
    assert calls == []
