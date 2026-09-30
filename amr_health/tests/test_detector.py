import math

import numpy as np
import pytest

from amr_health.detector import Detector
from amr_health.simulate import make_telemetry


def run(det, values):
    return [a for a in (det.update(float(v)) for v in values) if a]


def first_alert_index(values, **kw):
    alerts = run(Detector(**kw), values)
    return alerts[0].index if alerts else None


def test_no_alerts_during_warmup():
    det = Detector(warmup=50)
    assert run(det, np.random.default_rng(0).normal(0, 1, 50)) == []
    assert det.ready


@pytest.mark.parametrize("seed", range(10))
def test_no_false_alarms_on_clean_data(seed):
    t = make_telemetry(n=5000, seed=seed)
    assert run(Detector(), t.values) == []


@pytest.mark.parametrize("seed", range(10))
def test_step_fault_detected_quickly(seed):
    t = make_telemetry(fault="step", magnitude=4.0, seed=seed)
    idx = first_alert_index(t.values)
    assert idx is not None
    assert t.fault_start <= idx <= t.fault_start + 50


@pytest.mark.parametrize("seed", range(10))
def test_drift_fault_detected(seed):
    t = make_telemetry(fault="drift", magnitude=5.0, seed=seed)
    idx = first_alert_index(t.values)
    assert idx is not None and idx >= t.fault_start


@pytest.mark.parametrize("seed", range(10))
def test_spike_detected_immediately(seed):
    t = make_telemetry(fault="spike", magnitude=10.0, seed=seed)
    alerts = run(Detector(), t.values)
    assert alerts and alerts[0].kind == "spike"
    assert alerts[0].index == t.fault_start


def test_downward_shift_detected():
    t = make_telemetry(fault="step", magnitude=-4.0, seed=3)
    alerts = run(Detector(), t.values)
    assert alerts and alerts[0].kind == "cusum_low"


def test_non_finite_samples_are_skipped_not_fatal():
    det = Detector(warmup=20)
    for v in np.random.default_rng(1).normal(0, 1, 20):
        det.update(float(v))
    for bad in (math.nan, math.inf, -math.inf):
        assert det.update(bad) is None
    assert det.skipped == 3
    assert all(math.isfinite(v) for v in det.baseline)


def test_constant_signal_does_not_divide_by_zero():
    det = Detector(warmup=20, min_std=1e-3)
    assert run(det, [2.0] * 100) == []
    assert det.baseline[1] == pytest.approx(1e-3)


def test_reset_relearns_baseline():
    det = Detector(warmup=50)
    rng = np.random.default_rng(2)
    run(det, 1.5 + rng.normal(0, 0.1, 400))
    shifted = 3.0 + rng.normal(0, 0.1, 400)
    assert run(det, shifted)  # old baseline flags the new level
    det.reset()
    assert run(det, shifted) == []  # relearned, now normal


@pytest.mark.parametrize("bad", [{"warmup": 5}, {"min_std": 0}])
def test_invalid_config_rejected(bad):
    with pytest.raises(ValueError):
        Detector(**bad)
