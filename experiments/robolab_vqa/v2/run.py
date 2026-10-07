"""Run one V2 lane (cluster GPU) with schema/choice-constrained native decoding.

python -m experiments.robolab_vqa.v2.run --release <r2>/release.json --checkpoint <lane> --output <run-dir> \
    --phase qualify|eval --adapter-commit <sha>

Budget rules (protocol.json): qualification = the 6 fixtures once (never repeated); evaluation = each frozen query
attempted once in the frozen order (primary, then secondary); afterwards at most one retry per infrastructure-missing
query, drawing from 30 retry slots shared by all lanes (atomic mkdir on the shared PVC); 3 consecutive infrastructure
failures stop the lane. Every call to the engine's generate is a counted attempt in <lane>/attempts.jsonl.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from pathlib import Path

from .. import adapters as A
from .. import common as C
from . import config as V
from .scoring import parse_b2, parse_c2


def grammar_receipt(constraint: dict) -> dict:
    import xgrammar as xgr
    from vllm.v1.structured_output.utils import choice_as_grammar

    if constraint["type"] == "json_schema":
        g = xgr.Grammar.from_json_schema(constraint["schema_json"], any_whitespace=False)
    else:
        g = xgr.Grammar.from_ebnf(choice_as_grammar(constraint["choices"]))
    text = str(g)
    return {"grammar_sha256": C.sha256_text(text), "grammar_text": text, "xgrammar_version": getattr(xgr, "__version__", None)}


class ReadoutV2(A.Readout):
    """V1 native readout plus engine-level structured outputs; weights, processor and template unchanged."""

    def __init__(self, lane: str, gpu_memory_utilization: float = 0.85) -> None:
        for key, value in A.ENGINE_ENV.items():
            os.environ[key] = value
        from vllm import LLM

        self.lane = lane
        self.spec = A.LANES[lane]
        kwargs = dict(A.ENGINE)
        kwargs["gpu_memory_utilization"] = gpu_memory_utilization
        kwargs["structured_outputs_config"] = dict(V.ENGINE_STRUCTURED)
        self.loader_patches = A.apply_loader_patches(lane)
        self.model_path = A.materialize_view(lane)
        self.view = A.view_receipt(lane)
        t = time.time()
        self.llm = LLM(model=self.model_path, **kwargs)
        self.load_s = time.time() - t
        self.engine_kwargs = kwargs
        tok = self.llm.get_tokenizer()
        template = getattr(tok, "chat_template", None)
        self.tokenizer_template_sha256 = C.sha256_text(template) if isinstance(template, str) else None
        self._images = {}
        self.compiled: dict[str, dict] = {}

    def compile_check(self, constraints: dict[str, dict]) -> dict:
        """CPU-only: compile every distinct constraint against this tokenizer (no generation)."""
        import xgrammar as xgr

        tok = self.llm.get_tokenizer()
        vocab_size = self.llm.llm_engine.model_config.get_vocab_size()
        info = xgr.TokenizerInfo.from_huggingface(tok, vocab_size=vocab_size)
        compiler = xgr.GrammarCompiler(info, max_threads=8)
        out = {}
        for sha, c in constraints.items():
            rec = grammar_receipt(c)
            if c["type"] == "json_schema":
                compiler.compile_json_schema(c["schema_json"], any_whitespace=False)
            else:
                from vllm.v1.structured_output.utils import choice_as_grammar
                compiler.compile_grammar(choice_as_grammar(c["choices"]))
            out[sha] = {"grammar_sha256": rec["grammar_sha256"], "xgrammar_version": rec["xgrammar_version"],
                        "compiled_with_tokenizer": True, "vocab_size": vocab_size,
                        "stop_token_ids": list(getattr(info, "stop_token_ids", []) or [])}
            self.compiled[sha] = out[sha]
        return out

    def sampling(self, constraint: dict):
        from vllm import SamplingParams
        from vllm.sampling_params import StructuredOutputsParams

        if constraint["type"] == "json_schema":
            so = StructuredOutputsParams(json=constraint["schema_json"])
        elif constraint["type"] == "choice":
            so = StructuredOutputsParams(choice=list(constraint["choices"]))
        else:
            raise ValueError(constraint["type"])
        sp = SamplingParams(temperature=0.0, max_tokens=V.MAX_NEW_TOKENS, seed=C.ORDER_SEED, n=1, structured_outputs=so)
        return sp, so

    def generate_constrained(self, payload: dict, root: Path, image_meta: dict) -> dict:
        msgs = self.messages(payload, root, image_meta)
        sp, so = self.sampling(payload["output_constraint"])
        t = time.time()
        outs = self.llm.chat(msgs, sampling_params=sp, use_tqdm=False, chat_template_kwargs=A.CHAT_TEMPLATE_KWARGS)
        latency = time.time() - t
        out = outs[0]
        comp = out.outputs[0]
        tok = self.llm.get_tokenizer()
        return {"raw_response": comp.text, "raw_response_with_special_tokens": tok.decode(list(comp.token_ids), skip_special_tokens=False),
                "finish_reason": comp.finish_reason, "output_token_ids": list(comp.token_ids),
                "prompt_tokens": len(out.prompt_token_ids or []), "output_tokens": len(comp.token_ids),
                "rendered_prompt": out.prompt, "rendered_prompt_sha256": C.sha256_text(out.prompt or ""), "latency_s": latency,
                "structured_backend": getattr(so, "_backend", None) or getattr(sp.structured_outputs, "_backend", None)}


def parse_payload(payload: dict, text: str | None) -> dict:
    c = payload["output_constraint"]
    if payload["kind"] == "B2":
        return parse_b2(text, V.schema_of(c)["properties"]["target"]["enum"])
    return parse_c2(text, V.C2_ORDERS[payload["option_order"]])


def claim_retry_slot(run_dir: Path, lane: str, query_id: str) -> str | None:
    slots = run_dir / "_retry_slots"
    slots.mkdir(parents=True, exist_ok=True)
    for n in range(V.MAX_RETRIES_TOTAL):
        p = slots / f"slot-{n:02d}"
        try:
            os.mkdir(p)
        except FileExistsError:
            continue
        (p / "owner.json").write_text(json.dumps({"lane": lane, "query_id": query_id, "t": C.utc_now()}))
        return p.name
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--release", type=Path, required=True)
    ap.add_argument("--checkpoint", required=True, choices=list(V.LANES))
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--phase", required=True, choices=["qualify", "eval"])
    ap.add_argument("--adapter-commit", required=True)
    ap.add_argument("--gpu-memory-utilization", type=float, default=0.85)
    args = ap.parse_args()
    rel_dir = args.release.parent
    release = C.load_json(args.release)
    image_root = Path(release["image_root"])
    images = C.load_json(image_root / "images.json")
    lane = args.checkpoint
    V.assert_not_r1_path(args.output)
    lane_dir = args.output / lane
    lane_dir.mkdir(parents=True, exist_ok=True)
    attempts_path = lane_dir / "attempts.jsonl"
    prior_attempts = C.read_jsonl(attempts_path)
    if args.phase == "qualify":
        # A qualification call counts as made once it produced a response record (delivered or infrastructure error).
        # Ledger entries without a response record are aborted-before-generation entries (Amendment V2-A1).
        if C.read_jsonl(lane_dir / "qualification_responses.jsonl"):
            raise SystemExit("qualification already attempted for this lane; repeats are not permitted")
        payloads = C.read_jsonl(rel_dir / "dev_fixtures.jsonl")
        out_path = lane_dir / "qualification_responses.jsonl"
    else:
        rows = C.read_jsonl(rel_dir / "payloads.jsonl")
        primary = sorted([r for r in rows if r["bank"] != "secondary"], key=lambda r: r["order_key"])
        secondary = sorted([r for r in rows if r["bank"] == "secondary"], key=lambda r: r["order_key"])
        payloads = primary + secondary
        if len(payloads) != V.MAX_EVAL_PER_LANE:
            raise SystemExit(f"{len(payloads)} payloads != {V.MAX_EVAL_PER_LANE}")
        out_path = lane_dir / "responses.jsonl"
    manifest = A.lane_manifest(lane, None)
    manifest.update({"v2_engine_structured_outputs": V.ENGINE_STRUCTURED, "v2_decoding": {
        "temperature": 0.0, "max_tokens": V.MAX_NEW_TOKENS, "seed": C.ORDER_SEED, "n": 1,
        "chat_template_kwargs": A.CHAT_TEMPLATE_KWARGS}, "v2_implementation": V.V2_IMPLEMENTATION_VERSION,
        "v2_parser": V.V2_PARSER_VERSION, "expected_loaded_parameter_digest": V.R1_LOADED_DIGESTS[lane]})
    manifest["checkpoint_manifest_sha256"] = C.canonical_sha256({k: v for k, v in manifest.items() if k != "checkpoint_manifest_sha256"})
    C.write_json_atomic(lane_dir / "checkpoint_manifest_v2.json", manifest)
    t0 = time.time()
    receipt = {"lane": lane, "phase": args.phase, "release_content_sha256": release["release_content_sha256"],
               "release_json_sha256": C.sha256_file(args.release), "adapter_commit": args.adapter_commit,
               "started_utc": C.utc_now(), "command": sys.argv, "checkpoint_manifest_sha256": manifest["checkpoint_manifest_sha256"]}
    rpath = lane_dir / f"run_receipt_{args.phase}_{int(t0)}.json"
    try:
        readout = ReadoutV2(lane, args.gpu_memory_utilization)
        receipt.update({"load_s": readout.load_s, "engine_kwargs": readout.engine_kwargs, "loader_patches": readout.loader_patches,
                        "reasoner_view": readout.view, "model_path_loaded": readout.model_path,
                        "tokenizer_chat_template_sha256": readout.tokenizer_template_sha256,
                        "environment": A.environment_receipt()})
        digest = readout.loaded_parameter_digest()
        receipt["loaded_parameter_digest"] = digest
        if digest.get("sha256") != V.R1_LOADED_DIGESTS[lane]:
            raise RuntimeError(f"loaded parameter digest {digest.get('sha256')} != R1 {V.R1_LOADED_DIGESTS[lane]}")
        constraints = {p["output_constraint_sha256"]: p["output_constraint"] for p in payloads}
        receipt["grammars"] = readout.compile_check(constraints)
    except Exception as error:  # noqa: BLE001
        receipt.update({"status": "load_or_preflight_failed", "error": f"{type(error).__name__}: {error}",
                        "traceback": traceback.format_exc()[-6000:], "ended_utc": C.utc_now(), "generation_attempts": 0})
        C.write_json_atomic(rpath, receipt)
        print(json.dumps({k: receipt[k] for k in ("lane", "phase", "status", "error")}, indent=1))
        sys.exit(2)
    processor_id = f"{manifest['repo']}@{manifest['revision']}" + (f"/{manifest['subfolder']}" if manifest.get("subfolder") else "")
    existing = C.read_jsonl(out_path)
    delivered = {r["query_id"] for r in existing if r["status"] == "delivered"}
    attempts_by_q: dict[str, int] = {}
    for a in prior_attempts:
        attempts_by_q[a["query_id"]] = attempts_by_q.get(a["query_id"], 0) + 1
    consecutive, done, stopped = 0, 0, None

    def attempt(payload: dict, phase: str, retry_slot: str | None = None) -> str:
        nonlocal consecutive, done
        qid = payload["query_id"]
        n_prev = attempts_by_q.get(qid, 0)
        aid = f"{lane}.{qid}.a{n_prev + 1}"
        rec = {"query_id": qid, "kind": payload["kind"], "bank": payload.get("bank"), "condition": payload.get("condition"),
               "option_order": payload.get("option_order"),
               "option_mapping": V.C2_ORDERS[payload["option_order"]] if payload["kind"] == "C2" else None,
               "checkpoint_id": lane, "checkpoint_manifest_sha256": manifest["checkpoint_manifest_sha256"],
               "adapter_commit": args.adapter_commit, "processor_id_and_revision": processor_id,
               "effective_decoding": {**manifest["v2_decoding"], "greedy": True, "structured_outputs": V.ENGINE_STRUCTURED},
               "attempt_id": aid, "phase": phase, "retry_slot": retry_slot,
               "output_constraint_sha256": payload["output_constraint_sha256"],
               "grammar_sha256": readout.compiled[payload["output_constraint_sha256"]]["grammar_sha256"],
               "input_payload_sha256": A.payload_sha256(payload, images),
               "release_content_sha256": release["release_content_sha256"]}
        # Amendment V2-A1: the ledger entry is written only after the record is built, immediately before the engine call.
        attempts_by_q[qid] = n_prev + 1
        C.append_jsonl(attempts_path, {"attempt_id": aid, "query_id": qid, "phase": phase, "retry_slot": retry_slot,
                                       "t_start_utc": C.utc_now()})
        try:
            gen = readout.generate_constrained(payload, image_root, images)
            parsed = parse_payload(payload, gen["raw_response"])
            rec.update({"status": "delivered", "raw_response": gen["raw_response"],
                        "raw_response_with_special_tokens": gen["raw_response_with_special_tokens"],
                        "finish_reason": gen["finish_reason"], "truncated": gen["finish_reason"] == "length",
                        "parsed_response": parsed, "prompt_tokens": gen["prompt_tokens"], "output_tokens": gen["output_tokens"],
                        "output_token_ids": gen["output_token_ids"], "rendered_prompt_sha256": gen["rendered_prompt_sha256"],
                        "structured_backend": gen["structured_backend"], "latency_s": gen["latency_s"],
                        "timestamp_utc": C.utc_now(), "error": None})
            C.append_jsonl(lane_dir / ("rendered_prompts_qualification.jsonl" if phase == "qualification" else "rendered_prompts.jsonl"),
                           {"query_id": qid, "attempt_id": aid, "sha256": gen["rendered_prompt_sha256"], "text": gen["rendered_prompt"]})
            consecutive = 0
        except Exception as error:  # noqa: BLE001
            rec.update({"status": "infrastructure_error", "raw_response": None, "parsed_response": None, "prompt_tokens": None,
                        "output_tokens": None, "latency_s": None, "timestamp_utc": C.utc_now(),
                        "error": f"{type(error).__name__}: {error}", "traceback": traceback.format_exc()[-4000:]})
            consecutive += 1
        C.append_jsonl(out_path, rec)
        done += 1
        return rec["status"]

    if args.phase == "qualify":
        for p in payloads[: V.MAX_QUAL_PER_LANE]:
            attempt(p, "qualification")
    else:
        for p in payloads:
            if p["query_id"] in delivered or attempts_by_q.get(p["query_id"], 0) > 0:
                continue
            attempt(p, "evaluation")
            if consecutive >= V.MAX_CONSECUTIVE_INFRA:
                stopped = "repeated_infrastructure_fault"
                break
        if stopped is None:
            final = {}
            for r in C.read_jsonl(out_path):
                if r["status"] == "delivered" or r["query_id"] not in final:
                    final[r["query_id"]] = r
            for p in payloads:
                r = final.get(p["query_id"])
                if r is None or r["status"] == "delivered" or attempts_by_q.get(p["query_id"], 0) > V.MAX_RETRIES_PER_QUERY:
                    continue
                slot = claim_retry_slot(args.output, lane, p["query_id"])
                if slot is None:
                    receipt["retry_budget_exhausted"] = True
                    break
                attempt(p, "retry", slot)
                if consecutive >= V.MAX_CONSECUTIVE_INFRA:
                    stopped = "repeated_infrastructure_fault"
                    break
    rows = C.read_jsonl(out_path)
    final = {}
    for r in rows:
        if r["status"] == "delivered" or r["query_id"] not in final:
            final[r["query_id"]] = r
    att = C.read_jsonl(attempts_path)
    receipt.update({"ended_utc": C.utc_now(), "elapsed_s": time.time() - t0, "attempts_this_run": done, "stopped": stopped,
                    "status": "complete" if stopped is None else stopped,
                    "delivered_total": sum(1 for r in final.values() if r["status"] == "delivered"),
                    "valid_total": sum(1 for r in final.values() if r["status"] == "delivered" and (r.get("parsed_response") or {}).get("valid")),
                    "infrastructure_missing_total": sum(1 for r in final.values() if r["status"] != "delivered"),
                    "truncated_total": sum(1 for r in final.values() if r.get("truncated")),
                    "lane_attempts_total": len(att), "lane_attempts_by_phase": {ph: sum(1 for a in att if a["phase"] == ph)
                                                                                for ph in ("qualification", "evaluation", "retry")},
                    "latency_s_sum": sum(r.get("latency_s") or 0 for r in rows if r.get("status") == "delivered"),
                    "structured_backends": sorted({str(r.get("structured_backend")) for r in rows if r.get("status") == "delivered"})})
    C.write_json_atomic(rpath, receipt)
    print(json.dumps({k: receipt.get(k) for k in ("lane", "phase", "status", "attempts_this_run", "delivered_total", "valid_total",
                                                 "infrastructure_missing_total", "truncated_total", "elapsed_s", "load_s",
                                                 "lane_attempts_by_phase", "structured_backends")}, indent=1))


if __name__ == "__main__":
    main()
