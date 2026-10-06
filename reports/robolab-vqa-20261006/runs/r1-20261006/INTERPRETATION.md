# RQA-20261006 run r1-20261006 — interpretation

**Status: provisional.** No human answerability review was performed. All estimates are descriptive except the
pre-specified primary endpoint (C TF − RF, initial bank, S1/S3/S4), and that endpoint turned out to be uninformative
(see below). Numbers come from [`TABLES.md`](TABLES.md) and [`results/results.json`](results/results.json).

Four distinct reasoner weight sets were evaluated (six planned lanes; two pairs are tensor-identical):

| Readout | Relation to the robot policies |
|---|---|
| R1 Qwen3-VL-8B-Instruct | **Is** the executed N3 (Cosmos3-Nano-Policy-DROID) reasoner: all 750 reasoner tensors are byte-identical to the upstream release |
| R2 Cosmos3-Nano base reasoner | Separately post-trained reasoner (708/750 tensors differ from R1); **not** the executed policy's reasoner |
| R3 Cosmos3-Edge reasoner | **Is** the executed E3 policy's reasoner and the Edge base reasoner (identical loaded parameters) |
| R4 Qwen3-VL-4B-Instruct | Byte-identical to FLUX 3 Action's frozen shared text encoder; standalone image QA is an auxiliary capability control, not FLUX policy VQA |

## What the evidence supports

1. **The language/vision readouts of the executed N3 and E3 policies are unadapted components.** The N3 policy's
   reasoner equals the public Qwen3-VL-8B-Instruct release, and the E3 policy's reasoner equals its released base. Per
   the guide's interpretation table (§12), for these frozen/tensor-identical readouts there is no evidence that the
   readout weights lost ability during robot adaptation; any wording-dependent action differences must be investigated
   in how the action pathway conditions on these components (or elsewhere), not attributed to degraded readout weights.
2. **The readouts recover the requested target and reference, and the relation for TF/DIR wordings, but often return
   the converse relation for RF wordings.** With the initial images, the Qwen3-VL-lineage readouts were 100% correct on
   TF tuples in S1/S3/S4 (DIR: 100% for R1 and R2; 77.8% for R4, whose DIR errors were all the out-of-vocabulary
   relation `on_top_of`) but only 61.1% (R1), 53.5% (R2) and 36.1% (R4) correct on RF. On lateral and
   front/behind RF items the errors were almost always the converse relation, i.e. the relation word as written in the
   reference-first clause. In the finite text-only set every discordant TF/RF pair was TF-correct/RF-wrong (R2 4,
   R3 8, R4 9 pairs; R1 none). The direction matches the policies' TF > RF action gap (+14.6 pp N3, +8.1 pp E3,
   +13.8 pp F3, stable-ever).
3. **Moving the reference clause alone did not cause errors.** The clause-placement control (same relation words,
   reference early vs late) produced no B errors for R1, R2 and R4 (8/8 pairs text-only; image early − late 0.0 pp).
   The RF difficulty is therefore associated with the converse relational formulation, not merely with where the
   reference noun appears. (The control has no action outcomes.)
4. **Robot-frame scene-relation judgments (A) were weak.** Accuracy was 51.1% (R1, strongly yes-biased; balanced
   61.6%), 50.5% (R2) and 52.7% (R4), near chance despite the calibration-derived camera legend; R3 was better (71.4%,
   balanced 68.4%). Subject-order (converse question) differences existed but had inconsistent signs across readouts.

## What is inconclusive

- **Primary endpoint.** C TF − RF on initial S1/S3/S4 was 0.0 pp (R1, R4), +1.0 pp [+0.0, +3.1] (R3) and −9.0 pp
  [−16.3, −1.7] (R2). R1, R3 and R4 answered “no” to essentially every C query (240/240 R1; recall of initially
  satisfied arrangements 0–1.4% of 66), exactly as they did with no image (36/36 “no” for R1 and R4), so C accuracy
  equals the constant-“no” label prior (69.4%) and balanced accuracy is 50.0–50.7%. The degenerate interval reflects
  constant answers, not robustness to wording. The C test therefore could not measure whether instruction-plus-scene
  judgments are wording-sensitive. R2's negative gap arises because it answered “yes” to some DIR and TF queries
  (16 of its 24 TF “yes” answers were wrong) but never to RF queries; its balanced accuracy is near chance
  (53.1% [49.3, 56.8]).
- **Saved-rollout bank.** The same constant-“no” pattern held on the 64 saved rollout frames (balanced accuracy
  50.0–55.1%; TF − RF ≤ +2.4 pp). These frames use the lower-resolution policy-input composite.
- **R3 instruction interpretation.** 264/288 image-B and 16/36 text-B answers were invalid (natural-language object
  names, JSON arrays). Strict scoring cannot separate misinterpretation from vocabulary non-compliance for R3.
- **S5.** Initial S5 frames contain only “no” labels, so balanced accuracy is undefined; readouts split on whether
  “stack on” and “underneath and supporting” map to `stacked_on` or `on_top_supported`, which the design treats as a
  semantic distinction rather than a reference-language failure.

## What cannot be inferred

- That the policies' action-level wording gap is caused by the readout's RF interpretation errors: verbal readouts are
  not access to the policy's latent decision, and the action pathway conditions on hidden states, not on generated text.
- Any training-caused degradation or co-training benefit: the executed readouts are unadapted, R2 differs from R1 by
  Cosmos reasoning post-training rather than robot adaptation, and cross-family comparisons are confounded.
- Generalization beyond four fixed scene types, 32 starts and the fixed prompt templates. Start-bootstrap intervals for
  B are degenerate or narrow because answers barely vary across starts; the effective sample for wording effects is
  the 10 S1/S3/S4 instruction pairs.
- Publication-ready answerability: labels come from saved simulator geometry with an automated visibility pre-check
  only.

## Proposed short paragraph for a four-page paper (not inserted into any manuscript)

> To ask whether the wording effect is already present in the policies' language components, we queried their native
> text readouts on the saved initial observations (inference only). The executed Nano and Edge policies' reasoner
> weights are identical to Qwen3-VL-8B-Instruct and to the Cosmos3-Edge base reasoner, respectively, so these readouts
> reflect unadapted components. Asked to name the target, reference and requested relation, the Qwen3-VL-lineage
> readouts were always correct on TF wordings but frequently returned the converse relation for RF wordings once images
> were shown (RF 36–61% vs TF 100%), whereas moving the reference clause without converse relation words caused no
> errors. Asked whether a scene already showed the requested arrangement, the readouts almost always answered “no”, with
> or without images, so this pre-specified check could not detect a TF–RF difference. These provisional, descriptive
> results suggest that converse relational phrasing is difficult for the language components themselves; they do not
> show that this difficulty causes the policies' action-level gap.
