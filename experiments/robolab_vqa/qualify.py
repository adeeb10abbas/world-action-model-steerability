"""Qualification summary: tensor/output parity groups, lane statuses and the eligibility matrix (CPU).

python -m experiments.robolab_vqa.qualify --results <results-dir> --eligibility <audit.json> --output <dir>

A lane joins another lane's identity group only if (1) the parameters actually loaded by the native reasoner class
hash identically (names, dtypes, shapes, bytes), (2) tokenizer/processor/chat-template files are identical (processor
JSON compared after dropping writer metadata) and (3) all six development fixtures render byte-identical prompts with
identical token counts and return byte-identical raw text. Each group is evaluated once on the bank; the
other members reference that shared result and are never counted as independent evidence.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from . import common as C
from .adapters import ADAPTER_VERSION, LANES

PREFERRED = ["N3-policy", "E3-policy", "F3-qwen3vl4b", "N3-base", "E3-base", "N3-upstream-qwen3vl8b"]
PROCESSOR_FILES = ("preprocessor_config.json", "processor_config.json", "video_preprocessor_config.json", "tokenizer.json",
                   "tokenizer_config.json", "chat_template.json", "chat_template.jinja", "vocab.json", "merges.txt",
                   "generation_config.json", "special_tokens_map.json")
SEMANTIC_JSON = ("preprocessor_config.json", "processor_config.json", "video_preprocessor_config.json", "generation_config.json")


def latest_receipt(lane_dir: Path, phase: str) -> dict | None:
    rs = sorted(lane_dir.glob(f"run_receipt_{phase}_*.json"))
    return C.load_json(rs[-1]) if rs else None


def _strip_serialization(value, depth: int = 0):
    """Drop writer metadata that does not change preprocessing: transformers_version anywhere and the redundant
    processor_class copies nested inside image/video processor blocks (the top-level class is kept)."""
    if isinstance(value, dict):
        return {k: _strip_serialization(v, depth + 1) for k, v in value.items()
                if k != "transformers_version" and not (k == "processor_class" and depth > 0)}
    return value


def processor_identity(lane: str) -> dict:
    root = Path(LANES[lane]["path"])
    out = {}
    for rel in PROCESSOR_FILES:
        p = root / rel
        if not p.exists():
            continue
        if rel in SEMANTIC_JSON:
            # key order and the writer's transformers_version are serialization metadata, not processor behaviour
            out[rel] = C.canonical_sha256(_strip_serialization(json.loads(p.read_text())))
        else:
            out[rel] = C.sha256_file(p)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", type=Path, required=True)
    ap.add_argument("--eligibility", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    audit = C.load_json(args.eligibility)
    lanes = {}
    for lane in LANES:
        d = args.results / lane
        rec = latest_receipt(d, "dev")
        fx = {r["query_id"]: r for r in C.read_jsonl(d / "dev_fixture_responses.jsonl") if r["status"] == "delivered"}
        lanes[lane] = {"receipt": rec, "fixtures": fx, "processor": processor_identity(lane)}
    groups: list[list[str]] = []
    for lane in PREFERRED:
        info = lanes[lane]
        rec = info["receipt"]
        if not rec or rec.get("status") not in ("complete",) or len(info["fixtures"]) != 6:
            continue
        digest = (rec.get("loaded_parameter_digest") or {}).get("sha256")
        placed = False
        for g in groups:
            ref = lanes[g[0]]
            same_digest = digest and digest == (ref["receipt"].get("loaded_parameter_digest") or {}).get("sha256")
            same_proc = info["processor"] == ref["processor"]
            same_out = all(info["fixtures"][q]["raw_response"] == ref["fixtures"][q]["raw_response"]
                           and info["fixtures"][q]["rendered_prompt_sha256"] == ref["fixtures"][q]["rendered_prompt_sha256"]
                           and info["fixtures"][q]["prompt_tokens"] == ref["fixtures"][q]["prompt_tokens"]
                           for q in info["fixtures"])
            if same_digest and same_proc and same_out:
                g.append(lane)
                placed = True
                break
        if not placed:
            groups.append([lane])
    out_lanes = {}
    for lane, spec in LANES.items():
        info = lanes[lane]
        rec = info["receipt"] or {}
        group = next((g for g in groups if lane in g), None)
        entry = {"family": spec["family"], "role": spec["role"], "repo": spec["repo"], "revision": spec["revision"],
                 "path": spec["path"], "native_class": spec["native_class"], "adapter_version": ADAPTER_VERSION,
                 "loader_patches": rec.get("loader_patches"), "reasoner_view": (rec.get("reasoner_view") or {}).get("config_edits"),
                 "loaded_parameter_digest": rec.get("loaded_parameter_digest"), "dev_status": rec.get("status"),
                 "dev_fixtures_delivered": len(info["fixtures"]),
                 "dev_fixtures_valid_format": sum(1 for r in info["fixtures"].values() if (r.get("parsed_response") or {}).get("valid")),
                 "dev_mean_latency_s": (sum(r["latency_s"] for r in info["fixtures"].values()) / len(info["fixtures"])) if info["fixtures"] else None,
                 "dev_prompt_tokens": {q: r["prompt_tokens"] for q, r in info["fixtures"].items()},
                 "processor_identity": info["processor"]}
        if group is None:
            entry.update({"status": "blocked" if rec else "not_qualified", "responses_from": None,
                          "reason": rec.get("error") or "development fixtures incomplete"})
        else:
            entry.update({"identity_group": group, "responses_from": group[0],
                          "status": "evaluated" if lane == group[0] else "shared_tensor_identical"})
        out_lanes[lane] = entry
    result = {"created_utc": C.utc_now(), "identity_groups": groups, "lanes": out_lanes,
              "rule": "identical loaded parameters + identical tokenizer/processor/template + identical raw text on all six fixtures"}
    args.output.mkdir(parents=True, exist_ok=True)
    C.write_json_atomic(args.output / "lanes.json", result)
    rows = []
    for lane, e in out_lanes.items():
        a = audit["lanes"].get(lane, {})
        rows.append({
            "lane": lane, "family": e["family"], "role": e["role"], "repo_revision": f"{e['repo']}@{e['revision']}",
            "local_path": e["path"], "native_readout": f"vLLM {e['native_class']} (greedy text head)",
            "adapters": "; ".join((e["loader_patches"] or []) + ([f"packaging view {e['reasoner_view']}"] if e["reasoner_view"] else []))
                        or "none",
            "weight_files_match_hf_revision": a.get("all_weight_files_match_hf_revision"),
            "reasoner_params": a.get("reasoner_params"), "lm_head": "tied to token embedding" if a.get("tie_word_embeddings") else
            ("present" if a.get("has_lm_head_tensor") else "absent"),
            "vision_tower": "present" if (a.get("reasoner_components") or {}).get("vision_encoder") else "absent",
            "loaded_parameter_digest": (e["loaded_parameter_digest"] or {}).get("sha256"),
            "identity_group": "+".join(e.get("identity_group") or []), "status": e["status"],
            "responses_from": e.get("responses_from"), "eligible_tests": "A, B(text+image), C(image+no-image)"
            if e["status"] in ("evaluated", "shared_tensor_identical") else "none",
            "dev_fixtures_valid_format": f"{e['dev_fixtures_valid_format']}/{e['dev_fixtures_delivered']}"})
    with open(args.output / "model_eligibility.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(json.dumps({"groups": groups, "status": {k: v["status"] for k, v in out_lanes.items()}}, indent=1))


if __name__ == "__main__":
    sys.exit(main())
