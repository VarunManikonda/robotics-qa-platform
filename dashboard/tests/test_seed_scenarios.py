"""The demo scenarios must show what they claim to show (healthy really is green)."""

import importlib.util
import pathlib

import pytest

from app.summary import summarise

SPEC = importlib.util.spec_from_file_location(
    "seed_demo", pathlib.Path(__file__).resolve().parents[2] / "scripts" / "seed_demo.py"
)
seed_demo = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(seed_demo)


def rows_for(scenario, monkeypatch):
    bodies = []
    monkeypatch.setattr(seed_demo, "post", lambda url, body: bodies.append(body))
    seed_demo.seed("http://x", scenario)
    return [{**b, "id": i + 1, "created_at": "2026-10-03T08:00:00.000Z"} for i, b in enumerate(bodies)]


@pytest.mark.parametrize(
    "scenario,status,needle",
    [
        ("healthy", "green", None),
        ("slowing", "red", "longer per part"),
        ("defects", "red", "defective"),
        ("stuck", "amber", "could not be moved"),
        ("amr", "red", "not moving the way"),
    ],
)
def test_scenario_shows_what_it_claims(scenario, status, needle, monkeypatch):
    s = summarise(rows_for(scenario, monkeypatch))
    if status:
        assert s["status"] == status
    if needle:
        assert any(needle in i["title"] for i in s["attention"])
    else:
        assert s["attention"] == []
