"""Build the frozen V2 release (B2 + C2 payloads, gold/eligibility metadata, fixtures) from the frozen R1 release.

python -m experiments.robolab_vqa.v2.prepare --r1-release /data/users/ali/rqa-20261006/release/r1 \
    --output /data/users/ali/rqa-20261006/release/r2-final --implementation-commit <sha>

No images are re-rendered or re-encoded: every view is an R1 release image (raw RGB hash verified). The runner reads
images from the R1 release directory recorded as `image_root`.
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

# ---------------------------------------------------------------- instruction tuple verification (spec section 3)
NAME_MAP = {"rubiks cube": "rubiks_cube", "Rubik's cube": "rubiks_cube", "bowl": "bowl", "banana": "banana",
            "butter box": "butter", "raisin box": "raisin_box", "mustard bottle": "mustard_bottle",
            "mustard": "mustard_bottle"}
REL_MAP = {"to the left of": "left_of", "to the right of": "right_of", "in front of": "in_front_of", "behind": "behind",
           "to the left": "left_of", "to the right": "right_of", "in front": "in_front_of",
           "on top of and supported by": "on_top_supported", "on top of": "on_top_supported", "on": "on_top_supported",
           "underneath and supporting": "underneath_supporting"}
CONVERSE = {"left_of": "right_of", "right_of": "left_of", "in_front_of": "behind", "behind": "in_front_of",
            "underneath_supporting": "on_top_supported"}
PATTERNS = [
    ("relational_clause", re.compile(r"^(?:Place|Move) the (?P<mover>.+?)(?P<table> on the table)? so that the (?P<subj>.+?) is "
                                     r"(?P<rel>to the left of|to the right of|in front of|behind|on top of and supported by|"
                                     r"underneath and supporting) the (?P<obj>.+?)\.$")),
    ("direct_put", re.compile(r"^Put the (?P<mover>.+?) (?P<rel>to the left of|to the right of|in front of|behind) the (?P<obj>.+?)$")),
    ("direct_place_table", re.compile(r"^Place the (?P<mover>.+?)(?P<table> on the table) (?P<rel>to the left of|to the right of) "
                                      r"the (?P<obj>.+?)\.$")),
    ("direct_pick_place", re.compile(r"^Pick up the (?P<mover>.+?) and place it (?P<rel>on top of) the (?P<obj>.+?)$")),
    ("direct_place_on", re.compile(r"^Place the (?P<mover>.+?) (?P<rel>on) the (?P<obj>.+?)\. $")),
    ("placement_early", re.compile(r"^Relative to the (?P<obj>.+?), place the (?P<mover>.+?) (?P<rel>to the left|to the right|in front|behind)\.$")),
    ("placement_late", re.compile(r"^Place the (?P<mover>.+?) (?P<rel>to the left|to the right|in front|behind), relative to the (?P<obj>.+?)\.$")),
]


def parse_instruction(text: str) -> dict:
    for name, pat in PATTERNS:
        m = pat.match(text)
        if not m:
            continue
        g = m.groupdict()
        mover = NAME_MAP[g["mover"]]
        surface_rel = REL_MAP[g["rel"]]
        if name == "relational_clause":
            subj, obj = NAME_MAP[g["subj"]], NAME_MAP[g["obj"]]
        else:
            subj, obj = mover, NAME_MAP[g["obj"]]
        if subj == mover:
            target, reference, relation, converse = mover, obj, surface_rel, False
        elif obj == mover:
            target, reference, relation, converse = mover, subj, CONVERSE[surface_rel], True
        else:
            raise ValueError(f"mover not in relation clause: {text!r}")
        return {"pattern": name, "mover_phrase": g["mover"], "surface_subject": subj, "surface_relation_phrase": g["rel"],
                "surface_relation": surface_rel, "surface_object": obj, "requested_target": target,
                "requested_reference": reference, "requested_relation": relation,
                "surface_subject_is_reference": subj != mover, "converse_mapping": converse,
                "support_relation": relation == "on_top_supported",
                "support_wording": {"on top of and supported by": "explicit_support", "underneath and supporting": "explicit_support_converse",
                                    "on top of": "on_top_of_support_implied", "on": "on_support_implied"}.get(g["rel"]),
                "table_support_stated": bool(g.get("table"))}
    raise ValueError(f"no wording pattern for {text!r}")


def verify_tuples(catalog: dict) -> list[dict]:
    rows = []
    items = [(i, "original") for i in catalog["original_instructions"] if i["scene"] in V.SCENES] + \
            [(i, "placement") for i in catalog["placement_controls"]]
    for item, family in items:
        parsed = parse_instruction(item["prompt"])
        gold = item["gold_B"]
        derived = {"target": parsed["requested_target"], "reference": parsed["requested_reference"],
                   "relation": parsed["requested_relation"]}
        rows.append({"prompt_id": item["prompt_id"], "family": family, "display_form": item["display_form"],
                     "scene_id": item.get("scene") or item.get("scene_id"), "goal_id": item.get("goal") or item.get("goal_id"),
                     "instruction_utf8": item["prompt"], "instruction_utf8_sha256": C.sha256_text(item["prompt"]),
                     "catalog_sha256_matches": C.sha256_text(item["prompt"]) == item["prompt_sha256"],
                     **parsed, "catalog_gold": gold, "derived_tuple": derived, "matches_catalog": derived == gold})
    return rows


# ---------------------------------------------------------------- payload transformations
def remove_images(segs: list[dict]) -> list[dict]:
    return P.merge_text([s for s in segs if s["type"] != "image"])


def remove_headers(segs: list[dict]) -> list[dict]:
    out, found = [], {h: 0 for h in V.HEADER_STRINGS}
    for s in segs:
        if s["type"] == "text":
            t = s["text"]
            for h in V.HEADER_STRINGS:
                found[h] += t.count(h)
                t = t.replace(h, "")
            out.append({"type": "text", "text": t})
        else:
            out.append(dict(s))
    if any(n != 1 for n in found.values()):
        raise ValueError(f"header strings not found exactly once: {found}")
    return out


def replace_c_body(segs: list[dict], instruction: str, order: int) -> list[dict]:
    old = "\n\n" + P.C_WRAPPER.format(instruction=instruction)
    last = segs[-1]
    if last["type"] != "text" or not last["text"].endswith(old):
        raise ValueError("R1 C payload does not end with the R1 C wrapper")
    new_last = {"type": "text", "text": last["text"][: -len(old)] + "\n\n" + V.c2_body(instruction, order)}
    return [dict(s) for s in segs[:-1]] + [new_last]


def text_of(segs: list[dict], image_marker: str | None = None) -> str:
    return "".join(s["text"] if s["type"] == "text" else (image_marker or "") for s in segs)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--r1-release", type=Path, default=V.R1_RELEASE_DIR)
    ap.add_argument("--spec-dir", type=Path, default=C.SPEC_DIR)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--implementation-commit", default="uncommitted")
    args = ap.parse_args()
    r1 = args.r1_release
    out = args.output
    V.assert_not_r1_path(out)
    if out.resolve() == r1.resolve() or r1.resolve() in out.resolve().parents:
        raise ValueError("V2 release must not be written inside the R1 release")
    out.mkdir(parents=True, exist_ok=True)
    rel1 = C.load_json(r1 / "release.json")
    checks = {"r1_release_json_sha256": C.sha256_file(r1 / "release.json") == V.R1_RELEASE_JSON_SHA256,
              "r1_release_content_sha256": rel1["release_content_sha256"] == V.R1_RELEASE_CONTENT_SHA256,
              "r1_files_match": all(C.sha256_file(r1 / n) == h for n, h in rel1["files"].items())}
    if not all(checks.values()):
        raise RuntimeError(f"R1 release verification failed: {checks}")
    catalog = C.load_catalog(args.spec_dir)
    tuples = verify_tuples(catalog)
    if not all(t["matches_catalog"] and t["catalog_sha256_matches"] for t in tuples) or len(tuples) != 46:
        raise RuntimeError("instruction tuple verification failed; record a versioned amendment before inference")
    r1rows = {r["query_id"]: r for r in C.read_jsonl(r1 / "query_manifest.jsonl")}
    images = C.load_json(r1 / "images.json")
    frames = C.load_json(r1 / "frames.json")["frames"]
    instr = [i for i in catalog["original_instructions"] if i["scene"] in V.SCENES]
    placement = catalog["placement_controls"]
    vocab = {s: next(i["object_vocabulary"] for i in catalog["original_instructions"] if i["scene"] == s) for s in V.SCENES}
    init_frames = {s: sorted(f["frame_id"] for f in frames.values() if f.get("bank") == "initial" and f["scene_id"] == s) for s in V.SCENES}
    sec_frames = {s: sorted(f["frame_id"] for f in frames.values() if f.get("bank") == "secondary" and f["scene_id"] == s) for s in V.SCENES}
    assert sum(map(len, init_frames.values())) == 24 and sum(map(len, sec_frames.values())) == 48
    rows: list[dict] = []
    dedup: dict[str, dict] = {}

    def add(query_id, kind, bank, condition, order, family, item, src, segs, gold, answerable, exclusion, extra=None):
        scene = item.get("scene") or item.get("scene_id")
        goal = item.get("goal") or item.get("goal_id")
        constraint = V.output_constraint(kind, vocab[scene])
        rows.append({
            "query_id": query_id, "order_key": C.order_key(query_id), "kind": kind, "bank": bank, "condition": condition,
            "option_order": order, "option_mapping": V.C2_ORDERS[order] if kind == "C2" else None, "family": family,
            "scene_id": scene, "goal_id": goal, "physical_start_id": src["physical_start_id"] if src else None,
            "frame_id": src["frame_id"] if src else None, "source_episode_id": src.get("source_episode_id") if src else None,
            "requested_time_s": src.get("requested_time_s") if src else None, "observed_time_s": src.get("observed_time_s") if src else None,
            "original_prompt_id": item["prompt_id"], "display_form": item["display_form"], "instruction_utf8": item["prompt"],
            "instruction_utf8_sha256": C.sha256_text(item["prompt"]), "segments": segs,
            "full_prompt": P.full_prompt_text(segs), "full_prompt_sha256": C.sha256_text(P.full_prompt_text(segs)),
            "view_paths_and_sha256": [{"view": s["view"], "image_id": s["image_id"], "path": images[s["image_id"]]["path"],
                                       "raw_rgb_sha256": images[s["image_id"]]["raw_rgb_sha256"],
                                       "png_sha256": images[s["image_id"]]["png_sha256"]} for s in segs if s["type"] == "image"],
            "output_constraint": constraint, "output_constraint_sha256": V.constraint_sha256(constraint),
            "gold_answer": gold, "answerable": answerable, "exclusion_reason": exclusion,
            "annotation_version": V.V2_LABEL_VERSION, "source_r1_query_id": src["query_id"] if src else None,
            "pair_id": None, "item_key": None, **(extra or {})})

    def add_dedup(query_id, segs, **kw):
        h = C.sha256_text(json.dumps(segs, sort_keys=True))
        if query_id in dedup:
            if dedup[query_id]["hash"] != h:
                raise RuntimeError(f"{query_id}: no-image payload differs across starts; cannot deduplicate")
            dedup[query_id]["sources"].append(kw["src"]["query_id"])
            return
        dedup[query_id] = {"hash": h, "sources": [kw["src"]["query_id"]]}
        src = kw.pop("src")
        add(query_id, segs=segs, src=None, extra={"dedup_source_r1_query_ids": dedup[query_id]["sources"],
                                                    "condition_derived_from": src["query_id"]}, **kw)

    pair = lambda prefix, scene, goal: f"{prefix}.{scene}-{goal}"  # noqa: E731
    for item in instr:
        s, g, pid = item["scene"], item["goal"], item["prompt_id"]
        for fid in init_frames[s]:
            src = r1rows[f"B.initial.{fid}.{pid}"]
            ih = src["segments"]
            for cond, segs in (("IH", ih), ("I", remove_headers(ih))):
                add(f"B2.{cond}.{fid}.{pid}", "B2", "initial", cond, None, "original", item, src, segs, item["gold_B"], True, None,
                    {"pair_id": pair(f"B2.{cond}.{fid}", s, g)})
            for cond, segs in (("H", remove_images(ih)), ("T", remove_images(remove_headers(ih)))):
                add_dedup(f"B2.{cond}.{pid}", segs, kind="B2", bank="no_image", condition=cond, order=None, family="original",
                          item=item, gold=item["gold_B"], answerable=True, exclusion=None, src=src)
        for bank, flist in (("initial", init_frames[s]), ("secondary", sec_frames[s])):
            for fid in flist:
                src = r1rows[f"C.{bank}.{fid}.{pid}"]
                gold = {"yes": "match", "no": "nonmatch"}[src["gold_answer"]]
                for order in (0, 1):
                    segs = replace_c_body(src["segments"], item["prompt"], order)
                    add(f"C2.{bank}.o{order}.{fid}.{pid}", "C2", bank, "R1-presentation", order, "original", item, src, segs,
                        gold, bool(src["answerable"]), src["exclusion_reason"],
                        {"pair_id": pair(f"C2.{bank}.o{order}.{fid}", s, g), "item_key": f"C2.{bank}.{fid}.{pid}",
                         "r1_label_provenance": src.get("label_provenance")})
                    if bank == "initial":
                        add_dedup(f"C2.no_image.o{order}.{pid}", remove_images(segs), kind="C2", bank="no_image",
                                  condition="no_image_camera_text_retained", order=order, family="original", item=item,
                                  gold=None, answerable=None, exclusion="language_prior_control_reused_against_initial_labels", src=src)
    for item in placement:
        s, g, pid = item["scene_id"], item["goal_id"], item["prompt_id"]
        for fid in init_frames[s]:
            src = r1rows[f"PB.initial.{fid}.{pid}"]
            add(f"PB2.IH.{fid}.{pid}", "B2", "initial", "IH", None, "placement", item, src, src["segments"], item["gold_B"], True,
                None, {"pair_id": pair(f"PB2.IH.{fid}", s, g)})
            add_dedup(f"PB2.T.{pid}", remove_images(remove_headers(src["segments"])), kind="B2", bank="no_image", condition="T",
                      order=None, family="placement", item=item, gold=item["gold_B"], answerable=True, exclusion=None, src=src)
    for r in rows:
        if r["pair_id"] is None and r["bank"] == "no_image":
            r["pair_id"] = (f"{r['query_id'].rsplit('.', 1)[0]}.{r['scene_id']}-{r['goal_id']}")
        if r["kind"] == "C2" and r["bank"] == "no_image":
            r["item_key"] = f"C2.no_image.{r['original_prompt_id']}"
    counts = defaultdict(int)
    for r in rows:
        counts[f"{r['kind']}|{r['family']}|{r['bank']}|{r['condition']}"] += 1
    per_lane = len(rows)
    if per_lane != V.MAX_EVAL_PER_LANE:
        raise RuntimeError(f"planned per-lane evaluation queries {per_lane} != {V.MAX_EVAL_PER_LANE}: {dict(counts)}")
    rows.sort(key=lambda r: (0 if r["bank"] != "secondary" else 1, r["order_key"]))

    # ---------------------------------------------------------------- qualification fixtures (D00 development material)
    r1dev = {d["query_id"]: d for d in C.read_jsonl(r1 / "dev_fixtures.jsonl")}
    dev_views = {"S1-D00": {s["view"]: s["image_id"] for s in r1dev["DEV.F1"]["segments"] if s["type"] == "image"},
                 "S3-D00": {s["view"]: s["image_id"] for s in r1dev["DEV.F3"]["segments"] if s["type"] == "image"},
                 "S4-D00": {s["view"]: s["image_id"] for s in r1dev["DEV.F4"]["segments"] if s["type"] == "image"},
                 "S1-D00-t225": {s["view"]: s["image_id"] for s in r1dev["DEV.F6"]["segments"] if s["type"] == "image"}}

    def b_segs(instruction, scene, views, wrist_moving=False):
        return P.build_segments(test="B", instruction=instruction, objects=vocab[scene], current=views, wrist_moving=wrist_moving,
                                current_time_s=15.0 if wrist_moving else None)

    def c_segs(instruction, views, order, wrist_moving=False):
        segs = P.build_segments(test="C", instruction=instruction, current=views, wrist_moving=wrist_moving,
                                current_time_s=15.0 if wrist_moving else None)
        return replace_c_body(segs, instruction, order)

    fx = [
        ("Q1", "B2", "T", None, "S1", remove_images(remove_headers(b_segs("Put the banana in front of the bowl", "S1", dev_views["S1-D00"])))),
        ("Q2", "B2", "IH", None, "S3", b_segs("Place the raisin box to the left of the butter box.", "S3", dev_views["S3-D00"])),
        ("Q3", "B2", "I", None, "S4", remove_headers(b_segs("Put the raisin box behind the mustard bottle.", "S4", dev_views["S4-D00"]))),
        ("Q4", "C2", "initial", 0, "S1", c_segs("Put the banana to the left of the bowl", dev_views["S1-D00"], 0)),
        ("Q5", "C2", "secondary", 1, "S1", c_segs("Put the banana behind the Rubik's cube", dev_views["S1-D00-t225"], 1, True)),
        ("Q6", "C2", "no_image", 1, "S1", remove_images(c_segs("Put the bowl in front of the banana", dev_views["S1-D00"], 1))),
    ]
    dev_rows = []
    for qid, kind, cond, order, scene, segs in fx:
        constraint = V.output_constraint(kind, vocab[scene])
        dev_rows.append({"query_id": f"V2DEV.{qid}", "kind": kind, "condition": cond, "option_order": order, "scene_id": scene,
                         "segments": segs, "full_prompt_sha256": C.sha256_text(P.full_prompt_text(segs)),
                         "output_constraint": constraint, "output_constraint_sha256": V.constraint_sha256(constraint),
                         "image_files": {s["image_id"]: images[s["image_id"]]["path"] for s in segs if s["type"] == "image"},
                         "option_mapping": V.C2_ORDERS[order] if kind == "C2" else None,
                         "purpose": "schema/choice mechanics, image receipt, latency and memory; no accuracy gate; non-catalog wording on D00"})

    # ---------------------------------------------------------------- write
    payload_keys = ("query_id", "order_key", "kind", "bank", "condition", "option_order", "segments", "full_prompt_sha256",
                    "output_constraint", "output_constraint_sha256")
    payloads = []
    for r in rows:
        p = {k: r[k] for k in payload_keys}
        p["image_files"] = {s["image_id"]: images[s["image_id"]]["path"] for s in r["segments"] if s["type"] == "image"}
        payloads.append(p)
    C.write_jsonl(out / "payloads.jsonl", payloads)
    C.write_jsonl(out / "dev_fixtures.jsonl", dev_rows)
    C.write_json_atomic(out / "tuple_verification.json", {"rows": tuples, "all_match_catalog": True, "n": len(tuples),
                                                          "method": "deterministic wording patterns (no model judge)"})
    constraints = {}
    for r in rows:
        constraints[r["output_constraint_sha256"]] = r["output_constraint"]
    content = {"payloads_sha256": C.sha256_file(out / "payloads.jsonl"),
               "dev_fixtures_sha256": C.sha256_file(out / "dev_fixtures.jsonl"),
               "tuple_verification_sha256": C.sha256_file(out / "tuple_verification.json"),
               "gold_sha256": C.canonical_sha256([{k: r[k] for k in ("query_id", "gold_answer", "answerable", "exclusion_reason")} for r in rows]),
               "constraints": constraints, "frozen_text": V.frozen_v2_text(),
               "source_r1_release_content_sha256": V.R1_RELEASE_CONTENT_SHA256}
    release_sha = C.canonical_sha256(content)
    for r in rows:
        r["release_sha256"] = release_sha
    C.write_jsonl(out / "query_manifest.jsonl", rows)
    release = {
        "study_id": C.STUDY_ID, "design_version": V.DESIGN_VERSION, "implementation_version": V.V2_IMPLEMENTATION_VERSION,
        "implementation_commit": args.implementation_commit, "created_utc": C.utc_now(),
        "status": "frozen_provisional_answerability_original_mask", "release_content_sha256": release_sha, "content": content,
        "files": {n: C.sha256_file(out / n) for n in ("payloads.jsonl", "query_manifest.jsonl", "dev_fixtures.jsonl", "tuple_verification.json")},
        "image_root": str(r1), "source_r1": {"release_dir": str(r1), "release_json_sha256": V.R1_RELEASE_JSON_SHA256,
                                             "release_content_sha256": V.R1_RELEASE_CONTENT_SHA256, "checks": checks,
                                             "source_commit": V.R1_SOURCE_COMMIT},
        "v2_spec_files_sha256": {p.name: C.sha256_file(p) for p in sorted(V.SPEC_DIR.glob("*")) if p.is_file()},
        "counts": {"per_lane": per_lane, "by_kind_family_bank_condition": dict(sorted(counts.items())), "lanes": list(V.LANES),
                   "total_planned": per_lane * len(V.LANES), "qualification_fixtures_per_lane": len(dev_rows),
                   "answerable_c2": sum(1 for r in rows if r["kind"] == "C2" and r["answerable"] is True),
                   "excluded_c2": sum(1 for r in rows if r["kind"] == "C2" and r["answerable"] is False)},
        "frozen_settings": {
            "lanes": list(V.LANES), "loaded_parameter_digests_expected": V.R1_LOADED_DIGESTS,
            "decoding": {"temperature": 0.0, "greedy": True, "max_new_tokens": V.MAX_NEW_TOKENS, "n": 1, "seed": C.ORDER_SEED,
                         "chat_template_kwargs": {"enable_thinking": False}},
            "structured_outputs": {**V.ENGINE_STRUCTURED, "b2": "JSON schema: object with required target/reference/relation; enums = "
                                   "full sorted scene object vocabulary (including distractors) for target and reference, full relation "
                                   "vocabulary; additionalProperties false; xgrammar strict schema order; compact separators",
                                   "c2": "choice A|B|U (vLLM choice -> EBNF root ::= \"A\" | \"B\" | \"U\")"},
            "order": "primary (B2 all, C2 initial, C2 no-image) by sha256('6106|'+query_id), then C2 secondary by the same key",
            "budgets": {"max_eval_per_lane": V.MAX_EVAL_PER_LANE, "max_eval_total": V.MAX_EVAL_TOTAL, "max_qual_per_lane": V.MAX_QUAL_PER_LANE,
                        "max_retries_total": V.MAX_RETRIES_TOTAL, "max_retries_per_query": V.MAX_RETRIES_PER_QUERY,
                        "max_consecutive_infra": V.MAX_CONSECUTIVE_INFRA, "max_attempts_total": V.MAX_ATTEMPTS_TOTAL},
            "b2": "IH = R1 B payload; H = IH minus image segments; I = IH minus the three camera header strings; T = both removed; "
                  "H/T and placement T deduplicated across starts (one generation per instruction, reused for paired contrasts)",
            "c2": "R1 C payload (same views/headers/presentation) with the R1 C wrapper replaced by the fixed V2 wrapper; orders 0/1 "
                  "swap the complete A/B meanings; U unchanged; no-image = initial payload minus image segments (camera text kept), "
                  "deduplicated across starts",
            "answerability": "original mask = R1 geometry/boundary/visibility/transit exclusions; review mask applied at analysis by CPU rescoring",
        },
    }
    C.write_json_atomic(out / "release.json", release)
    print(json.dumps({"release_content_sha256": release_sha, "release_json_sha256": C.sha256_file(out / "release.json"),
                      "per_lane": per_lane, "counts": release["counts"]["by_kind_family_bank_condition"],
                      "c2_answerable": release["counts"]["answerable_c2"], "c2_excluded": release["counts"]["excluded_c2"]}, indent=1))


if __name__ == "__main__":
    sys.exit(main())
