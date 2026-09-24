# Balanced flat-table scene candidates

This is the active authored pool for clean scripted scene completion. It is not a qualified scene registry or a learned-policy release. **No study launch is authorized.**

**Execution uses the bounded derivative plans:** `bounded-execution-registration.json`,
`bounded-selection-plan.json`, and `bounded-runtime-plan.template.json`. They retain
only the first 100 catalog entries per family, following the frozen protocol's
candidate limit. The full catalog below is retained for provenance; its excluded
tail is not eligible for this run. Root records a separate executable plan after
both flat-table prototype attempts finish.

- LAT: 125 exact input files in the previous registered order (100 right, 25 left).
- HEIGHT: 100 exact input files in the previous registered order (50 per side).
- DIST: the exact left/right flat-table prototype inputs, then the 100 layouts returned by `scene_completion_dist_flat.campaign(workspace, 20260923, 100)` (51 per side overall). The generator's first 100 rows contain no zero-translation layout, so all 102 physical layouts are distinct and no duplicate was removed.

The immutable source registrations and inputs remain in their original folders. DIST inputs here use table-supported geometry; no pedestal DIST outcomes qualify them. All candidates retain the same six scripted trials: both goals, three resets each, and 450 actions per trial. The quota remains first 15 right and 14 left all-six passes per family in declared order, including a right pilot, two development layouts per side and twelve confirmation layouts per side. Valid physical failures stay in the pool and are never replayed.

`candidate-registration.json` records input hashes, order, known outcomes and generation details. `evidence-snapshot.json` records the read-only workstation observation and compact receipt hashes. At that snapshot, 14 LAT/HEIGHT receipts were complete (12 passes and two physical rejections); both flat DIST A2 attempts were pending. No pending prototype is accepted.

`selection-plan.json` is portable: resolve `repo` to this repository root and `evidence` to the workstation task's `evidence` directory, or a faithful mirror. Completed LAT/HEIGHT evidence uses its original clean campaign path; LAT-left-000 uses its original completion prototype path. Pending rows point to `SGW-BALANCED-FLAT-20260924/<family>/<id>`. The already-running flat prototypes are observed at `SGW-FLAT-DIST-PROTOTYPES-20260924-HEADLESS-A2/<id>`; bind those paths when their complete receipts become available, before freezing the runtime plan. Do not rerun a pending A2 attempt at the new default destination. The earlier DISPLAY startup failure remains a separate preserved attempt.

`runtime-plan.template.json` binds current required source hashes and measured runtime asset hashes. It names the intended code directory, both physical GPUs and two single-environment slots per GPU. Its template schema is deliberately rejected by the runtime entrypoint. The parent task must resolve A2 outcomes, update evidence references, verify staged source/runtime hashes, and create/hash the final runtime plan before any dispatch. Input paths are relative to the plan's directory; stage this folder with its `inputs` directory intact. Source and runtime bindings are snapshots, not permission to launch.

CPU validation confirmed that every preserved LAT/HEIGHT input is byte-identical and that the original 332 registration/input files are unchanged. Both receipt readers accept the 14 completed bindings. The portable package remains partial with 12 qualified layouts, two retained physical rejections, and zero qualified DIST layouts.
