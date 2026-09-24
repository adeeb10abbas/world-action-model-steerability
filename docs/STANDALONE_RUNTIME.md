# Runtime for the clean workshop study

**Construction only. No learned-policy launch is authorized.** The planned
1,566-cell clean study is cluster-only and is not currently released.

## External pins

| Dependency | Pinned identity |
| --- | --- |
| [RoboLab](https://github.com/NVlabs/RoboLab) | `0aef241fb088ca21bb4ebd24448940ed56620d17` |
| Cosmos source | `411d25b2e35bc441126f48c44a4b93e1c0564274`; native entry point `cosmos_framework.scripts.action_policy_server_robolab.RobolabPolicyService` |
| [N3 checkpoint](https://huggingface.co/nvidia/Cosmos3-Nano-Policy-DROID) | `6706d7680581c255ff61e0f3bb49d90eac55c79e` |
| [E3 checkpoint](https://huggingface.co/nvidia/Cosmos3-Edge-Policy-DROID) | Source/checkpoint pins and runtime integration pending |
| [F3 checkpoint](https://huggingface.co/black-forest-labs/flux-3-action-droid) | Root BF16 package; source/checkpoint pins, runtime and predicted-video export pending |

The documented scene runtime uses Python 3.11, Isaac Sim 5.0.0.0, Isaac Lab
2.2.0 and Torch 2.7.0+cu126. This records the source runtime identity; it is
not a claim that a new cluster environment has already been qualified.

The Nano checkpoint manifest retains its path under
`artifacts/vla_wam_shared_v2/pilot/expansion/`. DreamZero metadata and legacy
code remain historical references only; D1 is rejected by active runtime
entry points. No E3/F3 runtime or checkpoint pin has been qualified yet. Keep all model weights and
required auxiliary snapshots outside Git.

## Assets and path binding

RoboLab must be a Git checkout at the pinned revision with the complete asset
dependency graph for `assets/scenes/rubiks_cube_banana_bowl.usda` and the DROID
robot. `build_asset_manifest.py` hashes the actual referenced files. The clean
package preserves its measured workspace, controller calibration and compact
asset manifest; it does not redistribute the external native assets.

The unchanged source-bound scene launchers use a task directory with study
checkout `steerable/`, external `RoboLab/`, native `venv/`, and
`evidence/assets.json`. Their parent can be selected by `SGW_SCENE_ROOT`.
`SGW_SCENE_CODE_ROOT` selects the frozen study source snapshot independently
from the native runtime directory. Clear inherited SSH display variables for
headless launches. That layout describes registered scene execution, not a
command to start it.
New launch preparation must bind the actual target paths without rewriting
completed records or a registered plan's hashes.

USD overlays contain absolute base-scene references. Regenerate the selected
clean input against the target installation and retain the new path/hash
binding. Preserve object/support geometry, clean appearance and cameras within
each matched comparison. See [CLUSTER_HANDOFF.md](CLUSTER_HANDOFF.md) for the
resource-neutral queue preparation.

## Native production requirements

The general implementation is `release.py`, `worker.py`,
`native_worker_entrypoint.py`, and `robolab_jointpos_environment.py`. It needs
qualified clean fixtures, runtime/model identity, full resets, owned resources,
recordings and physical time maps before any later release. A source checkout
or passing CPU tests does not establish native readiness.

Native operation requires Linux, CUDA, Isaac/Omniverse and matching shared
libraries. Process identity, locks and NFS metadata refresh have platform
requirements. The CPU package setup installs none of the model or simulator
runtimes and performs no native qualification.
