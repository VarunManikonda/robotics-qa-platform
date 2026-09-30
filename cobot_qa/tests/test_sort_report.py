import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from cobot_qa.sort_report import build_run, layout_error_mm, post_run

RED = {"colour": "red", "x": 0.4009, "y": 0.1377}
BLUE = {"colour": "blue", "x": 0.311, "y": 0.0587}


def test_red_part_sorted_to_good_pad_is_a_pass():
    run = build_run("block_red_1", RED, "pad_good", 0, 31.24)
    assert run["status"] == "pass" and run["name"] == "part:block_red_1"
    assert run["metric"] == 31.2
    assert run["payload"]["bin"] == "good" and run["payload"]["slot"] == 0
    assert "pad_good slot 0" in run["message"]


def test_blue_part_sent_to_reject_pad_is_a_fail_that_was_handled_correctly():
    run = build_run("block_blue_1", BLUE, "pad_reject", 0, 28.0)
    assert run["status"] == "fail"
    assert run["payload"]["bin"] == "reject"
    assert "rejected" in run["message"]


def test_failed_pick_and_place_is_a_warning():
    run = build_run("block_red_2", RED, "pad_good", 1, 12.0, ok=False, reason="step 'lift' failed")
    assert run["status"] == "warn"
    assert "step 'lift' failed" in run["message"]
    assert run["payload"]["bin"] == "skipped"


def test_layout_error_is_measured_against_the_cell_layout():
    assert layout_error_mm(RED, "block_red_1") == pytest.approx(2.5, abs=0.1)  # hypot(0.9 mm, 2.3 mm)
    assert layout_error_mm(RED, "no_such_block") is None
    assert build_run("block_red_1", RED, "pad_good", 0, 1.0)["payload"]["layout_error_mm"] < 3


def test_body_has_exactly_the_fields_the_dashboard_accepts():
    run = build_run("block_red_1", RED, "pad_good", 0, 1.0)
    assert set(run) == {"project", "name", "status", "metric", "message", "payload"}
    assert run["status"] in {"pass", "fail", "warn"}
    json.dumps(run)  # serialisable


class _Capture(BaseHTTPRequestHandler):
    seen: list = []

    def do_POST(self):  # noqa: N802
        body = self.rfile.read(int(self.headers["Content-Length"]))
        _Capture.seen.append((self.path, json.loads(body)))
        self.send_response(201)
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *args):
        pass


def test_post_run_sends_json_to_runs_and_reports_success():
    _Capture.seen = []
    server = HTTPServer(("127.0.0.1", 0), _Capture)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        run = build_run("block_red_1", RED, "pad_good", 0, 1.0)
        assert post_run(run, f"http://127.0.0.1:{server.server_port}/") is True
    finally:
        server.shutdown()
    assert _Capture.seen == [("/runs", run)]


def test_post_run_returns_false_when_the_dashboard_is_down():
    run = build_run("block_red_1", RED, "pad_good", 0, 1.0)
    assert post_run(run, "http://127.0.0.1:1", timeout=0.5) is False  # nothing listens on port 1
    assert post_run(run, "not a url") is False
