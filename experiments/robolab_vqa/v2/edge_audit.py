"""Format audit of the existing R1 Edge (E3-policy) B responses on the V2 scene set (CPU; spec section 4).

python -m experiments.robolab_vqa.v2.edge_audit --output <dir>

Covers B.no_image (30), B.initial (240), PB.no_image (16) and PB.initial (128) in S1/S3/S4 = 414 requests. Original
strict scores are preserved; failures are classified by fixed deterministic rules (no model judge). A descriptive
alias mapping derived from the instruction wording (not from responses) reports how many failed answers would name the
catalog tuple; it is not used for any score.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

from .. import common as C
from .. import parse as P1
from . import config as V

FENCE = re.compile(r"^```(?:json|JSON)?[ \t]*\n(.*)\n```$", re.DOTALL)
OBJECT_ALIASES = {"rubik's cube": "rubiks_cube", "rubiks cube": "rubiks_cube", "rubik cube": "rubiks_cube", "rubiks_cube": "rubiks_cube",
                  "bowl": "bowl", "banana": "banana", "butter box": "butter", "butter": "butter", "raisin box": "raisin_box",
                  "raisin_box": "raisin_box", "mustard bottle": "mustard_bottle", "mustard": "mustard_bottle",
                  "mustard_bottle": "mustard_bottle"}
RELATION_ALIASES = {"left of": "left_of", "to the left of": "left_of", "left": "left_of", "left_of": "left_of",
                    "right of": "right_of", "to the right of": "right_of", "right": "right_of", "right_of": "right_of",
                    "in front of": "in_front_of", "in front": "in_front_of", "in_front_of": "in_front_of",
                    "behind": "behind", "on top of and supported by": "on_top_supported", "on top of": "on_top_supported",
                    "on top": "on_top_supported", "on": "on_top_supported", "on_top_supported": "on_top_supported",
                    "stacked on": "stacked_on", "stacked_on": "stacked_on", "unknown": "unknown"}


def classify(text: str | None, finish_reason: str | None, objects: list[str]) -> tuple[str, object]:
    if text is None:
        return "no_text", None
    if finish_reason == "length":
        return "truncation", None
    s = text.strip()
    m = FENCE.match(s)
    if m:
        s = m.group(1).strip()
    try:
        obj = json.loads(s)
    except json.JSONDecodeError:
        n_obj = len(re.findall(r"\{[^{}]*\}", s))
        return ("multiple_or_conflicting_answers" if n_obj > 1 else "json_structure_malformed"), None
    if isinstance(obj, list):
        if len(obj) == 1 and isinstance(obj[0], dict):
            return "json_structure_single_item_array", obj[0]
        return "multiple_or_conflicting_answers", None
    if not isinstance(obj, dict):
        return "json_structure_not_object", None
    if set(obj) != {"target", "reference", "relation"}:
        return "json_structure_keys", obj
    bad_obj = any(obj.get(k) not in objects for k in ("target", "reference"))
    bad_rel = obj.get("relation") not in C.RELATION_VOCABULARY
    if bad_obj and bad_rel:
        return "object_and_relation_vocabulary", obj
    if bad_obj:
        return "object_vocabulary", obj
    if bad_rel:
        return "relation_vocabulary", obj
    return "other", obj


def alias_tuple(obj) -> dict | None:
    if not isinstance(obj, dict):
        return None
    try:
        return {"target": OBJECT_ALIASES[str(obj["target"]).strip().lower()],
                "reference": OBJECT_ALIASES[str(obj["reference"]).strip().lower()],
                "relation": RELATION_ALIASES[str(obj["relation"]).strip().lower()]}
    except KeyError:
        return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--r1-release", type=Path, default=V.R1_RELEASE_DIR)
    ap.add_argument("--r1-run", type=Path, default=V.R1_RUN_DIR)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    V.assert_not_r1_path(args.output)
    manifest = {r["query_id"]: r for r in C.read_jsonl(args.r1_release / "query_manifest.jsonl")}
    resp = {}
    for r in C.read_jsonl(args.r1_run / "E3-policy" / "responses.jsonl"):
        if r["status"] == "delivered" or r["query_id"] not in resp:
            resp[r["query_id"]] = r
    catalog = C.load_catalog()
    vocab = {s: next(i["object_vocabulary"] for i in catalog["original_instructions"] if i["scene"] == s) for s in V.SCENES}
    rows = []
    for qid, q in manifest.items():
        if q["test"] != "B" or q["scene_id"] not in V.SCENES or q["bank"] not in ("no_image", "initial"):
            continue
        r = resp.get(qid)
        text = r.get("raw_response") if r else None
        strict = P1.parse_b(text, vocab[q["scene_id"]], list(C.RELATION_VOCABULARY))
        gold = q["gold_answer"]
        if strict["valid"]:
            cls, obj = ("strict_valid_correct" if strict["answer"] == gold else "strict_valid_incorrect"), strict["answer"]
        else:
            cls, obj = classify(text, r.get("finish_reason") if r else None, vocab[q["scene_id"]])
        alias = alias_tuple(obj) if not strict["valid"] else None
        rows.append({"query_id": qid, "family": q["family"], "bank": q["bank"], "scene": q["scene_id"], "goal": q["goal_id"],
                     "form": q["display_form"], "status": r["status"] if r else "missing", "finish_reason": r.get("finish_reason") if r else None,
                     "strict_valid": strict["valid"], "strict_tuple_correct": bool(strict["valid"] and strict["answer"] == gold),
                     "failure_class": None if strict["valid"] else cls, "strict_class": cls,
                     "alias_mapped": json.dumps(alias) if alias else None,
                     "alias_tuple_matches_gold_descriptive": (alias == gold) if alias else None,
                     "raw_excerpt": (text or "")[:160]})
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "edge_format_audit.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    summ = {"requests": len(rows), "by_family_bank": dict(Counter(f"{r['family']}|{r['bank']}" for r in rows)),
            "strict_valid": sum(r["strict_valid"] for r in rows), "strict_tuple_correct": sum(r["strict_tuple_correct"] for r in rows),
            "failure_classes": dict(Counter(r["failure_class"] for r in rows if r["failure_class"])),
            "failure_classes_by_family_bank": {k: dict(Counter(r["failure_class"] for r in rows if r["failure_class"] and f"{r['family']}|{r['bank']}" == k))
                                               for k in sorted({f"{r['family']}|{r['bank']}" for r in rows})},
            "alias_mappable_failures": sum(1 for r in rows if r["alias_mapped"]),
            "alias_mapped_matches_gold_descriptive": sum(1 for r in rows if r["alias_tuple_matches_gold_descriptive"]),
            "alias_mapped_by_form": {f: {"mapped": sum(1 for r in rows if r["alias_mapped"] and r["form"] == f and r["family"] == "original"),
                                         "matches_gold": sum(1 for r in rows if r["alias_tuple_matches_gold_descriptive"] and r["form"] == f and r["family"] == "original")}
                                     for f in ("DIR", "TF", "RF")},
            "note": "Descriptive alias mapping uses names/relations from the instruction wording; it is not a parser repair and "
                    "does not change R1 strict scores. A mapped-and-matching answer is not evidence that every format failure "
                    "was semantically correct."}
    C.write_json_atomic(out / "edge_format_audit_summary.json", summ)
    print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    sys.exit(main())
