# Matched execution videos requested for the paper

Read-only extraction request for the cluster agent. Do not run policies, alter episodes, or regenerate simulator trajectories. Sources below come from the committed result receipts at branch commit `750e8a0`; actual recordings remain on the cluster. The four original head-camera recordings were retrieved and their hashes verified on September 27, 2026. Full-view contact sheets and selected original frames were visually inspected for the paper montage.

## Selection rule

For each named scene/goal, enumerate complete S/I pairs and sort by `(model_id, state_slot, goal_id)` in ordinary lexicographic order. Pair A is the first with S passing and I failing the registered one-second stable-dwell endpoint. Pair B is the first with I passing and S failing that endpoint. This outcome-conditioned, deterministic illustration is not a random sample and is not additional statistical evidence. Both requested goals begin false in the frozen registry.

Keep the inconvenient second example. Its I episode has no target-gripper contact or detected target lift, substantial bowl movement, and loses the relation before the end. It illustrates what the relation metric can count, rather than demonstrating correct execution of the requested object movement. It also supplies the requested example of a stable-ever pass lost by the end; no third pair is needed.

## Requested output

- Retrieve the original full `exec_head_camera.mkv` for all four episodes: fixed head camera, 1280×720, original 15 fps. Retrieve each matching `exec_composite.mkv` as a separate supporting view (640×540); do not substitute different cameras between paired conditions.
- Verify each original against the receipt SHA256 below. Preserve the originals. Provide four full-length browser-viewable MP4 derivatives and two synchronized side-by-side head-camera montages, with S on the left and I on the right. Preserve the 15 fps timeline, all frames, and playback speed; do not crop, time-warp, omit idle time, or shorten to the apparent success interval.
- Include tick 0 through the final tick: Pair A has 601 frames spanning physical time 0–40 s; Pair B has 451 frames spanning 0–30 s. Container duration includes the displayed final frame.
- Put prompt text, model/state/goal, simulated time, and endpoint labels in separate title/border regions outside the camera image. Use robot-frame wording; do not silently translate the relation into camera-left/right. Do not draw an inferred target region without checking camera calibration.
- Pair A labels: S “stable dwell: yes; stable at end: yes”; I “stable dwell: no; stable at end: no.” Pair B: S “stable dwell: no; stable at end: no”; I “stable dwell: yes; stable at end: no; reference moved.” Do not label the latter “instruction followed.”
- Include a small contact sheet at fixed times: Pair A 0, 8, 16, 24, 32, 40 s; Pair B 0, 6, 12, 18, 24, 30 s. No generated or retouched images.
- Return `video_receipt.json` listing source/output paths, source SHA256 checks, fps, frame count, dimensions, transformation command, and any missing or corrupt source. If a source is inaccessible, report that exact file; do not select a more attractive replacement.

## Pair A: Mustard right: mover-first passes, reference-first fails

Model `E3`; fixed state `S4-C02`; goal `R`.

### S: `RWS-E3-S4-C02-R-S`

> Move the mustard bottle on the table so that the mustard bottle is to the right of the raisin box.

- Stable dwell: `true`; stable at end: `true`; target-gripper contact: `true`; detected target lift: `true`.
- Maximum reference displacement: 0.06 cm. Final target displacement from reset: 47.42 cm.
- First qualifying dwell begins at 23.467 s and completes at 24.467 s.
- Source result receipt: `artifacts/robolab_workshop_20260926/runs/episodes/RWS-E3-S4-C02-R-S/attempts/RWS-E3-S4-C02-R-S.20260927T030910.211247-alia40b-a40-2gpu.834826/result.json`.

Head camera (601 frames, 15 fps):

```text
/data/users/ali/rws-20260926/runs/episodes/RWS-E3-S4-C02-R-S/attempts/RWS-E3-S4-C02-R-S.20260927T030910.211247-alia40b-a40-2gpu.834826/exec_head_camera.mkv
SHA256 2e8abf6cc0b46d624548eafdb75aa4d70509062c9b970eeb5d0f6054a763337f
```

Policy camera composite:

```text
/data/users/ali/rws-20260926/runs/episodes/RWS-E3-S4-C02-R-S/attempts/RWS-E3-S4-C02-R-S.20260927T030910.211247-alia40b-a40-2gpu.834826/exec_composite.mkv
SHA256 201a60241928fdd8298a739b810adea95cca7f04941a3a8cbcbf7257279d00d4
```

### I: `RWS-E3-S4-C02-R-I`

> Move the mustard bottle on the table so that the raisin box is to the left of the mustard bottle.

- Stable dwell: `false`; stable at end: `false`; target-gripper contact: `true`; detected target lift: `false`.
- Maximum reference displacement: 3.91 cm. Final target displacement from reset: 15.70 cm.
- Source result receipt: `artifacts/robolab_workshop_20260926/runs/episodes/RWS-E3-S4-C02-R-I/attempts/RWS-E3-S4-C02-R-I.20260927T030304.211247-alia40b-a40-2gpu.834826/result.json`.

Head camera (601 frames, 15 fps):

```text
/data/users/ali/rws-20260926/runs/episodes/RWS-E3-S4-C02-R-I/attempts/RWS-E3-S4-C02-R-I.20260927T030304.211247-alia40b-a40-2gpu.834826/exec_head_camera.mkv
SHA256 d860f70a8f2d32fc4628aa73f7d7a9e9bffff5e849090c63efa7841f71852bf2
```

Policy camera composite:

