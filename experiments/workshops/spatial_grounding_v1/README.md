# Clean spatial-grounding study

This package implements the clean LAT, HEIGHT and DIST scene study for the world-action-model steerability workshop paper. Start with the [repository overview](../../../README.md) and [current status](../../../REPOSITORY_STATUS.json). Authored scenes and scripted physical qualification remain distinct from learned-policy results. The 1,566-cell learned-policy study is not authorized to launch.

- [Frozen experiment specification](spec/README.md): 18 exact prompts, matched six-cell comparisons, scoring rules and the 1,566-cell queue template.
- [Clean scene examples](../../../docs/CLEAN_SCENES.md) and [scene construction](../../../docs/scene_design_rtx/README.md): geometry, camera captures and scripted qualification.
- [Active candidate catalog](../../../artifacts/workshops/spatial_grounding_v1/balanced_flat_scene_candidates_20260924/): authored input bytes and declared order. Its bounded execution registration and selection plan admit only the first 100 candidates per family under the frozen protocol limit.
- [Clean cohort registration](../../../docs/CLEAN_SCENE_COHORT.md): scene identities, evidence boundaries and future study registration.
- [Runtime setup](../../../docs/STANDALONE_RUNTIME.md) and [cluster handoff](../../../docs/CLUSTER_HANDOFF.md): pinned external dependencies, whole matched-block partitions and prerequisites for a future authorized run.
- [CPU test scope](../../../tests/README.md): portable software checks and separate optional prerequisites.

Keep native task modules and shared geometry helpers with the runner: some are loaded through runtime paths. A scene becomes eligible only through the required complete physical receipts; authored inputs, pending trials and missing evidence never establish a pass. Preserve valid failures and immutable registered input/plan bytes. External simulator assets, model weights and raw recording arrays remain outside Git.

The clean extraction excludes disconnected historical audit and MAIN-P code. [The exclusion record](../../../provenance/legacy-source-exclusion.json) lists removed paths and hashes. Preserved prototype plans retain their original source inventories as provenance; current execution uses its own reviewed source/runtime binding.
