# World Action Model Steerability

Do equivalent descriptions of a spatial goal produce the same predicted and executed behavior? This repository contains the clean-scene study for the [CoRL 2026 world-model workshop](https://do-robots-need-world-models.github.io/).

**User stop, 25 September 16:05 UTC:** the close-camera study is held and
superseded. All five in-flight episodes finalized naturally: **431 unique
episodes** (N3 148, E3 158, F3 125), five successes and 426 valid failures,
plus the five preserved technical attempts. All ten GPUs were verified
released without interrupting work. All data and frozen records remain
preserved; this is a partial stopped cohort, not a completed study.
The new stock-left/right-camera N3-only revision requires minimal reset-view
and official per-view input-packing gates before launch. This explicitly
substitutes stock views for the requested front/side pair after visibility
inspection; no pinned stock pose is corrected or changed.
See [stop authority](handoff/cluster-execution-20260924/user-stop-authorization-20260925.json).
The separate competence diagnostic is cancelled; the
[final stop receipt](handoff/cluster-execution-20260924/user-stop-final-20260925.json)
records exact counts, control exits and GPU release evidence.

**All 87 required scenes are physically validated: 29 LAT, 29 HEIGHT and 29 flat DIST layouts. Each passed both goals across three resets (522 selected scripted trials). The learned-policy study had 396 of 1,566 unique episodes complete at 2026-09-25 15:18 UTC: all 54 pilots, 216 development episodes and 126 genuine confirmation episodes. All five supervised A40 policy/simulator pairs have completed confirmation episodes after the development barrier released at 11:28:27 UTC.**

The study compares Cosmos3 Nano Policy DROID (N3), Cosmos3 Edge Policy DROID (E3), and FLUX 3 Action DROID (F3) on left/right, higher/lower, and closer/farther placement. Each physical goal has direct, subject-first, and reference-inverted descriptions. All three checkpoints use the same clean layouts, robot, cameras, prompts and scoring rules. There are 29 layout slots per family: one pilot, four development and 24 confirmation layouts.

**Roster revision 1.2:** DreamZero is retired from the executable queue. Before study launch, all three pinned runtimes completed six genuine fixed-input and two live requests each on A100: 24 requests and 192 receiver-confirmed live actions. Those identities and Nano's original cleanup failure remain unchanged. After an infrastructure-only repair, each model's first valid A40 episode retained 15 genuine requests, 450 actions and a verified viewport video. All three were **valid model failures**, not task successes or technical invalidities. The five earlier technical-invalid attempts and the zero-request recovery hold remain preserved. Execution uses source `a94696d3fa75c78a4f756536b988cead607e53b8`, the same cohort and a first-technical-invalid fleet hold. Physical forecast alignment remains unavailable. See the [current cluster continuation](handoff/cluster-execution-20260924/README.md) for exact evidence and scope.

The two exterior cameras now use closer, elevated tabletop views; the wrist camera is unchanged. Geometric coverage passed for all 87 layouts, and six representative layouts passed native camera and offline input-preprocessing checks. The 522 earlier scripted trials establish unchanged physical geometry; they were not rerun with the new cameras. See [current views and camera checks](docs/CAMERA_ALIGNMENT.md).

| Start here | Contents |
| --- | --- |
| [Cluster agents: start here](handoff/README.md) | Current inputs, work assignments and remaining runtime steps |
| [Completed scene registry](artifacts/workshops/spatial_grounding_v1/scene_package_20260924/scene-registry.json) | 87 selected layouts, exact inputs and verification receipts |
| [Clean scene examples](docs/CLEAN_SCENES.md) | Current close exterior views and retained original captures |
| [Camera alignment](docs/CAMERA_ALIGNMENT.md) | Registered framing and retained native/input-check evidence |
| [Scripted recordings](docs/SCENE_RECORDS.md) | Locations and verified identities of raw arrays, videos and state records |
| [Scene construction](docs/scene_design_rtx/README.md) | Geometry, counterbalancing and scripted checks |
| [Candidate inputs](artifacts/workshops/spatial_grounding_v1/balanced_flat_scene_candidates_20260924/) | Recorded layouts and selection order |
| [Experiment specification](experiments/workshops/spatial_grounding_v1/spec/README.md) | Fixed protocol, 18 prompts and 1,566 planned cells |
| [Paper and analysis plan](docs/scene_design_rtx/overleaf/main.tex) | Research question, comparisons and remaining measurements |
| [Cluster handoff](docs/CLUSTER_HANDOFF.md) | 27 planned partitions containing 261 intact six-cell blocks |
| [Agent work split](docs/AGENT_TASKS.md) | Separate scene transfer, model integration, execution and analysis responsibilities |
| [Scene materialization](docs/SCENE_MATERIALIZATION.md) | Rebuild selected scenes and cell bindings at the cluster's actual paths |
| [Runtime setup](docs/STANDALONE_RUNTIME.md) | Simulator, model and checkpoint identities |
| [Source attribution](provenance/clean-extraction.json) | Origin and clean-only extraction scope |

The final registry is ready: each family has 14 left and 15 right arrangements, comprising one seeded pilot, four development and 24 confirmation layouts. Eight rejected candidates remain recorded. The 205 unused registered candidates were not run after the quotas were met. These scripted checks establish physical feasibility; genuine model qualification and learned-policy outcomes are recorded separately in the current cluster continuation.

## CPU setup

With Python 3.11 or later and `uv`, from the repository root:

```sh
uv sync --extra test
uv run python tools/validate_standalone_sgw.py --check-imports
uv run pytest
```

These commands check software and the planned queue. They do not install or run models or simulators. Native scene checks use the separately installed, pinned RoboLab environment. Regenerate scene overlays against the intended installation because their base-asset paths are absolute.

Raw arrays, full videos, simulator assets and model weights stay outside ordinary Git. The repository contains scene inputs, camera examples, compact physical-test receipts and their hashes. The Nano checkpoint manifest remains an active identity dependency. DreamZero files are retained for historical provenance and legacy regression coverage; active execution rejects D1. [Licensing notes](LICENSE_NOTICE.md) cover external dependencies.

Generated futures are compared with execution only when their physical time and camera mapping are verified. Missing evidence stays unavailable. Physical goal separation is reported in metres, separately from binary success asymmetry.
