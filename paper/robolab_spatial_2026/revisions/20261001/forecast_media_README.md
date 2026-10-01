# Forecast media: prediction versus execution for two preselected examples

This adds the appendix imagery for the forecast analysis in `revision_esmaeil.tex` (`app:forecasts`).

- **Content.** For two preselected examples it shows what the world–action model generated next to what the robot then did. Both rows show the same exterior camera, the same request and the same action chunk.
- **Inputs.** Only existing recordings are used. There are no new episodes, policy inference or VLM calls.
- **Unchanged.** `main.tex`, `revision_esmaeil.tex`, outcomes, labels and the existing revision notes are not modified.

## Outputs

**Figures.** Each is 7.2 in wide. The PDF embeds source pixels unresampled; the PNG is a 250 dpi preview.

- `paper/robolab_spatial_2026/revision_assets/rev_forecast_example_edge.{pdf,png}`: Cosmos3 Edge, prediction above execution.
- `paper/robolab_spatial_2026/revision_assets/rev_forecast_example_flux.{pdf,png}`: FLUX 3 Action, prediction above execution.
- `paper/robolab_spatial_2026/revision_assets/rev_forecast_packet_edge.{pdf,png}`: the original packet `legend.png` and `contact_sheet.png`, prediction only.
- `paper/robolab_spatial_2026/revision_assets/rev_forecast_packet_flux.{pdf,png}`: the same for FLUX 3 Action.

**Provenance and text** (all in `paper/robolab_spatial_2026/revisions/20261001/`):

| File | Contents |
|---|---|
| `forecast_media_provenance.json` | Source paths and hashes, request identity, camera and frame mappings, labels, every check, the commands, and the figure hashes. This file is authoritative. |
| `forecast_media_captions.md` | Proposed LaTeX captions and an optional body sentence. |
| `forecast_media/verification.json` | The raw output of the cluster verification run. |
| `forecast_media/{E3,F3}/` | Displayed windows and the original packet files: `packet.json`, `legend.png`, `contact_sheet.png`. |

**Code** (same directory):

- `extract_forecast_examples.py`: runs on the cluster. It verifies the sources and exports the frames.
- `build_forecast_example_figures.py`: runs locally. It re-hashes every input, draws the figures, self-checks the panels and writes the provenance file.

## Examples

Both examples were fixed in `forecast_packet_retrieval_manifest.json` before any media were viewed, by the rule "lexicographically first primary-window episode for model". They are kept as found.

| | Cosmos3 Edge (E3) | FLUX 3 Action (F3) |
|---|---|---|
| Episode | RWS-E3-S1-C01-B-D | RWS-F3-S1-C01-B-D |
| Annotation packet | Aef9bebaab690 | A5ee6df16bd49 |
| Attempt | `…/RWS-E3-S1-C01-B-D.20260927T045417.211247-alia40a-a40-2gpu.700205` | `…/RWS-F3-S1-C01-B-D.20260927T041238.211247-alia40d-a40-2gpu.554678` |
| Request | index 1, input at tick 32, seed 6100 | index 1, input at tick 32, seed 6100 |
| Executed chunk | 32 actions at ticks 32–63; t = 2.133–4.267 s | 32 actions at ticks 32–63; t = 2.133–4.267 s |
| Server call | `dev/servers/E3-alia100e-3-8607/server_calls.jsonl` line 347 (served index 346) | `dev/servers/F3-alia100g-3-cap1-8603/server_calls.jsonl` line 227 (served index 226) |
| Future | `futures/r01.npz`, 33×528×640×3 | `futures/r01.npz`, 33×544×640×3 |
| Camera shown | `over_shoulder_left_camera`: composite rows 360–539, cols 0–319 | same |
| Window shown | cell rows 57–146, cols 103–262 (160×90) | same |

- **Common setup.** The instruction is "Put the rubiks cube behind the bowl". The legend numbers are 1 banana, 2 bowl (reference) and 3 Rubik's cube (mover).
- **Paths.** Attempt directories are under `/data/users/ali/rws-20260926/runs/episodes/<episode>/attempts/`, and the server logs are under `/data/users/ali/rws-20260926/`.

## What was verified

There are 165 hard checks, all passing: 32 on sources, 66 per example and 1 on the pair. Eleven informational checks also pass. Every check is listed in `verification.json` and summarized per example in the provenance file.

**Request and chunk.** These link the packet, the request and the execution:

