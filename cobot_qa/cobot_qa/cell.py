"""Workcell layout and Gazebo SDF generation for the UR5e inspection-and-sort cell.

Pure Python (no ROS, no Gazebo) so the layout can be unit-tested:
every block and pad must be inside the arm's reach, and nothing may overlap.

Frame: world == robot base frame, x forward from the base, z up. The Gazebo
`empty.sdf` ground plane (z = 0) is the work surface, at the same height as the
UR5e base plate.

Rule for the demo: red is the nominal part colour; the blue block is the
"wrong-colour / defective" part that the inspector must reject.
"""

from __future__ import annotations

from dataclasses import dataclass

BLOCK_SIZE = 0.05  # metres, cube edge
BLOCK_MASS = 0.1  # kg
PAD_SIZE = 0.20  # metres, square drop zone
PAD_THICKNESS = 0.004

RED = (0.784, 0.157, 0.157)  # ~ (200, 40, 40) in 8-bit, the inspector's expected colour
BLUE = (0.157, 0.157, 0.784)
GREEN = (0.15, 0.6, 0.2)
ORANGE = (0.9, 0.5, 0.1)


@dataclass(frozen=True)
class Block:
    name: str
    rgb: tuple[float, float, float]
    x: float
    y: float
    defective: bool = False

    @property
    def z(self) -> float:
        return BLOCK_SIZE / 2


@dataclass(frozen=True)
class Pad:
    name: str
    rgb: tuple[float, float, float]
    x: float
    y: float


BLOCKS = (
    Block("block_red_1", RED, 0.40, 0.12),
    Block("block_red_2", RED, 0.48, 0.00),
    Block("block_red_3", RED, 0.40, -0.12),
    Block("block_blue_1", BLUE, 0.32, 0.00, defective=True),
)

PADS = (
    Pad("pad_good", GREEN, 0.30, 0.40),
    Pad("pad_reject", ORANGE, 0.30, -0.40),
)


def _material(rgb: tuple[float, float, float]) -> str:
    r, g, b = rgb
    return (
        f"<material><ambient>{r} {g} {b} 1</ambient>"
        f"<diffuse>{r} {g} {b} 1</diffuse></material>"
    )


def block_sdf(block: Block) -> str:
    a = BLOCK_SIZE
    inertia = BLOCK_MASS * a * a / 6.0  # solid cube
    return f"""<?xml version="1.0"?>
<sdf version="1.9">
  <model name="{block.name}">
    <link name="link">
      <inertial>
        <mass>{BLOCK_MASS}</mass>
        <inertia>
          <ixx>{inertia:.6e}</ixx><iyy>{inertia:.6e}</iyy><izz>{inertia:.6e}</izz>
          <ixy>0</ixy><ixz>0</ixz><iyz>0</iyz>
        </inertia>
      </inertial>
      <collision name="collision">
        <geometry><box><size>{a} {a} {a}</size></box></geometry>
        <surface>
          <friction><ode><mu>1.0</mu><mu2>1.0</mu2></ode></friction>
        </surface>
      </collision>
      <visual name="visual">
        <geometry><box><size>{a} {a} {a}</size></box></geometry>
        {_material(block.rgb)}
      </visual>
    </link>
  </model>
</sdf>
"""


def pad_sdf(pad: Pad) -> str:
    """Flat, visual-only, static marker for a drop zone (no collision, so it never affects physics)."""
    return f"""<?xml version="1.0"?>
<sdf version="1.9">
  <model name="{pad.name}">
    <static>true</static>
    <link name="link">
      <visual name="visual">
        <geometry><box><size>{PAD_SIZE} {PAD_SIZE} {PAD_THICKNESS}</size></box></geometry>
        {_material(pad.rgb)}
      </visual>
    </link>
  </model>
</sdf>
"""


def all_models() -> list[tuple[str, str, float, float, float]]:
    """(name, sdf, x, y, z) for every object in the cell. Blocks spawn 1 mm high so they settle."""
    out = [(b.name, block_sdf(b), b.x, b.y, b.z + 0.001) for b in BLOCKS]
    out += [(p.name, pad_sdf(p), p.x, p.y, PAD_THICKNESS / 2) for p in PADS]
    return out
