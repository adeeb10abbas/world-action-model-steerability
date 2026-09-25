# Exploratory failure-stage analysis: definitions fixed before analysis

Recorded 25 September 2026. **Exploratory and non-confirmatory.** This note
is committed separately before implementing the analyzer or reading any
confirmation-stage study outcomes in this analysis session. The request was
motivated by already reported pilot/development failure counts, dominated by
`pick_failed`; the choice to investigate pickup is therefore not outcome-blind.
This is not a claim that the note predates all confirmation data collection.
Only source schemas and model-blind geometry/calibration were inspected here.

The frozen specification permits pickup/transport/placement/release timelines
without new runs. Nothing here changes primary scoring, stage priority,
thresholds, prompts, cells, resets, or inference. No thresholds will be tuned
against study outcomes. A stage describes an observed criterion, not why the
model failed or whether it understood language.

## Primary stages and denominators

Retain recorded `failure_stage`, including the scorer's priority:
`pick_failed`, `anchor_disturbance`, `wrong_side`, `release_failed`,
`transport_failed`, or null for success. Do not reinterpret the priority as
the chronological order of all errors. In particular, `transport_failed`
means the final stable predicate failed after preceding checks passed.

Report counts by **stage P/D/C, model, family, form and physical goal sign**.
Do not pool pilot/development with confirmation, families, or opposite goals.
The stage-proportion denominator is valid, non-safety-censored model episodes,
including successes and valid failures; absent/unknown primary labels remain
an explicit `stage_unobservable` category in that denominator. Report its
numerator and denominator, not just a rounded proportion.

Also retain the full planned denominator and separate counts for `not_run`,
`technical_invalid`, and `safety_censored`. Technical and safety-censored rows
are never model-failure categories. A zero denominator yields null, not zero.
Completed attempts after authorized resumes are counted once; historical
attempts are not additional episodes.

For each model/layout/stage/sign, show the paired D, C and I labels, with
D-to-C, D-to-I and C-to-I transitions. A transition is available only if both
members have observed, valid, non-censored primary stages. Unrun, technical,
censored and unknown members stay explicit; do not infer a transition.

## Geometry and calibration, not outcome-selected thresholds

The fixed calibration is
`artifacts/workshops/spatial_grounding_v1/controller_calibrations/lat-closed-pad-20260923.json`,
SHA-256 `107442ccca01c4ac44ec6e1cb9674d51dbcd8663288a851dc54fa91a124f93d7`.
It records zero model requests/behavioral episodes, a measured closed-pad
virtual TCP relative to flange `base_link`, and a 0.12 m scripted approach
offset. Its robot asset hash is
`f555695465687548a1bd31b5e3f30385182d476a67c17080b7820ad0ef747e41`.
The virtual TCP offset in metres is
`[0.14365579295337055, 2.1544635288479885e-08, -1.233857550553778e-08]`.
It is a visual-pad midpoint, **not a measured contact point**.

Fix approach to TCP-to-cube geometric-center Euclidean distance **at most
0.12 m**, using that existing scripted approach distance. This is a broad
reach/proximity diagnostic, not contact, precise grasp alignment or intent.

`grasp_calibration.py:derive_calibration` fixes `finger_joint` open at 0 and
closed at 0.785398 radians, with absolute tolerance 1e-4 radians. Use the same
closed/open bands, not an outcome-fitted closure threshold. Intermediate
positions are neither fully open nor fully closed. Duplicate/missing joint
names, invalid positions or missing samples make closure unobservable.
Closure is not proof of contact or grasp. The reported real-study schema
does not contain filtered gripper contact forces; contact remains unobservable
there. If an existing record explicitly contains
`gripper_contact_forces.gripper__rubiks_cube.force_matrix_world_n`, contact
uses any recorded force-vector norm at least 1 N (the existing scripted
support-force convention), explicitly exploratory and independent of grasp.

Keep the existing lift and stable-predicate thresholds: cube rise at least
0.03 m from reset, sustained for 3 consecutive action steps; terminal stable
window at least 0.5 seconds, support true, detached true, linear speed below
0.02 m/s, angular speed below 0.2 rad/s, and requested relation margin at least
0.03 m. Report both the first single-sample 30 mm crossing and the onset of
the first three-step run; do not confuse a transient crossing with pickup.

## Recorded fields and coordinate checks

