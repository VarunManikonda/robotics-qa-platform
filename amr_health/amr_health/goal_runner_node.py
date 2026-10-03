"""ROS 2 node: patrol the TurtleBot3 world with Nav2 and report every goal to the dashboard.

Sets the initial pose (so nobody has to click in RViz), waits for Nav2, then drives `laps` laps of the
route. Each goal is posted as a `nav_goal` run: pass when reached, warn otherwise.

NOT run in the development sandbox (no ROS 2 there); see docs/TESTING.md.
"""

from __future__ import annotations

import time

import rclpy
from action_msgs.msg import GoalStatus
from geometry_msgs.msg import PoseWithCovarianceStamped
from nav2_msgs.action import NavigateToPose
from rclpy.action import ActionClient
from rclpy.node import Node

from . import goal_report, route


class GoalRunner(Node):
    def __init__(self) -> None:
        super().__init__("goal_runner")
        self.declare_parameter("laps", 3)
        self.declare_parameter("dashboard_url", "http://127.0.0.1:8000")
        self.declare_parameter("goal_timeout_s", 90.0)
        self._init_pub = self.create_publisher(PoseWithCovarianceStamped, "/initialpose", 10)
        self._client = ActionClient(self, NavigateToPose, "navigate_to_pose")

    def _pause(self, seconds: float) -> None:
        end = time.monotonic() + seconds
        while time.monotonic() < end and rclpy.ok():
            rclpy.spin_once(self, timeout_sec=0.1)

    def set_initial_pose(self) -> None:
        x, y, yaw = route.HOME
        z, w = route.yaw_to_quat(yaw)
        for _ in range(5):
            msg = PoseWithCovarianceStamped()
            msg.header.frame_id = "map"
            msg.header.stamp = self.get_clock().now().to_msg()
            msg.pose.pose.position.x, msg.pose.pose.position.y = x, y
            msg.pose.pose.orientation.z, msg.pose.pose.orientation.w = z, w
            msg.pose.covariance[0] = msg.pose.covariance[7] = 0.25
            msg.pose.covariance[35] = 0.07
            self._init_pub.publish(msg)
            self._pause(0.6)

    def go(self, x: float, y: float, yaw: float) -> tuple[str, float]:
        t0 = time.monotonic()
        goal = NavigateToPose.Goal()
        goal.pose.header.frame_id = "map"
        goal.pose.header.stamp = self.get_clock().now().to_msg()
        goal.pose.pose.position.x, goal.pose.pose.position.y = x, y
        goal.pose.pose.orientation.z, goal.pose.pose.orientation.w = route.yaw_to_quat(yaw)

        send = self._client.send_goal_async(goal)
        rclpy.spin_until_future_complete(self, send, timeout_sec=15.0)
        handle = send.result()
        if handle is None or not handle.accepted:
            return "rejected", time.monotonic() - t0
        result = handle.get_result_async()
        timeout = float(self.get_parameter("goal_timeout_s").value)
        rclpy.spin_until_future_complete(self, result, timeout_sec=timeout)
        if not result.done():
            handle.cancel_goal_async()
            self._pause(1.0)
            return "timeout", time.monotonic() - t0
        status = result.result().status
        outcome = {
            GoalStatus.STATUS_SUCCEEDED: "succeeded",
            GoalStatus.STATUS_ABORTED: "aborted",
            GoalStatus.STATUS_CANCELED: "canceled",
        }.get(status, "aborted")
        return outcome, time.monotonic() - t0

    def run(self) -> None:
        self.get_logger().info("waiting for Nav2 (navigate_to_pose)...")
        while rclpy.ok() and not self._client.wait_for_server(timeout_sec=2.0):
            pass
        self.get_logger().info("setting initial pose and letting localisation settle")
        self.set_initial_pose()
        self._pause(5.0)
        url = str(self.get_parameter("dashboard_url").value)
        stops = route.goals(int(self.get_parameter("laps").value))
        for n, (x, y, yaw) in enumerate(stops, 1):
            if not rclpy.ok():
                break
            outcome, secs = self.go(x, y, yaw)
            self.get_logger().info(f"goal {n}/{len(stops)} ({x:.2f}, {y:.2f}): {outcome} in {secs:.1f} s")
            if not goal_report.post_run(goal_report.build_run(outcome, secs, x, y), url):
                self.get_logger().warn("dashboard not reachable; continuing")
        self.get_logger().info("patrol finished")


def main() -> None:
    rclpy.init()
    node = GoalRunner()
    try:
        node.run()
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
