# RoboLab VQA V2 — final bounded follow-up

**RQA-20261006 · design v2.0 · October 6, 2026 · SPECIFICATION ONLY, NOT RUN**

Read [FINAL_EXECUTION_SPEC.md](FINAL_EXECUTION_SPEC.md). The [protocol](protocol.json) fixes scope and query ceilings. This is the final planned diagnostic pass for the four-page workshop paper, not a promise that every diagnostic will produce an interpretable result.

It addresses Edge's answer-format failures, review of visual answerability, and the nearly constant answers in the combined test. A matched image/header control also resolves a confound in the earlier Nano interpretation. Keep all three original policy families in the paper; use only the three relevant distinct components in this follow-up. The separately post-trained Nano base comparison remains in V1.

## Dispatch text

GPU cluster task: implement and execute the final RQA V2 handoff in `adeeb10abbas/world-action-model-steerability`, branch `codex/nano-stock-workstation-20260926`. Read `AGENTS.md`, then `docs/robolab-vqa-20261006/v2-final/FINAL_EXECUTION_SPEC.md` and its `protocol.json`. Use the existing cluster, saved R1 observations, and verified N3-policy, E3-policy, and F3-qwen3vl4b checkpoints. Preserve V1 unchanged. Implement the constrained-output B2 test, matched image/header controls, one fixed C2 question with counterbalanced answer codes, and the answerability audit exactly as specified. Freeze and push the new manifests, parsers, and settings before evaluation. Run at most 6,552 unique evaluation queries plus 18 qualification calls; do not tune prompts against evaluation answers or add a V3. An agent review must be labeled machine review; if human review is unavailable, finish with explicit provisional visual claims and a single prepared human-review packet. Save all outcomes, including failures and nulls, in a separate V2 report and update the report index. Commit and push code, manifests, compact results, and reports; verify the remote commit. Do not train, launch robot episodes, add benchmarks/models, or edit the manuscript/Overleaf. Stop after this fixed pass and return a paper-ready evidence summary, actual execution command, and completion receipt.

This text is an instruction to an execution agent, not a shell command. V2 has not yet been implemented or run. The execution agent must implement and verify the required interface rather than assuming V1's runner already supports it.
