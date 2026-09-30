"""Sort the blocks: pick each one with a virtual suction cup, carry it to its pad, release.

Red (good) -> green pad, blue (defective) -> orange reject pad. The arm parks out of the camera's
view before every detection, so blocks are never seen half-hidden. The block is "held" by teleporting
it under the tool 20 times a second through Gazebo's set_pose service (bridged in arm_cell.launch.py).

    python3 -m cobot_qa.sort_node --ros-args -p check_only:=true    # IK feasibility only, no motion
    python3 -m cobot_qa.sort_node --ros-args -p max_blocks:=1       # sort one block
    python3 -m cobot_qa.sort_node                                    # sort everything

Needs detect_node running. NOT run in the development sandbox; see docs/TESTING.md.
"""

from __future__ import annotations

import json
import time

import rclpy
from rclpy.node import Node
from ros_gz_interfaces.srv import SetEntityPose
from std_msgs.msg import String

from .arm import ArmDriver
from .cell import BLOCK_SIZE, PADS
from .sort_report import build_run, post_run
from .sorter import (
    BLOCK_REST_Z,
    PARK_JOINTS,
    READY_XYZ,
    SLOT_OFFSETS_Y,
    Z_CARRY,
    Z_GRASP,
    Z_HOVER,
    Z_PLACE,
    carried_block_pose,
    destination,
    name_for_detection,
    next_on_table,
    pad_load,
    slot_xy,
)

WORLD = "empty"


