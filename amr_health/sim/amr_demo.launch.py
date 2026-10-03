"""Launch the AMR demo: Nav2 + TurtleBot3 in Gazebo, a fault injector, the health monitor and a patrol.

    QT_QPA_PLATFORM=xcb ros2 launch <path>/amr_health/sim/amr_demo.launch.py

Signal path:  Nav2 -> /cmd_vel_raw -> fault injector -> /cmd_vel -> wheels (Gazebo)
              health monitor compares /cmd_vel_raw (what Nav2 asked for) with /odom (what the wheels did).

Arguments:
    fault_after_s   seconds of driving before the fault starts (use 99999 for a healthy run)
    scale           fraction of the commanded speed the wheels actually get once the fault is on
    laps            patrol laps
    dashboard_url   where results are posted
"""

import os
import tempfile

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, IncludeLaunchDescription, OpaqueFunction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration

HERE = os.path.dirname(os.path.abspath(__file__))
PKG_DIR = os.path.dirname(HERE)  # .../amr_health, the folder that contains the python package
ROUTE_MODULE = "amr_health"


def _patched_params() -> str:
    import sys

    sys.path.insert(0, PKG_DIR)
    from amr_health.nav_params import route_through_injector

    src = os.path.join(get_package_share_directory("nav2_bringup"), "params", "nav2_params.yaml")
    with open(src) as f:
        text = route_through_injector(f.read())
    fd, path = tempfile.mkstemp(prefix="nav2_params_amr_", suffix=".yaml")
    with os.fdopen(fd, "w") as f:
        f.write(text)
    return path


def _py(module: str, *params: str):
    cmd = ["python3", "-m", f"{ROUTE_MODULE}.{module}", "--ros-args", "-p", "use_sim_time:=true"]
    for p in params:
        cmd += ["-p", p]
    return cmd


def _build(context):
    arg = lambda name: LaunchConfiguration(name).perform(context)  # noqa: E731
    env = {"PYTHONPATH": PKG_DIR + os.pathsep + os.environ.get("PYTHONPATH", "")}
    nav2 = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(get_package_share_directory("nav2_bringup"), "launch", "tb3_simulation_launch.py")
        ),
        launch_arguments={"headless": "False", "params_file": _patched_params()}.items(),
    )
    injector = ExecuteProcess(
        cmd=_py(
            "fault_injector_node",
            "in_topic:=/cmd_vel_raw",
            "out_topic:=/cmd_vel",
            f"fault_after_s:={arg('fault_after_s')}",
            f"scale:={arg('scale')}",
        ),
        additional_env=env,
        output="screen",
    )
    monitor = ExecuteProcess(
        cmd=_py("monitor_node", "cmd_topic:=/cmd_vel_raw", f"dashboard_url:={arg('dashboard_url')}"),
        additional_env=env,
        output="screen",
    )
    runner = ExecuteProcess(
        cmd=_py("goal_runner_node", f"laps:={arg('laps')}", f"dashboard_url:={arg('dashboard_url')}"),
        additional_env=env,
        output="screen",
    )
    return [nav2, injector, monitor, runner]


def generate_launch_description():
    return LaunchDescription(
        [
            DeclareLaunchArgument("fault_after_s", default_value="60.0"),
            DeclareLaunchArgument("scale", default_value="0.5"),
            DeclareLaunchArgument("laps", default_value="3"),
            DeclareLaunchArgument("dashboard_url", default_value="http://127.0.0.1:8000"),
            OpaqueFunction(function=_build),
        ]
    )
