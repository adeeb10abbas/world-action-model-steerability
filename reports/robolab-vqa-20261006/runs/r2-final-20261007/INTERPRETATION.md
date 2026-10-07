# RQA V2 interpretation — run `r2-final-20261007`

**Status:** complete (6,552/6,552 evaluation queries delivered and valid). Visual answerability was reviewed by blinded
**machine** agents only, for 36 of the 72 view sets; no human reviewed any sheet. Every visual conclusion below is
therefore provisional. Numbers come from [TABLES.md](TABLES.md) and use the original R1 mask unless stated. Nothing
here has been inserted into a manuscript.

**The robot result stays central.** The existing policy result is the wording effect: TF − RF stable-ever success of
+14.6 pp (N3), +8.1 pp (E3) and +13.8 pp (F3) ([wording_contrasts.csv](../../../../paper/robolab_spatial_2026/analysis/wording_contrasts.csv)).
V2 asks a narrower question: do the released reasoner/encoder components behind those policies show compatible errors
when queried in a QA interface? The answers below describe QA behavior of unchanged component weights. They do not
reveal what the policies compute when acting, and they do not show that a QA error caused an action failure.

## 1. Was Edge previously blocked mainly by answer format, or does instruction difficulty remain under the assisted readout?

**Both. Once the format barrier is removed by construction, substantial instruction difficulty remains.**

**R1 format failures.** In R1, 375 of Edge's 414 B responses on S1/S3/S4 (90.6%) failed strict parsing; strict image
tuple accuracy was 2.4%.

| R1 failure class | Count |
|---|---:|
| JSON structure: single-item arrays | 217 |
| JSON structure: malformed | 6 |
| Object vocabulary | 64 |
| Object and relation vocabulary | 87 |
| Multiple answers | 1 |
| Truncation | 0 |

**V2 constrained readout.** With schema-constrained decoding every answer is format-valid, yet:

- Text only, Edge recovers 18 of 30 instructions (DIR 6, TF 8, RF 4 of 10).
- With image + header input it recovers 34.0% [31.7, 36.5] of items (TF 48.3%, RF 23.3%).
- It names the right objects (target and reference: 30/30 in T and 29/30 in H; 91–94% with images); the
  **relation** is what fails.
- Adding the camera images makes it worse:

  | Image contrast | Change, pp [95% CI] |
  |---|---:|
  | I − T | −26.9 [−28.9, −24.8] |
  | IH − H | −30.8 [−33.1, −28.4] |

**What not to infer from the R1 → V2 change.** The rise from 2.4% to 34.0% is a decoding-protocol comparison, not a
model change. It combines the format guarantee with any effect constrained decoding has on content, such as the fixed
target → reference → relation key order. A descriptive alias audit of the R1 failures found that 195 of 360
alias-mappable failures (original and placement families) matched the gold tuple. Among original-family failures the
matches were DIR 41/74, TF 54/76 and RF 17/76, so R1's format failures concealed a similar TF > RF pattern. This is not
a parser repair, it does not change R1's strict scores, and it does not show that every format failure was
semantically correct.

## 2. Do reference-first errors remain with matched headers, and what do the pixel/header contrasts support?

**Yes.** In every readout, RF accuracy stays below TF within each matched condition, but the source differs.

**N3-policy (executed Nano reasoner = Qwen3-VL-8B-Instruct).**

- Text-only it is perfect: 30/30 in both T and H.
- Reference-first errors appear only when the camera images are added. All of them are converse relations.

  | Condition | RF accuracy [95% CI] | TF accuracy |
  |---|---:|---:|
  | I (images) | 93.1% [87.5, 98.6] | 100% |
  | IH (images + header) | 89.9% [85.4, 94.8] | 100% |

- Pixel contrasts, with header presence matched within each pair:

  | Pixel contrast | RF change, pp [95% CI] |
  |---|---:|
  | IH − H | −10.1 [−14.6, −5.2] |
  | I − T | −6.9 [−12.5, −1.4] |

- Header text alone changed nothing (H − T: 0 discordant of 30). With images present, adding the header text gave
  IH − I RF = −3.1 pp [−8.0, +1.7], an interval that includes zero. The lateral/front-behind subset gave −5.2
  [−10.4, −1.0]. A header-by-image interaction is therefore unresolved, not shown.
- The image-conditioned errors depend on the start state and are concentrated in two of the ten RF instructions:
  - S3 "R": wrong in 4–5 of 8 starts.
  - S1 "B": wrong in 3 of 8 starts, with headers only.
