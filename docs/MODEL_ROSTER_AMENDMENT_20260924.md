# SGW-01 model roster amendment — 24 September 2026

## Decision and implementation status

Ali requested Cosmos3 Nano, Cosmos3 Edge, and FLUX 3 Action for the workshop study, replacing DreamZero in future runs. This records that decision before collecting outcomes. It authorizes preparation, not model inference or study launch.

The intended roster below supersedes the two-model choice in the earlier scientific plan. **Protocol revision 1.2 and the planned queue now contain N3/E3/F3 and 1,566 cells.** D1 is rejected by active release and runtime entry points. E3/F3 runtime adapters, immutable identities and forecast capture are still pending; this is not a runnable release. The old registry is archived byte-for-byte under `provenance/retired-n3-d1-registry-v1.1/`. Physical scene and camera receipts remain unchanged.

## Three checkpoints, two model families

| Study ID | Checkpoint | Role |
| --- | --- | --- |
| N3 | `nvidia/Cosmos3-Nano-Policy-DROID` | Retain the existing Cosmos Nano reference configuration and checkpoint pin. |
| E3 | `nvidia/Cosmos3-Edge-Policy-DROID` | Add the smaller Cosmos policy through its official RoboLab server. |
| F3 | `black-forest-labs/flux-3-action-droid` | Add the released root BF16 DROID policy through the official FLUX RoboLab server. |

D1 is excluded from the new execution roster. Preserve its source provenance and any historical records; do not relabel its cells, qualifications or observations as another model's results.

This is broad enough for a focused workshop study: repeat the same language contrasts in two model families, with two Cosmos checkpoints. Nano versus Edge is a checkpoint comparison, not a controlled model-size ablation: architecture, training and inference settings may differ. Three checkpoints are not three independent architecture families. RoboLab support establishes compatibility, not that our scenes occurred in training.

## Reuse the complete scene package

Retain all 87 selected layouts, their stage assignments, physical feasibility receipts, 18 exact prompt strings, task definitions, scoring, 450-action cap and registered camera geometry. Each layout has six instructions: two physical goals crossed with direct, syntax-matched and reference-inverted wording. Pass the original instruction text through each model's required input format without rewriting its meaning. Do not redesign scenes or select layouts based on model success.

The pre-amendment source queue was inspected: each existing model had 18 pilot, 72 development and 432 confirmation cells. Applying that same allocation to the new roster gives:

| Stage | Layouts per family | Episodes per model | All three models |
| --- | ---: | ---: | ---: |
| Pilot | 1 | 18 | 54 |
| Development | 4 | 72 | 216 |
| Confirmation | 24 | 432 | 1,296 |
| Total | 29 | 522 | **1,566** |

There are 261 model/layout blocks of six cells. This adds 522 planned episodes, or 50%, to the previous 1,044-cell plan. These are the planned behavioral cells; technical qualification and infrastructure failures must be accounted for separately. Pilot and development results remain separate from confirmation estimates.

## What the paper measures

Keep reference-inverted minus syntax-matched wording as the primary language comparison. Report direct versus syntax-matched wording separately, and measure whether opposite goals produce appropriately different physical outcomes in every wording condition. Estimate these contrasts within each model and relation family using the existing matched-layout rules. Show canonical-task competence alongside wording sensitivity; failure under every instruction does not isolate a language-grounding failure. Preserve valid failures rather than dropping uncooperative models or scenes.

Generated-future versus executed-motion analysis remains part of the intended study, but requires independently qualified output capture for each checkpoint. As inspected on 24 September, FLUX jointly samples video latents and actions, while its released API returns actions only. Its inference documentation says decoded-video export requires changes to the sampling and VAE decoding path. **F3 forecast capture is therefore pending, not supported by the current release.**

Capture any F3 future from the same sampling call that supplied executed actions, with camera and physical-time correspondence. Do not generate a separate attractive video and call it that action's prediction. Verify that enabling capture preserves actions under otherwise identical settings. If valid forecast evidence cannot be produced, report it as unavailable; any Cosmos-only forecast analysis must be labeled as such and the manuscript's cross-model claims narrowed explicitly. Missing forecasts never become zeros or grounds for removing valid behavior episodes.

## Bounded integration handoff

1. **Publish a new protocol and queue revision.** Retain the old frozen release as provenance. Generate N3/E3/F3 cells with unique identities and the same layout/prompt assignments; exclude D1 from execution. Update model validation, compiler, worker routing, release construction and analysis grouping together. The roster migration updated `contract.py`, `compile.py`, `adapters.py`, `runtime.py` and `native_worker_entrypoint.py` under `experiments/workshops/spatial_grounding_v1/`. Counts and active roster references in local status, instructions, cluster documents and manuscript have been updated. Runtime integration remains separate.
2. **Pin each new configuration before qualification.** Record immutable source and checkpoint revisions, dependency/image identities, full inference settings, precision, prompt formatting, camera packing, normalization, seed handling and returned/executed action horizons. E3 must use its own documented defaults; do not assume N3 settings are appropriate. F3 starts from the root BF16 package, not an FP8 or distilled variant. Pin supported control timing without silently changing the fixed physical task budget. Keep model server dependencies separate from the pinned simulator environment.
3. **Qualify the interfaces once.** Reuse the existing physical scenes and current camera binding. Check checkpoint-specific camera order, action units and gripper direction, reset/cache isolation, stopping, recording and restart behavior. New models do not inherit N3 or D1 preprocessing qualifications automatically. Verify effective randomness is matched across the six instructions where supported and disclose limitations. Do not require equal numerical seeds to represent equal random draws across architectures.
4. **Deliver a consistent cluster handoff.** Verify 1,566 unique planned cells, exactly six per model/layout block, all 18 prompt hashes preserved, and no D1 executable partitions. Run focused CPU contract checks for the changed interfaces. Document prediction-capture support and remaining gaps per model. Model inference and the learned-policy study remain unstarted until separately authorized; final study execution belongs on the cluster.

Edge is a plausible local 3090 pilot candidate given its reported memory use, but it has not been tested on that workstation here. FLUX's reported memory varies substantially by configuration; its 7B label does not establish that it fits a 24 GB GPU. Do not introduce quantization or change checkpoints solely to fit hardware without recording a separate configuration.

## Verified upstream references

- [Cosmos3 Edge DROID model and RoboLab quickstart](https://huggingface.co/nvidia/Cosmos3-Edge-Policy-DROID).
- [Shared Cosmos DROID server documentation](https://github.com/NVIDIA/cosmos-framework/blob/main/docs/action_policy_droid_server.md).
- [FLUX DROID checkpoint and optimization variants](https://huggingface.co/black-forest-labs/flux-3-action-droid).
- [FLUX setup and RoboLab serving](https://github.com/black-forest-labs/flux-action/blob/main/docs/setup.md#serve-to-robolab).
- [FLUX inference documentation, including the predicted-video limitation](https://docs.bfl.ai/flux_3/flux3_action_inference#predicted-video).
- [RoboLab leaderboard](https://research.nvidia.com/labs/srl/projects/robolab/leaderboard.html); reported benchmark scores and memory are not results on our custom scenes.
