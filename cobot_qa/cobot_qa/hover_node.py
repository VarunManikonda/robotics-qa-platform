"""Move the UR5e to a hover point above a detected block (step 4A: no grasping yet).

Flow: read /cell/detections -> pick a block -> ask MoveIt's /compute_ik for joint angles that put
tool0 above it, pointing down -> check them with our own FK -> send the trajectory to the arm.

    python3 -m cobot_qa.hover_node --ros-args -p colour:=red -p index:=0

NOT run in the development sandbox (no ROS 2 or Gazebo there); see docs/TESTING.md.
"""

from __future__ import annotations

import json

import numpy as np
import rclpy
from builtin_interfaces.msg import Duration
from control_msgs.action import FollowJointTrajectory
from geometry_msgs.msg import PoseStamped
from moveit_msgs.srv import GetPositionIK
from rclpy.action import ActionClient
from rclpy.node import Node
from sensor_msgs.msg import JointState
from std_msgs.msg import String
from trajectory_msgs.msg import JointTrajectoryPoint

from .hover import DOWN_QUAT, Z_CLEAR, hover_is_reachable, hover_position, select_target
from .kinematics import fk

JOINTS = ["shoulder_pan_joint", "shoulder_lift_joint", "elbow_joint",
          "wrist_1_joint", "wrist_2_joint", "wrist_3_joint"]
MOVEIT_OK = 1  # moveit_msgs/MoveItErrorCodes SUCCESS


class HoverNode(Node):
    def __init__(self) -> None:
        super().__init__("hover")
        self.declare_parameter("colour", "red")
        self.declare_parameter("index", 0)
        self.declare_parameter("z", Z_CLEAR)
        self.declare_parameter("duration_s", 6)
        self.dets: list[dict] | None = None
        self.js: JointState | None = None
        self.create_subscription(String, "/cell/detections", self._on_dets, 1)
        self.create_subscription(JointState, "/joint_states", self._on_js, 1)
        self.ik = self.create_client(GetPositionIK, "/compute_ik")
        self.traj = ActionClient(
            self, FollowJointTrajectory, "/scaled_joint_trajectory_controller/follow_joint_trajectory")

    def _on_dets(self, msg: String) -> None:
        self.dets = json.loads(msg.data)

    def _on_js(self, msg: JointState) -> None:
        self.js = msg

    def _wait(self, cond, what: str, timeout: float = 20.0) -> bool:
        end = self.get_clock().now().nanoseconds * 1e-9 + timeout
        while rclpy.ok() and not cond():
            rclpy.spin_once(self, timeout_sec=0.2)
            if self.get_clock().now().nanoseconds * 1e-9 > end:
                self.get_logger().error(f"timed out waiting for {what}")
                return False
        return True

    def run(self) -> int:
        colour = self.get_parameter("colour").value
        index = int(self.get_parameter("index").value)
        z = float(self.get_parameter("z").value)
        if not self._wait(lambda: self.dets is not None, "/cell/detections (is detect_node running?)"):
            return 1
        if not self._wait(lambda: self.js is not None, "/joint_states"):
            return 1
        det = select_target(self.dets, colour, index)
        if det is None:
            self.get_logger().error(f"no {colour} block #{index} in {self.dets}")
            return 1
        x, y, z = hover_position(det, z)
        self.get_logger().info(
            f"target {colour} #{index} at ({det['x']:.3f}, {det['y']:.3f}); hover z={z:.2f}")
        if not hover_is_reachable(det, z):
            self.get_logger().error("hover point is outside the arm's reach")
            return 1

        if not self.ik.wait_for_service(timeout_sec=10.0):
            self.get_logger().error("/compute_ik not available (is MoveIt running?)")
            return 1
        req = GetPositionIK.Request()
        r = req.ik_request
        r.group_name = "ur_manipulator"
        r.ik_link_name = "tool0"
        r.avoid_collisions = False
        r.timeout = Duration(sec=2)
        r.robot_state.joint_state = self.js
        ps = PoseStamped()
        ps.header.frame_id = "base_link"
        ps.pose.position.x, ps.pose.position.y, ps.pose.position.z = x, y, z
        (ps.pose.orientation.x, ps.pose.orientation.y,
         ps.pose.orientation.z, ps.pose.orientation.w) = DOWN_QUAT
        r.pose_stamped = ps
        fut = self.ik.call_async(req)
        rclpy.spin_until_future_complete(self, fut, timeout_sec=10.0)
        res = fut.result()
        if res is None or res.error_code.val != MOVEIT_OK:
            code = None if res is None else res.error_code.val
            self.get_logger().error(f"IK failed (error code {code})")
            return 1
        sol = dict(zip(res.solution.joint_state.name, res.solution.joint_state.position, strict=False))
        q = [sol[j] for j in JOINTS]

        # independent check: our own FK must put tool0 where we asked
        got = fk(q)[:3, 3]
        err_mm = float(np.linalg.norm(got - np.array([x, y, z]))) * 1000
        self.get_logger().info(f"IK ok; own FK says tool0 is {err_mm:.1f} mm from the target")
        if err_mm > 5.0:
            self.get_logger().error("IK solution disagrees with FK; not moving")
            return 1

        if not self.traj.wait_for_server(timeout_sec=10.0):
            self.get_logger().error("trajectory controller not available")
            return 1
        goal = FollowJointTrajectory.Goal()
        goal.trajectory.joint_names = JOINTS
        pt = JointTrajectoryPoint()
        pt.positions = [float(v) for v in q]
        pt.time_from_start = Duration(sec=int(self.get_parameter("duration_s").value))
        goal.trajectory.points = [pt]
        gfut = self.traj.send_goal_async(goal)
        rclpy.spin_until_future_complete(self, gfut, timeout_sec=10.0)
        handle = gfut.result()
        if handle is None or not handle.accepted:
            self.get_logger().error("trajectory rejected")
            return 1
        rfut = handle.get_result_async()
        rclpy.spin_until_future_complete(self, rfut)
        self.get_logger().info(f"move finished, controller error code {rfut.result().result.error_code}")
        return 0


def main() -> None:
    rclpy.init()
    node = HoverNode()
    try:
        code = node.run()
    finally:
        node.destroy_node()
        rclpy.shutdown()
    raise SystemExit(code)


if __name__ == "__main__":
    main()
