# RQA-20261006 implementation record (pre-inference)

**Written before any evaluation query was sent to a model.** This file records implementation choices that the
locked design (`EXPERIMENT_GUIDE.md`, v1.0) left to the execution agent, plus facts verified on the cluster before
inference. It does not change the protocol. Later changes are appended as dated amendments; nothing above an
amendment is rewritten.

## 1. Code and commands

| Step | Module | Command actually used (cluster) |
|---|---|---|
| Inventory | `experiments/robolab_vqa/inventory.py` | `python -m experiments.robolab_vqa.inventory --output /data/users/ali/rqa-20261006/inventory` |
| Checkpoint audit | `eligibility.py` | `python -m experiments.robolab_vqa.eligibility --output /data/users/ali/rqa-20261006/eligibility` |
| Prepare | `prepare.py` | `python -m experiments.robolab_vqa.prepare --inventory <inventory> --output /data/users/ali/rqa-20261006/release/r1 --implementation-commit <sha>` |
| Validate | `validate.py` | `python -m experiments.robolab_vqa.validate --release /data/users/ali/rqa-20261006/release/r1/release.json` |
| Qualify | `run.py --phase dev`, `qualify.py` | six development fixtures per lane; parity grouping |
| Infer | `run.py --phase all` | one lane per GPU |
| Analyze | `analyze.py` | frozen parsers, gold and bootstrap |

CPU steps use `/data/users/ali/vla_wam/envs/robolab-v2-isaac50/bin/python`; inference uses the existing
`/data/users/ali/vla_wam/envs/cosmos3-edge-vllm-omni-900a7f08-py313` environment (vLLM 0.26.0, torch 2.11.0+cu130,
transformers 5.14.1). Inputs come from the existing RWS-20260926 data root `/data/users/ali/rws-20260926`. Raw images,
responses and weights stay under `/data/users/ali/rqa-20261006/` on the shared PVC.

## 2. Evidence verified before preparation

- `release/release.json` sha256 `cd0d4783…` matches the protocol pin; 864/864 bound episodes have a `COMPLETE.json`,
  a valid `result.json` whose hash matches, and exactly one attempt; all 864 rows carry the catalog's exact prompt bytes.
- All 32 starts: `state.npz` hashes match the release and `frame_selection.json`; every original cell (36 S1, 27 S3,
  27 S4, 18 S5 per start across N3/E3/F3) used the same cached request-0 observation (wrist/left/right array hashes
  match the start's `first_obs.npz` in `first_observation.npz` and `requests/r00_input.npz`;
  `input_source=cached_first_observation`; one common composite hash per start).
- All 64 secondary frames: the source attempt resolves, the scheduled horizon matches, the bound frame is exactly the
  requested tick (offset 0 for all 64; horizon frames are the observation after the last executed action), and the
  decoded lossless composite frame matches the per-frame hash recorded at execution.
- Camera calibration is identical for all 32 starts; exterior cameras are static throughout the episodes.

## 3. Presentation decisions

- **Primary bank:** the cached request-0 observation, three native 720×1280 RGB views (wrist, left exterior, right
  exterior) in that order, as separate images in one message. No crops, overlays, panels or enhancement; native model
  resizing applies and is logged through prompt-token counts.
- **Secondary bank:** native views are saved only at request boundaries, so no native three-view observation exists at
  the selected ticks. The only saved synchronized observation is the lossless 540×640 executed composite (the policy
  input). It is split exactly into its three views (wrist 360×640, exterior 180×320 each). This is a disclosed
  bank-level resolution difference; initial and secondary statistics are never pooled.
- **Coordinate legend (calibration assistance).** At the starting pose the wrist image is rotated relative to the robot
  (robot-left appears at image right; farther from the robot appears toward the image bottom), so screen-direction
  reasoning would be systematically wrong and no robot base is visible in that view. A fixed, scene-independent header
  derived from the pinned camera extrinsics precedes each image (exterior: robot-left toward lower left / upper left;
  farther toward upper left / upper right for left/right cameras). In the secondary bank the wrist header states only
  that the camera moves with the gripper. This is a disclosed VQA presentation difference from the policy input.
- **S5 secondary:** start-time (t = 0 s) reference views precede the current views with explicit time labels, plus a
  fixed note that left/right bowl names refer to start positions.
- **B vocabulary:** catalog identifiers in alphabetical order (neutral; not target-first).

## 4. Gold labels and answerability (frozen, `labels.py`, version `rqa-gold-1`)

- Lateral/front/behind: pinned RoboLab vector cone (robot frame, 45°) recomputed from saved root positions and
  cross-checked against the stored per-tick predicate (no disagreements).
- A uses the named relation; TOP adds support (centroid in reference footprint ±1 cm AND force-cone support on the
  reference); S5 uses the stored open-top containment AND bowl–bowl contact.
- C uses the instruction's requested arrangement: relation plus table contact only when the instruction says “on the
  table”; TOP as above; S5 DIR/TF `stacked_on` = containment AND contact; S5 RF literal `on_top_supported` =
  footprint AND force-cone support. No dwell, speed or action history.
- Exclusions (gold retained for sensitivity tables): cone boundary within 5° or centres within 1 cm; object centre not
  projected into any presented view (automated pre-check; exterior views only for secondary frames because per-tick wrist
  poses were not saved); S5 secondary frames where both bowls moved >2 cm (identity not followable); C on secondary
  frames where the target or reference touches the gripper (final arrangement vs transit ambiguous).
- Human answerability review was **not performed**. Audit sheets and a review CSV template are prepared; all results
  are provisional with respect to answerability.

## 5. Readout lanes and lineage verified before inference

