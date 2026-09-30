"""Launch the UR5e inspection cell: Gazebo (custom world with camera), MoveIt, RViz, image bridge.

    QT_QPA_PLATFORM=xcb ros2 launch <path>/cobot_qa/sim/arm_cell.launch.py

This mirrors ur_simulation_gz's ur_sim_moveit.launch.py but forwards `world_file`, which that
launch file does not. Arguments and includes were taken from the upstream jazzy branch.
"""

import os

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_WORLD = os.path.join(HERE, "qa_cell.sdf")


def generate_launch_description():
    ur_type = LaunchConfiguration("ur_type")
    world_file = LaunchConfiguration("world_file")
    gazebo_gui = LaunchConfiguration("gazebo_gui")

    ur_control = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            PathJoinSubstitution(
                [FindPackageShare("ur_simulation_gz"), "launch", "ur_sim_control.launch.py"]
            )
        ),
        launch_arguments={
            "ur_type": ur_type,
            "launch_rviz": "false",
            "world_file": world_file,
            "gazebo_gui": gazebo_gui,
        }.items(),
    )

    ur_moveit = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            PathJoinSubstitution(
                [FindPackageShare("ur_moveit_config"), "launch", "ur_moveit.launch.py"]
            )
        ),
        launch_arguments={
            "ur_type": ur_type,
            "use_sim_time": "true",
            "launch_rviz": "true",
            "launch_servo": "false",
        }.items(),
    )

    image_bridge = Node(
        package="ros_gz_bridge",
        executable="parameter_bridge",
        arguments=["/overhead/image@sensor_msgs/msg/Image[gz.msgs.Image"],
        output="screen",
    )

    # lets sort_node teleport a block under the tool (the virtual suction cup)
    pose_bridge = Node(
        package="ros_gz_bridge",
        executable="parameter_bridge",
        arguments=["/world/empty/set_pose@ros_gz_interfaces/srv/SetEntityPose"],
        output="screen",
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument("ur_type", default_value="ur5e"),
            DeclareLaunchArgument("world_file", default_value=DEFAULT_WORLD),
            DeclareLaunchArgument("gazebo_gui", default_value="true"),
            ur_control,
            ur_moveit,
            image_bridge,
            pose_bridge,
        ]
    )