class SortNode(Node):
    def __init__(self) -> None:
        super().__init__("sorter")
        self.declare_parameter("max_blocks", 4)
        self.declare_parameter("check_only", False)
        self.declare_parameter("dashboard_url", "http://127.0.0.1:8000")  # "" turns reporting off
        self.dets: list[dict] | None = None
        self.carry: str | None = None
        self.create_subscription(String, "/cell/detections", self._on_dets, 1)
        self.arm = ArmDriver(self)
        self.arm.on_tick = self._follow
        self._pose = self.create_client(SetEntityPose, f"/world/{WORLD}/set_pose")

    def _on_dets(self, msg: String) -> None:
        self.dets = json.loads(msg.data)

    # ------------------------------------------------------------ gazebo helpers
    def _set_pose(self, name: str, x: float, y: float, z: float):
        req = SetEntityPose.Request()
        req.entity.name = name
        req.entity.type = 2  # MODEL
        req.pose.position.x, req.pose.position.y, req.pose.position.z = x, y, z
        req.pose.orientation.w = 1.0
        return self._pose.call_async(req)

    def _follow(self) -> None:
        if self.carry is not None:
            self._set_pose(self.carry, *carried_block_pose(self.arm.tool_xyz()))

    def _fresh_detections(self) -> list[dict] | None:
        self.arm.spin_for(1.5)  # let the arm and the camera image settle
        self.dets = None
        return self.dets if self.arm.wait_until(lambda: self.dets is not None, 8.0) else None

    # ------------------------------------------------------------ steps
    def _park(self) -> bool:
        if not self.arm.move_to(*READY_XYZ):  # never swing straight between far-apart poses
            return False
        return self.arm.move_joints(list(PARK_JOINTS), 8.0)

    def _sort_one(self, det: dict, load: int) -> bool:
        name = name_for_detection(det)
        if name is None:
            self.get_logger().error(f"detection {det} does not match any known block")
            return False
        pad = destination(det["colour"])
        px, py = slot_xy(pad, load)
        bx, by = det["x"], det["y"]
        self.get_logger().info(f"{name}: ({bx:.3f}, {by:.3f}) -> {pad.name} slot {load}")
        a = self.arm
        for label, xyz in (("ready", READY_XYZ), ("hover", (bx, by, Z_HOVER)), ("grasp", (bx, by, Z_GRASP))):
            if not a.move_to(*xyz):
                self.get_logger().error(f"step '{label}' failed")
                return False
        self.carry = name  # suction on: the block now follows the tool
        for label, xyz in (("lift", (bx, by, Z_CARRY)), ("transfer", (px, py, Z_CARRY)),
                           ("lower", (px, py, Z_PLACE))):
            if not a.move_to(*xyz):
                self.carry = None  # suction off: leave the block where the tool let go of it
                self.get_logger().error(f"step '{label}' failed; putting the block back")
                fut = self._set_pose(name, bx, by, BLOCK_SIZE / 2)
                a.wait_until(fut.done, 3.0)
                return False
            self.get_logger().info(f"step '{label}' done")
        self.carry = None  # suction off
        fut = self._set_pose(name, px, py, BLOCK_REST_Z)  # settle it exactly on the pad
        a.wait_until(fut.done, 3.0)
        return a.move_to(px, py, Z_CARRY)

    def _report(self, det: dict, pad_name: str, slot: int, cycle_s: float, ok: bool) -> None:
        url = self.get_parameter("dashboard_url").value
        if not url:
            return
        run = build_run(name_for_detection(det) or "unknown", det, pad_name, slot, cycle_s, ok,
                        "" if ok else "see sorter log")
        sent = post_run(run, url)
        status = "posted" if sent else f"NOT reachable at {url}"
        self.get_logger().info(f"dashboard: {status} - {run['message']}")

    def _check_only(self) -> int:
        a = self.arm
        rows, bad = [], 0
        for pad in PADS:
            for i in range(len(SLOT_OFFSETS_Y)):
                x, y = slot_xy(pad, i)
                for label, z in (("carry", Z_CARRY), ("place", Z_PLACE)):
                    ok = a.ik(x, y, z) is not None
                    bad += not ok
                    verdict = "ok" if ok else "NO IK"
                    rows.append(f"{pad.name} slot {i} {label:5s} ({x:.2f},{y:.2f},{z:.3f}): {verdict}")
        for d in self.dets or []:
            for label, z in (("hover", Z_HOVER), ("grasp", Z_GRASP)):
                ok = a.ik(d["x"], d["y"], z) is not None
                bad += not ok
                verdict = "ok" if ok else "NO IK"
                rows.append(f"{d['colour']:4s} block ({d['x']:.2f},{d['y']:.2f}) {label}: {verdict}")
        print("\n".join(rows))
        self.get_logger().info(f"check finished: {bad} unreachable pose(s)")
        return 1 if bad else 0

    def run(self) -> int:
        a = self.arm
        if not a.ready():
            return 1
        if not self._pose.wait_for_service(timeout_sec=10.0):
            self.get_logger().error(f"/world/{WORLD}/set_pose missing - is the ros_gz bridge for it running?")
            return 1
        if self.get_parameter("check_only").value:
            if not a.wait_until(lambda: self.dets is not None, 10.0):
                self.get_logger().error("no /cell/detections (is detect_node running?)")
                return 1
            return self._check_only()

        done = 0
        for _ in range(int(self.get_parameter("max_blocks").value)):
            if not self._park():
                return 1
            dets = self._fresh_detections()
            if dets is None:
                self.get_logger().error("no /cell/detections (is detect_node running?)")
                return 1
            det = next_on_table(dets)
            if det is None:
                self.get_logger().info("nothing left to sort")
                break
            pad = destination(det["colour"])
            slot = pad_load(dets, pad)
            started = time.monotonic()
            ok = self._sort_one(det, slot)
            self._report(det, pad.name, slot, time.monotonic() - started, ok)
            if not ok:
                self.get_logger().error("sort step failed; parking and stopping")
                self._park()
                return 1
            done += 1
        self._park()
        self.get_logger().info(f"sorted {done} block(s)")
        return 0


def main() -> None:
    rclpy.init()
    node = SortNode()
    try:
        code = node.run()
    finally:
        node.destroy_node()
        rclpy.shutdown()
    raise SystemExit(code)


if __name__ == "__main__":
    main()
