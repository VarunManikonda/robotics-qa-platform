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

## 4. Arm workcell in Gazebo (UR5e + MoveIt)

Run the standard simulation, then add the cell into the running world. Layout and SDF generation are
unit-tested (reach, spacing, physics values); spawning itself needs Gazebo and has been verified only by
the steps below.

```bash
# terminal 1: simulation (standard launcher, unchanged)
source /opt/ros/jazzy/setup.bash
QT_QPA_PLATFORM=xcb ros2 launch ur_simulation_gz ur_sim_moveit.launch.py ur_type:=ur5e

# terminal 2: add / remove the cell
source /opt/ros/jazzy/setup.bash
cd cobot_qa && python3 -m cobot_qa.spawn_cell spawn      # 3 red blocks, 1 blue block, 2 pads
python3 -m cobot_qa.spawn_cell remove                    # clean up before re-spawning
```

Expected: `6/6 succeeded`; in Gazebo, four cubes in front of the arm and a green and an orange square on the
floor. `ur_sim_moveit.launch.py` does not forward a `world_file` argument, which is why objects are spawned
into the running world instead of loading a custom world.

## 5. Overhead camera and block detection

`sim/arm_cell.launch.py` replaces `ur_sim_moveit.launch.py` for this cell. It is the same launch (Gazebo,
MoveIt, RViz) but loads `sim/qa_cell.sdf`, which contains the floor, the camera, the pads and the blocks,
and bridges the camera image into ROS as `/overhead/image`. (The upstream launch file drops `world_file`.)

```bash
# stop any earlier simulation first (Ctrl+C), then:
source /opt/ros/jazzy/setup.bash
QT_QPA_PLATFORM=xcb ros2 launch ~/Downloads/robotics-qa-platform/cobot_qa/sim/arm_cell.launch.py
```

Park the arm out of the camera's view (the simulation starts with the arm stretched over the blocks):

```bash
ros2 action send_goal /scaled_joint_trajectory_controller/follow_joint_trajectory \
  control_msgs/action/FollowJointTrajectory \
  "{trajectory: {joint_names: [shoulder_pan_joint, shoulder_lift_joint, elbow_joint, wrist_1_joint, wrist_2_joint, wrist_3_joint], points: [{positions: [1.5708, -1.5708, 0.0, -1.5708, 0.0, 0.0], time_from_start: {sec: 8}}]}}"
```

Check the camera: `ros2 topic hz /overhead/image` (about 10 Hz) and view it with
`ros2 run rqt_image_view rqt_image_view /overhead/image` (or add an Image display in RViz).
You should see a grey floor, a green and an orange square, three red squares and one blue square.

Run the detector (a terminal without the venv):

```bash
source /opt/ros/jazzy/setup.bash
cd ~/Downloads/robotics-qa-platform/cobot_qa
PYTHONNOUSERSITE=1 python3 -m cobot_qa.detect_node
```

Expected log: `4 blocks: ...` and `vs layout: block_red_1=<few>mm, ...`. The layout is deliberately not
symmetric, so a mirrored or upside-down image shows up as `MISSING` rather than matching by accident.
Errors of a few millimetres are expected (side faces of off-axis cubes are visible from above).


## 6. Sorting cycle with dashboard reporting

Four terminals. Terminals 1, 2 and 4 must NOT have the Python venv active; terminal 3 (the dashboard) does.

```bash
# terminal 1: simulator (Gazebo + MoveIt + RViz + camera and pose bridges)
source /opt/ros/jazzy/setup.bash
QT_QPA_PLATFORM=xcb ros2 launch <repo>/cobot_qa/sim/arm_cell.launch.py

# terminal 2: block detector
source /opt/ros/jazzy/setup.bash && cd <repo>/cobot_qa
PYTHONNOUSERSITE=1 python3 -m cobot_qa.detect_node

# terminal 3: dashboard (venv active)
cd <repo> && . .venv/bin/activate && make serve        # http://127.0.0.1:8000

# terminal 4: sorter
source /opt/ros/jazzy/setup.bash && cd <repo>/cobot_qa
PYTHONNOUSERSITE=1 python3 -m cobot_qa.sort_node --ros-args -p max_blocks:=4
```

Optional first: `-p check_only:=true` solves IK for every block and pad pose without moving the arm.

Expected: for each part a line `block_...: (x, y) -> pad_good slot N`, three `step '...' done` lines,
`dashboard: posted - ...`, and finally `sorted 4 block(s)`. The dashboard shows four `part:block_...` rows
under `cobot_qa`: three `pass` (red, good pad, slots 0 to 2) and one `fail` (blue, reject pad: correctly
rejected). Reset the cell between runs with `python3 -m cobot_qa.spawn_cell remove` then `spawn`.
