"""Validate a frozen RQA-20261006 release before inference.

python -m experiments.robolab_vqa.validate --release <release-dir>/release.json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from . import common as C

REQUIRED_QUERY_FIELDS = ("query_id", "release_sha256", "test", "bank", "scene_id", "physical_start_id", "frame_id",
                         "source_episode_id", "requested_time_s", "observed_time_s", "view_paths_and_sha256", "goal_id",
                         "original_prompt_id", "display_form", "instruction_utf8_sha256", "full_prompt", "full_prompt_sha256",
                         "pair_id", "equivalence_status", "gold_answer", "answerable", "exclusion_reason", "annotation_version")
PLANNED = {"original|A|initial": 192, "original|B|no_image": 36, "original|B|initial": 288, "original|C|initial": 288,
           "placement|B|no_image": 16, "placement|B|initial": 128, "placement|C|initial": 128, "original|C|no_image": 36,
           "original|A|secondary": 384, "original|C|secondary": 576}


def validate(release_path: Path, spec_dir: Path = C.SPEC_DIR) -> dict:
    root = release_path.parent
    rel = C.load_json(release_path)
    rows = C.read_jsonl(root / "query_manifest.jsonl")
    payloads = C.read_jsonl(root / "payloads.jsonl")
    frames = C.load_json(root / "frames.json")["frames"]
    images = C.load_json(root / "images.json")
    catalog = C.load_catalog(spec_dir)
    checks: dict[str, bool] = {}
    notes: dict[str, object] = {}
    # file hashes
    checks["release_file_hashes_match"] = all(C.sha256_file(root / n) == h for n, h in rel["files"].items())
    # counts
    counts = defaultdict(int)
    for r in rows:
        counts[f"{r['family']}|{r['test']}|{r['bank']}"] += 1
    checks["query_counts_match_plan"] = dict(counts) == PLANNED
    checks["total_queries_2072"] = len(rows) == 2072 == sum(PLANNED.values())
    checks["unique_query_ids"] = len({r["query_id"] for r in rows}) == len(rows)
    checks["required_query_fields_present"] = all(all(k in r for k in REQUIRED_QUERY_FIELDS) for r in rows)
    checks["single_release_sha"] = len({r["release_sha256"] for r in rows}) == 1 and rows[0]["release_sha256"] == rel["release_content_sha256"]
    # prompt bytes
    cat = {i["prompt_id"]: i for i in catalog["original_instructions"] + catalog["placement_controls"]}
    ok = True
    for r in rows:
        if r["original_prompt_id"]:
            item = cat[r["original_prompt_id"]]
            ok &= r["instruction_utf8"] == item["prompt"] and r["instruction_utf8_sha256"] == item["prompt_sha256"]
            ok &= ("Instruction:\n" + item["prompt"] + "\n\n") in r["full_prompt"]
    checks["instruction_bytes_exact_in_wrapper"] = bool(ok)
    s4 = [r for r in rows if r["original_prompt_id"] == "S4-TOP-D"]
    checks["s4_top_d_trailing_space_preserved"] = bool(s4) and all(r["instruction_utf8"].endswith(". ") for r in s4)
    # frames
    init = [f for f in frames.values() if f.get("bank") == "initial"]
    sec = [f for f in frames.values() if f.get("bank") == "secondary"]
    checks["32_initial_frames_available"] = len(init) == 32 and all(f["available"] for f in init)
    checks["64_secondary_frames_available"] = len(sec) == 64 and all(f["available"] for f in sec)
    checks["distinct_frame_ids"] = len(frames) == 96
    checks["three_views_single_source_per_frame"] = all(
        len({p["source"] for v in f["views"].values() for p in images[v]["provenance"] if p["frame_id"] == f["frame_id"]}) == 1
        for f in frames.values() if f.get("available"))
    checks["initial_views_native_720x1280"] = all(images[v]["height"] == 720 and images[v]["width"] == 1280
                                                  for f in init for v in f["views"].values())
    # image order and payload hygiene
    order_ok = True
    for p in payloads:
        views = [s["view"] for s in p["segments"] if s["type"] == "image"]
        for i in range(0, len(views), 3):
            order_ok &= tuple(views[i:i + 3]) == C.VIEW_KEYS
    checks["camera_order_wrist_left_right"] = bool(order_ok)
    forbidden = ("gold", "answerable", "stable_ever", "success", "N3", "E3", "F3", "exclusion")
    checks["payloads_free_of_gold_and_model_names"] = all(
        not any(f in s.get("text", "") for f in forbidden) for p in payloads for s in p["segments"])
    checks["payload_fields_minimal"] = all(set(p) == {"query_id", "order_key", "test", "bank", "segments", "full_prompt_sha256",
                                                      "image_files"} for p in payloads)
    checks["image_ids_opaque"] = all(k.startswith("img-") and len(k) == 28 for k in images)
    checks["image_files_hash_match"] = all(C.sha256_file(root / m["path"]) == m["png_sha256"] for m in images.values())
    checks["order_keys_match"] = all(r["order_key"] == C.order_key(r["query_id"]) for r in rows)
    # label equivalence and joint exclusions
    by_pair = defaultdict(list)
    for r in rows:
        if r["pair_id"]:
            by_pair[r["pair_id"]].append(r)
    a_ok = all(len({(x["gold_answer"], x["answerable"], x["exclusion_reason"]) for x in v}) == 1
               for k, v in by_pair.items() if k.startswith("A."))
    checks["A_pairs_share_gold_and_exclusions"] = a_ok
    eq_bad, s5_diff = [], []
    for k, v in by_pair.items():
        if not (k.startswith("C.initial") or k.startswith("C.secondary")):
            continue
        forms = {x["display_form"]: x for x in v}
        if v[0]["scene_id"] in C.MAIN_POOL_SCENES:
            if len({(x["gold_answer"], x["answerable"]) for x in v}) != 1:
                eq_bad.append(k)
        else:
            if forms["TF"]["gold_answer"] != forms["RF"]["gold_answer"]:
                s5_diff.append(k)
    checks["main_pool_C_DIR_TF_RF_labels_equivalent"] = not eq_bad
    notes["main_pool_C_label_mismatches"] = eq_bad
    notes["s5_C_TF_vs_RF_form_specific_label_differences"] = s5_diff
    pc_ok = all(len({(x["gold_answer"], x["answerable"]) for x in v}) == 1 for k, v in by_pair.items() if k.startswith("PC."))
    checks["placement_C_pairs_share_gold"] = pc_ok
    b_ok = all(r["gold_answer"] == cat[r["original_prompt_id"]]["gold_B"] for r in rows if r["test"] == "B")
    checks["B_gold_from_catalog"] = b_ok
    checks["release_status_declares_provisional_review"] = "provisional" in rel["status"]
    # exclusion summary
    excl = defaultdict(int)
    for r in rows:
        if r["answerable"] is False:
            for reason in r["exclusion_reason"].split(";"):
                excl[f"{r['test']}|{r['bank']}|{reason.split(':')[0]}"] += 1
    notes["exclusions"] = dict(sorted(excl.items()))
    labels = defaultdict(lambda: defaultdict(int))
    for r in rows:
        if r["test"] in ("A", "C") and r["gold_answer"] in ("yes", "no"):
            labels[f"{r['family']}|{r['test']}|{r['bank']}|{r['scene_id']}"][f"{r['gold_answer']}|{'ans' if r['answerable'] else 'excl'}"] += 1
    notes["label_distribution"] = {k: dict(v) for k, v in sorted(labels.items())}
    result = {"release": str(release_path), "release_json_sha256": C.sha256_file(release_path),
              "release_content_sha256": rel["release_content_sha256"], "validated_utc": C.utc_now(),
              "passed": all(checks.values()), "checks": checks, "notes": notes,
              "human_answerability_review": "not performed (pending); release is provisional"}
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--release", type=Path, required=True)
    ap.add_argument("--spec-dir", type=Path, default=C.SPEC_DIR)
    args = ap.parse_args()
    result = validate(args.release, args.spec_dir)
    C.write_json_atomic(args.release.parent / "validation.json", result)
    print(json.dumps({"passed": result["passed"], "failed": [k for k, v in result["checks"].items() if not v],
                      "exclusions": result["notes"]["exclusions"]}, indent=1))
    sys.exit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
