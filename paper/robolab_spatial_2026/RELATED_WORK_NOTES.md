# Sources and paper structure

Verified 27 September 2026. These are writing notes, not manuscript text. The bibliography has eight research entries and three official model-card entries; cite only those needed by the final four-page paper. A compact main-paper set can omit VIMA, SIMPLER and SC3-Eval while keeping the directly evaluated models and closest language-robustness work. Do not enlarge the reference list with unverified model-paper titles.

## Closest work and the claim it permits

| Work and publication status | What was verified | Consequence for our paper |
|---|---|---|
| [SIMPLER](https://proceedings.mlr.press/v270/li25c.html), CoRL 2024; PMLR publication year **2025** | Paired real/simulation evaluation, control and visual alignment, and policy sensitivity beyond aggregate rankings. [Author PDF](https://jiajunwu.com/papers/simpler_corl.pdf), abstract and Figures 1–2. | Motivation for controlled simulator evaluation; it does not establish real-world transfer for our RoboLab findings. Its claim-first abstract and figures that directly instantiate the question are useful structure examples. |
| [VIMA](https://proceedings.mlr.press/v202/jiang23b.html), ICML 2023 | Multimodal task specification, a procedurally generated benchmark, and four distinct generalization levels. [Published PDF](https://proceedings.mlr.press/v202/jiang23b/jiang23b.pdf), Sections 2–3 and Figures 1–2. | Establish that task specification is an established research problem. Follow its concrete prompt examples and explicit evaluation definitions. The published title is **VIMA: Robot Manipulation with Multimodal Prompts**, without “General.” |
| [LIBERO-Plus](https://openaccess.thecvf.com/content/CVPR2026/html/Fei_LIBERO-Plus_A_Progressive_Robustness_Benchmark_for_Visual-Language-Action_Models_CVPR_2026_paper.html), CVPR 2026 | Controlled robustness perturbations across seven dimensions, explicitly including language instructions; fine-grained failure analysis. Publisher metadata and abstract verified; PDF opening was unreliable, so no detailed section claim is made here. | Language robustness and fine-grained failure analysis are not new. Our narrow intervention is exchanging the relational reference while preserving the requested placement. Use the final publisher title, not the different arXiv title. |
| [Bring the Apple, Not the Sofa](https://aclanthology.org/2026.eacl-srw.63/), EACL 2026 **Student Research Workshop** | Human paraphrases and irrelevant context harm VLA performance. [PDF](https://aclanthology.org/2026.eacl-srw.63.pdf), abstract and first-page result figure. | Explicit prior paraphrase-sensitivity evidence. Do not describe it as an EACL main-track paper. Its concrete instruction perturbations and first-page empirical summary offer a useful presentation model. |
| [LIBERO-Para](https://arxiv.org/abs/2603.28301), arXiv v2 states **accepted EMNLP 2026 main** | [PDF](https://arxiv.org/pdf/2603.28301), Sections 1–3: meaning-preserving action/object variations, fixed initial conditions, and planning-versus-execution failure analysis. Final proceedings metadata not verified. | Especially close prior work. Do **not** claim the first paired paraphrase study or first attempt to distinguish instruction interpretation from execution. Our contribution must be relational reference inversion in released WAMs, with a bounded analysis of their own predicted videos. |
| [RoboLab](https://www.roboticsproceedings.org/rss22/p096.html), RSS 2026 | Published proceedings metadata and benchmark purpose. The [official project](https://research.nvidia.com/labs/srl/projects/robolab/) already shows a same-scene/same-goal language-specificity example. | Cite the environment and reuse of stock tasks. Do not claim native task design, broad simulator novelty, or first wording experiment in RoboLab. Proceedings and latest arXiv describe different benchmark versions; avoid unnecessary task-count claims. |
| [SG-WAM](https://arxiv.org/abs/2608.08839), preprint | Text-grounded/spatial semantic guidance for WAMs; predicts semantic foresight to improve instruction following. [PDF](https://arxiv.org/pdf/2608.08839) and abstract verified. | Semantic misalignment in generated WAM futures is established motivation, not our discovery. Do not confuse it with the unrelated “Self-Guided World Modeling” SG-WAM at arXiv:2608.01397. |
| [SC3-Eval](https://arxiv.org/abs/2606.18610), preprint | Action-conditioned generated rollouts for evaluation; consistency constraints and fine-grained comparison of failure modes. | Distinguish a separately trained rollout evaluator from our analysis of each policy's own contemporaneous forecast. If space is short and forecast analysis is secondary, this is an optional citation. |

## A defensible positioning paragraph

Task specification and instruction robustness are established problems in robot learning. Prior work evaluates broad language perturbations and meaning-preserving paraphrases, including failures in task identification. This study isolates relational reference inversion: expressing a placement by describing the stationary reference relative to the moved object. It tests the same goal from paired starts across three released world-action policies in stock RoboLab scenes, then asks whether the accompanying short-horizon forecasts provide an additional diagnostic signal. The latter analysis is limited by automated annotation reliability.

This is a scope statement, not a claim that no prior paper has ever tested a converse spatial relation. The present search does not establish priority for that specific transformation.

## Presentation learned from the published examples

- Start the abstract with the concrete scientific issue, state the controlled comparison, give the main measured result, and finish with the limited implication. Avoid a bullet-list abstract or a project-status report.
- Put one scene and the actual equivalent instructions near the beginning, as VIMA makes the prompting interface tangible. Both instructions must explicitly move the same object.
- State the experimental question before the matrix. Distinguish physical goals, wording forms, episodes, and independent state clusters in one compact table or caption.
- Like SIMPLER, let the primary figure show evidence for the central question. Here that should be the paired S–I effect and uncertainty, not a generic pipeline drawing.
- Organize results around questions: Does reference inversion change success? Does the effect persist under the final-state endpoint? What can the generated forecast tell us? Preserve “prespecified” versus “post-hoc sensitivity” distinctions.
- Put the forecast annotation limitation beside its result. A null from unreliable automated labels is not evidence that WAM predictions contain no goal information.
- For four pages including references, use a short related-work paragraph in the introduction, one protocol figure/prompt table, one main result figure/table, and a compact limitations paragraph. Avoid dedicated architecture, dataset, or benchmark sections that imply a contribution we did not make.

## Official style and workshop scope

The [official CoRL 2026 author instructions](https://2026.corl.org/contributions/instruction-for-authors) link the [LaTeX template ZIP](https://drive.google.com/file/d/1R9irIW0ImqeDHh5g8Ukm2XGy91sWxOsQ/view?usp=drive_link). The named package is `corl_2026`; the page requests `final` mode for camera-ready papers. No official GitHub template repository was verified. The main-conference page limit is not the workshop limit.

The [target workshop](https://do-robots-need-world-models.github.io/) requests papers up to four pages in the CoRL template and invites head-to-head comparisons and negative or surprising results. Keep the entire draft, including references, within four pages as a conservative working constraint; the public workshop text does not clearly state whether references are excluded. We are contributing evidence about instruction-grounded behavior and evaluation, not answering whether world models are necessary for robot control.

## Bibliography details

`references.bib` preserves primary-source author lists, publisher titles, and publication status. For SIMPLER the official PMLR author ordering was used (Mees before Pertsch), even though the author's PDF displays the two core contributors in the reverse order. The arXiv entries for SG-WAM and SC3-Eval intentionally do not invent peer-reviewed venues. LIBERO-Para records the acceptance note while retaining the arXiv bibliographic record until proceedings metadata can be verified.

## Evaluated model attribution

The three official model-card names match `docs/robolab-workshop-20260926/MODEL_CONFIGS.json`. Each exact checkpoint revision below also resolved through Hugging Face's `/api/models/<repo>/revision/<sha>` endpoint on 27 September 2026, returning the identical SHA and official organization author. These are model-card/checkpoint citations, not invented conference papers.

| Study ID | Official name and citation key | Checkpoint revision | Source repository / recorded commit |
|---|---|---|---|
| N3 | [Cosmos3-Nano-Policy-DROID](https://huggingface.co/nvidia/Cosmos3-Nano-Policy-DROID), `nvidia2026nano` | `6706d7680581c255ff61e0f3bb49d90eac55c79e` | [NVIDIA/cosmos-framework](https://github.com/NVIDIA/cosmos-framework), `411d25b2e35bc441126f48c44a4b93e1c0564274` |
| E3 | [Cosmos3-Edge-Policy-DROID](https://huggingface.co/nvidia/Cosmos3-Edge-Policy-DROID), `nvidia2026edge` | `a7c7288f9b6ac1684e993007b0f9703dd26e58ef` | [NVIDIA/cosmos-framework](https://github.com/NVIDIA/cosmos-framework), `cf5d68c00d97ccd2480a2320ed652b92dec63102` |
| F3 | [FLUX 3 Action DROID](https://huggingface.co/black-forest-labs/flux-3-action-droid), `bfl2026fluxaction` | `3d0887bdc7acee1686b19afac267125d519ff4f1` | [black-forest-labs/flux-action](https://github.com/black-forest-labs/flux-action), `e2dd1d8dbc5977b54315d61f7548c63c043d6d4f` |

The official current cards identify Nano as 16B parameters, Edge as 4B, and FLUX 3 Action as 7B. Therefore Nano-versus-Edge must not be described as increasing size in that order, and none of these comparisons is a controlled scaling study. Parameter counts are optional in a short paper; names and checkpoint identities are essential.

N3/E3 release receipts explicitly retain the same checkpoint revision and source commit as the plan. F3's release receipt retains the expected source commit and checkpoint path ending `flux-3-action-droid-3d0887b`, but its `revision` field is null. Thus the full F3 weight pin is verified as the declared/public checkpoint; the compact release receipt alone does not independently prove the full weight identity. Do not conflate that distinction with a different model being used.

F3's shared encoder source is `black-forest-labs/flux-3-action-base` at `62878e2925e59b7a89ec14463ce89932624c490d`, as declared in MODEL_CONFIGS. The root DROID package is the BF16 four-step model, not its optional distilled or FP8 variants. The official card documents 32 absolute joint-action commands at 15 Hz and joint action/video denoising; our video export instrumentation remains study code and should be described as such.

## Requested violin-plot presentation

The user supplied [TRI LBM-1](https://toyotaresearchinstitute.github.io/lbm1/files/TRI-LBM-1.pdf) as a visual reference. Figure 2 on PDF page 5 and the statistical discussion on pages 10–11 were inspected. TRI uses Beta-posterior violins for binary success. Our figure instead shows observed paired-state effects, with all 32 physical starts and the unchanged cluster-bootstrap mean intervals. This preserves pairing and does not introduce a posterior interpretation or replace the original inferential analysis. The heatmap retains the goal-by-wording breakdown.

## Model-selection rationale (September 27, 2026)

The [official RoboLab leaderboard](https://research.nvidia.com/labs/srl/projects/robolab/leaderboard.html), Overall table checked today, lists FLUX 3 Action at rank 1 (515/1200, 42.9%), Cosmos3 Nano at rank 5 (441/1200, 36.8%), and Cosmos3 Edge at rank 11 (275/1200, 22.9%). Thus the manuscript motivates Nano and FLUX through strong benchmark performance and describes Edge separately as a smaller Cosmos-family comparison, not a top-ranked model. The leaderboard lists Nano at 16B and Edge at 4B, consistent with the official model cards. These are external benchmark results and are not pooled with our spatial study.
