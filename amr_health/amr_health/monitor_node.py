"""ROS 2 node: velocity-tracking health monitor for an AMR.

Signal: |commanded linear velocity - measured linear velocity| sampled at
`sample_hz` while the robot is being commanded to move. Rising tracking error
is a symptom of wheel slip, motor wear, a dragging brake or a stall. The
signal feeds `Detector`; alerts are posted to the dashboard.

Set `cmd_vel_stamped:=true` if your build publishes geometry_msgs/TwistStamped
on the command topic (check with `ros2 topic info /cmd_vel`).

NOT run in the development sandbox (no ROS 2 there); see docs/TESTING.md.
"""

from __future__ import annotations

import json
import threading
import urllib.request

import rclpy
from geometry_msgs.msg import Twist, TwistStamped
from nav_msgs.msg import Odometry
from rclpy.node import Node

from .detector import Detector
from .throttle import RateLimiter


class TrackingMonitor(Node):
    def __init__(self) -> None:
        super().__init__("tracking_monitor")
        self.declare_parameter("dashboard_url", "http://127.0.0.1:8000")
        self.declare_parameter("cmd_topic", "/cmd_vel")
        self.declare_parameter("odom_topic", "/odom")
        self.declare_parameter("cmd_vel_stamped", False)
        self.declare_parameter("sample_hz", 10.0)
        self.declare_parameter("min_cmd_mps", 0.05)
        self.declare_parameter("warmup", 200)
        self.declare_parameter("alert_every_s", 5.0)

        self._det = Detector(warmup=int(self.get_parameter("warmup").value))
        self._limit = RateLimiter(float(self.get_parameter("alert_every_s").value))
        self._cmd_v = 0.0
        self._odom_v = 0.0
        stamped = bool(self.get_parameter("cmd_vel_stamped").value)
        topic = self.get_parameter("cmd_topic").value
        if stamped:
            self.create_subscription(TwistStamped, topic, lambda m: self._set_cmd(m.twist.linear.x), 10)
        else:
            self.create_subscription(Twist, topic, lambda m: self._set_cmd(m.linear.x), 10)
        self.create_subscription(
            Odometry, self.get_parameter("odom_topic").value,
            lambda m: setattr(self, "_odom_v", m.twist.twist.linear.x), 10,
        )
        self.create_timer(1.0 / float(self.get_parameter("sample_hz").value), self._sample)

    def _set_cmd(self, v: float) -> None:
        self._cmd_v = v

    def _sample(self) -> None:
        if abs(self._cmd_v) < float(self.get_parameter("min_cmd_mps").value):
            return  # only score samples while actually driving
        err = abs(self._cmd_v - self._odom_v)
        was_ready = self._det.ready
        alert = self._det.update(err)
        if not was_ready and self._det.ready:
            mean, sd = self._det.baseline
            self.get_logger().info(f"baseline learned: mean={mean:.3f} sd={sd:.3f}")
            self._post_async({
                "project": "amr_health", "name": "velocity_tracking", "status": "pass", "metric": mean,
                "message": f"monitoring started, normal tracking error {mean:.3f} m/s",
                "payload": {"mean": mean, "sd": sd},
            })
        if alert is not None and self._limit.allow():
            self.get_logger().warn(f"ANOMALY {alert.kind} z={alert.z:.1f} err={err:.3f}")
            body = {
                "project": "amr_health",
                "name": "velocity_tracking",
                "status": "fail",
                "metric": err,
                "message": f"{alert.kind} (z={alert.z:.1f})",
                "payload": {"cmd": self._cmd_v, "odom": self._odom_v},
            }
            self._post_async(body)

    def _post_async(self, body: dict) -> None:
        threading.Thread(target=self._post, args=(body,), daemon=True).start()

    def _post(self, body: dict) -> None:
        url = self.get_parameter("dashboard_url").value + "/runs"
        req = urllib.request.Request(
            url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
        )
        try:
            urllib.request.urlopen(req, timeout=3).close()
        except Exception as exc:
            self.get_logger().warn(f"dashboard post failed: {exc}")


def main() -> None:
    rclpy.init()
    node = TrackingMonitor()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
