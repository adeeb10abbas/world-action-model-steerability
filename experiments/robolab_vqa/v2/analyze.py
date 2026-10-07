"""Analyse RQA V2 responses with the frozen scoring rules (CPU). Also the CPU rescoring path for review masks.

python -m experiments.robolab_vqa.v2.analyze --release <r2>/release.json --run <run-dir> --output <dir> \
    [--mask <ledger>/mask.json] [--r1-scored <r1 analysis>/scored_rows.csv]
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from .. import common as C
from . import config as V
from . import scoring as S

LATERAL_GOALS = {("S1", "L"), ("S1", "R"), ("S1", "F"), ("S1", "B"), ("S3", "L"), ("S3", "R"), ("S4", "L"), ("S4", "R")}
MARKER = re.compile(r"<\|vision_start\|>.*?<\|vision_end\|>", re.DOTALL)


def load_final(path: Path) -> dict:
    out = {}
    for r in C.read_jsonl(path):
        if r["status"] == "delivered" or r["query_id"] not in out:
            out[r["query_id"]] = r
    return out


# ---------------------------------------------------------------------- B2
def b2_items(rows: list[dict], resp: dict, vocab: dict) -> list[dict]:
    items = []
    for q in rows:
        if q["kind"] != "B2":
            continue
        r = resp.get(q["query_id"])
        delivered = bool(r and r["status"] == "delivered")
        parsed = S.parse_b2(r.get("raw_response"), vocab[q["scene_id"]]) if delivered else {"valid": False, "answer": None, "reason": "missing"}
        f = S.b2_fields(parsed, q["gold_answer"]) if delivered else {}
        items.append({"query_id": q["query_id"], "family": q["family"], "condition": q["condition"], "scene": q["scene_id"],
                      "goal": q["goal_id"], "form": q["display_form"], "prompt_id": q["original_prompt_id"],
                      "start": q["physical_start_id"], "frame": q["frame_id"], "delivered": delivered, "valid": parsed["valid"],
                      "invalid_reason": parsed["reason"], "answer": parsed["answer"], "truncated": bool(r and r.get("truncated")),
                      "error_class": S.b2_error_class(parsed, q["gold_answer"]) if delivered else "missing", **f})
    return items


def b2_text_summary(items: list[dict], cond: str, family: str = "original") -> dict:
    sel = [i for i in items if i["condition"] == cond and i["family"] == family]
    out = {"n": len(sel), "delivered": sum(i["delivered"] for i in sel), "valid": sum(i["valid"] for i in sel)}
    for subset, pred in (("all_goals", lambda i: True), ("lateral_8_goals", lambda i: (i["scene"], i["goal"]) in LATERAL_GOALS)):
        s = [i for i in sel if pred(i)]
        d = {"n": len(s)}
        for k in ("tuple", "target", "reference", "relation"):
            d[f"{k}_correct"] = int(sum(i.get(k, 0) for i in s))
        forms = sorted({i["form"] for i in s})
        d["by_form"] = {f: {"n": sum(1 for i in s if i["form"] == f), "tuple_correct": int(sum(i.get("tuple", 0) for i in s if i["form"] == f))}
                        for f in forms}
        pairs = (("TF", "RF"), ("DIR", "TF")) if family == "original" else (("reference_early", "reference_late"),)
        for a, b in pairs:
            by = defaultdict(dict)
            for i in s:
                by[(i["scene"], i["goal"])][i["form"]] = i
            tab = Counter()
            for g in by.values():
                if a in g and b in g:
                    tab[f"{a}={int(g[a].get('tuple', 0))},{b}={int(g[b].get('tuple', 0))}"] += 1
            d[f"paired_{a}_{b}"] = dict(sorted(tab.items()))
        d["error_classes"] = dict(Counter(i["error_class"] for i in s))
        d["error_classes_by_form"] = {f: dict(Counter(i["error_class"] for i in s if i["form"] == f)) for f in forms}
        out[subset] = d
    return out


def b2_image_metrics(items: list[dict], cond: str, idx: dict, family: str = "original") -> dict:
    sel = [i for i in items if i["condition"] == cond and i["family"] == family and i["delivered"]]
    out = {}
    for subset, pred in (("all_goals", lambda i: True), ("lateral_8_goals", lambda i: (i["scene"], i["goal"]) in LATERAL_GOALS)):
        s = [i for i in sel if pred(i)]
        d = {}
        for k in ("tuple", "target", "reference", "relation"):
            d[f"{k}_accuracy"] = S.hier_mean([(i["scene"], i["goal"], i["start"], i[k]) for i in s], idx)
        forms = sorted({i["form"] for i in s})
        for f in forms:
            d[f"tuple_accuracy_{f}"] = S.hier_mean([(i["scene"], i["goal"], i["start"], i["tuple"]) for i in s if i["form"] == f], idx)
        pairs = (("TF", "RF"), ("DIR", "TF"), ("DIR", "RF")) if family == "original" else (("reference_early", "reference_late"),)
        for a, b in pairs:
            by = defaultdict(dict)
            for i in s:
                by[(i["scene"], i["goal"], i["start"])][i["form"]] = i
            units_gap, units_both = [], []
            for (sc, g, st), x in by.items():
                if a in x and b in x:
                    units_gap.append((sc, g, st, x[a]["tuple"] - x[b]["tuple"]))
                    units_both.append((sc, g, st, float(x[a]["tuple"] == 1.0 and x[b]["tuple"] == 1.0)))
            d[f"gap_{a}_minus_{b}"] = S.hier_mean(units_gap, idx)
            d[f"both_correct_{a}_{b}"] = S.hier_mean(units_both, idx)
            d[f"pairs_{a}_{b}"] = len(units_gap)
        d["error_classes_by_form"] = {f: dict(Counter(i["error_class"] for i in s if i["form"] == f)) for f in forms}
        out[subset] = d
    return out


def b2_contrasts(items: list[dict], idx: dict) -> dict:
    """Image contrasts I-T, IH-H; header contrasts IH-I (paired cells) and H-T (finite). No-image answers reused per cell."""
    cell = defaultdict(dict)   # (prompt_id, start) -> cond -> item
    text = defaultdict(dict)   # prompt_id -> cond -> item
    for i in items:
        if i["family"] != "original" or not i["delivered"]:
            continue
        if i["condition"] in ("I", "IH"):
            cell[(i["prompt_id"], i["start"])][i["condition"]] = i
        else:
            text[i["prompt_id"]][i["condition"]] = i
    out = {"reuse_note": "T and H answers are one generation per instruction, reused against each of the 8 initial cells for paired "
                         "image contrasts; intervals are conditional on those fixed text-only answers"}
    for name, (a, b) in {"image_I_minus_T": ("I", "T"), "image_IH_minus_H": ("IH", "H"), "header_IH_minus_I": ("IH", "I"),
                         "header_H_minus_T": ("H", "T")}.items():
        res = {}
        for subset, pred in (("all_goals", lambda sc, g: True), ("lateral_8_goals", lambda sc, g: (sc, g) in LATERAL_GOALS)):
            d = {}
            for form in (None, "DIR", "TF", "RF"):
                units = []
                if a in ("I", "IH"):
                    for (pid, st), x in cell.items():
                        if a not in x:
                            continue
                        ya = x[a]
                        yb = x.get(b) if b in ("I", "IH") else text.get(pid, {}).get(b)
                        if yb is None or not pred(ya["scene"], ya["goal"]) or (form and ya["form"] != form):
                            continue
                        units.append((ya["scene"], ya["goal"], st, ya["tuple"] - yb["tuple"]))
                    d[f"tuple_{form or 'all'}"] = S.hier_mean(units, idx)
                else:
                    diffs = []
                    for pid, x in text.items():
                        if a in x and b in x and pred(x[a]["scene"], x[a]["goal"]) and (not form or x[a]["form"] == form):
                            diffs.append(x[a]["tuple"] - x[b]["tuple"])
                    d[f"tuple_{form or 'all'}"] = {"finite_items": len(diffs), "sum_difference": float(sum(diffs)),
                                                   "a_only_correct": sum(1 for v in diffs if v > 0), "b_only_correct": sum(1 for v in diffs if v < 0)}
            # TF-RF gap difference between conditions
            units = []
            if a in ("I", "IH"):
                by = defaultdict(dict)
                for (pid, st), x in cell.items():
                    if a in x:
                        by[(x[a]["scene"], x[a]["goal"], st)][x[a]["form"]] = (x[a], x.get(b) if b in ("I", "IH") else text.get(pid, {}).get(b))
                for (sc, g, st), f in by.items():
                    if "TF" in f and "RF" in f and all(v[1] is not None for v in (f["TF"], f["RF"])) and pred(sc, g):
                        ga = f["TF"][0]["tuple"] - f["RF"][0]["tuple"]
                        gb = f["TF"][1]["tuple"] - f["RF"][1]["tuple"]
                        units.append((sc, g, st, ga - gb))
                d["tf_rf_gap_difference"] = S.hier_mean(units, idx)
            res[subset] = d
        out[name] = res
    return out


# ---------------------------------------------------------------------- C2
def c2_items(rows: list[dict], resp: dict, mask: dict | None, mask_name: str) -> list[dict]:
    """One record per (bank, frame, prompt) item with both orders."""
    by = defaultdict(dict)
    for q in rows:
        if q["kind"] != "C2" or q["bank"] == "no_image":
            continue
        by[q["item_key"]][q["option_order"]] = q
    items = []
    for key, orders in by.items():
        q0 = orders[0]
        ans = {}
        for o, q in orders.items():
            r = resp.get(q["query_id"])
            if r and r["status"] == "delivered":
                p = S.parse_c2(r.get("raw_response"), q["option_mapping"])
                ans[o] = p["semantic"] if p["valid"] else "invalid"
            else:
                ans[o] = None
        answerable = bool(q0["answerable"])
        reason = q0["exclusion_reason"]
        if mask_name != "original" and answerable:
            m = (mask or {}).get("items", {}).get(f"{q0['frame_id']}|{q0['goal_id']}")
            key_m = "C_strict" if mask_name == "strict" else "C"
            if m is None:
                answerable, reason = False, "not_reviewed"
            elif not m[key_m]:
                answerable, reason = False, f"review_{mask_name}_excluded"
        corr = {o: (None if a is None else float(a == q0["gold_answer"])) for o, a in ans.items()}
        both = all(corr.get(o) is not None for o in (0, 1))
        items.append({"item_key": key, "bank": q0["bank"], "scene": q0["scene_id"], "goal": q0["goal_id"], "form": q0["display_form"],
                      "prompt_id": q0["original_prompt_id"], "start": q0["physical_start_id"], "frame": q0["frame_id"],
                      "observed_time_s": q0["observed_time_s"], "gold": q0["gold_answer"], "answerable": answerable,
                      "exclusion_reason": reason, "answer_o0": ans.get(0), "answer_o1": ans.get(1),
                      "correct_o0": corr.get(0), "correct_o1": corr.get(1), "both_orders_delivered": both,
                      "correct": (corr[0] + corr[1]) / 2 if both else None,
                      "order_agreement": (ans[0] == ans[1]) if both else None})
    return items


def c2_bank_metrics(items: list[dict], bank: str, idx: dict) -> dict:
    sel = [i for i in items if i["bank"] == bank]
    sc = [i for i in sel if i["answerable"] and i["correct"] is not None]
    out = {"items_proposed": len(sel), "items_answerable": sum(i["answerable"] for i in sel), "items_scored": len(sc),
           "items_missing_an_order": sum(1 for i in sel if i["answerable"] and i["correct"] is None)}
    out["balanced_accuracy_all_forms"] = S.class_recall([(i["scene"], i["goal"], i["start"], i["gold"], i["correct"]) for i in sc],
                                                        ("match", "nonmatch"), idx)
    out["accuracy_all_forms"] = S.hier_mean([(i["scene"], i["goal"], i["start"], i["correct"]) for i in sc], idx)
    for f in ("DIR", "TF", "RF"):
        s = [i for i in sc if i["form"] == f]
        out[f"balanced_accuracy_{f}"] = S.class_recall([(i["scene"], i["goal"], i["start"], i["gold"], i["correct"]) for i in s],
                                                       ("match", "nonmatch"), idx)
        out[f"accuracy_{f}"] = S.hier_mean([(i["scene"], i["goal"], i["start"], i["correct"]) for i in s], idx)
    for o in (0, 1):
        s = [i for i in sel if i["answerable"] and i[f"correct_o{o}"] is not None]
        out[f"order{o}_balanced_accuracy"] = S.class_recall([(i["scene"], i["goal"], i["start"], i["gold"], i[f"correct_o{o}"]) for i in s],
                                                            ("match", "nonmatch"), idx)
        out[f"order{o}_accuracy"] = S.hier_mean([(i["scene"], i["goal"], i["start"], i[f"correct_o{o}"]) for i in s], idx)
        out[f"order{o}_answer_distribution"] = dict(Counter(str(i[f"answer_o{o}"]) for i in sel))
    out["answer_distribution_all_items"] = dict(Counter(str(a) for i in sel for a in (i["answer_o0"], i["answer_o1"])))
    out["answer_distribution_answerable_by_gold"] = {g: dict(Counter(str(a) for i in sel if i["answerable"] and i["gold"] == g
                                                                  for a in (i["answer_o0"], i["answer_o1"]))) for g in ("match", "nonmatch")}
    agree = [i["order_agreement"] for i in sel if i["order_agreement"] is not None]
    out["semantic_agreement_across_orders"] = {"items": len(agree), "agree": int(sum(agree)),
                                               "rate": (sum(agree) / len(agree)) if agree else None}
    # constant baselines with the declared weights
    prev = S.class_recall([(i["scene"], i["goal"], i["start"], i["gold"], 1.0) for i in sc], ("match", "nonmatch"), None)
    w_match = prev["recall_match"]["declared_weight_share"]
    w_non = prev["recall_nonmatch"]["declared_weight_share"]
    tot = (w_match or 0) + (w_non or 0)
    out["constant_baselines"] = {"always_match_accuracy": (w_match / tot) if tot else None,
                                 "always_nonmatch_accuracy": (w_non / tot) if tot else None, "constant_balanced_accuracy": 0.5}
    # paired form gaps (order-averaged within item)
    by = defaultdict(dict)
    for i in sc:
        by[(i["scene"], i["goal"], i["start"], i["frame"])][i["form"]] = i
    for a, b in (("TF", "RF"), ("DIR", "TF"), ("DIR", "RF")):
        ug, ub, ud = [], [], []
        for (scn, g, st, fr), x in by.items():
            if a in x and b in x:
                ug.append((scn, g, st, x[a]["correct"] - x[b]["correct"]))
                ub.append((scn, g, st, np.mean([x[a][f"correct_o{o}"] * x[b][f"correct_o{o}"] for o in (0, 1)])))
                ud.append((scn, g, st, np.mean([float(x[a][f"answer_o{o}"] != x[b][f"answer_o{o}"]) for o in (0, 1)])))
        out[f"gap_{a}_minus_{b}"] = S.hier_mean(ug, idx)
        out[f"both_correct_{a}_{b}"] = S.hier_mean(ub, idx)
        out[f"disagreement_{a}_{b}"] = S.hier_mean(ud, idx)
        out[f"pairs_{a}_{b}"] = len(ug)
    return out


def truth_changing_pairs(items: list[dict]) -> dict:
    """Per start-goal: earliest matching and earliest nonmatching answerable frame (initial/50%/100%; frame ID breaks ties)."""
    frames = defaultdict(dict)
    for i in items:
        if i["answerable"]:
            frames[(i["scene"], i["goal"], i["start"])].setdefault(i["frame"], {"t": i["observed_time_s"], "gold": i["gold"], "forms": {}})
            frames[(i["scene"], i["goal"], i["start"])][i["frame"]]["forms"][i["form"]] = i
    pairs = []
    for key, fr in frames.items():
        order = sorted(fr.items(), key=lambda kv: (kv[1]["t"], kv[0]))
        m = next((f for f in order if f[1]["gold"] == "match"), None)
        n = next((f for f in order if f[1]["gold"] == "nonmatch"), None)
        if m is None or n is None:
            continue
        rec = {"scene": key[0], "goal": key[1], "start": key[2], "match_frame": m[0], "nonmatch_frame": n[0]}
        for form in ("DIR", "TF", "RF"):
            a, b = m[1]["forms"].get(form), n[1]["forms"].get(form)
            if a and b and a["correct"] is not None and b["correct"] is not None:
                rec[f"both_correct_{form}"] = float(np.mean([a[f"correct_o{o}"] * b[f"correct_o{o}"] for o in (0, 1)]))
        pairs.append(rec)
    summ = {"available_pairs": len(pairs), "start_goals_considered": len(frames)}
    for form in ("DIR", "TF", "RF"):
        v = [p[f"both_correct_{form}"] for p in pairs if f"both_correct_{form}" in p]
        summ[form] = {"pairs": len(v), "mean_both_correct": (float(np.mean(v)) if v else None),
                      "pairs_both_correct_in_both_orders": int(sum(1 for x in v if x == 1.0))}
    summ["status"] = "unavailable_no_pairs" if not pairs else "available"
    return {"summary": summ, "pairs": pairs}


def c2_no_image(rows: list[dict], resp: dict, items: list[dict], idx: dict) -> dict:
    noimg = {}
    for q in rows:
        if q["kind"] == "C2" and q["bank"] == "no_image":
            r = resp.get(q["query_id"])
            if r and r["status"] == "delivered":
                p = S.parse_c2(r.get("raw_response"), q["option_mapping"])
                noimg[(q["original_prompt_id"], q["option_order"])] = p["semantic"] if p["valid"] else "invalid"
            else:
                noimg[(q["original_prompt_id"], q["option_order"])] = None
    dist = {o: dict(Counter(str(v) for (p, oo), v in noimg.items() if oo == o)) for o in (0, 1)}
    by_form = {}
    form_of = {q["original_prompt_id"]: q["display_form"] for q in rows if q["kind"] == "C2"}
    for f in ("DIR", "TF", "RF"):
        by_form[f] = dict(Counter(str(v) for (p, o), v in noimg.items() if form_of[p] == f))
    reuse = []
    for i in items:
        if i["bank"] != "initial" or not i["answerable"]:
            continue
        a0, a1 = noimg.get((i["prompt_id"], 0)), noimg.get((i["prompt_id"], 1))
        if a0 is None or a1 is None:
            continue
        reuse.append((i["scene"], i["goal"], i["start"], i["gold"], (float(a0 == i["gold"]) + float(a1 == i["gold"])) / 2))
    return {"answer_distribution_by_order": dist, "answer_distribution_by_form": by_form, "expected_evidential_answer": "unknown",
            "unknown_rate": sum(1 for v in noimg.values() if v == "unknown") / max(len(noimg), 1),
            "reused_against_initial_labels": {"accuracy": S.hier_mean([u[:3] + (u[4],) for u in reuse], idx),
                                              "balanced_accuracy": S.class_recall(reuse, ("match", "nonmatch"), idx),
                                              "note": "60 fixed answers (30 per order) reused; disclosed language-prior control"}}


# ---------------------------------------------------------------------- A rescoring (existing R1 answers)
def a_rescore(r1_scored: Path, lanes, mask: dict | None, idx: dict) -> dict:
    rows = []
    with open(r1_scored) as f:
        for x in csv.DictReader(f):
            if x["lane"] in lanes and x["test"] == "A" and x["scene"] in V.SCENES and x["bank"] in ("initial", "secondary"):
                rows.append(x)
    out = {}
    for lane in lanes:
        out[lane] = {}
        for bank in ("initial", "secondary"):
            out[lane][bank] = {}
            for mname in ("original", "revised", "strict"):
                if mname != "original" and mask is None:
                    out[lane][bank][mname] = {"status": "not_available_no_review_mask"}
                    continue
                sel = []
                for x in rows:
                    if x["lane"] != lane or x["bank"] != bank or x["answerable"] != "True" or x["status"] != "delivered":
                        continue
                    if mname != "original":
                        m = mask["items"].get(f"{x['frame_id']}|{x['goal']}")
                        if m is None or not m["A_strict" if mname == "strict" else "A"]:
                            continue
                    sel.append(x)
                units = [(x["scene"], x["goal"], x["physical_start_id"], float(x["correct"])) for x in sel]
                cls = [(x["scene"], x["goal"], x["physical_start_id"], x["gold"], float(x["correct"])) for x in sel]
                pairs = defaultdict(dict)
                for x in sel:
                    pairs[(x["scene"], x["goal"], x["physical_start_id"], x["frame_id"])][x["form"]] = float(x["correct"])
                gap = [(k[0], k[1], k[2], v["target_subject"] - v["reference_subject"]) for k, v in pairs.items()
                       if "target_subject" in v and "reference_subject" in v]
                out[lane][bank][mname] = {"items": len(sel), "accuracy": S.hier_mean(units, idx),
                                          "balanced_accuracy": S.class_recall(cls, ("yes", "no"), idx),
                                          "target_minus_reference_subject_gap": S.hier_mean(gap, idx), "pairs": len(gap)}
    return out


# ---------------------------------------------------------------------- rendered-prompt equality (post hoc)
def rendered_checks(run: Path, lane: str, rows: list[dict]) -> dict:
    rp = {}
    for r in C.read_jsonl(run / lane / "rendered_prompts.jsonl"):
        rp[r["query_id"]] = r["text"]
    strip = lambda t: MARKER.sub("", t)  # noqa: E731
    by = {q["query_id"]: q for q in rows}
    res = Counter()
    for q in rows:
        if q["kind"] != "B2" or q["condition"] != "IH" or q["family"] != "original":
            continue
        fid, pid = q["frame_id"], q["original_prompt_id"]
        t = {c: rp.get(qid) for c, qid in (("IH", q["query_id"]), ("I", f"B2.I.{fid}.{pid}"), ("H", f"B2.H.{pid}"), ("T", f"B2.T.{pid}"))}
        if any(v is None for v in t.values()):
            res["missing"] += 1
            continue
        res["IH_eq_H_after_markers"] += strip(t["IH"]) == t["H"]
        res["I_eq_T_after_markers"] += strip(t["I"]) == t["T"]
        d1 = t["IH"]
        for h in V.HEADER_STRINGS:
            d1 = d1.replace(h, "", 1)
        res["IH_minus_headers_eq_I"] += d1 == t["I"]
        d2 = t["H"]
        for h in V.HEADER_STRINGS:
            d2 = d2.replace(h, "", 1)
        res["H_minus_headers_eq_T"] += d2 == t["T"]
        res["cells"] += 1
    return dict(res)


def coverage(rows: list[dict], resp: dict, lane: str) -> list[dict]:
    groups = defaultdict(list)
    for q in rows:
        groups[(q["kind"], q["family"], q["bank"], q["condition"])].append(q)
    out = []
    for (kind, fam, bank, cond), qs in sorted(groups.items()):
        rs = [resp.get(q["query_id"]) for q in qs]
        dl = [r for r in rs if r and r["status"] == "delivered"]
        out.append({"lane": lane, "kind": kind, "family": fam, "bank": bank, "condition": cond, "planned": len(qs),
                    "answerable_original_mask": sum(1 for q in qs if q["answerable"] is True), "delivered": len(dl),
                    "valid": sum(1 for r in dl if (r.get("parsed_response") or {}).get("valid")),
                    "invalid": sum(1 for r in dl if not (r.get("parsed_response") or {}).get("valid")),
                    "unknown_code": sum(1 for r in dl if (r.get("parsed_response") or {}).get("semantic") == "unknown"),
                    "truncated": sum(1 for r in dl if r.get("truncated")), "infrastructure_missing": len(qs) - len(dl)})
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--release", type=Path, required=True)
    ap.add_argument("--run", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--mask", type=Path, default=None)
    ap.add_argument("--r1-scored", type=Path, default=V.R1_RUN_DIR / "analysis" / "scored_rows.csv")
    ap.add_argument("--bootstrap", type=int, default=C.BOOTSTRAP_REPLICATES)
    args = ap.parse_args()
    V.assert_not_r1_path(args.output)
    rel = C.load_json(args.release)
    rows = C.read_jsonl(args.release.parent / "query_manifest.jsonl")
    catalog = C.load_catalog()
    vocab = {s: sorted(next(i["object_vocabulary"] for i in catalog["original_instructions"] if i["scene"] == s)) for s in V.SCENES}
    mask = C.load_json(args.mask) if args.mask and args.mask.exists() else None
    idx = S.bootstrap_index(args.bootstrap)
    res = {"study_id": C.STUDY_ID, "design_version": V.DESIGN_VERSION, "parser_version": V.V2_PARSER_VERSION,
           "release_content_sha256": rel["release_content_sha256"], "created_utc": C.utc_now(),
           "bootstrap": {"replicates": args.bootstrap, "seed": C.BOOTSTRAP_SEED, "unit": "physical start within S1/S3/S4"},
           "mask": {"original": "R1 mask", "revised": "R1 mask AND review-answerable" if mask else "not available",
                    "strict": "revised minus geometry discrepancies" if mask else "not available",
                    "mask_sha256": C.sha256_file(args.mask) if mask else None,
                    "reviewer_types": mask.get("reviewer_types") if mask else None,
                    "human_coverage": mask.get("human_coverage") if mask else None,
                    "machine_coverage": mask.get("machine_coverage") if mask else None},
           "lanes": {}}
    cov_rows, b2_rows, c2_rows, pair_rows = [], [], [], []
    for lane in V.LANES:
        resp = load_final(args.run / lane / "responses.jsonl")
        att = C.read_jsonl(args.run / lane / "attempts.jsonl")
        L = {"role": V.LANE_ROLE[lane], "attempts": dict(Counter(a["phase"] for a in att)), "ledger_entries": len(att)}
        cov_rows += coverage(rows, resp, lane)
        bi = b2_items(rows, resp, vocab)
        L["b2_text"] = {c: b2_text_summary(bi, c) for c in ("T", "H")}
        L["b2_placement_text"] = b2_text_summary(bi, "T", "placement")
        L["b2_image"] = {c: b2_image_metrics(bi, c, idx) for c in ("I", "IH")}
        L["b2_placement_image"] = b2_image_metrics(bi, "IH", idx, "placement")
        L["b2_contrasts"] = b2_contrasts(bi, idx)
        b2_rows += [{"lane": lane, **{k: (json.dumps(v) if isinstance(v, dict) else v) for k, v in i.items()}} for i in bi]
        L["c2"] = {}
        for mname in ("original", "revised", "strict"):
            if mname != "original" and mask is None:
                L["c2"][mname] = {"status": "not_available_no_review_mask"}
                continue
            ci = c2_items(rows, resp, mask, mname)
            L["c2"][mname] = {"initial": c2_bank_metrics(ci, "initial", idx), "secondary": c2_bank_metrics(ci, "secondary", idx),
                              "truth_changing_pairs": truth_changing_pairs(ci)}
            if mname == "original":
                L["c2_no_image"] = c2_no_image(rows, resp, ci, idx)
                c2_rows += [{"lane": lane, "mask": mname, **i} for i in ci]
                pair_rows += [{"lane": lane, **p} for p in L["c2"][mname]["truth_changing_pairs"]["pairs"]]
            else:
                c2_rows += [{"lane": lane, "mask": mname, **i} for i in ci]
        L["rendered_prompt_checks"] = rendered_checks(args.run, lane, rows)
        res["lanes"][lane] = L
    if args.r1_scored.exists():
        res["a_rescore_r1_answers"] = a_rescore(args.r1_scored, V.LANES, mask, idx)
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    C.write_json_atomic(out / "results_v2.json", S.strip_boot(res))
    for name, data in (("coverage_v2.csv", cov_rows), ("b2_items.csv", b2_rows), ("c2_items.csv", c2_rows), ("c2_truth_pairs.csv", pair_rows)):
        write_csv(out / name, data)
    write_csv(out / "metrics_long_v2.csv", flatten(S.strip_boot(res)))
    print(json.dumps(compact(res), indent=1))


def compact(res: dict) -> dict:
    g = lambda d: None if not d or d.get("estimate") is None else round(d["estimate"], 3)  # noqa: E731
    out = {}
    for lane, L in res["lanes"].items():
        t = L["b2_text"]["T"]["all_goals"]["by_form"]
        out[lane] = {"B2_T_TF": t.get("TF", {}).get("tuple_correct"), "B2_T_RF": t.get("RF", {}).get("tuple_correct"),
                     "B2_IH_TF": g(L["b2_image"]["IH"]["all_goals"].get("tuple_accuracy_TF")),
                     "B2_IH_RF": g(L["b2_image"]["IH"]["all_goals"].get("tuple_accuracy_RF")),
                     "C2_init_BA": g(L["c2"]["original"]["initial"]["balanced_accuracy_all_forms"]["balanced_accuracy"]),
                     "C2_init_gap": g(L["c2"]["original"]["initial"]["gap_TF_minus_RF"]),
                     "C2_sec_BA": g(L["c2"]["original"]["secondary"]["balanced_accuracy_all_forms"]["balanced_accuracy"])}
    return out


def flatten(res: dict) -> list[dict]:
    rows = []

    def walk(prefix, obj):
        if isinstance(obj, dict):
            if "estimate" in obj and not isinstance(obj.get("estimate"), dict):
                ci = obj.get("ci95") or [None, None]
                rows.append({"metric": "/".join(prefix), "estimate": obj.get("estimate"), "ci_low": ci[0], "ci_high": ci[1],
                             "n_items": obj.get("n_items"), "support": obj.get("support"), "status": obj.get("status")})
            for k, v in obj.items():
                if k in ("pairs",) and isinstance(v, list):
                    continue
                walk(prefix + [k], v)
    walk([], res)
    return rows


def write_csv(path: Path, data: list[dict]) -> None:
    if not data:
        path.write_text("")
        return
    keys = []
    for r in data:
        for k in r:
            if k not in keys:
                keys.append(k)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in data:
            w.writerow({k: (json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in r.items()})


if __name__ == "__main__":
    sys.exit(main())
