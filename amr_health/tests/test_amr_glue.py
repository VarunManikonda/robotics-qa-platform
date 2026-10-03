import math

import pytest

from amr_health import goal_report, nav_params, route
from amr_health.throttle import RateLimiter

NAV2_SNIPPET = """\
collision_monitor:
  ros__parameters:
    base_frame_id: "base_footprint"
    cmd_vel_in_topic: "cmd_vel_smoothed"
    cmd_vel_out_topic: "cmd_vel"
    state_topic: "collision_monitor_state"
"""


def test_nav_params_reroutes_only_the_output_topic():
    out = nav_params.route_through_injector(NAV2_SNIPPET)
    assert 'cmd_vel_out_topic: "cmd_vel_raw"' in out
    assert 'cmd_vel_in_topic: "cmd_vel_smoothed"' in out
    assert out.count("cmd_vel_raw") == 1


@pytest.mark.parametrize("text", ["nothing: here\n", NAV2_SNIPPET + NAV2_SNIPPET])
def test_nav_params_refuses_when_the_file_is_not_what_we_expect(text):
    with pytest.raises(ValueError, match="found"):
        nav_params.route_through_injector(text)


def test_rate_limiter_allows_once_per_interval():
    t = [0.0]
    rl = RateLimiter(5.0, clock=lambda: t[0])
    assert rl.allow()
    t[0] = 1.0
    assert not rl.allow() and not rl.allow()
    t[0] = 5.0
    assert rl.allow()
    assert rl.suppressed == 2
    with pytest.raises(ValueError):
        RateLimiter(-1)


def test_route_quaternion_is_unit_and_goals_repeat():
    for _, _, yaw in route.WAYPOINTS:
        z, w = route.yaw_to_quat(yaw)
        assert math.isclose(z * z + w * w, 1.0)
    assert route.yaw_to_quat(0.0) == (0.0, 1.0)
    assert len(route.goals(3)) == 3 * len(route.WAYPOINTS)
    with pytest.raises(ValueError):
        route.goals(0)


def test_goal_run_reports_pass_and_warn():
    ok = goal_report.build_run("succeeded", 12.34, 0.5, -0.5)
    assert ok["status"] == "pass" and ok["name"] == "nav_goal" and ok["metric"] == 12.3
    bad = goal_report.build_run("aborted", 30.0, 0.55, 0.55)
    assert bad["status"] == "warn" and "aborted" in bad["message"]
    assert bad["payload"]["outcome"] == "aborted"


def test_goal_post_never_raises():
    assert goal_report.post_run({}, "not a url") is False
    assert goal_report.post_run({}, "http://127.0.0.1:1") is False