The native per-step schema exposes `action_step`, `sim_time_s`,
`cube_xyz_m`, `bowl_xyz_m`, `plate_xyz_m`, `supported`,
`final_detached_release`, `gripper_holding`, `linear_speed_m_s`,
`angular_speed_rad_s`, and `raw_snapshot`. The latter includes
`objects.rubiks_cube.attached_to_gripper`, `robot_body_frames.bodies`,
`robot_snapshot.body_frames.bodies`, root position/quaternion, joint
names/positions and asset identity; `context_measurements` may contain
object bounding boxes. There is **no directly recorded end-effector XYZ
field**. Joint position is not a substituted Cartesian position.

`native_geometry_measurements.robot_snapshot` records articulation root
position in env-local coordinates as world position minus environment
origin, with no rotation. `robolab_measurements.articulation_body_frames`
records body positions/quaternions in world coordinates. JSON sorts keys;
never treat the first serialized body as the root.

For approach, explicitly supply the existing model-blind workspace receipt
whose hash matches the layout's `regenerate_scene.workspace_sha256` in the
completed scene registry. Use its recorded `environment_origin_world_xyz_m`
and robot env-local root; no new geometry authority or zero-origin default.
Bind the calibration and recorded study robot to the same asset hash.

At every step match body quaternion to the recorded root quaternion (unit
quaternions, sign-invariant Euclidean difference at most 1e-4). If unique,
derive origin as that body's world position minus recorded env-local root,
and require agreement with the registered workspace origin within 1e-4 m.
If multiple bodies match, accept the workspace origin only when the study's
env-local root matches the workspace root within 1e-4 m and at least one
matching body's position also agrees with that origin. Require the env-local
root and derived origin to remain constant across the episode within 1e-4 m.
Missing fields, no match, inconsistent mapping, or asset mismatch make
approach unobservable for the episode, with the reason recorded.

Rotate the calibrated TCP offset by the recorded flange `base_link`
quaternion, add its world position, then subtract the checked origin.
Compare with the same-step cube env-local center. Do not use bounding-box
overlap as contact, invent a TCP from joint angles, assume origin zero, or
borrow a camera transform. The report inventories available field paths and
body names, and identifies the calibration/workspace hashes used.

## Pickup sub-stages and timelines

Keep primary `pick_failed` unchanged. Add these **diagnostic** sub-stages:

- `no_approach`: observed full trace never comes within the approach radius,
  with no recorded attachment contradicting it.
- `approach_no_close`: approach occurred but the gripper never reached the
  closed band anywhere in the observed trace, and never attached.
- `close_no_attach`: gripper was closed while within the approach radius,
  but attachment was never true.
- `attach_no_lift`: attachment occurred, but no observed cube rise reached
  30 mm. This is not a claim that closure alone was a successful grasp.

Use actual `gripper_holding` and/or
`raw_snapshot.objects.rubiks_cube.attached_to_gripper` for attachment; when
both exist they must agree. The native flag is RoboLab's `object_grabbed`
predicate, not a diagnosis of control intent.

These categories are not artificially exhaustive: a brief 30 mm crossing
without three sustained steps is `lift_not_sustained`; closure only away
from the cube is `close_away_from_cube`. Missing/inconsistent evidence is
`unobservable`, not a failed stage or zero. A recorded `pick_failed` with a
complete sustained-lift trace is explicitly inconsistent/unobservable and
does not overwrite the recorded primary label. Other primary stages have
sub-stage `not_applicable`.

Per episode report first approach, contact, closed-band entry, attachment,
30 mm lift crossing, sustained-lift onset, detachment after attachment, and
open-band entry after closure. Reset openness/detachment is not a release
event. `final_stable` is the onset of the terminal uninterrupted qualifying
suffix when it lasts at least 0.5 seconds; a temporary earlier stable phase
does not count. Report control step and recorded simulated time, not
wall-clock latency. Require ordered contiguous reset/action samples with an
explicit executed endpoint; missing sequence coverage stays unobservable.
Any missing predicate before a possible first event prevents an exact first
event claim. Fully observed non-occurrence is `not_observed`, not step zero.

Per-group median timelines are **conditional on exactly observed events** in
valid, non-safety-censored model episodes. Always include observed,
not-observed and unobservable counts and the eligible denominator. Null
medians stay null. These are descriptive episode medians, not independent
layout estimates, confidence intervals, tests or equivalence evidence.
Render stage-stacked bars by model/form with family/sign facets and explicit
stage selection, plus similarly faceted conditional median timelines.

All implementation/renderer tests use synthetic states only. No new native
runs, model requests, recordings or scientific gates are authorized.
