"""ROS 2 node: degrade the velocity command to simulate a wheel/motor fault.

Relays `in_topic` to `out_topic`, multiplying the linear velocity by `scale`
after `fault_after_s` seconds. Use it to prove the monitor detects a fault:
run Nav2 publishing to /cmd_vel_raw, remap this node's out_topic to /cmd_vel,
and watch the dashboard.

Set `stamped:=true` for geometry_msgs/TwistStamped.

NOT run in the development sandbox (no ROS 2 there); see docs/TESTING.md.
"""

from __future__ import annotations

import rclpy
from geometry_msgs.msg import Twist, TwistStamped
from rclpy.node import Node


class FaultInjector(Node):
    def __init__(self) -> None:
        super().__init__("fault_injector")
        self.declare_parameter("in_topic", "/cmd_vel_raw")
        self.declare_parameter("out_topic", "/cmd_vel")
        self.declare_parameter("stamped", False)
        self.declare_parameter("fault_after_s", 60.0)  # seconds after the first command
        self.declare_parameter("scale", 0.6)
        self._t0 = None  # the fault clock starts at the first command, not at launch
        msg_t = TwistStamped if self.get_parameter("stamped").value else Twist
        self._stamped = bool(self.get_parameter("stamped").value)
        self._pub = self.create_publisher(msg_t, self.get_parameter("out_topic").value, 10)
        self.create_subscription(msg_t, self.get_parameter("in_topic").value, self._on_cmd, 10)
        self._announced = False

    def _on_cmd(self, msg) -> None:
        if self._t0 is None:
            self._t0 = self.get_clock().now()
        elapsed = (self.get_clock().now() - self._t0).nanoseconds * 1e-9
        active = elapsed >= float(self.get_parameter("fault_after_s").value)
        if active and not self._announced:
            self.get_logger().warn("fault injection ACTIVE")
            self._announced = True
        if active:
            scale = float(self.get_parameter("scale").value)
            (msg.twist.linear if self._stamped else msg.linear).x *= scale
        self._pub.publish(msg)


def main() -> None:
    rclpy.init()
    node = FaultInjector()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
