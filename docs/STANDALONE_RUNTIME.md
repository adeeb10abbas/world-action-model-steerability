# Runtime for the clean workshop study

**Runtime integration is authorized; no behavioral release exists yet.** The
1,566-cell clean study is cluster-only. Follow the
[current continuation](../handoff/cluster-execution-20260924/README.md), including
its checked-in startup bootstrap and preserved zero-request failures.

## External pins

| Dependency | Pinned identity |
| --- | --- |
| [RoboLab](https://github.com/NVlabs/RoboLab) | `0aef241fb088ca21bb4ebd24448940ed56620d17` |
| Cosmos source | `411d25b2e35bc441126f48c44a4b93e1c0564274`; native entry point `cosmos_framework.scripts.action_policy_server_robolab.RobolabPolicyService` |
| [N3 checkpoint](https://huggingface.co/nvidia/Cosmos3-Nano-Policy-DROID) | `6706d7680581c255ff61e0f3bb49d90eac55c79e` |
| [E3 checkpoint](https://huggingface.co/nvidia/Cosmos3-Edge-Policy-DROID) | Source `cf5d68c00d97ccd2480a2320ed652b92dec63102`; checkpoint `a7c7288f9b6ac1684e993007b0f9703dd26e58ef`; native qualification pending |
| [F3 checkpoint](https://huggingface.co/black-forest-labs/flux-3-action-droid) | Source `e2dd1d8dbc5977b54315d61f7548c63c043d6d4f`; root BF16 checkpoint `3d0887bdc7acee1686b19afac267125d519ff4f1`; native qualification pending |

The documented scene runtime uses Python 3.11, Isaac Sim 5.0.0.0, Isaac Lab
2.2.0 and Torch 2.7.0+cu126. This records the source runtime identity; it is
not a claim that a new cluster environment has already been qualified.

The Nano checkpoint manifest retains its path under
`artifacts/vla_wam_shared_v2/pilot/expansion/`. DreamZero metadata and legacy
code remain historical references only; D1 is rejected by active runtime
entry points. No E3/F3 runtime or checkpoint pin has been qualified yet. Keep all model weights and
required auxiliary snapshots outside Git.

The implemented E3/F3 backends verify immutable upstream file identities and
load offline only. [Their identity manifest](../experiments/workshops/spatial_grounding_v1/checkpoint_integrations.json)
records settings, Python/dependency requirements, environment variables and
the F3 base-encoder pin `62878e2925e59b7a89ec14463ce89932624c490d`.
Decoded forecasts remain explicitly unmapped pending native qualification.

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

## Current-scene Nano fixed-input check

`nano_fixed_input.py` accepts `sgw-01-n3-current-fixed-input-registration-v2`
for a separately authorized cluster runtime check. Unlike its historical v1
registration, this input binds the current 87-layout/1,566-cell materialization
and a destination `tools/camera_checks/capture.py` receipt for **LAT-P01**.
It does not require or rerun the historical `SGW-ENG-008-LAT-057` experiment.

The v2 registration retains the existing six-request order (direct positive,
repeat positive, direct negative, twice), unchanged N3 inference settings and
native video decoding. Its sampling seed must equal the frozen LAT-P01 N3
block's effective policy seed, not the historical fixed-input seed. In addition
to the v1 capture/source/prompt references, bind `materialization`,
`environment_binding`, `bound_cells`, and the capture's
`reset-1/observation.npz` as `observation`, each with path, byte count and
SHA-256. Set `layout_id` to `LAT-P01`; omit `engineering_verification`.
The capture, binding and materialization must agree on source, candidate and
current camera identity. Each NPZ image must exactly match its hash-bound
captured sensor PNG. Proprioception is passed through the native observation
helper unchanged; measurement state is never sent to the policy.

Run from the pinned study source in the pinned Nano environment:

```sh
python -m experiments.workshops.spatial_grounding_v1.nano_fixed_input \
  --registration /persistent/current-n3-registration.json \
  --output /persistent/new-current-n3-check
```

This makes at most six actual inference requests and **executes no actions**.
It retains request intents, returned actions, same-request decoded futures,
native latents, repeated-input comparisons and three offline redecodes.
Identical outputs for opposite prompts are recorded, not retried or treated
as infrastructure failure. Errors preserve partial evidence with no automatic
retry; existing output paths cannot be reused. Successful completion alone
does not qualify physical prediction timing, closed-loop behavior, other
checkpoints, or a study release.
