"""RQA V2 report assets (CPU only; never loads a model).

Builds the compact paper table, detailed tables, figures, run-receipt summary, durable raw-artifact index and
completion receipt of one V2 run from the frozen analysis outputs.

python -m experiments.robolab_vqa.v2.report --run-id r2-final-20261007 \
    --analysis <run>/analysis_original [--analysis-machine <run>/analysis_machine_mask] \
    [--review-ledger <work>/review/v2-machine-ledger] --edge-audit <run>/edge_audit \
    --r1-metrics reports/robolab-vqa-20261006/runs/r1-20261006/results/metrics_long.csv \
    --commits '{"implementation": "...", ...}' --output <dir>
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

from .. import common as C
from . import config as V

FORMS = ("DIR", "TF", "RF")
READOUT = {
    "N3-policy": "N3-policy (executed Nano reasoner = Qwen3-VL-8B-Instruct)",
    "E3-policy": "E3-policy (executed Edge reasoner = Edge base reasoner)",
    "F3-qwen3vl4b": "F3-qwen3vl4b (FLUX frozen shared encoder = Qwen3-VL-4B-Instruct)",
}
SUB = {"all_goals": "all 10 goals", "lateral_8_goals": "8 lateral/front-behind goals"}
MASKS = ("original", "revised", "strict")
BANKS = ("initial", "secondary")


# ------------------------------------------------------------------ formatting
def est(d):
    return d.get("estimate") if isinstance(d, dict) else None


def pct(x, nd=1):
    x = est(x) if isinstance(x, dict) else x
    return "undefined" if x is None else f"{100 * x:.{nd}f}%"


def pci(d, nd=1):
    e = est(d)
    if e is None:
        return "undefined" + (f" ({d['status']})" if isinstance(d, dict) and d.get("status") else "")
    s = f"{100 * e:.{nd}f}%"
    if d.get("ci95"):
        lo, hi = d["ci95"]
        s += f" [{100 * lo:.{nd}f}, {100 * hi:.{nd}f}]"
    return s


def ppci(d, nd=1):
    e = est(d)
    if e is None:
        return "undefined"
    s = f"{100 * e:+.{nd}f}"
    if d.get("ci95"):
        lo, hi = d["ci95"]
        s += f" [{100 * lo:+.{nd}f}, {100 * hi:+.{nd}f}]"
    return s


def dist(d: dict | None) -> str:
    if not d:
        return "—"
    return ", ".join(f"{k} {v}" for k, v in sorted(d.items()))


def classes(by_form: dict) -> str:
    parts = []
    for f in sorted(by_form):
        c = {k: v for k, v in by_form[f].items() if k != "correct"}
        parts.append(f"{f}: " + (", ".join(f"{k} {v}" for k, v in sorted(c.items())) if c else "none"))
    return "; ".join(parts)


def pairs4(p: dict) -> str:
    keys = [k for k in p if k.startswith("TF=")] or list(p)
    a = p.get("TF=1,RF=1", 0)
    b = p.get("TF=1,RF=0", 0)
    c = p.get("TF=0,RF=1", 0)
    d = p.get("TF=0,RF=0", 0)
    return f"{a} / {b} / {c} / {d}" if keys else "—"


def table(header: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(str(x) for x in r) + " |" for r in rows]
    return "\n".join(out)


def finite(d: dict) -> str:
    return f"{d['sum_difference']:+.0f} ({d['a_only_correct']} vs {d['b_only_correct']} discordant of {d['finite_items']})"


def r1_b(r1_metrics: Path | None) -> dict:
    out = {}
    if not r1_metrics or not r1_metrics.exists():
        return out
    with open(r1_metrics) as f:
        for row in csv.DictReader(f):
            parts = row["metric"].split("/")
            if len(parts) == 4 and parts[0] in V.LANES and parts[1] == "initial" and parts[2] == "main_S1_S3_S4":
                out[(parts[0], parts[3])] = float(row["estimate"]) if row["estimate"] not in ("", "None") else None
    return out


# ------------------------------------------------------------------ tables
def coverage_rows(path: Path) -> tuple[list[str], list[list]]:
    with open(path) as f:
        rows = list(csv.reader(f))
    return rows[0], rows[1:]


def b2_text_md(res: dict) -> str:
    rows = []
    for lane in V.LANES:
        for cond in ("T", "H"):
            for sub in ("all_goals", "lateral_8_goals"):
                t = res["lanes"][lane]["b2_text"][cond][sub]
                bf = t["by_form"]
                rows.append([lane, cond, SUB[sub]] + [f"{bf[f]['tuple_correct']}/{bf[f]['n']}" for f in FORMS]
                            + [f"{t['tuple_correct']}/{t['n']}", f"{t['target_correct']}/{t['n']}", f"{t['reference_correct']}/{t['n']}",
                               f"{t['relation_correct']}/{t['n']}", pairs4(t["paired_TF_RF"]), classes(t["error_classes_by_form"])])
    return table(["Readout", "Cond.", "Goals", "DIR", "TF", "RF", "Tuple", "Target", "Reference", "Relation",
                  "TF/RF pairs: both ✓ / TF only / RF only / neither", "Errors by form (counts)"], rows)


def b2_image_md(res: dict) -> str:
    rows = []
    for lane in V.LANES:
        for cond in ("I", "IH"):
            for sub in ("all_goals", "lateral_8_goals"):
                m = res["lanes"][lane]["b2_image"][cond][sub]
                rows.append([lane, cond, SUB[sub], pci(m["tuple_accuracy"])] + [pci(m[f"tuple_accuracy_{f}"]) for f in FORMS]
                            + [ppci(m["gap_TF_minus_RF"]), pci(m["both_correct_TF_RF"]), pct(m["target_accuracy"]),
                               pct(m["reference_accuracy"]), pct(m["relation_accuracy"])])
    return table(["Readout", "Cond.", "Goals", "Tuple acc.", "DIR", "TF", "RF", "TF−RF gap, pp", "Both-correct TF/RF",
                  "Target", "Reference", "Relation"], rows)


def b2_image_errors_md(res: dict) -> str:
    rows = []
    for lane in V.LANES:
        for cond in ("I", "IH"):
            m = res["lanes"][lane]["b2_image"][cond]["all_goals"]["error_classes_by_form"]
            for f in FORMS:
                c = m.get(f, {})
                rows.append([lane, cond, f, c.get("correct", 0), dist({k: v for k, v in c.items() if k != "correct"})])
    return table(["Readout", "Cond.", "Form", "Correct (items)", "Error classes (items; converse ≠ support-label swap)"], rows)


def contrasts_md(res: dict) -> str:
    rows = []
    names = [("image_I_minus_T", "image: I − T (no header text)"), ("image_IH_minus_H", "image: IH − H (header text kept)"),
             ("header_IH_minus_I", "header: IH − I (images kept)"), ("header_H_minus_T", "header: H − T (no images; finite)")]
    for lane in V.LANES:
        for key, label in names:
            for sub in ("all_goals", "lateral_8_goals"):
                c = res["lanes"][lane]["b2_contrasts"][key][sub]
                if key == "header_H_minus_T":
                    rows.append([lane, label, SUB[sub], finite(c["tuple_all"])] + [finite(c[f"tuple_{f}"]) for f in FORMS] + ["—"])
                else:
                    rows.append([lane, label, SUB[sub], ppci(c["tuple_all"])] + [ppci(c[f"tuple_{f}"]) for f in FORMS]
                                + [ppci(c["tf_rf_gap_difference"])])
    return table(["Readout", "Contrast", "Goals", "All forms (pp)", "DIR", "TF", "RF", "Change in TF−RF gap"], rows)


def placement_md(res: dict) -> str:
    rows = []
    for lane in V.LANES:
        L = res["lanes"][lane]
        t = L["b2_placement_text"]["all_goals"]
        m = L["b2_placement_image"]["all_goals"]
        rows.append([lane, f"{t['tuple_correct']}/{t['n']}", dist({k: f"{v['tuple_correct']}/{v['n']}" for k, v in t["by_form"].items()}),
                     dist(t["paired_reference_early_reference_late"]), pci(m["tuple_accuracy"]),
                     pci(m["tuple_accuracy_reference_early"]), pci(m["tuple_accuracy_reference_late"]),
                     ppci(m["gap_reference_early_minus_reference_late"]), classes(m["error_classes_by_form"])])
    return table(["Readout", "T tuple (finite)", "T by placement form", "T early/late pairs", "IH tuple acc.", "IH reference-early",
                  "IH reference-late", "IH early − late, pp", "IH errors by form"], rows)


def cross_protocol_md(res: dict, r1: dict) -> str:
    rows = []
    for lane in V.LANES:
        m = res["lanes"][lane]["b2_image"]["IH"]["all_goals"]
        r1v = [r1.get((lane, f"B_image_tuple_accuracy_{f}")) for f in FORMS]
        rows.append([lane, pct(r1.get((lane, "B_image_tuple_accuracy")))] + [pct(x) for x in r1v]
                    + [pct(m["tuple_accuracy"])] + [pct(m[f"tuple_accuracy_{f}"]) for f in FORMS])
    return table(["Readout", "R1 B free generation, strict parse: tuple", "R1 DIR", "R1 TF", "R1 RF",
                  "V2 B2 IH constrained: tuple", "B2 DIR", "B2 TF", "B2 RF"], rows)


def c2_md(res: dict, mask: str) -> str:
    rows = []
    for lane in V.LANES:
        C2 = res["lanes"][lane]["c2"].get(mask, {})
        for bank in BANKS:
            m = C2.get(bank)
            if not m:
                rows.append([lane, bank, C2.get("status", "not available")] + ["—"] * 11)
                continue
            ba = m["balanced_accuracy_all_forms"]
            rows.append([lane, bank, f"{m['items_scored']}/{m['items_proposed']}", pci(ba["balanced_accuracy"]),
                         pct(ba["recall_match"]), pct(ba["recall_nonmatch"]), pci(m["accuracy_all_forms"]),
                         pct(m["constant_baselines"]["always_nonmatch_accuracy"]), ppci(m["gap_TF_minus_RF"]),
                         pci(m["both_correct_TF_RF"]), pct(m["order0_balanced_accuracy"]["balanced_accuracy"]),
                         pct(m["order1_balanced_accuracy"]["balanced_accuracy"]),
                         f"{m['semantic_agreement_across_orders']['agree']}/{m['semantic_agreement_across_orders']['items']}"])
    return table(["Readout", "Bank", "Items scored / proposed", "Balanced acc. [95% CI]", "Recall match", "Recall nonmatch",
                  "Accuracy", "Always-nonmatch acc.", "TF−RF gap, pp", "Both-correct TF/RF", "Order 0 BA", "Order 1 BA",
                  "Same semantic answer across orders"], rows)


def c2_forms_md(res: dict, mask: str = "original") -> str:
    rows = []
    for lane in V.LANES:
        for bank in BANKS:
            m = res["lanes"][lane]["c2"][mask][bank]
            rows.append([lane, bank] + [pci(m[f"balanced_accuracy_{f}"]["balanced_accuracy"]) for f in FORMS]
                        + [pci(m[f"accuracy_{f}"]) for f in FORMS] + [ppci(m["gap_DIR_minus_TF"]), ppci(m["gap_DIR_minus_RF"]),
                                                                      pci(m["disagreement_TF_RF"])])
    return table(["Readout", "Bank", "BA DIR", "BA TF", "BA RF", "Acc. DIR", "Acc. TF", "Acc. RF", "DIR−TF, pp", "DIR−RF, pp",
                  "TF/RF disagreement"], rows)


def c2_answers_md(res: dict, mask: str = "original") -> str:
    rows = []
    for lane in V.LANES:
        for bank in BANKS:
            m = res["lanes"][lane]["c2"][mask][bank]
            g = m["answer_distribution_answerable_by_gold"]
            rows.append([lane, bank, dist(m["answer_distribution_all_items"]), dist(m["order0_answer_distribution"]),
                         dist(m["order1_answer_distribution"]), dist(g.get("match")), dist(g.get("nonmatch"))])
    return table(["Readout", "Bank", "All delivered answers (both orders)", "Order 0 (A = match)", "Order 1 (A = nonmatch)",
                  "Answerable, gold match → answers", "Answerable, gold nonmatch → answers"], rows)


def c2_no_image_md(res: dict) -> str:
    rows = []
    for lane in V.LANES:
        n = res["lanes"][lane]["c2_no_image"]
        reuse = n["reused_against_initial_labels"]
        rows.append([lane, dist(n["answer_distribution_by_form"].get("DIR")), dist(n["answer_distribution_by_form"].get("TF")),
                     dist(n["answer_distribution_by_form"].get("RF")), dist(n["answer_distribution_by_order"].get("0")),
                     dist(n["answer_distribution_by_order"].get("1")), pct(n["unknown_rate"]), pct(reuse["accuracy"]),
                     pct(reuse["balanced_accuracy"]["balanced_accuracy"])])
    return table(["Readout", "DIR (20)", "TF (20)", "RF (20)", "Order 0 (30)", "Order 1 (30)", "U rate (expected U)",
                  "Reuse vs initial labels: acc.", "Reuse BA"], rows)


def truth_pairs_md(res: dict, mask: str) -> str:
    rows = []
    for lane in V.LANES:
        tp = res["lanes"][lane]["c2"].get(mask, {}).get("truth_changing_pairs")
        if not tp:
            rows.append([lane, "not available"] + ["—"] * 6)
            continue
        s = tp["summary"]
        if s.get("status") != "available":
            rows.append([lane, f"{s.get('status')} ({s.get('available_pairs', 0)} pairs)"] + ["—"] * 6)
            continue
        rows.append([lane, f"{s['available_pairs']} of {s['start_goals_considered']} start–goals"]
                    + [f"{s[f]['mean_both_correct'] * s[f]['pairs']:.1f}/{s[f]['pairs']}" for f in FORMS]
                    + [f"{s[f]['pairs_both_correct_in_both_orders']}/{s[f]['pairs']}" for f in FORMS])
    return table(["Readout", "Available pairs", "Both frames correct, DIR (order-averaged)", "TF", "RF",
                  "Both frames correct in both orders, DIR", "TF", "RF"], rows)


def a_rescore_md(res: dict) -> str:
    rows = []
    a = res.get("a_rescore_r1_answers") or {}
    for lane in V.LANES:
        for bank in BANKS:
            for mask in MASKS:
                m = a.get(lane, {}).get(bank, {}).get(mask)
                if not m or "accuracy" not in m:
                    rows.append([lane, bank, mask, (m or {}).get("status", "not available")] + ["—"] * 5)
                    continue
                b = m["balanced_accuracy"]
                rows.append([lane, bank, mask, f"{m['items']} items / {m['pairs']} pairs", pci(m["accuracy"]),
                             pci(b["balanced_accuracy"]), pct(b["recall_yes"]), pct(b["recall_no"]),
                             ppci(m["target_minus_reference_subject_gap"])])
    return table(["Readout", "Bank", "Mask", "Scored", "Accuracy", "Balanced acc. (V2 class weights)", "Recall yes", "Recall no",
                  "Target − reference subject gap, pp"], rows)


def edge_md(summary: dict, audit_csv: Path) -> str:
    with open(audit_csv) as f:
        rows = list(csv.DictReader(f))
    cls = ["json_structure_single_item_array", "json_structure_malformed", "object_vocabulary", "relation_vocabulary",
           "object_and_relation_vocabulary", "multiple_or_conflicting_answers", "truncation", "other"]
    groups = sorted({(r["family"], r["bank"]) for r in rows})
    out = []
    for fam, bank in groups:
        sub = [r for r in rows if r["family"] == fam and r["bank"] == bank]
        cnt = Counter(r["failure_class"] for r in sub if r["strict_valid"] != "True")
        out.append([fam, bank, len(sub), sum(r["strict_valid"] == "True" for r in sub), sum(r["strict_tuple_correct"] == "True" for r in sub)]
                   + [cnt.get(c, 0) for c in cls])
    tot = ["**all**", "", len(rows), sum(r["strict_valid"] == "True" for r in rows), sum(r["strict_tuple_correct"] == "True" for r in rows)]
    cnt = Counter(r["failure_class"] for r in rows if r["strict_valid"] != "True")
    out.append(tot + [cnt.get(c, 0) for c in cls])
    t1 = table(["Family", "Bank", "Requests", "Strict-valid", "Strict tuple correct"] + [c.replace("_", " ") for c in cls], out)
    am = summary.get("alias_mapped_by_form", {})
    t2 = table(["Form", "Format failures with a descriptive alias mapping", "Mapped tuple matches gold (descriptive only)"],
               [[f, am.get(f, {}).get("mapped", 0), am.get(f, {}).get("matches_gold", 0)] for f in FORMS])
    return t1 + "\n\n" + t2


def review_md(ingest: dict | None, mask: dict | None) -> str:
    if not ingest:
        return "No review forms were ingested; revised and strict masks are unavailable (every reviewed-mask result is reported as not available)."
    rows = [["Ledger rows (reviewer × item)", ingest["ledger_rows"]], ["Frames reviewed (of 72)", ingest["frames_reviewed"]],
            ["Reviewer types", ", ".join(ingest["reviewer_types"])],
            ["Machine coverage (frames)", f"{mask['machine_coverage']['frames']}/{mask['machine_coverage']['of']}" if mask else "—"],
            ["Human coverage (frames)", f"{mask['human_coverage']['frames']}/{mask['human_coverage']['of']}" if mask else "—"],
            ["Ledger rows answerable for A / for C", f"{ingest['review_answerable_A']} / {ingest['review_answerable_C']}"],
            ["Ledger rows with a discrepancy vs geometry, A / C", f"{ingest['discrepancy_A']} / {ingest['discrepancy_C']}"],
            ["mask.json SHA256", f"`{ingest['mask_sha256']}`"], ["review_ledger.csv SHA256", f"`{ingest['ledger_sha256']}`"]]
    return table(["Field", "Value"], rows)


def _true(v) -> bool:
    return str(v) == "True"


def review_stats(ledger_csv: Path) -> tuple[dict, list[dict]]:
    """Item-level summary of a review ledger (frame × goal; several reviewers per item). Mask rule as in review.ingest."""
    with open(ledger_csv) as f:
        rows = list(csv.DictReader(f))
    by: dict[tuple, list[dict]] = {}
    for r in rows:
        by.setdefault((r["frame_id"], r["goal_id"]), []).append(r)
    items = []
    for (frame, goal), rs in sorted(by.items()):
        rec = {"frame_id": frame, "goal_id": goal, "bank": rs[0]["bank"], "scene_id": rs[0]["scene_id"], "reviewers": len(rs),
               "reviewer_ids": ";".join(sorted(r["reviewer_id"] for r in rs)), "gold_A": rs[0]["gold_A"], "gold_C": rs[0]["gold_C"],
               "proposed_relations": ";".join(r["proposed_visible_relation"] for r in rs),
               "relation_agreement": len({r["proposed_visible_relation"] for r in rs}) == 1}
        for test in ("A", "C"):
            ok = [_true(r[f"review_answerable_{test}"]) for r in rs]
            disc = [_true(r[f"discrepancy_{test}"]) for r in rs]
            r1 = _true(rs[0][f"r1_answerable_{test}"])
            rec |= {f"r1_answerable_{test}": r1, f"review_answerable_all_{test}": all(ok), f"review_answerable_any_{test}": any(ok),
                    f"answerability_agreement_{test}": len(set(ok)) == 1, f"discrepancy_any_{test}": any(disc),
                    f"revised_{test}": r1 and all(ok), f"strict_{test}": r1 and all(ok) and not any(disc),
                    f"exclusion_reasons_{test}": ";".join(sorted({x for r in rs for x in (r[f"review_exclusion_{test}"] or "").split(";") if x}))}
        items.append(rec)
    out = {"ledger_rows": len(rows), "items": len(items), "frames": len({i["frame_id"] for i in items}),
           "reviewers_per_item": dict(Counter(i["reviewers"] for i in items)),
           "reviewer_ids": sorted({r["reviewer_id"] for r in rows}), "reviewer_types": sorted({r["reviewer_type"] for r in rows}),
           "relation_agreement_items": sum(i["relation_agreement"] for i in items),
           "proposed_relation_counts": dict(Counter(r["proposed_visible_relation"] for r in rows)),
           "confidence_counts": dict(Counter(r["confidence"] for r in rows)), "tests": {}}
    for test in ("A", "C"):
        t = {}
        for bank in ("initial", "secondary", "all"):
            sub = [i for i in items if bank == "all" or i["bank"] == bank]
            reasons = Counter(x for r in rows if bank == "all" or r["bank"] == bank
                              for x in (r[f"review_exclusion_{test}"] or "").split(";") if x)
            t[bank] = {"items": len(sub), "r1_answerable": sum(i[f"r1_answerable_{test}"] for i in sub),
                       "review_answerable_all_reviewers": sum(i[f"review_answerable_all_{test}"] for i in sub),
                       "review_answerable_disagreement": sum(not i[f"answerability_agreement_{test}"] for i in sub),
                       "revised_answerable": sum(i[f"revised_{test}"] for i in sub),
                       "revised_with_any_discrepancy": sum(i[f"revised_{test}"] and i[f"discrepancy_any_{test}"] for i in sub),
                       "strict_answerable": sum(i[f"strict_{test}"] for i in sub),
                       "reviewer_row_exclusion_reasons": dict(sorted(reasons.items()))}
        out["tests"][test] = t
    return out, items


def review_stats_md(stats: dict) -> str:
    rows = []
    for test in ("A", "C"):
        for bank in ("initial", "secondary", "all"):
            s = stats["tests"][test][bank]
            rows.append([test, bank, s["items"], s["r1_answerable"], s["review_answerable_all_reviewers"], s["review_answerable_disagreement"],
                         s["revised_answerable"], s["revised_with_any_discrepancy"], s["strict_answerable"]])
    t1 = table(["Test labels", "Bank", "Frame–goal items", "R1 mask answerable", "Answerable for every machine reviewer",
                "Reviewers disagree on answerability", "Revised mask (R1 AND review)", "…of which a reviewer label differs from geometry",
                "Strict mask"], rows)
    rr = []
    for test in ("A", "C"):
        for reason, n in stats["tests"][test]["all"]["reviewer_row_exclusion_reasons"].items():
            rr.append([test, reason, n])
    t2 = table(["Test labels", "Exclusion reason (reviewer rows; one item can have several)", "Rows"], rr) if rr else "No exclusions."
    agree = (f"Reviewers per item: {dist(stats['reviewers_per_item'])}. Identical proposed visible relation from every reviewer: "
             f"{stats['relation_agreement_items']}/{stats['items']} items. Confidence (reviewer rows): {dist(stats['confidence_counts'])}.")
    return t1 + "\n\n" + agree + "\n\n" + t2


def mask_counts(res_m: dict | None) -> list[list]:
    rows = []
    if not res_m:
        return rows
    for bank in BANKS:
        for mask in MASKS:
            m = res_m["lanes"]["N3-policy"]["c2"].get(mask, {}).get(bank)
            if m:
                rows.append([bank, mask, f"{m['items_answerable']}/{m['items_proposed']}"])
    return rows


# ------------------------------------------------------------------ paper table
def paper_table(res: dict, res_m: dict | None, cov: dict, audit_status: str) -> str:
    rows = []
    for lane in V.LANES:
        L = res["lanes"][lane]
        t = L["b2_text"]["T"]["all_goals"]["by_form"]
        m = L["b2_image"]["IH"]["all_goals"]
        c0 = L["c2"]["original"]
        aux = " *(aux.)*" if lane == "F3-qwen3vl4b" else ""
        ba = " / ".join(pct(c0[b]["balanced_accuracy_all_forms"]["balanced_accuracy"]) for b in BANKS)
        if res_m:
            cr = res_m["lanes"][lane]["c2"]["revised"]
            ba += " (machine-revised mask: " + " / ".join(pct(cr[b]["balanced_accuracy_all_forms"]["balanced_accuracy"]) for b in BANKS) + ")"
        gap = " / ".join(ppci(c0[b]["gap_TF_minus_RF"]) for b in BANKS)
        rows.append([READOUT[lane], " / ".join(str(t[f]["tuple_correct"]) for f in FORMS),
                     f"{pct(m['tuple_accuracy_TF'])} / {pct(m['tuple_accuracy_RF'])}{aux}", ppci(m["gap_TF_minus_RF"]) + aux,
                     ba + aux, gap + aux, f"{cov[lane]['delivered']}/{cov[lane]['valid']} of {cov[lane]['planned']}", audit_status])
    head = ["Readout (distinct weights)", "B2 text-only tuple correct, T (DIR / TF / RF of 10; finite)",
            "B2 image + header (IH) tuple acc., TF / RF", "B2 IH TF−RF gap, pp [95% CI]",
            "C2 balanced acc., initial / secondary (original mask)", "C2 TF−RF gap, pp, initial / secondary",
            "Coverage: delivered / valid of planned", "Audit status"]
    return table(head, rows)


# ------------------------------------------------------------------ figures
def figures(res: dict, analysis: Path, edge_csv: Path, r1: dict, out: Path) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out.mkdir(parents=True, exist_ok=True)
    made = []
    colors = {"DIR": "#7f7f7f", "TF": "#1f77b4", "RF": "#d62728"}
    # Fig 1: B2 by condition and form
    fig, axes = plt.subplots(1, 3, figsize=(13.5, 4.1), sharey=True)
    for ax, lane in zip(axes, V.LANES):
        L = res["lanes"][lane]
        for j, f in enumerate(FORMS):
            for i, cond in enumerate(("T", "H", "I", "IH")):
                x = i + (j - 1) * 0.26
                first = lane == V.LANES[0] and i == 0
                if cond in ("T", "H"):
                    b = L["b2_text"][cond]["all_goals"]["by_form"][f]
                    ax.bar([x], [b["tuple_correct"] / b["n"]], width=0.24, color=colors[f], label=f if first else None)
                else:
                    d = L["b2_image"][cond]["all_goals"][f"tuple_accuracy_{f}"]
                    y = d["estimate"]
                    ax.bar([x], [y], width=0.24, color=colors[f], yerr=[[y - d["ci95"][0]], [d["ci95"][1] - y]], capsize=2,
                           error_kw={"lw": 0.8})
            r1v = r1.get((lane, f"B_image_tuple_accuracy_{f}"))
            if r1v is not None:
                ax.plot([3 + (j - 1) * 0.26], [r1v], marker="D", mfc="white", mec="black", ms=5, ls="none",
                        label="R1 free generation (IH payload; different protocol)" if (lane == V.LANES[0] and j == 0) else None)
        ax.set_xticks(range(4), ["T\ntext only", "H\n+header", "I\n+images", "IH\n+both"])
        ax.set_ylim(0, 1.05)
        ttl = {"N3-policy": "N3-policy (Nano reasoner)", "E3-policy": "E3-policy (Edge reasoner)",
               "F3-qwen3vl4b": "F3 (FLUX shared encoder)\nimage conditions auxiliary"}[lane]
        ax.set_title(ttl, fontsize=10)
        ax.grid(axis="y", alpha=0.3)
    axes[0].set_ylabel("B2 tuple accuracy (all 10 goals)")
    fig.legend(loc="lower center", ncol=4, fontsize=8, frameon=False)
    fig.suptitle("B2 constrained instruction readout: T/H are finite counts over 10 instructions per form; I/IH 95% start-bootstrap CIs",
                 fontsize=9)
    fig.tight_layout(rect=(0, 0.07, 1, 0.95))
    for ext in ("png", "pdf"):
        p = out / f"fig1_b2_conditions.{ext}"
        fig.savefig(p, dpi=170)
        made.append(p.name)
    plt.close(fig)

    # Fig 2: C2 answer distributions by gold class
    with open(analysis / "c2_items.csv") as f:
        items = [r for r in csv.DictReader(f) if r["mask"] == "original"]
    cats = [("initial", "match"), ("initial", "nonmatch"), ("secondary", "match"), ("secondary", "nonmatch"), ("no_image", None)]
    labels = ["initial\ngold match", "initial\ngold nonmatch", "secondary\ngold match", "secondary\ngold nonmatch", "no image\n(expected U)"]
    ans_colors = {"match": "#2ca02c", "nonmatch": "#d62728", "unknown": "#bcbd22", "invalid": "#000000"}
    fig, axes = plt.subplots(1, 3, figsize=(13.5, 4.0), sharey=True)
    for ax, lane in zip(axes, V.LANES):
        fr = {a: [] for a in ans_colors}
        ns = []
        for bank, gold in cats:
            if bank == "no_image":
                d = Counter()
                for o, v in res["lanes"][lane]["c2_no_image"]["answer_distribution_by_order"].items():
                    d.update(v)
            else:
                d = Counter()
                for r in items:
                    if r["lane"] == lane and r["bank"] == bank and r["gold"] == gold and r["answerable"] == "True":
                        for k in ("answer_o0", "answer_o1"):
                            d[r[k] if r[k] in ("match", "nonmatch", "unknown") else "invalid"] += 1
            n = sum(d.values())
            ns.append(n)
            for a in ans_colors:
                fr[a].append(d.get(a, 0) / n if n else 0)
        bottom = [0] * len(cats)
        for a, c in ans_colors.items():
            ax.bar(range(len(cats)), fr[a], bottom=bottom, color=c, label=a if lane == V.LANES[0] else None, width=0.7)
            bottom = [b + v for b, v in zip(bottom, fr[a])]
        for i, n in enumerate(ns):
            ax.text(i, 1.02, f"n={n}", ha="center", fontsize=7)
        ax.set_xticks(range(len(cats)), labels, fontsize=7.5)
        ax.set_ylim(0, 1.1)
        ax.set_title(lane, fontsize=10)
    axes[0].set_ylabel("Share of answers (both option orders)")
    fig.legend(loc="lower center", ncol=4, fontsize=8, frameon=False)
    fig.suptitle("C2 current-state question: answers by simulator gold class (original R1 mask, answerable items)", fontsize=9)
    fig.tight_layout(rect=(0, 0.07, 1, 0.95))
    for ext in ("png", "pdf"):
        p = out / f"fig2_c2_answers.{ext}"
        fig.savefig(p, dpi=170)
        made.append(p.name)
    plt.close(fig)

    # Fig 3: Edge R1 B format audit
    with open(edge_csv) as f:
        rows = list(csv.DictReader(f))
    groups = sorted({(r["family"], r["bank"]) for r in rows})
    cls = ["strict valid, tuple correct", "strict valid, tuple wrong", "json_structure_single_item_array", "json_structure_malformed",
           "object_vocabulary", "object_and_relation_vocabulary", "relation_vocabulary", "multiple_or_conflicting_answers",
           "truncation", "other"]
    pal = ["#2ca02c", "#98df8a", "#1f77b4", "#aec7e8", "#ff7f0e", "#d62728", "#ffbb78", "#9467bd", "#8c564b", "#7f7f7f"]
    fig, ax = plt.subplots(figsize=(12, 3.2))
    left = [0] * len(groups)
    for c, col in zip(cls, pal):
        vals = []
        for fam, bank in groups:
            sub = [r for r in rows if r["family"] == fam and r["bank"] == bank]
            if c == "strict valid, tuple correct":
                v = sum(r["strict_valid"] == "True" and r["strict_tuple_correct"] == "True" for r in sub)
            elif c == "strict valid, tuple wrong":
                v = sum(r["strict_valid"] == "True" and r["strict_tuple_correct"] != "True" for r in sub)
            else:
                v = sum(r["strict_valid"] != "True" and r["failure_class"] == c for r in sub)
            vals.append(v)
        if any(vals):
            ax.barh(range(len(groups)), vals, left=left, color=col, label=c.replace("_", " "))
        left = [a + b for a, b in zip(left, vals)]
    ax.set_yticks(range(len(groups)), [f"{fam} · {bank}" for fam, bank in groups], fontsize=8)
    ax.set_xlabel("R1 E3-policy B responses (count)")
    ax.legend(fontsize=7, ncol=1, loc="center left", bbox_to_anchor=(1.01, 0.5), frameon=False)
    ax.set_title("Edge R1 free-generation B responses on S1/S3/S4: strict validity and format-failure classes (no repair)", fontsize=9)
    fig.tight_layout()
    for ext in ("png", "pdf"):
        p = out / f"fig3_edge_format_audit.{ext}"
        fig.savefig(p, dpi=170)
        made.append(p.name)
    plt.close(fig)
    return made


# ------------------------------------------------------------------ receipts / index
def receipts(run: Path) -> dict:
    out = {}
    for lane in V.LANES:
        recs = []
        for p in sorted((run / lane).glob("run_receipt_*.json")):
            d = C.load_json(p)
            recs.append({k: d.get(k) for k in ("phase", "status", "started_utc", "ended_utc", "elapsed_s", "load_s", "latency_s_sum",
                                               "attempts_this_run", "delivered_total", "valid_total", "truncated_total",
                                               "infrastructure_missing_total", "lane_attempts_by_phase", "lane_attempts_total",
                                               "command", "adapter_commit", "release_content_sha256", "release_json_sha256",
                                               "loaded_parameter_digest", "loader_patches", "model_path_loaded", "reasoner_view",
                                               "checkpoint_manifest_sha256", "tokenizer_chat_template_sha256", "structured_backends",
                                               "engine_kwargs", "grammars", "environment", "stopped")} | {"file": p.name, "sha256": C.sha256_file(p)})
        out[lane] = sorted(recs, key=lambda r: r["started_utc"])
    return out


def entry(path: Path, role: str, root: Path, **extra) -> dict:
    return {"path": str(path), "relative_to_work_root": str(path.relative_to(root)) if str(path).startswith(str(root)) else None,
            "role": role, "bytes": path.stat().st_size, "sha256": C.sha256_file(path), "availability": "shared PVC 211247-prod-pvc (/data)",
            **extra}


def listing(path: Path, role: str, pattern: str = "*") -> dict:
    files = sorted(p for p in path.glob(pattern) if p.is_file())
    return {"path": str(path), "role": role, "files": len(files), "bytes": sum(p.stat().st_size for p in files),
            "listing_sha256": C.canonical_sha256({p.name: C.sha256_file(p) for p in files})}


def artifact_index(root: Path, run: Path, release: Path, packet: Path, extra_dirs: list[tuple[Path, str]]) -> dict:
    items = []
    for p in sorted(release.iterdir()):
        if p.is_file():
            items.append(entry(p, "frozen V2 release r2-final", root))
    rel = C.load_json(release / "release.json")
    image_root = rel.get("image_root")
    if image_root and Path(image_root).exists():
        items.append(listing(Path(image_root) / "images" if (Path(image_root) / "images").exists() else Path(image_root),
                             "R1 lossless model-input images reused by V2 (per-file hashes in V2 query manifest image bindings)", "*.png"))
    for name in ("packet_manifest.json", "review_form_blank.csv", "REVIEW_INSTRUCTIONS.md"):
        if (packet / name).exists():
            items.append(entry(packet / name, "blinded review packet", root))
    for name in ("frame_map.json", "labels.json"):
        if (packet / "key" / name).exists():
            items.append(entry(packet / "key" / name, "review packet key (sealed from reviewers; used only by CPU ingest)", root))
    for sub, role in (("sheets", "review sheets shown to reviewers (no labels/answers)"), ("views", "evaluation-resolution views in packet")):
        if (packet / sub).exists():
            items.append(listing(packet / sub, role))
    for lane in V.LANES:
        for p in sorted((run / lane).iterdir()):
            if p.is_file():
                role = ("raw evaluation responses" if p.name == "responses.jsonl" else "attempt ledger" if p.name == "attempts.jsonl"
                        else "rendered prompts" if p.name.startswith("rendered_prompts") else
                        "qualification responses" if p.name.startswith("qualification") else "receipt/manifest")
                items.append(entry(p, role, root, lane=lane))
    for p in sorted((run / "_logs").glob("*.log")):
        items.append(entry(p, "process log", root))
    for p in sorted((run / "_retry_slots").glob("*/owner.json")):
        items.append(entry(p, "consumed shared retry slot (Amendment V2-A1 charge)", root))
    for d, role in extra_dirs:
        if d.exists():
            for p in sorted(d.iterdir()):
                if p.is_file():
                    items.append(entry(p, role, root))
    return {"study_id": C.STUDY_ID, "design_version": V.DESIGN_VERSION, "created_utc": C.utc_now(), "work_root": str(root),
            "storage": "Kubernetes namespace 211247-prod, PVC 211247-prod-pvc mounted at /data (NFS); not in Git", "items": items}


# ------------------------------------------------------------------ main
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--work-root", type=Path, default=V.WORK_ROOT)
    ap.add_argument("--release", default="r2-final")
    ap.add_argument("--packet", type=Path, default=None)
    ap.add_argument("--analysis", type=Path, required=True)
    ap.add_argument("--analysis-machine", type=Path, default=None)
    ap.add_argument("--review-ledger", type=Path, default=None)
    ap.add_argument("--review-forms", type=Path, default=None)
    ap.add_argument("--edge-audit", type=Path, required=True)
    ap.add_argument("--r1-metrics", type=Path, default=None)
    ap.add_argument("--commits", default="{}")
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    root = args.work_root
    run = root / "runs" / args.run_id
    release = root / "release" / args.release
    packet = args.packet or (root / "review" / "v2-packet")
    out = args.output
    V.assert_not_r1_path(out)
    (out / "results").mkdir(parents=True, exist_ok=True)

    res = C.load_json(args.analysis / "results_v2.json")
    res_m = C.load_json(args.analysis_machine / "results_v2.json") if args.analysis_machine else None
    edge_summary = C.load_json(args.edge_audit / "edge_format_audit_summary.json")
    ingest = C.load_json(args.review_ledger / "ingest_summary.json") if args.review_ledger else None
    mask = C.load_json(args.review_ledger / "mask.json") if args.review_ledger else None
    r1 = r1_b(args.r1_metrics)

    # compact results
    copies = [(args.analysis, "results_v2.json", "results_v2_original_mask.json"), (args.analysis, "coverage_v2.csv", "coverage_v2.csv"),
              (args.analysis, "metrics_long_v2.csv", "metrics_long_v2_original_mask.csv"),
              (args.analysis, "c2_truth_pairs.csv", "c2_truth_pairs_original_mask.csv")]
    if args.analysis_machine:
        copies += [(args.analysis_machine, "results_v2.json", "results_v2_machine_mask.json"),
                   (args.analysis_machine, "metrics_long_v2.csv", "metrics_long_v2_machine_mask.csv"),
                   (args.analysis_machine, "c2_truth_pairs.csv", "c2_truth_pairs_machine_mask.csv")]
    for src_dir, name, dest in copies:
        shutil.copy2(src_dir / name, out / "results" / dest)
    gz = [(args.analysis, "b2_items.csv", "b2_items.csv.gz"), (args.analysis, "c2_items.csv", "c2_items_original_mask.csv.gz")]
    if args.analysis_machine:
        gz.append((args.analysis_machine, "c2_items.csv", "c2_items_machine_mask.csv.gz"))
    for src_dir, name, dest in gz:
        with open(src_dir / name, "rb") as src, gzip.GzipFile(out / "results" / dest, "wb", mtime=0) as dst:
            shutil.copyfileobj(src, dst)
    shutil.copy2(args.edge_audit / "edge_format_audit_summary.json", out / "results" / "edge_format_audit_summary.json")
    shutil.copy2(args.edge_audit / "edge_format_audit.csv", out / "results" / "edge_format_audit.csv")
    rstats = None
    if args.review_ledger:
        rdir = out / "review"
        rdir.mkdir(exist_ok=True)
        for name in ("review_ledger.csv", "mask.json", "ingest_summary.json"):
            shutil.copy2(args.review_ledger / name, rdir / f"machine_{name}")
        if args.review_forms and args.review_forms.exists():
            for p in sorted(args.review_forms.glob("*.csv")):
                shutil.copy2(p, rdir / p.name)
        rstats, ritems = review_stats(args.review_ledger / "review_ledger.csv")
        C.write_json_atomic(rdir / "machine_review_summary.json", rstats)
        with open(rdir / "machine_review_items.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(ritems[0]))
            w.writeheader()
            w.writerows(ritems)

    # coverage per lane
    hdr, cov_rows = coverage_rows(args.analysis / "coverage_v2.csv")
    cov = {}
    for r in cov_rows:
        d = dict(zip(hdr, r))
        c = cov.setdefault(d["lane"], Counter())
        for k in ("planned", "delivered", "valid", "invalid", "truncated", "infrastructure_missing", "unknown_code"):
            c[k] += int(d[k])
    audit_status = ("machine review (2 independent blinded agents per sheet); no human review — visual results provisional"
                    if ingest else "no review ingested — visual results provisional")
    pt = ["# RQA V2 candidate compact table (not inserted into any manuscript)", "",
          f"Run `{args.run_id}`; S1/S3/S4 only (24 physical starts, 10 goals, 30 exact DIR/TF/RF instructions). Image metrics are "
          "macro-weighted (items within start × goal cell → starts → goals → scenes) with 95% percentile intervals from 10,000 "
          "physical-start bootstrap replicates within scene (seed 6106), conditional on the three fixed scenes and wording "
          "templates. Text-only B2 is a finite set of 10 instructions per form (counts, no interval). B2 uses schema-constrained "
          "JSON decoding (an assisted readout; format validity is guaranteed by construction). C2 uses one fixed wrapper and "
          "counterbalanced A/B codes, averaged over both orders within each item.", "",
          paper_table(res, res_m, cov, audit_status), "",
          "*(aux.)* Per the protocol, F3's text-only B2 counts test the language path of FLUX's frozen shared Qwen3-VL-4B "
          "component; its image-conditioned results are auxiliary (standalone image QA is not FLUX policy VQA).",
          "Read C2 against its label prior: the always-nonmatch rule scores balanced accuracy 50%; always-nonmatch accuracy is "
          f"{pct(res['lanes']['N3-policy']['c2']['original']['initial']['constant_baselines']['always_nonmatch_accuracy'])} (initial) and "
          f"{pct(res['lanes']['N3-policy']['c2']['original']['secondary']['constant_baselines']['always_nonmatch_accuracy'])} (secondary).",
          "Detailed header/pixel contrasts, option-order checks, no-image controls and the Edge format audit: TABLES.md."]
    (out / "PAPER_TABLE.md").write_text("\n".join(pt) + "\n")

    t = [f"# RQA V2 detailed tables — run `{args.run_id}`", "",
         "Generated by `python -m experiments.robolab_vqa.v2.report` from the frozen analysis outputs. Percentages are macro-weighted "
         "estimates with 95% physical-start bootstrap intervals (10,000 replicates, seed 6106) unless a cell is a finite count. "
         "Paired contrasts use identical resamples and common items.", "",
         "## 1. Coverage", "", table(hdr, cov_rows), "",
         "## 2. B2 text-only conditions (finite counts; one deterministic generation per instruction)", "", b2_text_md(res), "",
         "## 3. B2 image conditions (initial views; 8 starts per instruction)", "", b2_image_md(res), "",
         "### B2 image error classes (all 10 goals, item counts)", "", b2_image_errors_md(res), "",
         "## 4. B2 pixel and header contrasts", "",
         "Paired contrasts reuse each no-image answer (one generation per instruction) against all eight initial cells of the same "
         "instruction; their intervals are conditional on those fixed text-only answers. H − T is a finite comparison of 10 "
         "instructions per form, shown as the summed difference and discordant counts.", "", contrasts_md(res), "",
         "## 5. Placement-only control (T: 16 finite; IH: 128 initial-image requests)", "", placement_md(res), "",
         "## 6. Cross-protocol reference: R1 free generation versus V2 constrained decoding (descriptive)", "",
         "Same IH payload content; R1 used free generation with a strict parser, V2 uses schema-constrained decoding. This is a "
         "decoding-protocol comparison, not a model or training effect.", "", cross_protocol_md(res, r1), "",
         "## 7. C2 current-state question", ""]
    for mask_name in MASKS:
        label = {"original": "original R1 mask", "revised": "machine-revised mask (R1 mask AND every machine reviewer marks answerable)",
                 "strict": "machine-strict mask (revised AND no reviewer/geometry discrepancy)"}[mask_name]
        src = res if mask_name == "original" else res_m
        t += [f"### C2 — {label}", "", c2_md(src, mask_name) if src else "Not available (no review mask ingested).", ""]
    t += ["### C2 by wording form (original mask)", "", c2_forms_md(res), "",
          "### C2 answer distributions and order check (original mask)", "", c2_answers_md(res), "",
          "### C2 no-image control (camera text retained; expected evidential answer U)", "", c2_no_image_md(res), "",
          "### C2 truth-changing frame pairs (same start and goal; one pair per start–goal; order-averaged)", ""]
    for mask_name in MASKS:
        src = res if mask_name == "original" else res_m
        t += [f"**{mask_name} mask**", "", truth_pairs_md(src, mask_name) if src else "Not available.", ""]
    t += ["## 8. A rescore of existing R1 answers (no new A inference)", "",
          "Accuracy and the converse-question gap reproduce R1 exactly under the original mask. Balanced accuracy uses the V2 "
          "class-weight normalization (protocol §7: declared item weights normalized within each gold class), so it can differ "
          "slightly from R1's within-class hierarchical recall.", "",
          a_rescore_md(res_m or res), "",
          "## 9. Edge R1 B format audit (existing responses; no parser repair; original strict scores unchanged)", "",
          edge_md(edge_summary, args.edge_audit / "edge_format_audit.csv"), "", f"Note: {edge_summary.get('note', '')}", "",
          "## 10. Answerability review (machine)", "", review_md(ingest, mask), ""]
    if rstats:
        t += ["### Item-level machine review summary (frame × goal items; mask rule frozen in `review.ingest`)", "",
              "An item is in the revised mask when the R1 mask kept it and every machine reviewer marked it answerable; the "
              "strict mask additionally drops any item where a reviewer's proposed label differs from the simulator geometry "
              "(any inter-reviewer disagreement on an answerable item implies such a difference).", "", review_stats_md(rstats), ""]
    mc = mask_counts(res_m)
    if mc:
        t += ["C2 answerable items per mask (identical across lanes):", "", table(["Bank", "Mask", "Answerable / proposed items"], mc), ""]
    (out / "TABLES.md").write_text("\n".join(t) + "\n")

    made = figures(res, args.analysis, args.edge_audit / "edge_format_audit.csv", r1, out / "figures")

    rec = receipts(run)
    C.write_json_atomic(out / "run_receipts_summary.json", rec)
    extra = [(args.analysis, "analysis output (original mask)"), (args.edge_audit, "Edge R1 B format audit output")]
    if args.analysis_machine:
        extra.append((args.analysis_machine, "analysis output (machine-review masks)"))
    if args.review_ledger:
        extra.append((args.review_ledger, "machine review ledger and mask"))
    if args.review_forms:
        extra.append((args.review_forms, "machine review forms (blinded agents)"))
    idx = artifact_index(root, run, release, packet, extra)
    C.write_json_atomic(out / "artifact_index.json", idx)

    commits = json.loads(args.commits)
    elapsed = {lane: {r["phase"]: r["elapsed_s"] for r in rec[lane]} for lane in V.LANES}
    gpu_s = sum(sum(v.values()) for v in elapsed.values())
    planned = sum(c["planned"] for c in cov.values())
    receipt = {
        "study_id": C.STUDY_ID, "design_version": V.DESIGN_VERSION, "run_id": args.run_id, "created_utc": C.utc_now(),
        "status": "complete_machine_reviewed_provisional" if ingest else "complete_unreviewed_provisional",
        "release": {"content_sha256": res["release_content_sha256"],
                    "release_json_sha256": rec[V.LANES[0]][0]["release_json_sha256"]},
        "counts": {"planned_evaluation": planned, "delivered": sum(c["delivered"] for c in cov.values()),
                   "missing": sum(c["infrastructure_missing"] for c in cov.values()),
                   "valid": sum(c["valid"] for c in cov.values()), "invalid": sum(c["invalid"] for c in cov.values()),
                   "truncated": sum(c["truncated"] for c in cov.values()),
                   "c2_unknown_code_answers": sum(c["unknown_code"] for c in cov.values()),
                   "per_lane": {lane: dict(cov[lane]) for lane in V.LANES}},
        "attempt_budget": {"hard_cap": V.MAX_ATTEMPTS_TOTAL, "evaluation_ceiling": V.MAX_EVAL_TOTAL,
                           "ledger_entries": sum(r[-1]["lane_attempts_total"] for r in rec.values()),
                           "ledger_by_phase": {lane: rec[lane][-1]["lane_attempts_by_phase"] for lane in V.LANES},
                           "aborted_before_generation_entries": 3,
                           "model_generation_calls": sum(r[-1]["lane_attempts_total"] for r in rec.values()) - 3,
                           "qualification_generation_calls": 18, "infrastructure_retries": 0,
                           "shared_retry_slots_charged_by_amendment_V2_A1": 3,
                           "shared_retry_slots_unused": V.MAX_RETRIES_TOTAL - 3,
                           "note": "qualification ledger count per lane is 7 = 1 aborted-before-generation entry (Amendment V2-A1) + 6 fixture generations"},
        "timing_utc": {lane: {r["phase"]: {"started": r["started_utc"], "ended": r["ended_utc"], "elapsed_s": round(r["elapsed_s"], 1),
                                           "model_load_s": round(r["load_s"], 1)} for r in rec[lane]} for lane in V.LANES},
        "gpu_time": {"active_process_seconds_total": round(gpu_s, 1), "active_gpu_hours": round(gpu_s / 3600, 3),
                     "per_lane_seconds": {lane: {k: round(v, 1) for k, v in elapsed[lane].items()} for lane in V.LANES},
                     "hardware": "3 × NVIDIA B200 (one per lane, separate pods, run in parallel)",
                     "aborted_first_launch": "01:36–01:39 UTC, model load then KeyError before any generation; no receipt (Amendment V2-A1)",
                     "allocation_note": "GPU pods were created about 01:10–01:20 UTC and deleted at 13:12 UTC on 2026-10-07; after 01:52 UTC they were idle (no generation; attempt ledgers end at 01:51:56) while machine review was blocked by a workstation network outage"},
        "commands": {
            "inference": [" ".join(["python"] + r["command"]) for lane in V.LANES for r in rec[lane]],
            "edge_audit": f"python -m experiments.robolab_vqa.v2.edge_audit --output {args.edge_audit}",
            "analysis_original": f"python -m experiments.robolab_vqa.v2.analyze --release {release}/release.json --run {run} --output {args.analysis}",
            "review_ingest": (f"python -m experiments.robolab_vqa.v2.review ingest --packet {packet} --forms <machine_form_1..12.csv> --output {args.review_ledger}"
                              if args.review_ledger else None),
            "analysis_machine_mask": (f"python -m experiments.robolab_vqa.v2.analyze --release {release}/release.json --run {run} --output {args.analysis_machine} --mask {args.review_ledger}/mask.json"
                                      if args.analysis_machine else None),
            "human_rescore_cpu_only": (f"python -m experiments.robolab_vqa.v2.review ingest --packet {packet} --forms <human_form.csv>[,<second_human_form.csv>] --output <ledger dir> && "
                                       f"python -m experiments.robolab_vqa.v2.analyze --release {release}/release.json --run {run} --output <dir> --mask <ledger dir>/mask.json"),
            "report": " ".join(["python -m experiments.robolab_vqa.v2.report"] + sys.argv[1:])},
        "environment": rec[V.LANES[0]][-1]["environment"] | {"xgrammar": "0.2.3 (installed dist-info; receipt grammar field null)"},
        "decoding": {"engine_kwargs": rec[V.LANES[0]][-1]["engine_kwargs"], "greedy": True, "max_new_tokens": V.MAX_NEW_TOKENS,
                     "enable_thinking": False, "completions": 1},
        "commits": commits,
        "review": {"human": "not performed (packet and CPU-only rescore path delivered)",
                   "machine": ({"reviewers": "12 blinded agent forms (two independent reviewers per sheet)", "frames": mask["machine_coverage"] if mask else None,
                                "complete": mask.get("complete") if mask else None, "mask_sha256": ingest["mask_sha256"],
                                "ledger_sha256": ingest["ledger_sha256"],
                                "item_summary": {k: rstats[k] for k in ("items", "reviewers_per_item", "relation_agreement_items", "tests")} if rstats else None}
                               if ingest else "not ingested")},
        "figures": made,
        "stop": "Bounded V2 pass complete; no V3, no additional inference.",
    }
    C.write_json_atomic(out / "COMPLETION_RECEIPT.json", receipt)
    print(json.dumps({"output": str(out), "figures": made, "artifact_items": len(idx["items"]), "planned": planned,
                      "delivered": receipt["counts"]["delivered"], "gpu_hours": receipt["gpu_time"]["active_gpu_hours"]}, indent=1))


if __name__ == "__main__":
    sys.exit(main())
