# SGW-01: Equivalent spatial instructions in world–action models

This directory preserves the fixed scientific contract for the clean WAM steerability study. The scene generators, scorer, recorder, release builder and production worker are implemented. Scripted physical qualification remains in progress; native model/runtime and prediction-time qualification are separate prerequisites. **The 1,044-cell learned-policy study has not started and no launch is authorized.** Read the [current repository status](../../../../REPOSITORY_STATUS.json) for the latest preparation state.

The study asks whether equivalent spatial descriptions preserve a physical goal, and whether each WAM's generated futures reliably describe its executed movement. It compares direct (D), subject-first (C) and reference-inverted (I) wording on clean lateral, height and relative-distance scenes. The paper and evidence scope contains this clean cohort only.

| Fixed study dimension | Scope |
| --- | --- |
| Models | Cosmos3 Nano Policy DROID (N3); official conditional-action DreamZero DROID (D1) |
| Relations | Left/right; higher/lower; closer/farther relative to two anchors |
| Conditions | Three wording forms × two opposite physical goals |
| Layouts per relation | 1 pilot + 4 development + 24 confirmation |
| Planned cells | 36 pilot + 144 development + 864 confirmation = **1,044** |
| Matched comparisons | 174 intact six-cell blocks; layout is the independent sampling unit |

## Current documents

- [Experiment specification](EXPERIMENT_SPEC.md): D/C/I comparisons, physical scoring, aligned forecasts, persistence, missingness and inference limits.
- [Workshop framing](WORKSHOP_FIT.md): the WAM contribution and claim boundaries.
- [Agent handoff](AGENT_HANDOFF.md): pointers to the current [agent work split](../../../../docs/AGENT_TASKS.md) and [cluster handoff](../../../../docs/CLUSTER_HANDOFF.md).
- [Canonical paper](../../../../docs/scene_design_rtx/overleaf/main.tex): the single maintained manuscript. This specification contains no duplicate paper or PDF.
- [Clean cohort registration](../../../../docs/CLEAN_SCENE_COHORT.md), [scene construction](../../../../docs/scene_design_rtx/README.md) and [scene materialization](../../../../docs/SCENE_MATERIALIZATION.md): selected inputs, native physical receipts and portable cluster transfer.

## Fixed files and package index

`prompts.json` contains 18 exact instructions and hashes. `protocol.json` fixes the scientific settings. `planned_cells.csv` retains the 1,044 original cell IDs, prompts, seeds and matched order as an unreleased template. `registry_validation.json` and `build_registry.py` are preserved source-era planning records/code; their old readiness wording is not the current implementation status. Do not regenerate or edit these files during repository preparation. Use `tools/validate_standalone_sgw.py` from the repository root for a read-only consistency check.

`PACKAGE_MANIFEST.json` indexes the retained clean specification files and points to the canonical manuscript and handoff. `DELIVERY_CHECKS.json` reports this documentation-only cleanup. The [exclusion record](../../../../provenance/legacy-spec-paper-exclusion.json) preserves the original package/delivery index text and the exact excluded paper hashes as extraction provenance. Original paper copies remain in the original source checkout; their numerical results are outside this repository's current paper and experiment scope.

The generic `kubernetes/worker-job.yaml.in` remains an unbound reference template. It is not a native launch manifest or authorization. The current cluster handoff explains supported partitions, existing runtime entrypoints, concrete resource bindings and outstanding qualification.