- **What this supports:** in this QA interface, adding the policy's camera views is associated with
  reference-first converse errors, and the camera-orientation sentences alone are not. This resolves the R1
  confound, where images and header text were always presented together. It does not support a broad,
  wording-independent effect.

**F3-qwen3vl4b (FLUX frozen shared encoder = Qwen3-VL-4B-Instruct; text-only B2 is the relevant language path).**

- The RF errors are already present without images:

  | Text-only condition | RF correct | Converse errors | TF correct |
  |---|---:|---:|---:|
  | T | 4/10 | 6 | 10/10 |
  | H | 3/10 | 7 | 10/10 |

  This is a language-path misreading of reference-first phrasing. Every discordant TF/RF pair was TF-correct and
  RF-wrong.
- The image results are auxiliary. They leave the pattern unchanged: RF is 41.7% in both I and IH, identical across
  starts; I − T RF = 0.0.

**E3-policy.** RF is the lowest form in every condition (T 4/10; IH 23.3%). Edge also errs on DIR and TF, including
target/reference swaps under RF wording, so its RF errors are part of general relation difficulty.

**Scope of the contrasts.** They test what happens when image content is added within this QA interface. They do not
reveal the policy's internal action computation.

**Placement-only control.** It moves the reference clause without converse words.

| Readout | Text-only (T) | Image + header (IH) |
|---|---:|---:|
| N3 | 16/16 | 100% |
| F3 | 16/16 | 100% |
| E3 | 13/16 | 50.5%; reference-early minus reference-late −17.7 pp [−25.0, −10.4] |

This construction differs from the RF instructions, so it does not prove that all noun-order effects are absent.

## 3. Does C2 distinguish both truth classes and changing frames, or remain uninformative?

**It remains uninformative.** V1's prespecified primary diagnostic C was uninformative: it gave a constant "no",
balanced accuracy 50.0–50.7%. That result stands unchanged. C2 fixed the answer codes and wording, yet with images every
readout still judged nearly every arrangement as "does not match":

| Readout | Initial: balanced acc. [95% CI] | Initial: matches recognized | Secondary: balanced acc. [95% CI] | Secondary: matches recognized |
|---|---:|---:|---:|---:|
| N3 | 49.4% [48.9, 49.8] | 0.0% | 49.8% [49.4, 50.0] | 0.0% |
| E3 | 48.5% [48.0, 49.0] | 0.0% | 50.1% [47.1, 53.1] | 5.2% |
| F3 | 50.0% | 0.0% | 50.0% | 0.0% |

"Matches recognized" is recall on items whose simulator label is a match.

- **Order check.** The bias is semantic, not positional. When the A/B meanings were exchanged, the letter flipped and
  the meaning held: 96–100% of items received the same semantic answer in both orders.
- **TF − RF gaps.** They are 0.0 pp or within ±1.3 pp. These are floor effects, not evidence of wording robustness.
- **Truth-changing pairs.** 11 pairs were available, each a match and a nonmatch frame from the same start and goal.
  Both frames were classified correctly in 0 of 11 pairs (N3, F3) and in at most 1 of 11 (E3).
- **No-image control.** The evidentially correct answer is U. N3 answered U 48 of 60 times, E3 25 of 60, and F3 never:
  it answered "does not match" 60 of 60 times, a language prior. With images, **no readout ever answered U** (0 of
  4,320 image-conditioned C2 answers).

As the protocol requires, the result is retained and the pass stops. No prompt changes were made after seeing answers,
and there is no V3.

## 4. Which visual conclusions have human support, and which remain provisional?

**None has human support.** No human reviewed the packet.

**What the machine review found.**

- **Coverage:** a blinded machine review covered 36 of 72 view sets (120 of 240 frame–goal items); 12 sheets were
  reviewed twice.
- **Answerability:** every reviewed initial-frame item (39/39) was judged answerable. Only 27 of 81 reviewed
  secondary-frame items were, because of gripper contact or transit, occlusion, boundary and other ambiguity.
- **Geometry:** no item judged answerable contradicted the simulator geometry.

**How reliable that review is.**

- Seven of the twelve launched reviewer agents failed on model-API errors without producing forms.
- Two reviewers never saw the images and judged from programmatic pixel analysis.
- One form was excluded from the primary mask because its agent used Qwen3-VL-8B, the evaluated N3 weights, to locate
  objects. Including it does not change the masks.
