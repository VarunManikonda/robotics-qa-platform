# Robotics QA Platform

A quality-assurance and health-monitoring layer for robot software, built around two robot
scenarios and one shared run-history dashboard.

| Package | What it does | Robot / stack |
|---|---|---|
| `dashboard/` | FastAPI + SQLite run-history service with progressive filtering, keyset pagination, stats and a small web UI | any client that can POST JSON |
| `cobot_qa/` | Inspection-and-sort cell logic for a 6-DOF arm: independent UR5e forward kinematics, reachability pre-flight, colour-based part inspection, and a ROS 2 node that cross-checks FK against TF | Universal Robots UR5e, ROS 2 Jazzy, MoveIt 2 |
| `amr_health/` | Streaming anomaly detector (frozen baseline + spike + CUSUM) for AMR health signals, a velocity-tracking monitor node, and a fault injector to prove detection | Nav2 / TurtleBot3 on ROS 2 Jazzy |

## Why this exists

Robot projects usually have plenty of simulation and control work and very little automated
verification. This repo shows the layer that is often missing:

* **Regression tests that catch real failures.** For example, a reachability test that rejects
  a block placed 0.87 m from the base, the kind of mistake that makes a pick-and-place demo
  fail silently.
* **Measured detector behaviour, not guesses.** Detector thresholds were chosen from a sweep
  over false-alarm rate and detection delay (see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)).
* **Results in one searchable place.** Every check posts to the dashboard, so failures can be
  filtered by project, status, text and metric range.

## Quick start (no ROS needed)

```bash
make setup                 # creates .venv and installs dependencies
. .venv/bin/activate
make test                  # 76 tests across the three packages
make lint                  # ruff
make serve                 # dashboard on http://127.0.0.1:8000  (terminal 1)
make demo                  # posts cobot + AMR results, saves docs/amr_detection.png (terminal 2)
```

Open http://127.0.0.1:8000 and try the project / status / search filters.

## Dashboard API

```
POST /runs                 record a run           {"project","name","status":"pass|fail|warn","metric","message","payload"}
GET  /runs                 filters: project, status, q, since, until, min_metric, max_metric, limit, cursor
GET  /runs/{id}
GET  /stats
GET  /health
```

Pagination is keyset-based (`cursor` = last id seen), so paging stays fast and stable while
new runs arrive.

## Running with ROS 2

The core logic is pure Python and fully tested. The ROS 2 nodes are thin wrappers and need a
ROS 2 Jazzy machine; the exact steps are in [docs/TESTING.md](docs/TESTING.md).

## What has and has not been verified

* Verified in CI and locally: dashboard API, UR5e FK against a four-pose answer key, reachability,
  inspection and mission logic, and the anomaly detector (false alarms, step, drift, spike).
* **Not yet run on real ROS 2:** `fk_monitor_node.py`, `monitor_node.py`, `fault_injector_node.py`.
  They compile and follow the same interfaces as the tested code, but they need a first run on a
  Jazzy machine. See TESTING.md.
* Sensor data in the demos is synthetic. Detector settings should be re-tuned on real recordings.

## Repository layout

```
dashboard/   FastAPI service + tests
cobot_qa/    kinematics, inspector, mission, ROS node + tests
amr_health/  detector, simulator, ROS nodes + tests
scripts/     offline end-to-end demo
docs/        architecture, ROS testing runbook, standards mapping
.github/     CI (tests per package, lint, docker build)
```

## Roadmap

1. Package the ROS nodes as ament packages with `launch_testing` integration tests.
2. Replace the synthetic inspector image with frames from the simulated wrist camera.
3. Add a real motor-current / effort signal to the AMR monitor on hardware.
4. Add authentication and Postgres to the dashboard for multi-user deployments.
