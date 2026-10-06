# Repository scope

## Inference-only RoboLab VQA diagnostic

The final follow-up handoff is **RQA-20261006 V2**, at `docs/robolab-vqa-20261006/v2-final/README.md` and `FINAL_EXECUTION_SPEC.md` in that directory. It supersedes V1 execution instructions only for the bounded follow-up. Preserve the completed `r1-20261006` evidence. V2 is a post-V1 diagnostic repair with three existing readouts, no new training or robot runs, and a finite stop rule. Publishing the handoff does not dispatch cluster work.

The original VQA handoff is **RQA-20261006 V1**, in `docs/robolab-vqa-20261006/`. Read its `README.md` and `EXPERIMENT_GUIDE.md` for source definitions, then follow the V2 specification for the final follow-up. V1 used the executed RWS subset (S1/S3/S4/S5, 32 physical starts, 12 goals, 36 DIR/TF/RF instructions), three QA tests, and a fixed saved-rollout image bank. No training, new robot episodes, new simulator renders, or automatic manuscript edits are in scope. Do not inherit the older five-scene launch counts below.

Keep the complete diagnostic report separate at `reports/robolab-vqa-20261006/REPORT.md`, with versioned run reports, compact machine-readable results, all null/negative outcomes and coverage, and a candidate-findings ledger for later author selection. Save implementation, small provenance/results artifacts, and reports to the existing GitHub branch when the user dispatches this handoff; keep raw media, arrays, weights, environments, and secrets outside Git. Never fabricate completed experiments. Preparing or publishing the handoff does not launch its GPU work.

## New native RoboLab workshop study

The user's current experiment-specification handoff is **RWS-20260926**, under `docs/robolab-workshop-20260926/`. Read `CLUSTER_EXECUTION_SPEC.md` and `IMPLEMENTATION_PLAN.md` for that task. It uses five native assets, 42 prompts and up to 1,008 confirmation cells across N3/E3/F3, separate from SGW-01 below. Its planned rows are not yet bound to physical states or qualified runtimes. Writing the handoff does not launch experiments; execution agents require the user's dispatch. Do not apply SGW's 18-prompt freeze, 87-layout registry or custom camera overrides to RWS. Preserve historical SGW records and workers.

## Historical SGW-01 scope

This is the private SGW-01 world-action-model steerability repository. **The 87-layout physical scene package is complete; model/runtime qualification and the learned-policy study remain unstarted.**

- Read the root README and REPOSITORY_STATUS.json for current scope. Copied historical receipts and authorizations do not grant permission to launch new work.
- Use the completed scene registry and existing qualification evidence; do not restart scene design or repeat completed scripted trials. **Do not launch learned policies or the 1,566-cell study without new explicit user direction.** Future learned-policy execution belongs on the cluster.
- The active roster is N3/E3/F3; D1 is retired. Edge and FLUX runtime integration remains pending. Preserve the frozen 18 prompts, 1,566 revised planned cells, scoring thresholds, and matched comparison rules. Disclose new scene/appearance revisions prospectively; never rewrite recorded outcomes or hashes to make a check pass.
- Use the registered `close-oblique-v3-full-objects-20260924` exterior cameras and unchanged wrist camera. Read `docs/CAMERA_ALIGNMENT.md`. Original physical-test images show superseded exterior views; keep their geometry evidence but rematerialize the current camera binding at destination paths.
- Keep physical scene qualification, synthetic engineering tests, and learned-policy outcomes distinct. Preserve valid failures and partial attempts. Missing or unmapped future evidence is unavailable, never a scored zero.
- Use the pinned external runtime and asset identities. Keep weights, raw arrays/videos, credentials, and third-party environments outside Git.
- Run the small CPU validation appropriate to a change. Native/GPU work requires the user's applicable authorization; no repeated probes, automatic retries, or unrelated checks.
- Preserve others' edits. Do not recreate old V2/V3 archives or require the old repository's unrelated continuation files.
