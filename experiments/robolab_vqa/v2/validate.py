"""Validate the frozen V2 release before any evaluation query.

python -m experiments.robolab_vqa.v2.validate --release /data/users/ali/rqa-20261006/release/r2-final/release.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

from .. import common as C
from .. import prompts as P
from . import config as V
from .prepare import remove_headers, remove_images

PLANNED = {"B2|original|initial|IH": 240, "B2|original|initial|I": 240, "B2|original|no_image|H": 30,
           "B2|original|no_image|T": 30, "B2|placement|initial|IH": 128, "B2|placement|no_image|T": 16,
           "C2|original|initial|R1-presentation": 480, "C2|original|secondary|R1-presentation": 960,
           "C2|original|no_image|no_image_camera_text_retained": 60}
OPTION_LINE = re.compile(r"^(A|B|U): (.+)$", re.MULTILINE)


def validate(release_path: Path) -> dict:
    root = release_path.parent
    rel = C.load_json(release_path)
    rows = C.read_jsonl(root / "query_manifest.jsonl")
    payloads = C.read_jsonl(root / "payloads.jsonl")
    dev = C.read_jsonl(root / "dev_fixtures.jsonl")
    r1root = Path(rel["image_root"])
    r1 = {r["query_id"]: r for r in C.read_jsonl(r1root / "query_manifest.jsonl")}
    r1frames = C.load_json(r1root / "frames.json")["frames"]
    images = C.load_json(r1root / "images.json")
    catalog = C.load_catalog()
    cat = {i["prompt_id"]: i for i in catalog["original_instructions"] + catalog["placement_controls"]}
    ck: dict[str, bool] = {}
    notes: dict = {}
    ck["release_file_hashes_match"] = all(C.sha256_file(root / n) == h for n, h in rel["files"].items())
    ck["r1_release_unchanged"] = (C.sha256_file(r1root / "release.json") == V.R1_RELEASE_JSON_SHA256
                                  and C.load_json(r1root / "release.json")["release_content_sha256"] == V.R1_RELEASE_CONTENT_SHA256)
    ck["v2_release_not_in_r1_paths"] = root.resolve() != r1root.resolve() and not str(root.resolve()).startswith(str(r1root.resolve()) + "/")
    counts = defaultdict(int)
    for r in rows:
        counts[f"{r['kind']}|{r['family']}|{r['bank']}|{r['condition']}"] += 1
    ck["counts_match_plan"] = dict(counts) == PLANNED
    ck["per_lane_2184_total_6552"] = len(rows) == V.MAX_EVAL_PER_LANE and len(rows) * len(V.LANES) == V.MAX_EVAL_TOTAL
    ck["unique_query_ids"] = len({r["query_id"] for r in rows}) == len(rows) == len(payloads)
    ck["order_keys"] = all(r["order_key"] == C.order_key(r["query_id"]) for r in rows)
    ck["scenes_S1_S3_S4_only"] = {r["scene_id"] for r in rows} == set(V.SCENES)
    ck["single_release_sha"] = {r["release_sha256"] for r in rows} == {rel["release_content_sha256"]}
    # instruction bytes
    ok = True
    for r in rows:
        item = cat[r["original_prompt_id"]]
        ok &= r["instruction_utf8"] == item["prompt"] and r["instruction_utf8_sha256"] == item["prompt_sha256"]
        ok &= ("Instruction:\n" + item["prompt"] + "\n\n") in r["full_prompt"]
    ck["instruction_bytes_exact"] = bool(ok)
    ck["s4_top_d_trailing_space"] = all(r["instruction_utf8"].endswith(". ") for r in rows if r["original_prompt_id"] == "S4-TOP-D")
    tv = C.load_json(root / "tuple_verification.json")
    ck["tuples_verified_46"] = tv["n"] == 46 and all(t["matches_catalog"] for t in tv["rows"])
    # paired B2 inputs
    by = {r["query_id"]: r for r in rows}
    pair_ok, header_ok, img_ok = True, True, True
    for r in rows:
        if r["kind"] != "B2" or r["condition"] != "IH":
            continue
        fid, pid = r["frame_id"], r["original_prompt_id"]
        pre = "PB2" if r["family"] == "placement" else "B2"
        ih = r["segments"]
        t = by[f"{pre}.T.{pid}"]["segments"]
        if pre == "B2":
            i = by[f"B2.I.{fid}.{pid}"]["segments"]
            h = by[f"B2.H.{pid}"]["segments"]
            pair_ok &= P.full_prompt_text(remove_images(ih)) == P.full_prompt_text(h)
            pair_ok &= P.full_prompt_text(remove_images(i)) == P.full_prompt_text(t)
            header_ok &= remove_headers(ih) == i and remove_headers(h) == t
            img_ok &= [s["image_id"] for s in ih if s["type"] == "image"] == [s["image_id"] for s in i if s["type"] == "image"]
            stripped = P.full_prompt_text(ih)
            for hs in V.HEADER_STRINGS:
                stripped = stripped.replace(hs, "", 1)
            header_ok &= stripped == P.full_prompt_text(i)
        else:
            pair_ok &= P.full_prompt_text(remove_images(remove_headers(ih))) == P.full_prompt_text(t)
        ih_r1 = r1[r["source_r1_query_id"]]["segments"]
        img_ok &= ih == ih_r1
    ck["b2_IH_equals_R1_B_payload"] = bool(img_ok)
    ck["b2_text_equal_IH_H_and_I_T_after_removing_images"] = bool(pair_ok)
    ck["b2_header_only_differences_IH_I_and_H_T"] = bool(header_ok)
    ck["b2_no_image_deduplicated_8_starts"] = all(len(r.get("dedup_source_r1_query_ids") or []) == 8
                                                  for r in rows if r["kind"] == "B2" and r["bank"] == "no_image")
    # B2 constraints
    vocab = {s: sorted(next(i["object_vocabulary"] for i in catalog["original_instructions"] if i["scene"] == s)) for s in V.SCENES}
    sch_ok = True
    for r in rows:
        oc = r["output_constraint"]
        if r["kind"] == "B2":
            sc = V.schema_of(oc)
            sch_ok &= V.schema_property_order(oc) == ["target", "reference", "relation"]
            sch_ok &= oc["type"] == "json_schema" and sc["required"] == ["target", "reference", "relation"]
            sch_ok &= sc["additionalProperties"] is False and set(sc["properties"]) == {"target", "reference", "relation"}
            sch_ok &= sc["properties"]["target"]["enum"] == vocab[r["scene_id"]] == sc["properties"]["reference"]["enum"]
            sch_ok &= sc["properties"]["relation"]["enum"] == V.RELATIONS
        else:
            sch_ok &= oc == {"type": "choice", "choices": ["A", "B", "U"]}
    ck["output_constraints_full_vocab_no_gold_pruning"] = bool(sch_ok)
    notes["distinct_constraints"] = len({r["output_constraint_sha256"] for r in rows})
    # C2 options, mapping and source alignment
    map_ok, src_ok, body_ok = True, True, True
    for r in rows:
        if r["kind"] != "C2":
            continue
        text = P.full_prompt_text(r["segments"])
        lines = dict(OPTION_LINE.findall(text))
        sem = {"match": V.OPTION_MATCH, "nonmatch": V.OPTION_NONMATCH, "unknown": V.OPTION_UNKNOWN}
        map_ok &= {code: next(k for k, v in sem.items() if v == lines[code]) for code in "ABU"} == r["option_mapping"]
        map_ok &= r["option_mapping"] == V.C2_ORDERS[r["option_order"]]
        if r["bank"] in ("initial", "secondary"):
            src = r1[r["source_r1_query_id"]]
            body_ok &= r["segments"][:-1] == src["segments"][:-1]
            body_ok &= text.endswith(V.c2_body(r["instruction_utf8"], r["option_order"]))
            fr = r1frames[r["frame_id"]]
            src_ok &= (src["frame_id"] == r["frame_id"] and src["physical_start_id"] == r["physical_start_id"]
                       and [s["image_id"] for s in r["segments"] if s["type"] == "image"] == [fr["views"][v] for v in C.VIEW_KEYS])
            src_ok &= {"yes": "match", "no": "nonmatch"}[src["gold_answer"]] == r["gold_answer"]
            src_ok &= (src["answerable"], src["exclusion_reason"]) == (r["answerable"], r["exclusion_reason"])
        else:
            body_ok &= not any(s["type"] == "image" for s in r["segments"])
            body_ok &= all(h in text for h in V.HEADER_STRINGS)
    ck["c2_option_orders_map_identical_semantics"] = bool(map_ok)
    ck["c2_same_views_headers_as_R1_only_wrapper_replaced"] = bool(body_ok)
    ck["c2_source_frame_gold_and_mask_alignment"] = bool(src_ok)
    orders = defaultdict(set)
    for r in rows:
        if r["kind"] == "C2":
            orders[r["item_key"]].add(r["option_order"])
    ck["c2_every_item_has_both_orders"] = all(v == {0, 1} for v in orders.values())
    # payload hygiene / gold leakage
    forbidden = ("gold", "answerable", "stable_ever", "success", "N3", "E3", "F3", "exclusion", "simulator", "policy")
    ck["payloads_free_of_gold_and_model_names"] = all(not any(f in s.get("text", "") for f in forbidden)
                                                      for p in payloads for s in p["segments"])
    ck["payload_fields_minimal"] = all(set(p) == {"query_id", "order_key", "kind", "bank", "condition", "option_order", "segments",
                                                  "full_prompt_sha256", "output_constraint", "output_constraint_sha256", "image_files"}
                                       for p in payloads)
    ck["camera_order_wrist_left_right"] = all(
        [s["view"] for s in p["segments"] if s["type"] == "image"] in ([], list(C.VIEW_KEYS)) for p in payloads)
    ck["image_hashes_in_r1_release"] = all(images[s["image_id"]]["raw_rgb_sha256"] for p in payloads for s in p["segments"]
                                           if s["type"] == "image")
    # dev fixtures
    kinds = sorted((d["kind"], d["condition"]) for d in dev)
    ck["six_qualification_fixtures"] = len(dev) == V.MAX_QUAL_PER_LANE and kinds == sorted(
        [("B2", "T"), ("B2", "IH"), ("B2", "I"), ("C2", "initial"), ("C2", "secondary"), ("C2", "no_image")])
    catalog_texts = {i["prompt"] for i in cat.values()}
    ck["fixtures_use_non_catalog_wording"] = all(not any(t in P.full_prompt_text(d["segments"]) for t in catalog_texts) for d in dev)
    # answerability summary
    c2 = [r for r in rows if r["kind"] == "C2" and r["bank"] in ("initial", "secondary")]
    notes["c2_mask"] = {b: {"answerable": sum(1 for r in c2 if r["bank"] == b and r["answerable"]),
                            "excluded": sum(1 for r in c2 if r["bank"] == b and not r["answerable"])} for b in ("initial", "secondary")}
    notes["c2_gold"] = {b: {g: sum(1 for r in c2 if r["bank"] == b and r["answerable"] and r["gold_answer"] == g)
                            for g in ("match", "nonmatch")} for b in ("initial", "secondary")}
    return {"release": str(release_path), "release_json_sha256": C.sha256_file(release_path),
            "release_content_sha256": rel["release_content_sha256"], "validated_utc": C.utc_now(),
            "passed": all(ck.values()), "checks": ck, "notes": notes,
            "human_answerability_review": "not performed; original R1 mask frozen; review mask applied later by CPU rescoring"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--release", type=Path, required=True)
    args = ap.parse_args()
    res = validate(args.release)
    C.write_json_atomic(args.release.parent / "validation.json", res)
    print(json.dumps({"passed": res["passed"], "failed": [k for k, v in res["checks"].items() if not v], "notes": res["notes"]}, indent=1))
    sys.exit(0 if res["passed"] else 1)


if __name__ == "__main__":
    main()
