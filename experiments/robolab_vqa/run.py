"""Run one readout lane over the frozen RQA-20261006 release (cluster GPU).

python -m experiments.robolab_vqa.run --release <release-dir>/release.json --checkpoint <lane> --output <results-dir> \
    --phase dev|primary|secondary|all [--adapter-commit <sha>] [--eligibility <audit.json>]

Each query is one fresh single-turn conversation; requests are issued one at a time in the frozen order
(primary bank first, then secondary; within a bank by sha256('6106|'+query_id)). Responses are appended
atomically to <output>/<lane>/responses.jsonl. Resume skips delivered queries and retries only
infrastructure-missing ones under a new attempt id. Three consecutive infrastructure faults stop the lane.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import traceback
from pathlib import Path

from . import common as C
from . import parse as PARSE
from .adapters import CHAT_TEMPLATE_KWARGS, DECODING, LANES, Readout, environment_receipt, lane_manifest, payload_sha256

MAX_CONSECUTIVE_INFRA = 3
VOCAB_LINE = re.compile(r"^Object vocabulary: (.+)$", re.MULTILINE)


def parse_payload_response(payload: dict, text: str | None) -> dict:
    if payload["test"] in ("A", "C"):
        return PARSE.parse_yes_no(text)
    body = "".join(s.get("text", "") for s in payload["segments"])
    objects = [o.strip() for o in VOCAB_LINE.search(body).group(1).split(",")]
    return PARSE.parse_b(text, objects, list(C.RELATION_VOCABULARY))


def phase_payloads(release_dir: Path, phase: str) -> list[dict]:
    if phase == "dev":
        return C.read_jsonl(release_dir / "dev_fixtures.jsonl")
    rows = C.read_jsonl(release_dir / "payloads.jsonl")
    primary = sorted([r for r in rows if r["bank"] in ("initial", "no_image")], key=lambda r: r["order_key"])
    secondary = sorted([r for r in rows if r["bank"] == "secondary"], key=lambda r: r["order_key"])
    return {"primary": primary, "secondary": secondary, "all": primary + secondary}[phase]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--release", type=Path, required=True)
    ap.add_argument("--checkpoint", required=True, choices=sorted(LANES))
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--phase", default="all", choices=["dev", "primary", "secondary", "all"])
    ap.add_argument("--adapter-commit", default="uncommitted")
    ap.add_argument("--eligibility", type=Path, default=None)
    ap.add_argument("--gpu-memory-utilization", type=float, default=0.85)
    ap.add_argument("--limit", type=int, default=0, help="debug only: stop after N new requests")
    args = ap.parse_args()
    release_dir = args.release.parent
    release = C.load_json(args.release)
    images = C.load_json(release_dir / "images.json")
    lane_dir = args.output / args.checkpoint
    lane_dir.mkdir(parents=True, exist_ok=True)
    audit = C.load_json(args.eligibility) if args.eligibility and args.eligibility.exists() else None
    manifest = lane_manifest(args.checkpoint, audit)
    C.write_json_atomic(lane_dir / "checkpoint_manifest.json", manifest)
    out_name = "dev_fixture_responses.jsonl" if args.phase == "dev" else "responses.jsonl"
    out_path = lane_dir / out_name
    existing = C.read_jsonl(out_path)
    delivered = {r["query_id"] for r in existing if r["status"] == "delivered"}
    attempts: dict[str, int] = {}
    for r in existing:
        attempts[r["query_id"]] = attempts.get(r["query_id"], 0) + 1
    todo = [p for p in phase_payloads(release_dir, args.phase) if p["query_id"] not in delivered]
    receipt = {"lane": args.checkpoint, "phase": args.phase, "release_content_sha256": release["release_content_sha256"],
               "release_json_sha256": C.sha256_file(args.release), "adapter_commit": args.adapter_commit,
               "checkpoint_manifest_sha256": manifest["checkpoint_manifest_sha256"], "started_utc": C.utc_now(),
               "already_delivered": len(delivered), "to_run": len(todo), "command": sys.argv}
    t0 = time.time()
    try:
        readout = Readout(args.checkpoint, args.gpu_memory_utilization)
    except Exception as error:  # noqa: BLE001
        receipt.update({"status": "load_failed", "error": f"{type(error).__name__}: {error}",
                        "traceback": traceback.format_exc()[-6000:], "ended_utc": C.utc_now()})
        C.write_json_atomic(lane_dir / f"run_receipt_{args.phase}_{int(t0)}.json", receipt)
        print(json.dumps({k: receipt[k] for k in ("lane", "status", "error")}, indent=1))
        sys.exit(2)
    receipt["environment"] = environment_receipt()
    receipt["engine_kwargs"] = readout.engine_kwargs
    receipt["load_s"] = readout.load_s
    receipt["loader_patches"] = readout.loader_patches
    receipt["reasoner_view"] = readout.view
    receipt["model_path_loaded"] = readout.model_path
    receipt["tokenizer_chat_template_sha256"] = readout.tokenizer_template_sha256
    try:
        receipt["loaded_parameter_digest"] = readout.loaded_parameter_digest()
        receipt["loaded_value_digest"] = readout.name_insensitive_value_digest()
    except Exception as error:  # noqa: BLE001
        receipt["loaded_parameter_digest"] = {"error": f"{type(error).__name__}: {error}"}
    processor_id = f"{manifest['repo']}@{manifest['revision']}" + (f"/{manifest['subfolder']}" if manifest.get("subfolder") else "")
    consecutive = 0
    done = 0
    stopped = None
    for payload in todo:
        qid = payload["query_id"]
        attempts[qid] = attempts.get(qid, 0) + 1
        rec = {"query_id": qid, "test": payload["test"], "bank": payload["bank"], "checkpoint_id": args.checkpoint,
               "checkpoint_manifest_sha256": manifest["checkpoint_manifest_sha256"], "adapter_commit": args.adapter_commit,
               "processor_id_and_revision": processor_id, "effective_decoding": {**DECODING, "chat_template_kwargs": CHAT_TEMPLATE_KWARGS,
                                                                                  "greedy": True},
               "attempt_id": f"{args.checkpoint}.{qid}.a{attempts[qid]}", "input_payload_sha256": payload_sha256(payload, images),
               "release_content_sha256": release["release_content_sha256"]}
        try:
            gen = readout.generate(payload, release_dir, images)
            parsed = parse_payload_response(payload, gen["raw_response"])
            rec.update({"status": "delivered", "raw_response": gen["raw_response"],
                        "raw_response_with_special_tokens": gen["raw_response_with_special_tokens"],
                        "finish_reason": gen["finish_reason"], "truncated": gen["finish_reason"] == "length",
                        "parsed_response": parsed, "prompt_tokens": gen["prompt_tokens"], "output_tokens": gen["output_tokens"],
                        "output_token_ids": gen["output_token_ids"], "rendered_prompt_sha256": gen["rendered_prompt_sha256"],
                        "latency_s": gen["latency_s"], "timestamp_utc": C.utc_now(), "error": None})
            C.append_jsonl(lane_dir / ("rendered_prompts_dev.jsonl" if args.phase == "dev" else "rendered_prompts.jsonl"),
                           {"query_id": qid, "sha256": gen["rendered_prompt_sha256"], "text": gen["rendered_prompt"]})
            consecutive = 0
        except Exception as error:  # noqa: BLE001
            rec.update({"status": "infrastructure_error", "raw_response": None, "parsed_response": None, "prompt_tokens": None,
                        "output_tokens": None, "latency_s": None, "timestamp_utc": C.utc_now(),
                        "error": f"{type(error).__name__}: {error}", "traceback": traceback.format_exc()[-4000:]})
            consecutive += 1
        C.append_jsonl(out_path, rec)
        done += 1
        if consecutive >= MAX_CONSECUTIVE_INFRA:
            stopped = "repeated_infrastructure_fault"
            break
        if args.limit and done >= args.limit:
            stopped = "debug_limit"
            break
    rows = C.read_jsonl(out_path)
    final = {}
    for r in rows:
        if r["status"] == "delivered" or r["query_id"] not in final:
            final[r["query_id"]] = r
    receipt.update({"ended_utc": C.utc_now(), "elapsed_s": time.time() - t0, "requests_this_run": done, "stopped": stopped,
                    "status": "complete" if stopped is None else stopped,
                    "delivered_total": sum(1 for r in final.values() if r["status"] == "delivered"),
                    "infrastructure_missing_total": sum(1 for r in final.values() if r["status"] != "delivered"),
                    "latency_s_sum": sum(r.get("latency_s") or 0 for r in rows if r.get("status") == "delivered"),
                    "truncated_total": sum(1 for r in final.values() if r.get("truncated"))})
    C.write_json_atomic(lane_dir / f"run_receipt_{args.phase}_{int(t0)}.json", receipt)
    print(json.dumps({k: receipt.get(k) for k in ("lane", "phase", "status", "requests_this_run", "delivered_total",
                                                 "infrastructure_missing_total", "elapsed_s", "load_s", "truncated_total")}, indent=1))
    print(json.dumps(receipt.get("loaded_parameter_digest"), indent=1))


if __name__ == "__main__":
    main()
