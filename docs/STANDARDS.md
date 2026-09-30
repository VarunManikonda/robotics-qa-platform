# Standards and practices mapping

This project is **not certified** against any standard and makes no compliance claim. The table
shows which established practice each part is designed to support, and what is still missing.
Check current editions before citing them: ISO 10218 has been under revision, and its content
overlaps with ISO/TS 15066 for collaborative operation.

| Practice / standard | Area | What this repo does | What is missing |
|---|---|---|---|
| ISO 10218-1/-2 | Industrial robot safety | Reachability pre-flight rejects targets outside the work envelope; joint-limit checks | No safety-rated stop or speed monitoring; not a safety function |
| ISO/TS 15066 | Collaborative operation | Nothing yet (roadmap: tests that speed limits are respected) | Force/pressure limits, speed and separation monitoring |
| ISO 9283 | Manipulator performance | FK accuracy is measured against a known answer key (in simulation) | Real repeatability/accuracy trials on hardware |
| ISO/IEC/IEEE 29119 | Software testing | Per-package test suites with parametrised, boundary and negative cases | Formal test plan and traceability matrix |
| ROS 2 REP-2004 | Package quality levels | Tests, lint and CI are in place | Ament packaging, quality declaration, coverage tracking |
| C++ Core Guidelines / MISRA C++ | Safe C++ | Not applicable yet (Python only) | Relevant when the Dynamixel ros2_control interface is written |
| CI/CD and reproducibility | Delivery | GitHub Actions matrix, Docker image, pinned Python versions | Pinned dependency lockfile |
