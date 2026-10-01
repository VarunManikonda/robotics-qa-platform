# Architecture

```
 ROS 2 nodes / scripts                     Dashboard (FastAPI + SQLite)
 ------------------------                  ----------------------------
 cobot_qa.fk_monitor_node  --POST /runs-->  runs table  <-- GET /runs (filters, cursor)
 amr_health.monitor_node   --POST /runs-->                <-- GET /stats
 scripts/demo_offline.py   --POST /runs-->                <-- web UI at /
        |
        v
 pure-Python logic (fully unit-tested, no ROS import)
 cobot_qa.kinematics / inspector / mission      amr_health.detector / simulate
```

The rule: **all decisions live in pure-Python modules**; ROS nodes only move data in and out.
This is what makes the logic testable in CI without a ROS install.

## Dashboard design

* One table, `runs`, with indexes on `(project, id)`, `(status, id)` and `created_at`.
* Every filter is optional and they AND together, so users narrow a large history step by step.
* Keyset pagination (`id < cursor`, newest first). The service fetches `limit + 1` rows so the
  last page never reports a phantom next page (tested).
* Text search escapes `%` and `_`, so searching for `100%` matches literally (tested).
* SQLite is a deliberate v1 choice (zero setup). The storage code is isolated in `db.py`.

## cobot_qa

* `kinematics.fk` uses the published UR5e DH parameters and a 180-degree base rotation to match
  the ROS `base_link` frame. It is checked against a four-pose answer key (millimetre accuracy)
  and properties (rotation matrix is orthonormal; spinning wrist 3 does not move the tool origin).
* `reachable()` is a conservative sphere test. A `False` is a reliable rejection; a `True` does
  **not** guarantee IK success (orientation, wrist offsets and collisions still matter).
* `inspector` classifies a part from a defect-pixel ratio against an expected colour.
* `mission.run_mission` skips unreachable parts *before* inspecting them (tested).
* `fk_monitor_node` compares our FK with the TF `base_link -> tool0` transform and reports the
  error. It catches wrong URDF parameters, joint-order mistakes and stale TF.

## amr_health detector

Signal: velocity-tracking error (commanded vs measured linear velocity) while driving.

1. Learn mean/std from the first `warmup` samples, then **freeze** the baseline. An adaptive
   baseline absorbs a slowly drifting fault and never raises it.
2. Alert on `|z| > z_spike` (sudden events) or on a two-sided CUSUM exceeding `h`
   (step changes and drift).
3. Non-finite samples are counted and skipped; a constant signal is handled by a `min_std` floor.

### How the parameters were chosen

The first version (`k=0.5, h=8`) failed its own tests: it raised false alarms on clean data in
most seeds because the baseline learned from 200 samples is slightly off. A sweep over 30 seeds
(20,000 clean samples each; steps and drift injected at sample 1000) gave:

| k | h | seeds with a false alarm (of 30) | 4-sigma step delay (median / max samples) |
|---|---|---|---|
| 0.5 | 8 | 25 | (not usable) |
| 0.5 | 12 | 8 | 3 / 4 |
| 0.75 | 12 | 0 | 3 / 5 |
| **1.0** | **8** | **0** | **2 / 3** |

Chosen: `k=1.0, h=8, warmup=200`. Measured sensitivity on synthetic data (30 seeds each):

| Injected shift | Detected | Median delay |
|---|---|---|
| 1.5 sigma | 30/30 | 15 samples |
| 2 sigma | 30/30 | 7 samples |
| 3 sigma | 30/30 | 3 samples |
| 4 sigma | 30/30 | 2 samples |

Shifts around 1 sigma are only caught eventually (median delay 56) and should not be relied on.
All of this is on **synthetic Gaussian noise**. Real sensors have non-Gaussian noise, duty-cycle
changes and thermal drift, so re-run the sweep on recorded data before trusting the numbers.

### Known limitations

* Stationary-baseline assumption: call `reset()` after maintenance or a duty-cycle change.
* Single-signal, single-robot. Multi-signal fusion and per-mode baselines are future work.
* No root-cause classification; it says "something changed", not why.


## Lessons from running it in simulation

Three problems were invisible to unit tests and only appeared when the arm ran in Gazebo. Each now has
a regression test for the part that can be tested offline.

| What happened | Cause | Fix |
|---|---|---|
| A carried block fell through the floor on release | Gazebo keeps a teleported body's velocity, so 20 teleports a second under gravity built up huge downward speed | Blocks are static, visual-only models moved only by teleport (`cell.py`, tested) |
| A block bumped by the arm slid away and was lost (an intermediate fix had removed gravity) | With gravity off there is no floor friction either | Same fix: a static model has no velocity to leak |
| Moves to the same waypoint were 2.94 rad one time and 1.91 rad the next, and the second one stalled the arm (controller error -4) | MoveIt's `/compute_ik` returned different arm configurations for the same pose | `ik.py`: a deterministic solver that walks to the target from a fixed nominal configuration, so every pose is reached in the same configuration (tested over all 25 cell poses, with a mutation check) |

Also found by running: the camera sees the arm's own body, so the sorter parks the arm before every
detection and ignores blobs smaller than 85 % of a whole block; neighbouring cubes 1 cm apart merge into
one blob, so cubes on a pad are counted from blob width, not blob number.