```text
/data/users/ali/rws-20260926/runs/episodes/RWS-E3-S4-C02-R-I/attempts/RWS-E3-S4-C02-R-I.20260927T030304.211247-alia40b-a40-2gpu.834826/exec_composite.mkv
SHA256 f3497e63dd264d46aedd7f127a5656d398b399e6c521bac6865fa9fbf380985e
```

## Pair B: Cube behind: reference-first passes the relation metric by a different behavior

Model `N3`; fixed state `S1-C01`; goal `B`.

### S: `RWS-N3-S1-C01-B-S`

> Place the Rubik's cube so that the Rubik's cube is behind the bowl.

- Stable dwell: `false`; stable at end: `false`; target-gripper contact: `true`; detected target lift: `true`.
- Maximum reference displacement: 1.30 cm. Final target displacement from reset: 26.86 cm.
- Source result receipt: `artifacts/robolab_workshop_20260926/runs/episodes/RWS-N3-S1-C01-B-S/attempts/RWS-N3-S1-C01-B-S.20260927T040651.211247-alia40i-a40-1gpu.114390/result.json`.

Head camera (451 frames, 15 fps):

```text
/data/users/ali/rws-20260926/runs/episodes/RWS-N3-S1-C01-B-S/attempts/RWS-N3-S1-C01-B-S.20260927T040651.211247-alia40i-a40-1gpu.114390/exec_head_camera.mkv
SHA256 786b538381a2a37fec9a8dd1e9cb844a926428c9f14cb17bad82a5e00a1b870a
```

Policy camera composite:

```text
/data/users/ali/rws-20260926/runs/episodes/RWS-N3-S1-C01-B-S/attempts/RWS-N3-S1-C01-B-S.20260927T040651.211247-alia40i-a40-1gpu.114390/exec_composite.mkv
SHA256 a799c65305425c36e7f7322a4cdb9de50d9f430766d3157a4df858614d633cb9
```

### I: `RWS-N3-S1-C01-B-I`

> Place the Rubik's cube so that the bowl is in front of the Rubik's cube.

- Stable dwell: `true`; stable at end: `false`; target-gripper contact: `false`; detected target lift: `false`.
- Maximum reference displacement: 28.30 cm. Final target displacement from reset: 1.87 cm.
- First qualifying dwell begins at 24.400 s and completes at 25.400 s.
- Source result receipt: `artifacts/robolab_workshop_20260926/runs/episodes/RWS-N3-S1-C01-B-I/attempts/RWS-N3-S1-C01-B-I.20260927T035616.211247-alia40i-a40-1gpu.114390/result.json`.

Head camera (451 frames, 15 fps):

```text
/data/users/ali/rws-20260926/runs/episodes/RWS-N3-S1-C01-B-I/attempts/RWS-N3-S1-C01-B-I.20260927T035616.211247-alia40i-a40-1gpu.114390/exec_head_camera.mkv
SHA256 f3a663d7bfc6894b71212b1726825e672bc7a6ceeed90f334182118ba802790f
```

Policy camera composite:

```text
/data/users/ali/rws-20260926/runs/episodes/RWS-N3-S1-C01-B-I/attempts/RWS-N3-S1-C01-B-I.20260927T035616.211247-alia40i-a40-1gpu.114390/exec_composite.mkv
SHA256 10a59bdb53f8ca97b98f099f24cd575e8fe7dbb39137a6776974dd722f803d35
```

## Scoring caveat for captions and narration

The registered stable endpoint checks the requested relation, support/containment, gripper detachment, and target speed for at least one second. It does not require prior target movement/contact/lift or an unmoved reference (`scoring.py:90–109`; `EXPERIMENT_SPEC.md:97–106`). Therefore a relational pass does not by itself establish that the named object was manipulated as instructed.

Exploratory counts from the existing committed results, using frozen-registry achievement strata: among 167 achievement episodes with a stable dwell, 12 have no recorded target-gripper contact, 15 have no detected target lift, and 50 move the reference by more than 2 cm. All 15 no-lift cases also exceed the reference-displacement threshold. Per-model `(stable passes, no target contact, no lift, reference >2 cm)` counts are N3 `(70, 9, 10, 13)`, E3 `(21, 1, 1, 3)`, and F3 `(76, 2, 4, 34)`. These are overlapping categories. Absence of lift alone is not failure: pushing may satisfy a lateral goal, and support objects may move through physical contact. Do not introduce these observations as retrospective exclusions from the registered endpoint.

All seven cube-behind I passes are Nano episodes with no detected cube lift; six also have no recorded cube-gripper contact, while the bowl moves 23.3–38.9 cm. Pair B was selected before inspecting its video and must remain in the montage. Verify its actual motion from the full recording before attributing intent or a specific grasp failure.

## Completed paper-figure extraction (September 27, 2026)

Both pairs above are included in Figure 3. Pair A is shown at 0 and 40 s; Pair B at 0 and 25.4 s (the first I qualifying interval completion). Each S/I pair uses the same snapshot time. The selected Pair B I frame shows the gripper holding the bowl while the cube remains beside the banana; its S frame shows the cube inside the bowl. These visual observations are narrower than a complete account of the trajectory.

For print legibility, the paper figure differs from the original full-video request: it uses the same crop `(380, 100, 920, 635)` in the original 1280×720 frame and a 90-degree counterclockwise rotation in every panel. Full-frame source PNGs remain in `figures/execution_frames/`, and original MKVs remain locally in ignored `tmp/paper_montage/`. All transformations and original hashes are recorded in `analysis/execution_examples_receipt.json`. Full-length MP4 derivatives, composites, and synchronized playback montages have not been produced in this figure revision.
