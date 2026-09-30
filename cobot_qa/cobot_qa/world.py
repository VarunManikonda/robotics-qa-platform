"""Complete Gazebo world for the inspection cell: floor, light, overhead camera, blocks, pads.

The world is generated from `cell.py` and `camera.py` so the layout has a single source of
truth. `sim/qa_cell.sdf` is the committed output; a test fails if the two drift apart.

    python3 -m cobot_qa.world --write sim/qa_cell.sdf

The world is named `empty` so that `spawn_cell` (which auto-detects the world) still works
for resetting the cell (`remove` then `spawn`).
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

from .camera import Camera
from .cell import BLOCKS, PADS, _block_model, _pad_model, block_pose, pad_pose

CAMERA = Camera()

_HEADER = """<?xml version="1.0"?>
<sdf version="1.9">
<world name="empty">
  <physics name="1ms" type="ignored">
    <max_step_size>0.001</max_step_size>
    <real_time_factor>1.0</real_time_factor>
  </physics>
  <plugin filename="gz-sim-physics-system" name="gz::sim::systems::Physics"/>
  <plugin filename="gz-sim-user-commands-system" name="gz::sim::systems::UserCommands"/>
  <plugin filename="gz-sim-scene-broadcaster-system" name="gz::sim::systems::SceneBroadcaster"/>
  <plugin filename="gz-sim-sensors-system" name="gz::sim::systems::Sensors">
    <render_engine>ogre2</render_engine>
  </plugin>

  <light type="directional" name="sun">
    <cast_shadows>false</cast_shadows>
    <pose>0 0 10 0 0 0</pose>
    <diffuse>0.9 0.9 0.9 1</diffuse>
    <specular>0.1 0.1 0.1 1</specular>
    <direction>-0.2 0.1 -1</direction>
  </light>

  <model name="ground_plane">
    <static>true</static>
    <link name="link">
      <collision name="collision">
        <geometry><plane><normal>0 0 1</normal><size>100 100</size></plane></geometry>
      </collision>
      <visual name="visual">
        <geometry><plane><normal>0 0 1</normal><size>100 100</size></plane></geometry>
        <material>
          <ambient>0.55 0.55 0.55 1</ambient>
          <diffuse>0.55 0.55 0.55 1</diffuse>
          <specular>0 0 0 1</specular>
        </material>
      </visual>
    </link>
  </model>
"""


def camera_model_xml(cam: Camera = CAMERA) -> str:
    # pitch = +pi/2 makes the camera's forward (+x) axis point straight down (-z)
    pitch = round(math.pi / 2, 6)
    return f"""  <model name="overhead_camera">
    <static>true</static>
    <pose>{cam.x} {cam.y} {cam.z} 0 {pitch} 0</pose>
    <link name="link">
      <visual name="body">
        <geometry><box><size>0.06 0.06 0.04</size></box></geometry>
        <material><ambient>0.1 0.1 0.1 1</ambient><diffuse>0.1 0.1 0.1 1</diffuse></material>
      </visual>
      <sensor name="camera" type="camera">
        <always_on>true</always_on>
        <update_rate>10</update_rate>
        <visualize>false</visualize>
        <topic>overhead/image</topic>
        <camera>
          <horizontal_fov>{round(cam.hfov, 6)}</horizontal_fov>
          <image>
            <width>{cam.width}</width>
            <height>{cam.height}</height>
            <format>R8G8B8</format>
          </image>
          <clip><near>0.1</near><far>5</far></clip>
        </camera>
      </sensor>
    </link>
  </model>
"""


def build_world_sdf() -> str:
    parts = [_HEADER, camera_model_xml(), "\n"]
    parts += [_pad_model(p, pad_pose(p)) + "\n" for p in PADS]
    parts += [_block_model(b, block_pose(b)) + "\n" for b in BLOCKS]
    parts.append("</world>\n</sdf>\n")
    return "".join(parts)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", metavar="PATH", help="write the world here instead of printing it")
    args = ap.parse_args(argv)
    sdf = build_world_sdf()
    if args.write:
        Path(args.write).write_text(sdf)
        print(f"wrote {args.write} ({len(sdf)} bytes)")
    else:
        sys.stdout.write(sdf)
    return 0


if __name__ == "__main__":
    sys.exit(main())