- The packet key row names the episode, request 1 and the hash of the future file.
- `requests.jsonl` request 1 records pre_tick 32, 32 executed actions, seed 6100 and a decoded future.
- The server calls log records the same input hash, returned-action hash, seed and future file.
- The executed commands for ticks 32–63 equal the first 32 returned actions.
- The executed frame at tick 32 equals the request-1 input, and the frame at tick 64 equals the request-2 input. Both are exact pixel matches.
- `forecast.mkv` and `contact_sheet.png` were re-derived from the same future array.

**Camera.** These show that both rows display the same camera:

- The request composite was rebuilt from the raw camera renders: the wrist view sits above [left | right], and swapping the exterior cells does not reproduce it.
- Generated frame 0 matches the input in the same cell:
  - left-cell PSNR is 31.0 dB (E3) and 25.8 dB (F3), against about 8 dB for swapped cells;
  - the best spatial shift is (0, 0).

**Time.** The model and export source fixes the mapping: a 33-frame window, 32 actions plus 1, with frame 0 as the conditioning frame. For FLUX, `cfg.fps = 15` and action k produces frame k+1. The worker's recorded `future_frame_times` agree, but they were not used as evidence. File and line citations are in `model_source_citations`.

| k | Generated frame | Executed frame (tick) | t (s) | Actions executed |
|---|---|---|---|---|
| 0 | 0 (decoded input) | 32 | 2.133 | 0 |
| 8 | 8 | 40 | 2.667 | 8 |
| 16 | 16 | 48 | 3.200 | 16 |
| 24 | 24 | 56 | 3.733 | 24 |
| 32 | 32 | 64 | 4.267 | 32 |

**Display.**

- The PDF embeds every image at source resolution.
- In the PNG, each predicted and executed window is an exact 2× pixel replication. Every build checks this against `np.kron` of the source, excluding a 4-pixel inset and the k = 0 tag text.
- Negative tests show the check catches:
  - a 1-pixel content roll;
  - a 1-pixel position shift;
  - swapped prediction and execution panels.
- Builds are byte-for-byte deterministic.

## Unresolved alignment issues

1. **Pace.** It is not established that the generated content proceeds at the nominal 15 Hz pace.
   - A supporting diagnostic finds, for each generated frame k, the executed offset (0–32) with the lowest mean squared error in the same camera cell.
   - In the left camera this best offset rises with k and then plateaus. For k = 20–32 the values are:

     | Model | Left camera | Wrist camera |
     |---|---|---|
     | E3 | 14–15 | 14–32 |
     | F3 | 15–19 | 11–29 |

   - A plateau fits a forecast that slows down relative to the execution. It equally fits later content that matches no executed frame well.
   - The diagnostic is inconclusive and is not a timing measurement.
2. **Frame 0.** Generated frame 0 is a decoded reconstruction of the input, not the input itself.
3. **FLUX decoder.** FLUX 3 Action uses a non-causal video decoder, so every decoded frame, including frame 0, depends on the predicted latents.
4. **Executed frames.** They show the simulator after the controller tracked the commanded actions. They are not a pixel target the forecast was trained to reproduce.
5. **E3 decoded rows.** Cosmos3 Edge decodes 528 of the 540 composite rows (exterior rows 0–167 of 180). The displayed window, rows 57–146, is inside them.
6. **Scope.** Only these two packets were verified. For all other packets the paper's statement that the correspondence documentation "remains to be attached" still holds.

## Observations (not alignment issues)

- **Legend markup.** `legend.png` writes each number above and to the right of its circle and draws the arrows over the numbers.
  - Left view: the arrows cover 1 and 3, and the bowl's 2 sits nearer the banana than the bowl.
  - Right view: the cube's 3 falls on the banana's circle.
  - The two legends are byte-identical, because both episodes start from the same restored state.
- **Misnumbered free text.** Two of six VLM free-text observations misnumber objects:
  - E3 labeler A writes "1: red bowl, 2: banana";
  - the F3 adjudicator calls the cube "object 1".

  The structured fields are unaffected: every `moving_object` is 3.
- **Disputed fields.**
  - E3 `visible_final_relation`: A none, B on_top_of, adjudicated none.
  - F3 `relation_object`: A none, B 3 (the cube itself), adjudicated none.
- **E3 packet layout.** The E3 packet stretches the 168 decoded exterior rows to 184. This affects the contact sheet and `forecast.mkv`, not the montages, which are cut from the future array.

## Cluster-only media

These files are not in Git.

**Under `/data/users/ali/rws-20260926/`:**

