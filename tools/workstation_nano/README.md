# Stock Nano wording diagnostic

This is a separate six-cell diagnostic on one unchanged stock RoboLab scene.
It does not run or alter the SGW clean-scene queue. Six cells are not six
independent trials: every cell uses the same stock left-task scene and seed
6100. No object is relocated to manufacture a neutral start.

`common.py` contains the full prospective queue: D-left, D-right, C-left,
C-right, I-left, I-right. D/C/I prompt bytes match the existing SGW LAT
wordings, including reference inversion. Both physical goals always use
`RubiksCubeLeftOfBowlTask`'s `rubiks_cube_banana_bowl.usda`, the stock robot,
lighting, background, original `WRIST_LEFT_RIGHT_HEAD` camera preset and
official native Cosmos image packing. The stock right task uses another
scene and is intentionally not loaded.

`run.py` removes only goal termination, leaving the stock 30-second timeout:
450 actions at 15 Hz, 32 actions per model request. It records upstream
left/right predicates rather than using native timeout status as success.
The original predicate only requires the spatial relation and gripper
detachment; it does not prove a completed manipulation. Results therefore
include reset predicates, final predicates, ever-grabbed, release after a
grasp and cube displacement separately.

## Server contract

Use the separate two-rank launcher in `tools/workstation_nano_server/server.py`.
The pinned official Cosmos source is `411d25b2e35bc441126f48c44a4b93e1c0564274`;
the checkpoint is Nano Policy DROID revision
`6706d7680581c255ff61e0f3bb49d90eac55c79e`. Inference uses the native OpenPI
WebSocket protocol, normally port 18026. HTTP `/healthz` is only a health check.

The server must resolve the settings in `common.SERVER_CONFIG`: deterministic
seed 6100, guidance 3, 4 denoising steps, shift 5, resolution 480, 15 conditioning
FPS, 32x8 joint-position actions, one state/history row, and decoded video.
The exact pinned native server ignores a request's `sampling_seed`; its
`deterministic_seed=True` option makes every request use its configured seed.
Do not claim that adding an unused request field controls its sampling.

The runner validates the server launch receipt and its WebSocket handshake
metadata, then requests the distributed wrapper's explicit reset control
before each episode. This is an orchestration message, not a model request.
The normal model request is unchanged: `observation/image`,
`observation/joint_position`, `observation/gripper_position`, and `prompt`.
Normal responses retain native `action` and `video` arrays. No automatic
request retries are performed.

## Run selected cells

Run with the already installed native RoboLab Python/runtime. `run.py` adds
the requested pinned RoboLab checkout to the import path; its Isaac/native
library environment still needs to be activated by the caller.

```sh
python tools/workstation_nano/run.py \
  --robolab-root /home/ali/sgw-scene-design-20260923/RoboLab \
  --output-root /home/ali/stock-nano-20260926/raw \
  --server-receipt /home/ali/stock-nano-20260926/server-launch.json \
  --remote-host 127.0.0.1 --remote-port 18026 --device cuda:0 \
  --cells D-left D-right
```

Then run the remaining four cells with the same output root and server receipt:
`--cells C-left C-right I-left I-right`. Omitting `--cells` selects all six.
`--resume-completed` skips only completed cells; an incomplete cell directory
is preserved and causes an error. Use a fresh output root for a new attempt.

The first request captures the actual physical state after the native episode
runner's **two reset calls**. Every later cell compares the full physical
state against that baseline with absolute tolerance 1e-5 and zero relative
tolerance, saving `reset_match.json`. A mismatch stops before model inference;
it is not silently counted as a matched pair. The comparison includes all
state values, not only cube/bowl positions. Native initial-state records also
retain camera extrinsics. No qualification of reset-image equality is claimed.

## Retained evidence

Each cell retains:

- Native sensor and viewport MP4s, `run_0.hdf5`, and resolved `env_cfg.json`.
  HDF5 records actual simulator actions, initial state, per-step scene state,
  end-effector poses and object bounding boxes.
- `initial_state.npz`, `reset_match.json`, and per-step `poses.jsonl`, including
  cube-minus-bowl displacement in robot coordinates and upstream predicates.
- Per-request raw three-camera/proprio observations, official packed image
  and state, returned 32x8 action chunks, and exposed decoded RGB futures.
- `requests.json` binding each future to its exact prompt, request index,
  initial execution step, seed and input/action hashes.
- `requested_step_actions.npy`, including actions requested from the client;
  the HDF5 action stream remains the source of actual simulator actions.
- Server launch metadata and reset acknowledgement; `result.json` only after
  all 450 actions and cleanup. Exceptions leave `partial.json` and existing
  raw outputs. Missing future output is explicitly unavailable, never zero.

Future arrays are retained from the same model request as the action chunk.
They are **not yet qualified for physical-time/camera-aligned forecast scores**.
No successful-manipulation rate, language-invariance result, or confirmation
claim is justified by preparation alone.

Validation performed locally: Python compilation only. No native simulator,
GPU inference, transport round trip or episode has been run by this subtask.