| Lane | Checkpoint | Verified fact |
|---|---|---|
| N3-policy | `nvidia/Cosmos3-Nano-Policy-DROID@6706d76` (executed) | All 750 reasoner tensors (36-layer LM, embeddings, LM head, vision tower) are byte-identical to `Qwen/Qwen3-VL-8B-Instruct@0c351dd`; tokenizer, processor and chat template files are identical too |
| N3-upstream-qwen3vl8b | `Qwen/Qwen3-VL-8B-Instruct@0c351dd` | Named as the backbone in the policy config; tensor-identical to the N3-policy reasoner |
| N3-base | `nvidia/Cosmos3-Nano@e59a53c` (weights unchanged since the 2026-06-01 squash) | Differs from the policy/upstream reasoner in 708/750 tensors (42 vision tensors identical). It is therefore **not** the parent of the executed policy's reasoner; it is a separately post-trained Cosmos reasoner |
| E3-policy | `nvidia/Cosmos3-Edge-Policy-DROID@a7c7288` (executed) | Reasoner tensors loaded by vLLM are identical to the Edge base; only generation-path tensors (incl. `k_norm_und_for_gen`) differ |
| E3-base | `nvidia/Cosmos3-Edge@ff48d221` (initial-release weights, pre-2026-08-24 update) | Tensor-identical reasoner to E3-policy |
| F3-qwen3vl4b | `black-forest-labs/flux-3-action-base@62878e2` `text_encoder/` | Executed path from the F3 server receipt; files match the HF revision and are byte-identical to `Qwen/Qwen3-VL-4B-Instruct@ebb281e` (tied LM head). Standalone image QA is an auxiliary capability control, not FLUX policy VQA |

Native readout for every lane: vLLM 0.26.0's registered class (`Cosmos3ForConditionalGeneration`,
`Cosmos3EdgeForConditionalGeneration`, `Qwen3VLForConditionalGeneration`) with the checkpoint's own LM head,
tokenizer, processor and chat template; no head is attached or trained. Settings: BF16, greedy (temperature 0), at most
256 new tokens, `enable_thinking=False` passed to every chat template (only the Edge template uses it), eager mode,
FLASH_ATTN backend, no prefix caching, FlashInfer sampler disabled (no CUDA toolkit for JIT), one isolated request at a
time, seed 6106.

Adapter `rqa-adapter-1` (packaging only; no reasoner weight changes):
1. vLLM's Cosmos3-Edge weight mapper drops other generation-tower tensors but not
   `layers.N.self_attn.k_norm_und_for_gen.weight`, so both released Edge checkpoints fail to load. The patch drops that
   generation-path key norm like the other generation-only tensors.
2. The Edge policy `config.json` declares the unified omni class; a view directory symlinks every policy file and
   rewrites only `architectures`/`model_type` in a copy of the policy's own config (all reasoner fields are identical
   to the Edge reasoner config).

Lanes that are tensor- and processor-identical are evaluated once after a six-fixture output-parity check, and the
other member references that result; shared results are not independent evidence.

## 6. Compute

The user authorized as many GPUs as needed. Five single-B200 pods owned by user `ali` (`211247-alirqa-b200-*`) plus
one CPU pod (`211247-alirqa-cpu`) were created in namespace `211247-prod`; a first pod spec inherited
`NVIDIA_VISIBLE_DEVICES=all` from an existing template and exposed other users' GPUs, so it was deleted before any
work and recreated with device-plugin isolation (one visible GPU). No other user's pod or GPU was used.

## Amendment A1 — qualification (2026-10-06 22:13 UTC, after the six development fixtures, before any bank query)

- All six lanes loaded through the native vLLM classes (with `rqa-adapter-1` for both Edge checkpoints). 36/36 fixture
  calls were delivered; 35/36 were format-valid. The invalid one (Edge, B fixture) used natural-language object names
  instead of the vocabulary identifiers — a preserved model failure; the prompt and parser were not changed.
- The parity rule in `qualify.py` now compares processor JSON after dropping writer metadata (`transformers_version`
  and the redundant nested `processor_class` copies, which are the only processor-config differences between the Edge
  base and policy) and additionally requires byte-identical rendered prompts and token counts on all six fixtures. The
  first grouping pass had split the Edge pair only because of those metadata keys. No payload, wrapper, label, parser
  or decoding setting changed.
- Identity groups (identical loaded parameters, processor, rendered prompts and fixture outputs):
  `N3-policy ≡ N3-upstream-qwen3vl8b`, `E3-policy ≡ E3-base`, `F3-qwen3vl4b`, `N3-base`. The bank runs once per group
  on the executed-policy member where one exists (`N3-policy`, `E3-policy`); `N3-upstream-qwen3vl8b` and `E3-base`
  reference those results and are not independent evidence.
- Bank inference therefore uses four B200 GPUs (one per distinct readout); the fifth pod was deleted unused.

## Post-run note (2026-10-06, after analysis)

- Run `r1-20261006` completed: 8,288/8,288 evaluation calls delivered, no infrastructure faults, no stop rule
  triggered. Results and the populated report are under `reports/robolab-vqa-20261006/`.
- `PACKET_MANIFEST.json` hashes for `REPORT.md`, `RUN_INDEX.json` and `CANDIDATE_FINDINGS.csv` describe their
  initialized versions (commit `60bf9eb`); those files were populated as the packet instructs. The locked design files
  (`EXPERIMENT_GUIDE.md`, `protocol.json`, `question_catalog.json`, `frame_selection.json`) are unchanged.
- Descriptive additions made after reading results (labelled exploratory in the report): the B error taxonomy, the
  constant-“no” baseline drawn in Fig. 1, and the image-dependence observation for the N3 policy reasoner. No parser,
  label, exclusion or scoring rule was changed after inference.
