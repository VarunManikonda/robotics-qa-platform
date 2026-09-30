# Testing

## 1. Unit and API tests (no ROS)

```bash
make test        # dashboard 11, cobot_qa 18, amr_health 47
make lint
```

CI runs the same per-package, plus lint and a Docker build (`.github/workflows/ci.yml`).

**Troubleshooting: `ModuleNotFoundError: No module named 'yaml'` from `launch_testing`.** This happens when
ROS 2 is sourced in the same shell: ROS's pytest plugins get auto-loaded inside the venv. `make test`
already sets `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`. If you run pytest by hand, use
`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q`, or open a shell without ROS sourced.

## 2. ROS 2 runbook (Ubuntu 24.04, ROS 2 Jazzy)

**Status: these steps have not been executed by the author of this repo.** The nodes compile
and reuse tested logic, but wiring differs between machines. Treat this section as the first
integration test, and fix the runbook where reality differs.

### 2a. UR5e forward-kinematics monitor

```bash
sudo apt install ros-jazzy-ur ros-jazzy-tf2-ros
source /opt/ros/jazzy/setup.bash

# terminal 1: dashboard
make serve

# terminal 2: UR5e with mock hardware (no robot needed)
ros2 launch ur_robot_driver ur_control.launch.py ur_type:=ur5e robot_ip:=yyy \
  use_mock_hardware:=true launch_rviz:=false initial_joint_controller:=joint_trajectory_controller

# terminal 3: the monitor (run from cobot_qa/ so the package imports)
cd cobot_qa && python3 -m cobot_qa.fk_monitor_node
```

Expected: a `fk_vs_tf` run every 2 s, status `pass`, error well under 2 mm.
Known behaviour from earlier UR5e mock-hardware work: it can start at -1.57 rad rather than
exactly -pi/2, giving a sub-millimetre offset. The default 2 mm tolerance covers that.

Negative test: edit `A` or `D` in `kinematics.py`, restart the node, and confirm runs turn `fail`.

### 2b. AMR tracking monitor and fault injection

```bash
sudo apt install ros-jazzy-nav2-bringup ros-jazzy-turtlebot3-gazebo ros-jazzy-turtlebot3-navigation2
export TURTLEBOT3_MODEL=waffle
ros2 launch nav2_bringup tb3_simulation_launch.py headless:=False

# check the command message type on your build
ros2 topic info /cmd_vel        # Twist or TwistStamped? if Stamped, add stamped:=true / cmd_vel_stamped:=true
```

Simplest fault test (bypasses Nav2 so the wiring is easy to reason about):

```bash
# terminal A: monitor (watches /cmd_vel and /odom)
cd amr_health && python3 -m amr_health.monitor_node

# terminal B: injector relays /cmd_vel_raw -> /cmd_vel, degrading speed after 60 s
cd amr_health && python3 -m amr_health.fault_injector_node --ros-args -p fault_after_s:=60.0 -p scale:=0.6

# terminal C: drive straight at 0.2 m/s through the injector
ros2 topic pub -r 10 /cmd_vel_raw geometry_msgs/msg/Twist "{linear: {x: 0.2}}"
```

The monitor needs about 200 driving samples (~20 s at 10 Hz) to learn its baseline, so leave
the robot clear of walls. After 60 s a fault should appear on the dashboard under `amr_health`.
If the robot reaches a wall first, it will also produce tracking error, which is a valid alert
but not the injected one; use an open area in the world.

## 3. What a good next test looks like

Convert the checks above into `launch_testing` tests that start the simulation, wait for a
`pass` run, inject the fault, and assert a `fail` run appears within a time budget.
