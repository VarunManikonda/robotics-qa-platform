"""Spawn (or remove) the inspection cell in a running Gazebo simulation.

Usage (with the UR5e simulation already running):

    cd cobot_qa
    python3 -m cobot_qa.spawn_cell spawn
    python3 -m cobot_qa.spawn_cell remove
    python3 -m cobot_qa.spawn_cell spawn --dry-run     # print commands only

Objects are added through `ros2 run ros_gz_sim create`, so the standard
`ur_sim_moveit.launch.py` is used unchanged (it does not accept a custom world).
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys

from .cell import BLOCKS, PADS, all_models

WORLD_RE = re.compile(r"/world/([^/\s]+)/create")


def find_world() -> str:
    """Ask Gazebo which world is running (usually `empty`)."""
    out = subprocess.run(
        ["gz", "service", "-l"], capture_output=True, text=True, timeout=15, check=False
    ).stdout
    m = WORLD_RE.search(out)
    if not m:
        raise RuntimeError("no Gazebo world found - is the simulation running? (gz service -l)")
    return m.group(1)


def build_spawn_commands(world: str) -> list[list[str]]:
    cmds = []
    for name, sdf, x, y, z in all_models():
        cmds.append(
            [
                "ros2", "run", "ros_gz_sim", "create",
                "-world", world, "-name", name, "-string", sdf,
                "-x", f"{x:.4f}", "-y", f"{y:.4f}", "-z", f"{z:.4f}",
            ]
        )
    return cmds


def build_remove_commands(world: str) -> list[list[str]]:
    names = [b.name for b in BLOCKS] + [p.name for p in PADS]
    return [
        [
            "gz", "service", "-s", f"/world/{world}/remove",
            "--reqtype", "gz.msgs.Entity", "--reptype", "gz.msgs.Boolean",
            "--timeout", "3000", "--req", f'name: "{n}" type: MODEL',
        ]
        for n in names
    ]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=["spawn", "remove"])
    ap.add_argument("--world", default=None, help="Gazebo world name (default: auto-detect)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    world = args.world or ("empty" if args.dry_run else find_world())
    cmds = build_spawn_commands(world) if args.action == "spawn" else build_remove_commands(world)

    failed = 0
    for cmd in cmds:
        label = cmd[cmd.index("-name") + 1] if "-name" in cmd else cmd[-1]
        if args.dry_run:
            print(" ".join(cmd[:8]), "...", flush=True)
            continue
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)
        ok = res.returncode == 0
        print(f"[{'ok' if ok else 'FAILED'}] {args.action} {label}")
        if not ok:
            failed += 1
            print((res.stderr or res.stdout).strip()[-400:])
    print(f"world={world}  {len(cmds) - failed}/{len(cmds)} succeeded")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
