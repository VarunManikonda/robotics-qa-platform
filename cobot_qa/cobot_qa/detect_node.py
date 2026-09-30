"""ROS 2 node: detect blocks in the overhead camera image.

Subscribes to /overhead/image (sensor_msgs/Image, rgb8), publishes the detections as JSON on
/cell/detections (std_msgs/String), and - because the simulated layout is known - logs the
position error of each block against the layout, which verifies the camera geometry.

NOT run in the development sandbox (no ROS 2 or Gazebo there); see docs/TESTING.md.
"""

from __future__ import annotations

import json

import numpy as np
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import String

from .cell import BLOCKS
from .detector import detect_blocks, match_to_layout


def image_to_rgb(msg: Image) -> np.ndarray:
    """Convert a sensor_msgs/Image (rgb8 or bgr8) to an HxWx3 uint8 RGB array."""
    if msg.encoding not in ("rgb8", "bgr8"):
        raise ValueError(f"unsupported encoding {msg.encoding!r}")
    row = np.frombuffer(msg.data, dtype=np.uint8).reshape(msg.height, msg.step)
    img = row[:, : msg.width * 3].reshape(msg.height, msg.width, 3)
    return img[..., ::-1] if msg.encoding == "bgr8" else img


class DetectNode(Node):
    def __init__(self) -> None:
        super().__init__("block_detector")
        self.declare_parameter("image_topic", "/overhead/image")
        self.declare_parameter("period_s", 1.0)
        self.declare_parameter("compare_layout", True)
        self._last = 0.0
        self._pub = self.create_publisher(String, "/cell/detections", 10)
        self.create_subscription(Image, self.get_parameter("image_topic").value, self._on_image, 1)
        self.get_logger().info("waiting for images on " + self.get_parameter("image_topic").value)

    def _on_image(self, msg: Image) -> None:
        now = self.get_clock().now().nanoseconds * 1e-9
        if now - self._last < float(self.get_parameter("period_s").value):
            return
        self._last = now
        try:
            dets = detect_blocks(image_to_rgb(msg))
        except ValueError as exc:
            self.get_logger().warn(str(exc))
            return
        payload = [
            {"colour": d.colour, "x": round(d.x, 4), "y": round(d.y, 4), "area_px": d.area_px,
             "w_px": d.w_px, "h_px": d.h_px}
            for d in dets
        ]
        self._pub.publish(String(data=json.dumps(payload)))
        self.get_logger().info(f"{len(dets)} blocks: " + ", ".join(
            f"{d.colour}({d.x:.3f},{d.y:.3f})" for d in dets))
        if self.get_parameter("compare_layout").value:
            errs = match_to_layout(dets, BLOCKS)
            self.get_logger().info("vs layout: " + ", ".join(
                f"{n}={'MISSING' if e is None else f'{e:.1f}mm'}" for n, e in errs))


def main() -> None:
    rclpy.init()
    node = DetectNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