- `runs/episodes/<episode>/attempts/<attempt>/exec_composite.mkv`: the execution recording, decoded frame i at tick i. E3 is 137 MB, F3 is 145 MB.
- `runs/episodes/<episode>/attempts/<attempt>/futures/r01.npz`: the generated future.
- `runs/episodes/<episode>/attempts/<attempt>/requests.jsonl`, plus `requests/r01_input.npz` and `requests/r02_input.npz`: the request records.
- `annotation/packets/{Aef9bebaab690,A5ee6df16bd49}/forecast.mkv`: the packet video the labelers sampled.
- `annotation/_key/key.jsonl` and `annotation/labels_vlm_{a,b,adjudicated}{,_raw}.jsonl`: the packet key and the labels.

**Under `/data/users/ali/rws-20260926/revision_media/forecast_examples_20261001/{E3,F3}/`:**

- `sync_exterior_pred_exec.mkv`: generated frame k beside executed tick 32 + k for the left exterior cell. It is 640×180, 33 frames, 15 fps, lossless (`libx264rgb`, qp 0).
- `sync_composite_pred_exec.mkv`: the same for the full composite, 1280×540.
- `full/`: full composites at the selected k, and the raw camera render at tick 64.

All paths, sizes and hashes are in `forecast_media_provenance.json` under `sources` and `cluster_only_media`.

## Reproduce

Run from the repository root, at the commit that adds these files. The generated `commands` block in `forecast_media_provenance.json` is authoritative.

```bash
# Stage the code on the pod.
git archive --format=tar HEAD experiments/__init__.py experiments/robolab_workshop paper/robolab_spatial_2026/revisions/20261001/extract_forecast_examples.py paper/robolab_spatial_2026/revisions/20261001/forecast_packet_retrieval_manifest.json | kubectl exec -i -n 211247-prod 211247-aliv100-v100-1gpu -- sh -c 'rm -rf /tmp/fm_run && mkdir -p /tmp/fm_run/repo && tar -C /tmp/fm_run/repo -xf -'

# Re-verify into a scratch directory and compare every compact file with the recorded output.
kubectl exec -n 211247-prod 211247-aliv100-v100-1gpu -- sh -c 'cd /tmp/fm_run/repo && /data/users/ali/vla_wam/envs/robolab-v2-isaac50/bin/python paper/robolab_spatial_2026/revisions/20261001/extract_forecast_examples.py --out /tmp/fm_run/reverify && cd /tmp/fm_run/reverify && sha256sum E3/*.png E3/packet/* F3/*.png F3/packet/* | (cd /data/users/ali/rws-20260926/revision_media/forecast_examples_20261001 && sha256sum -c --quiet -) && echo COMPACT_FILES_IDENTICAL'

# The recorded run, which overwrites the cluster output directory:
# kubectl exec -n 211247-prod 211247-aliv100-v100-1gpu -- sh -c 'cd /tmp/fm_run/repo && /data/users/ali/vla_wam/envs/robolab-v2-isaac50/bin/python paper/robolab_spatial_2026/revisions/20261001/extract_forecast_examples.py --out /data/users/ali/rws-20260926/revision_media/forecast_examples_20261001 --sync-videos'

# Copy the compact subset into the repository.
kubectl exec -n 211247-prod 211247-aliv100-v100-1gpu -- sh -c 'cd /data/users/ali/rws-20260926/revision_media/forecast_examples_20261001 && tar -cf - verification.json E3/*.png E3/packet F3/*.png F3/packet' | tar -C paper/robolab_spatial_2026/revisions/20261001/forecast_media -xf -

# Build the figures and provenance (Python 3.13, numpy 2.2.6, matplotlib 3.10.9, Pillow 11.3.0).
python paper/robolab_spatial_2026/revisions/20261001/build_forecast_example_figures.py

# Clean up the pod.
kubectl exec -n 211247-prod 211247-aliv100-v100-1gpu -- rm -rf /tmp/fm_run
```

The cluster run used Python 3.11.13, numpy 1.26.0 and ffmpeg 7.0.2 from the `robolab-v2-isaac50` environment. The builder stops if any input hash differs from `verification.json`, or if any exact-panel self-check fails.

## Relation to `forecast_evidence_notes.md`

`forecast_evidence_notes.md` is not edited.

- **Graphic 3.** This work provides the notes' recommended graphic 3: a same-request prediction and execution montage. It has the initial scene, timestamps and the original independent VLM labels.
  - The examples were selected by an explicit rule.
  - Both include a labeler disagreement.
  - The montages show only the exterior camera. The generated wrist view appears in the packet contact sheets and in the cluster-only `sync_composite_pred_exec.mkv`.
- **Superseded bullet.** It supersedes the bullet "No verified forecast-only montage frames are present locally", for these two examples only.
