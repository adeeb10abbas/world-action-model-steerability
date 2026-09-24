# World Action Model Steerability

Do equivalent descriptions of a spatial goal produce the same predicted and executed behavior? This repository contains the clean-scene study for the [CoRL 2026 world-model workshop](https://do-robots-need-world-models.github.io/).

**Scene generators are implemented; physical validation is running. The 1,044-episode learned-policy study has not started and will run on the cluster.**

The study compares Cosmos3 Nano Policy DROID (N3) and DreamZero DROID (D1) on left/right, higher/lower, and closer/farther placement. Each physical goal has direct, subject-first, and reference-inverted descriptions. Both models use the same clean layouts, robot, cameras, prompts and scoring rules. There are 29 layout slots per family: one pilot, four development and 24 confirmation layouts.

| Start here | Contents |
| --- | --- |
| [Clean scene examples](docs/CLEAN_SCENES.md) | Actual shoulder and wrist camera captures |
| [Scene construction](docs/scene_design_rtx/README.md) | Geometry, counterbalancing and scripted checks |
| [Candidate inputs](artifacts/workshops/spatial_grounding_v1/balanced_flat_scene_candidates_20260924/) | Recorded layouts and selection order |
| [Experiment specification](experiments/workshops/spatial_grounding_v1/spec/README.md) | Fixed protocol, 18 prompts and 1,044 planned cells |
| [Paper and analysis plan](docs/scene_design_rtx/overleaf/main.tex) | Research question, comparisons and remaining measurements |
| [Cluster handoff](docs/CLUSTER_HANDOFF.md) | 18 supported partitions containing 174 intact six-cell blocks |
| [Agent work split](docs/AGENT_TASKS.md) | Separate scene transfer, model integration, execution and analysis responsibilities |
| [Scene materialization](docs/SCENE_MATERIALIZATION.md) | Rebuild selected scenes and cell bindings at the cluster's actual paths |
| [Runtime setup](docs/STANDALONE_RUNTIME.md) | Simulator, model and checkpoint identities |
| [Source attribution](provenance/clean-extraction.json) | Origin and clean-only extraction scope |

Every selected layout must pass both physical goals across three resets with the scripted controller. Valid failures remain in the clean-scene records. These checks establish feasibility, not learned-model performance. The complete scene package requires 87 qualified layouts; authored inputs alone do not establish that result.

## CPU setup

With Python 3.11 or later and `uv`, from the repository root:

```sh
uv sync --extra test
uv run python tools/validate_standalone_sgw.py --check-imports
uv run pytest
```

These commands check software and the planned queue. They do not install or run models or simulators. Native scene checks use the separately installed, pinned RoboLab environment. Regenerate scene overlays against the intended installation because their base-asset paths are absolute.

Raw arrays, full videos, simulator assets and model weights stay outside ordinary Git. The repository contains scene inputs, camera examples, compact physical-test receipts and their hashes. The two V2-named checkpoint manifests are identity files required by the current N3/D1 wrappers; they are not additional experiment results. [Licensing notes](LICENSE_NOTICE.md) cover external dependencies.

Generated futures are compared with execution only when their physical time and camera mapping are verified. Missing evidence stays unavailable. Physical goal separation is reported in metres, separately from binary success asymmetry.
