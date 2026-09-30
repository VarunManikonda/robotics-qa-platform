"""Small helper around MoveIt's IK service and the joint trajectory controller.

Used by sort_node. NOT run in the development sandbox (no ROS 2 there); see docs/TESTING.md.
"""

from __future__ import annotations

import time

import numpy as np
import rclpy
from builtin_interfaces.msg import Duration
from control_msgs.action import FollowJointTrajectory
from geometry_msgs.msg import PoseStamped
from moveit_msgs.srv import GetPositionIK
from rclpy.action import ActionClient
from rclpy.node import Node
from sensor_msgs.msg import JointState
from trajectory_msgs.msg import JointTrajectoryPoint

from .hover import DOWN_QUAT
from .kinematics import fk, nearest_equivalent

JOINTS = ["shoulder_pan_joint", "shoulder_lift_joint", "elbow_joint",
          "wrist_1_joint", "wrist_2_joint", "wrist_3_joint"]
CONTROLLER = "/scaled_joint_trajectory_controller/follow_joint_trajectory"
MOVEIT_OK = 1
MAX_JOINT_STEP = 4.0  # rad; a bigger single move usually means IK flipped to another arm configuration
TICK_S = 0.05  # on_tick is called at 20 Hz while a move runs


def _duration(seconds: float) -> Duration:
    return Duration(sec=int(seconds), nanosec=int((seconds % 1.0) * 1e9))


class ArmDriver:
    def __init__(self, node: Node) -> None:
        self.node = node
        self.log = node.get_logger()
        self.js: JointState | None = None
        self.on_tick = None  # optional callable, run every TICK_S while waiting
        self._last_tick = 0.0
        node.create_subscription(JointState, "/joint_states", self._on_js, 1)
        self._ik = node.create_client(GetPositionIK, "/compute_ik")
        self._traj = ActionClient(node, FollowJointTrajectory, CONTROLLER)

    def _on_js(self, msg: JointState) -> None:
        self.js = msg

    # ------------------------------------------------------------ waiting helpers
    def _tick(self) -> None:
        now = time.monotonic()
        if self.on_tick and now - self._last_tick >= TICK_S:
            self._last_tick = now
            self.on_tick()

    def spin_for(self, seconds: float) -> None:
        end = time.monotonic() + seconds
        while rclpy.ok() and time.monotonic() < end:
            rclpy.spin_once(self.node, timeout_sec=0.01)
            self._tick()

    def wait_until(self, cond, timeout: float) -> bool:
        end = time.monotonic() + timeout
        while rclpy.ok() and not cond():
            if time.monotonic() > end:
                return False
            rclpy.spin_once(self.node, timeout_sec=0.01)
            self._tick()
        return cond()

    def ready(self, timeout: float = 20.0) -> bool:
        if not self.wait_until(lambda: self.js is not None, timeout):
            self.log.error("no /joint_states")
            return False
        if not self._ik.wait_for_service(timeout_sec=timeout):
            self.log.error("/compute_ik not available (is MoveIt running?)")
            return False
        if not self._traj.wait_for_server(timeout_sec=timeout):
            self.log.error("trajectory controller not available")
            return False
        return True

    # ------------------------------------------------------------ state
    def joints(self) -> list[float]:
        pos = dict(zip(self.js.name, self.js.position, strict=False))
        return [pos[j] for j in JOINTS]

    def tool_xyz(self) -> tuple[float, float, float]:
        p = fk(self.joints())[:3, 3]
        return float(p[0]), float(p[1]), float(p[2])

    # ------------------------------------------------------------ motion
    def ik(self, x: float, y: float, z: float) -> list[float] | None:
        """Joint angles that put tool0 at (x, y, z) pointing down, checked against our own FK."""
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
        fut = self._ik.call_async(req)
        if not self.wait_until(fut.done, 10.0):
            return None
        res = fut.result()
        if res is None or res.error_code.val != MOVEIT_OK:
            return None
        sol = dict(zip(res.solution.joint_state.name, res.solution.joint_state.position, strict=False))
        q = nearest_equivalent([sol[j] for j in JOINTS], self.joints())
        err = float(np.linalg.norm(fk(q)[:3, 3] - np.array([x, y, z])))
        return q if err < 0.005 else None

    def move_joints(self, q, seconds: float | None = None) -> bool:
        delta = max(abs(a - b) for a, b in zip(q, self.joints(), strict=True))
        if delta > MAX_JOINT_STEP:
            self.log.error(f"refusing a {delta:.1f} rad single-joint move (IK configuration flip?)")
            return False
        if seconds is None:
            seconds = max(2.0, min(12.0, delta / 0.5))
        goal = FollowJointTrajectory.Goal()
        goal.trajectory.joint_names = JOINTS
        pt = JointTrajectoryPoint()
        pt.positions = [float(v) for v in q]
        pt.time_from_start = _duration(seconds)
        goal.trajectory.points = [pt]
        gfut = self._traj.send_goal_async(goal)
        if not self.wait_until(gfut.done, 10.0):
            self.log.error("trajectory goal not answered")
            return False
        handle = gfut.result()
        if handle is None or not handle.accepted:
            self.log.error("trajectory rejected")
            return False
        rfut = handle.get_result_async()
        if not self.wait_until(rfut.done, seconds + 15.0):
            self.log.error("trajectory did not finish in time")
            return False
        result = rfut.result().result
        if result.error_code != 0:
            self.log.error(f"controller error {result.error_code}: {result.error_string}")
        return result.error_code == 0

    def move_to(self, x: float, y: float, z: float) -> bool:
        q = self.ik(x, y, z)
        if q is None:
            self.log.error(f"no IK solution for ({x:.3f}, {y:.3f}, {z:.3f})")
            return False
        return self.move_joints(q)