- So this is weak, partial, provisional support. On it:
  - initial-state relations appear answerable from the supplied views;
  - many secondary frames do not.

- **Provisional:** everything whose meaning depends on whether a view shows the relation. That covers C2 (both banks,
  truth-changing pairs) and the A rescore.
  - The C2 null does not depend on the mask. On the machine-reviewed subset (117 initial and 69 secondary items),
    balanced accuracy is 48.3–50.0% in every lane, and 0 of 2 remaining truth-changing pairs are classified
    correctly.
  - The N3 converse-question gap in A persists on the reviewed initial subset: −8.9 pp [−11.1, −3.7] over 39 pairs,
    versus −11.6 pp originally.
- **Not provisional on answerability:** B2 tuples are defined by the instruction text, so B2 scoring does not depend on
  answerability (protocol §4). B2 still measures QA behavior, not visual ground truth.
- **Path to human review:** a complete human-review packet and a CPU-only rescore command are delivered. They can
  replace the machine mask without new inference ([REPORT §7](REPORT.md#7-answerability-review-machine-and-a-rescore)).

## 5. What can go into a four-page paper, and what remains an unresolved measurement limitation?

**Candidates (author decision pending; see [CANDIDATE_FINDINGS.csv](../../CANDIDATE_FINDINGS.csv)).**

1. **Component identity (V1, verified by hashes).** The executed Nano and Edge policy reasoners are the unadapted
   public/base checkpoints, and FLUX's shared encoder is Qwen3-VL-4B-Instruct. The policies' language-conditioned
   differences therefore cannot come from changed reasoner weights.
2. **Instruction readout under constrained decoding (one compact table row per family).**
   - N3 reads all 30 instructions correctly from text but makes start-dependent reference-first converse errors once
     camera views are attached: IH − H RF −10.1 pp.
   - FLUX's shared encoder misreads 6 of 10 reference-first instructions from text alone, always as the converse
     relation.
   - Edge remains weak even with enforced format (34.0% with images).
   - Every component-level asymmetry has the same direction as the policies' TF > RF wording effect. It is not
     evidence that QA errors cause action failures.
3. **A null measurement, reported as such.** Neither the V1 combined question nor the V2 current-state question
   could measure whether the readouts judge current arrangements: answers were constant "no" / "does not match".

**Unresolved limitations.**

- No human answerability audit, and only partial (36 of 72 sheets) machine review.
- The QA interface does not observe the policy's internal use of language.
- Text-only B2 is 10 deterministic instructions per form.
- Image intervals condition on three fixed scenes and wording templates, and some are degenerate because answers
  are constant across starts.
- The N3 image effect is concentrated in two instructions.
- The header × image interaction is unresolved.
- Current-state judgment is unmeasured (floor).
- Constrained decoding is an assisted readout, and R1-vs-V2 differences are protocol comparisons.
- S5 stacking/support ambiguity remains a separate V1 result.

## Paper-ready paragraph (candidate wording; numbers from this run)

> To test whether the reasoner components themselves misread reference-first instructions, we queried the executed
> Nano reasoner (identical to Qwen3-VL-8B-Instruct), the Edge reasoner, and FLUX's shared Qwen3-VL-4B encoder with a
> schema-constrained readout of each instruction's target, reference and relation. From text alone, the Nano reasoner
> recovered all 30 instructions. FLUX's encoder recovered every target-first instruction but only 4 of 10
> reference-first ones, answering with the converse relation. Edge recovered 18 of 30. When the policy's camera views
> were attached, the Nano reasoner made reference-first converse errors that depended on the start state (RF tuple
> accuracy 89.9% [85.4, 94.8] vs. 100% target-first; −10.1 pp [−14.6, −5.2] relative to the same text without images).
> Camera-orientation text alone had no detectable effect. These component-level asymmetries share the direction of the
> policies' target-first advantage, but they are measured in a question-answering interface and do not establish the
> policies' internal computation. A direct current-state question was uninformative: every readout judged nearly every
> arrangement as not matching the instruction (balanced accuracy 48.5–50.1%) under both answer-code orders.
> Visual-answerability labels were only partially machine-reviewed and remain provisional.

## Do not claim

- That robot adaptation degraded the reasoner weights. The executed reasoners are identical to their
  public/base checkpoints.
- That co-training helped.
- That any QA error caused an action failure.
- That C/C2's TF ≈ RF shows wording robustness. It is a constant-answer floor.
- That Edge's R1 format failures were semantically correct.
- That machine review is a human audit.
