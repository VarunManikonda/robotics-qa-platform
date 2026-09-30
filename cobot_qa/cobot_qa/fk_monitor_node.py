"""ROS 2 node: check that TF agrees with our independent FK for the UR5e.

Subscribes to /joint_states, computes tool0 pose with `kinematics.fk`, looks up
base_link -> tool0 from TF, and reports the position error to the dashboard
(pass under `tolerance_mm`, fail above). This catches wrong URDF parameters,
wrong joint ordering and stale TF.

NOT run in the development sandbox (no ROS 2 there); see docs/TESTING.md for
how to verify it on a ROS 2 Jazzy machine.
"""

from __future__ import annotations

import json
import threading
import urllib.request

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import JointState
from tf2_ros import Buffer, TransformListener

from .kinematics import fk

JOINT_ORDER = [
    "shoulder_pan_joint",
    "shoulder_lift_joint",
    "elbow_joint",
    "wrist_1_joint",
    "wrist_2_joint",
    "wrist_3_joint",
]


class FkMonitor(Node):
    def __init__(self) -> None:
        super().__init__("fk_monitor")
        self.declare_parameter("dashboard_url", "http://127.0.0.1:8000")
        self.declare_parameter("tolerance_mm", 2.0)
        self.declare_parameter("report_period_s", 2.0)
        self.declare_parameter("base_frame", "base_link")
        self.declare_parameter("tool_frame", "tool0")
        self._tf_buffer = Buffer()
        self._tf_listener = TransformListener(self._tf_buffer, self)
        self._latest: JointState | None = None
        self.create_subscription(JointState, "/joint_states", self._on_js, 10)
        period = self.get_parameter("report_period_s").value
        self.create_timer(float(period), self._check)

    def _on_js(self, msg: JointState) -> None:
        self._latest = msg

    def _check(self) -> None:
        msg = self._latest
        if msg is None:
            return
        pos = dict(zip(msg.name, msg.position, strict=False))
        if not all(j in pos for j in JOINT_ORDER):
            self.get_logger().warn("joint_states missing UR5e joints")
            return
        q = [pos[j] for j in JOINT_ORDER]
        try:
            tf = self._tf_buffer.lookup_transform(
                self.get_parameter("base_frame").value,
                self.get_parameter("tool_frame").value,
                rclpy.time.Time(),
            )
        except Exception as exc:  # TF not ready yet
            self.get_logger().warn(f"TF lookup failed: {exc}")
            return
        t = tf.transform.translation
        ours = fk(q)[:3, 3]
        err_mm = 1000.0 * float(
            ((ours[0] - t.x) ** 2 + (ours[1] - t.y) ** 2 + (ours[2] - t.z) ** 2) ** 0.5
        )
        tol = float(self.get_parameter("tolerance_mm").value)
        body = {
            "project": "cobot_qa",
            "name": "fk_vs_tf",
            "status": "pass" if err_mm <= tol else "fail",
            "metric": err_mm,
            "message": f"FK/TF position error {err_mm:.2f} mm (tolerance {tol} mm)",
            "payload": {"joints": q},
        }
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
    node = FkMonitor()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
