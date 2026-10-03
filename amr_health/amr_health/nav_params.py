"""Re-route Nav2's final velocity command so a fault can be injected between Nav2 and the wheels.

Nav2 Jazzy's collision monitor publishes the final command on /cmd_vel. We make it publish /cmd_vel_raw
instead; the fault injector relays it to /cmd_vel (unchanged until the fault starts).
"""

from __future__ import annotations

import re

_PATTERN = re.compile(r'^(\s*cmd_vel_out_topic:\s*)"cmd_vel"(\s*)$', re.MULTILINE)


def route_through_injector(params_yaml: str) -> str:
    patched, n = _PATTERN.subn(r'\1"cmd_vel_raw"\2', params_yaml)
    if n != 1:
        raise ValueError(
            f"expected exactly one cmd_vel_out_topic: \"cmd_vel\" in the Nav2 params, found {n}; "
            "the Nav2 version differs from Jazzy, check the params file by hand"
        )
    return patched
