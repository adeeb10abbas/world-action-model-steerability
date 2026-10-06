"""Figures, compact paper table and markdown tables for the RQA-20261006 report (CPU).

python -m experiments.robolab_vqa.report --analysis <analysis-dir> --run-id <id> --output <report-run-dir>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import common as C

READOUT_LABEL = {
    "N3-policy": "Qwen3-VL-8B-Instruct = N3 policy reasoner",
    "N3-upstream-qwen3vl8b": "Qwen3-VL-8B-Instruct (upstream)",
    "N3-base": "Cosmos3-Nano base reasoner",
    "E3-policy": "Cosmos3-Edge reasoner = E3 policy reasoner",
    "E3-base": "Cosmos3-Edge base reasoner",
    "F3-qwen3vl4b": "Qwen3-VL-4B-Instruct (FLUX shared encoder; auxiliary)",
}
FAMILY_POLICY = {"N3-policy": "N3", "N3-base": "N3", "E3-policy": "E3", "F3-qwen3vl4b": "F3"}


def pct(x, digits=1):
    return "n/a" if x is None else f"{100 * x:.{digits}f}"


def pp(x, digits=1):
    return "n/a" if x is None else f"{100 * x:+.{digits}f}"


def est(d):
    return None if not d else d.get("estimate")


def ci(d, scale=100, signed=False):
    if not d or not d.get("ci95"):
        return "n/a"
    lo, hi = d["ci95"]
    f = "{:+.1f}" if signed else "{:.1f}"
    return f"[{f.format(scale * lo)}, {f.format(scale * hi)}]"


def evaluated(results: dict) -> list[str]:
    return [l for l, s in results["lanes"].items() if s["status"] == "evaluated"]


def paper_table(results: dict) -> str:
    rows = ["| Readout (distinct weights) | B tuple correct, text-only (finite) / image acc. | A both-correct | C TF acc. | C RF acc. | "
            "C TF−RF gap, pp [95% CI] | C both-correct | C balanced acc. (TF+RF) | Coverage (delivered / valid, answerable C pairs) |",
            "|---|---|---|---|---|---|---|---|---|"]
    for lane in evaluated(results):
        r = results["per_lane"][lane]
        m = r["initial"]["main_S1_S3_S4"]
        tb = r["text_only_B"]["original"]
        main_text = [x for x in tb["paired_rows"] if x["scene"] in C.MAIN_POOL_SCENES]
        tf_ok = int(sum(x.get("TF_correct") or 0 for x in main_text))
        rf_ok = int(sum(x.get("RF_correct") or 0 for x in main_text))
        group = results["lanes"][lane].get("identity_group") or [lane]
        name = " ≡ ".join(READOUT_LABEL.get(g, g) for g in group)
        cov = results["coverage_summary"].get(lane, {})
        rows.append(
            f"| {name} | TF {tf_ok}/{len(main_text)}, RF {rf_ok}/{len(main_text)} / {pct(est(m['B_image_tuple_accuracy']))}% | "
            f"{pct(est(m['A_pairs']['both_correct']))}% | {pct(est(m['C_TF_RF']['accuracy_TF']))}% | "
            f"{pct(est(m['C_TF_RF']['accuracy_RF']))}% | {pp(est(m['C_TF_RF']['gap']))} {ci(m['C_TF_RF']['gap'], signed=True)} | "
            f"{pct(est(m['C_TF_RF']['both_correct']))}% | {pct(est(m['C_balanced_all_forms']['balanced_accuracy']))}% | "
            f"{cov.get('delivered', 'n/a')}/{cov.get('valid', 'n/a')} of {cov.get('proposed', 'n/a')}; "
            f"{m['C_TF_RF']['pairs_complete']} C pairs |")
    return "\n".join(rows)


SHORT = {"N3-policy": "Qwen3-VL-8B\n(= N3 policy reasoner)", "N3-base": "Cosmos3-Nano\nbase reasoner",
         "E3-policy": "Cosmos3-Edge reasoner\n(= E3 policy and base)", "F3-qwen3vl4b": "Qwen3-VL-4B\n(FLUX shared encoder)"}


def constant_no_baseline(scored_csv: Path, lane: str, bank: str, scenes: tuple[str, ...]) -> float:
    """Macro-weighted accuracy of answering 'no' to every answerable original C item (label prior)."""
    import csv as _csv
    from .analyze import cell_table, macro_point

    units = []
    with open(scored_csv) as f:
        for x in _csv.DictReader(f):
            if (x["lane"] == lane and x["test"] == "C" and x["bank"] == bank and x["family"] == "original"
                    and x["scene"] in scenes and x["answerable"] == "True"):
                units.append((x["scene"], x["goal"], x["physical_start_id"], float(x["gold"] == "no")))
    return macro_point(cell_table(units), scenes)


def figures(results: dict, out: Path, analysis_dir: Path) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    files = []
    lanes = evaluated(results)
    order = [l for l in ("N3-policy", "N3-base", "E3-policy", "F3-qwen3vl4b") if l in lanes] + \
            [l for l in lanes if l not in ("N3-policy", "N3-base", "E3-policy", "F3-qwen3vl4b")]
    labels = [SHORT.get(l, l) for l in order]
    base = constant_no_baseline(analysis_dir / "scored_rows.csv", order[0], "initial", C.MAIN_POOL_SCENES)
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 5.0), gridspec_kw={"width_ratios": [1.2, 1]})
    ax = axes[0]
    w = 0.38
    for j, (form, color) in enumerate((("TF", "#1f77b4"), ("RF", "#d62728"))):
        for i, lane in enumerate(order):
            d = results["per_lane"][lane]["initial"]["main_S1_S3_S4"]["C_TF_RF"][f"accuracy_{form}"]
            ax.bar(i + (j - 0.5) * w, 100 * d["estimate"], w,
                   yerr=[[100 * (d["estimate"] - d["ci95"][0])], [100 * (d["ci95"][1] - d["estimate"])]],
                   color=color, alpha=0.85, capsize=3, label=form if i == 0 else None)
    ax.axhline(100 * base, color="k", lw=1.2, ls="--", label=f"answer 'no' to every item ({100 * base:.1f}%)")
    ax.axhline(50, color="grey", lw=0.8, ls=":")
    ax.set_xticks(range(len(order)))
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylabel("C accuracy (%), initial S1/S3/S4")
    ax.set_ylim(0, 100)
    ax.legend(fontsize=8, loc="lower right")
    ax.set_title("Primary endpoint: instruction + scene (C), TF vs RF", fontsize=10)
    ax = axes[1]
    pol = {r["model"]: r for r in results.get("policy_wording_contrasts_reference", [])
           if r["stratum"] == "all" and r["endpoint"] == "stable_ever"}
    fam = {"N3-policy": "N3", "N3-base": None, "E3-policy": "E3", "F3-qwen3vl4b": "F3"}
    for i, lane in enumerate(order):
        y = len(order) - 1 - i
        m = results["per_lane"][lane]["initial"]["main_S1_S3_S4"]
        for off, d, style, lab in ((0.22, m["C_TF_RF"]["gap"], dict(fmt="o", color="k"), "VQA C (primary)"),
                                   (0.0, m["B_image_TF_RF"]["gap"], dict(fmt="^", color="#1f77b4"), "VQA B tuple, with images")):
            ax.errorbar(100 * d["estimate"], y + off, xerr=[[100 * (d["estimate"] - d["ci95"][0])], [100 * (d["ci95"][1] - d["estimate"])]],
                        capsize=3, ms=6, label=lab if i == 0 else None, **style)
        f = fam.get(lane)
        if f and f in pol:
            r = pol[f]
            v, lo, hi = 100 * float(r["difference"]), 100 * float(r["ci_low"]), 100 * float(r["ci_high"])
            ax.errorbar(v, y - 0.22, xerr=[[v - lo], [hi - v]], fmt="s", color="#2ca02c", ms=5, capsize=3,
                        label="policy action, stable-ever (existing)" if i == 0 else None)
    ax.axvline(0, color="grey", lw=0.8)
    ax.set_yticks(range(len(order)))
    ax.set_yticklabels(list(reversed(labels)), fontsize=8)
    ax.set_xlabel("TF − RF difference (percentage points), 95% physical-start bootstrap CI")
    ax.legend(fontsize=7.5, loc="upper center", bbox_to_anchor=(0.45, -0.16), ncol=3, frameon=False)
    ax.set_title("Where the wording gap appears", fontsize=10)
    fig.tight_layout()
    for ext in ("png", "pdf"):
        p = out / f"fig1_primary_C_TF_RF.{ext}"
        fig.savefig(p, dpi=170)
        files.append(p.name)
    plt.close(fig)
    metrics = [("A acc.", lambda m: m["A_accuracy"]), ("A bal. acc.", lambda m: m["A_balanced"]["balanced_accuracy"]),
               ("B img tuple", lambda m: m.get("B_image_tuple_accuracy")), ("C TF", lambda m: m["C_accuracy_TF"]),
               ("C RF", lambda m: m["C_accuracy_RF"]), ("C bal. acc.", lambda m: m["C_balanced_all_forms"]["balanced_accuracy"]),
               ("C no-image\n(reused)", lambda m: m.get("C_no_image_reuse_accuracy"))]
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.8), sharey=True)
    colors = ["#d62728", "#2ca02c", "#1f77b4", "#ff7f0e", "#9467bd", "#8c564b"]
    for ax, (bank, pool, title) in zip(axes, (("initial", "main_S1_S3_S4", "Initial frames, S1/S3/S4 (headline pool)"),
                                               ("initial", "S5", "Initial frames, S5 (separate; one label class)"),
                                               ("secondary", "main_S1_S3_S4", "Saved rollout frames, S1/S3/S4"))):
        width = 0.8 / max(len(order), 1)
        for i, lane in enumerate(order):
            m = results["per_lane"][lane][bank][pool]
            for k, (name, fn) in enumerate(metrics):
                d = fn(m)
                if d is None or d.get("estimate") is None:
                    continue
                c = d.get("ci95") or [d["estimate"], d["estimate"]]
                ax.bar(k + (i - (len(order) - 1) / 2) * width, 100 * d["estimate"], width, color=colors[i % len(colors)],
                       yerr=[[100 * (d["estimate"] - c[0])], [100 * (c[1] - d["estimate"])]], capsize=1.5,
                       label=SHORT.get(lane, lane).replace("\n", " ") if (k == 0 and ax is axes[0]) else None)
        ax.axhline(50, color="grey", lw=0.8, ls=":")
        ax.set_xticks(range(len(metrics)))
        ax.set_xticklabels([n for n, _ in metrics], fontsize=7.5)
        ax.set_title(title, fontsize=9)
        ax.set_ylim(0, 105)
    axes[0].set_ylabel("macro-weighted % (95% start-bootstrap CI)")
    fig.legend(loc="upper center", ncol=len(order), fontsize=8, bbox_to_anchor=(0.5, 1.0))
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    for ext in ("png", "pdf"):
        p = out / f"fig2_tests_overview.{ext}"
        fig.savefig(p, dpi=170)
        files.append(p.name)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(11, 4.6))
    cats = ["yes", "no", "unknown", "invalid", "valid_json", "infrastructure_missing"]
    ccol = ["#2ca02c", "#1f77b4", "#bcbd22", "#d62728", "#9edae5", "#7f7f7f"]
    rows = []
    for lane in order:
        r = results["per_lane"][lane]
        short = SHORT.get(lane, lane).split("\n")[0]
        for bank, key in (("initial", "answer_distribution_A"), ("secondary", "answer_distribution_A"),
                          ("initial", "answer_distribution_C"), ("secondary", "answer_distribution_C")):
            rows.append((f"{short}: {key[-1]} {bank}", r[bank]["all_scenes"][key]))
        rows.append((f"{short}: C no-image", r["C_no_image_answers"]))
    left = [0.0] * len(rows)
    for cat, color in zip(cats, ccol):
        vals = [100 * dist.get(cat, 0) / max(sum(dist.values()), 1) for _, dist in rows]
        if any(vals):
            ax.barh(range(len(rows)), vals, left=left, color=color, label=cat)
        left = [a + b for a, b in zip(left, vals)]
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([r[0] for r in rows], fontsize=6.5)
    ax.invert_yaxis()
    ax.set_xlabel("% of delivered queries (all scenes)")
    ax.legend(fontsize=7, ncol=5, loc="lower center", bbox_to_anchor=(0.5, 1.0))
    fig.tight_layout()
    for ext in ("png", "pdf"):
        p = out / f"fig3_answer_distributions.{ext}"
        fig.savefig(p, dpi=170)
        files.append(p.name)
    plt.close(fig)
    return files


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--analysis", type=Path, required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    results = C.load_json(args.analysis / "results.json")
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "figures").mkdir(exist_ok=True)
    files = figures(results, args.output / "figures", args.analysis)
    table = paper_table(results)
    (args.output / "PAPER_TABLE.md").write_text(
        "# RQA-20261006 candidate compact table (not inserted into any manuscript)\n\n"
        f"Run `{args.run_id}`; initial-state bank; headline pool S1/S3/S4 (24 starts, 10 goals). Estimates are macro-weighted "
        "(items within start×goal cell → starts → goals → scenes); 95% intervals: 10,000 percentile bootstrap replicates "
        "(seed 6106) resampling physical starts within scene, conditional on the four fixed scenes and prompt templates. "
        "Text-only B is a finite set (counts, no interval). Answerability labels are provisional (no human review). "
        "Rows are distinct reasoner weights; tensor-identical readouts share one row.\n\n" + table + "\n\n"
        f"Read C against the label prior: answering “no” to every answerable C item scores "
        f"{100 * constant_no_baseline(args.analysis / 'scored_rows.csv', evaluated(results)[0], 'initial', C.MAIN_POOL_SCENES):.1f}% "
        "here, and balanced accuracy 50% is chance. Full metrics, controls and caveats: TABLES.md and INTERPRETATION.md.\n")
    (args.output / "TABLES.md").write_text("# RQA-20261006 generated result tables\n\n"
                                           f"Run `{args.run_id}`. Generated by `experiments.robolab_vqa.report` from `results.json`, "
                                           "`coverage.csv`, `scored_rows.csv` and `action_join_counts.csv`. Percentages are macro-weighted "
                                           "estimates with 95% physical-start bootstrap intervals where shown.\n\n" + tables_markdown(results, args.analysis))
    tax = b_error_taxonomy(args.analysis / "scored_rows.csv")
    with open(args.analysis / "b_error_taxonomy.csv", "w", newline="") as f:
        import csv as _csv
        w = _csv.DictWriter(f, fieldnames=list(tax[0]))
        w.writeheader()
        w.writerows(tax)
    print(table)
    print(json.dumps(files))



# ---------------------------------------------------------------------- markdown tables (all generated)
CONVERSE = {"left_of": "right_of", "right_of": "left_of", "in_front_of": "behind", "behind": "in_front_of"}


def fmt_est(d, signed=False):
    if not d or d.get("estimate") is None:
        return (d or {}).get("status", "undefined") if d else "n/a"
    v = 100 * d["estimate"]
    s = f"{v:+.1f}" if signed else f"{v:.1f}"
    return f"{s} {ci(d, signed=signed)}" if d.get("ci95") else s


def readout_name(results, lane):
    group = results["lanes"][lane].get("identity_group") or [lane]
    return " ≡ ".join(READOUT_LABEL.get(g, g) for g in group)


def b_error_taxonomy(scored_csv: Path) -> list[dict]:
    import csv as _csv

    counts: dict = {}
    with open(scored_csv) as f:
        for x in _csv.DictReader(f):
            if x["test"] != "B" or x["family"] != "original":
                continue
            key = (x["lane"], x["bank"], x["form"], x["scene"] in C.MAIN_POOL_SCENES)
            c = counts.setdefault(key, {"n": 0, "correct_tuple": 0, "invalid_format": 0, "relation_converse_of_gold": 0,
                                        "on_top_vs_stacked_swap": 0, "other_relation_error": 0, "object_error": 0})
            c["n"] += 1
            if x["valid"] != "True":
                c["invalid_format"] += 1
                continue
            gold, ans = json.loads(x["gold"]), json.loads(x["parsed_answer"])
            if ans == gold:
                c["correct_tuple"] += 1
                continue
            if ans["target"] != gold["target"] or ans["reference"] != gold["reference"]:
                c["object_error"] += 1
            if ans["relation"] != gold["relation"]:
                if CONVERSE.get(gold["relation"]) == ans["relation"]:
                    c["relation_converse_of_gold"] += 1
                elif {gold["relation"], ans["relation"]} == {"on_top_supported", "stacked_on"}:
                    c["on_top_vs_stacked_swap"] += 1
                else:
                    c["other_relation_error"] += 1
    rows = []
    for (lane, bank, form, main), c in sorted(counts.items()):
        rows.append({"lane": lane, "bank": bank, "form": form, "pool": "S1/S3/S4" if main else "S5", **c})
    return rows


def tables_markdown(results: dict, analysis_dir: Path) -> str:
    import csv as _csv

    lanes = evaluated(results)
    out = []
    # coverage
    out.append("### Coverage per readout (all 2,072 queries; shared readouts reuse the same responses)\n")
    out.append("| Readout | Proposed | Delivered | Valid format | Infrastructure missing |\n|---|---:|---:|---:|---:|")
    for lane, cov in results["coverage_summary"].items():
        out.append(f"| {lane} (responses from {cov['responses_from']}) | {cov['proposed']} | {cov['delivered']} | {cov['valid']} | "
                   f"{cov['infrastructure_missing']} |")
    rows = list(_csv.DictReader(open(analysis_dir / "coverage.csv")))
    out.append("\n| Readout | Family | Test | Bank | Proposed | Answerable | Excluded | Delivered | Valid | Unknown | Invalid | Missing |\n"
               "|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for r in rows:
        if r["lane"] in lanes:
            out.append(f"| {r['lane']} | {r['family']} | {r['test']} | {r['bank']} | {r['proposed']} | {r['answerable']} | "
                       f"{r['excluded']} | {r['delivered']} | {r['valid_format']} | {r['unknown']} | {r['invalid']} | "
                       f"{r['infrastructure_missing']} |")
    # primary endpoint
    for bank, title in (("initial", "C, initial bank"), ("secondary", "C, saved-rollout bank")):
        for pool in ("main_S1_S3_S4", "S5", "all_scenes"):
            out.append(f"\n### {title}, {pool.replace('_', ' ')}\n")
            out.append("| Readout | C DIR acc. | C TF acc. | C RF acc. | TF−RF gap pp | DIR−TF gap pp | Both-correct (TF,RF) | "
                       "Disagreement | Balanced acc. (all forms) | Recall yes / no (support) | Complete pairs (joint excl.) |\n"
                       "|---|---|---|---|---|---|---|---|---|---|---|")
            for lane in lanes:
                m = results["per_lane"][lane][bank][pool]
                p = m["C_TF_RF"]
                ba = m["C_balanced_all_forms"]
                out.append(f"| {readout_name(results, lane)} | {fmt_est(m['C_accuracy_DIR'])} | {fmt_est(p['accuracy_TF'])} | "
                           f"{fmt_est(p['accuracy_RF'])} | {fmt_est(p['gap'], True)} | {fmt_est(m['C_DIR_TF']['gap'], True)} | "
                           f"{fmt_est(p['both_correct'])} | {fmt_est(p['disagreement'])} | {fmt_est(ba['balanced_accuracy'])} | "
                           f"{pct(ba['recall_yes']['estimate'])} ({ba['recall_yes']['support']}) / {pct(ba['recall_no']['estimate'])} "
                           f"({ba['recall_no']['support']}) | {p['pairs_complete']} ({p['pairs_excluded_jointly']}) |")
    out.append("\n### C, all-geometry sensitivity (boundary-excluded items re-included), initial S1/S3/S4\n")
    out.append("| Readout | TF−RF gap pp | Complete pairs |\n|---|---|---|")
    for lane in lanes:
        p = results["per_lane"][lane]["initial"]["main_S1_S3_S4"]["C_TF_RF_all_geometry_sensitivity"]
        out.append(f"| {readout_name(results, lane)} | {fmt_est(p['gap'], True)} | {p['pairs_complete']} |")
    out.append("\n### C, all four scenes with S5 RF scored against the intended (stacked) goal — declared sensitivity\n")
    out.append("| Readout | TF−RF gap pp | Complete pairs |\n|---|---|---|")
    for lane in lanes:
        for bank in ("initial", "secondary"):
            p = results["per_lane"][lane][bank]["all_scenes_intended_goal_sensitivity"]["C_TF_RF"]
            out.append(f"| {readout_name(results, lane)} ({bank}) | {fmt_est(p['gap'], True)} | {p['pairs_complete']} |")
    # A
    for bank in ("initial", "secondary"):
        out.append(f"\n### A (scene relations), {bank} bank\n")
        out.append("| Readout | Pool | Accuracy | Balanced acc. | Recall yes / no | target−reference subject gap pp | Both-correct | "
                   "Answers yes/no/unknown/invalid |\n|---|---|---|---|---|---|---|---|")
        for lane in lanes:
            for pool in ("main_S1_S3_S4", "S5"):
                m = results["per_lane"][lane][bank][pool]
                ba = m["A_balanced"]
                dist = m["answer_distribution_A"]
                out.append(f"| {readout_name(results, lane)} | {pool.replace('_', ' ')} | {fmt_est(m['A_accuracy'])} | "
                           f"{fmt_est(ba['balanced_accuracy'])} | {pct(ba['recall_yes']['estimate'])} / {pct(ba['recall_no']['estimate'])} | "
                           f"{fmt_est(m['A_pairs']['gap'], True)} | {fmt_est(m['A_pairs']['both_correct'])} | "
                           f"{dist.get('yes', 0)}/{dist.get('no', 0)}/{dist.get('unknown', 0)}/{dist.get('invalid', 0)} |")
    # B
    out.append("\n### B (instruction understanding), text-only — finite set of 36 instructions (counts, no interval)\n")
    out.append("| Readout | Tuple correct | DIR | TF | RF | Valid | Target / reference / relation correct | TF/RF paired (TF=1,RF=0 / TF=0,RF=1) | Invalid reasons |\n"
               "|---|---|---|---|---|---|---|---|---|")
    for lane in lanes:
        t = results["per_lane"][lane]["text_only_B"]["original"]
        bf = t["by_form"]
        pt = t["paired_tuple_table"]
        out.append(f"| {readout_name(results, lane)} | {t['tuple_correct']}/{t['n']} | {bf.get('DIR', {}).get('tuple_correct', 0)}/12 | "
                   f"{bf.get('TF', {}).get('tuple_correct', 0)}/12 | {bf.get('RF', {}).get('tuple_correct', 0)}/12 | {t['valid']}/{t['n']} | "
                   f"{t['target_correct']}/{t['reference_correct']}/{t['relation_correct']} | {pt.get('TF=1,RF=0', 0)} / {pt.get('TF=0,RF=1', 0)} | "
                   f"{json.dumps(t['invalid_reasons'])} |")
    out.append("\n### B with initial images (288 start×instruction cells; 24 starts in S1/S3/S4)\n")
    out.append("| Readout | Pool | Tuple acc. | DIR | TF | RF | TF−RF gap pp | Target / reference / relation acc. |\n|---|---|---|---|---|---|---|---|")
    for lane in lanes:
        for pool in ("main_S1_S3_S4", "S5"):
            m = results["per_lane"][lane]["initial"][pool]
            out.append(f"| {readout_name(results, lane)} | {pool.replace('_', ' ')} | {fmt_est(m['B_image_tuple_accuracy'])} | "
                       f"{pct(est(m['B_image_tuple_accuracy_DIR']))} | {pct(est(m['B_image_tuple_accuracy_TF']))} | "
                       f"{pct(est(m['B_image_tuple_accuracy_RF']))} | {fmt_est(m['B_image_TF_RF']['gap'], True)} | "
                       f"{pct(est(m['B_image_target_accuracy']))} / {pct(est(m['B_image_reference_accuracy']))} / "
                       f"{pct(est(m['B_image_relation_accuracy']))} |")
    tax = b_error_taxonomy(analysis_dir / "scored_rows.csv")
    out.append("\n### B error taxonomy (exploratory, descriptive; strict scoring unchanged)\n")
    out.append("| Readout | Bank | Pool | Form | n | Correct tuple | Invalid format | Relation = converse of gold | on_top_supported↔stacked_on | "
               "Other relation error | Object error |\n|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|")
    for r in tax:
        if r["lane"] in lanes:
            out.append(f"| {r['lane']} | {r['bank']} | {r['pool']} | {r['form']} | {r['n']} | {r['correct_tuple']} | {r['invalid_format']} | "
                       f"{r['relation_converse_of_gold']} | {r['on_top_vs_stacked_swap']} | {r['other_relation_error']} | {r['object_error']} |")
    # controls
    out.append("\n### C no-image control (36 fixed answers; reused against initial-frame labels, interval conditional on the answers)\n")
    out.append("| Readout | Answers DIR | Answers TF | Answers RF | Reused accuracy S1/S3/S4 | Reused TF−RF gap pp |\n|---|---|---|---|---|---|")
    for lane in lanes:
        r = results["per_lane"][lane]
        m = r["initial"]["main_S1_S3_S4"]
        a = r["C_no_image_answers_by_form"]
        out.append(f"| {readout_name(results, lane)} | {json.dumps(a['DIR'])} | {json.dumps(a['TF'])} | {json.dumps(a['RF'])} | "
                   f"{fmt_est(m['C_no_image_reuse_accuracy'])} | {fmt_est(m['C_no_image_reuse_TF_RF']['gap'], True)} |")
    out.append("\n### Clause-placement control (reference early − late; same relation words; no action outcomes exist)\n")
    out.append("| Readout | B text-only (paired tuple table) | B image early−late pp | C image early−late pp | C image accuracy |\n|---|---|---|---|---|")
    for lane in lanes:
        r = results["per_lane"][lane]
        m = r["initial"]["main_S1_S3_S4"]
        out.append(f"| {readout_name(results, lane)} | {json.dumps(r['text_only_B']['placement']['paired_tuple_table'])} | "
                   f"{fmt_est(m['placement_B_image']['gap'], True)} | {fmt_est(m['placement_C_image']['gap'], True)} | "
                   f"{fmt_est(m['placement_C_image_accuracy'])} |")
    # contrasts
    out.append("\n### Checkpoint contrasts, initial S1/S3/S4 (descriptive; same start resamples)\n")
    out.append("| Contrast | Identical/shared? | C TF acc. | C RF acc. | C gap | A acc. | B image tuple |\n|---|---|---|---|---|---|---|")
    for name, c in results["checkpoint_contrasts_initial_main_pool"].items():
        out.append(f"| {name} | {c['shared_or_identical']} | {fmt_est(c['C_TF_accuracy'], True)} | {fmt_est(c['C_RF_accuracy'], True)} | "
                   f"{fmt_est(c['C_TF_RF_gap'], True)} | {fmt_est(c['A_accuracy'], True)} | {fmt_est(c['B_image_tuple_accuracy'], True)} |")
    # action join
    rows = list(_csv.DictReader(open(analysis_dir / "action_join_counts.csv")))
    out.append("\n### Initial-state QA correctness joined with existing action outcomes (counts; descriptive; family mapping N3/E3/F3)\n")
    out.append("| Readout | Test | Action field | Stratum | QA correct & action success | QA correct & action failure | QA incorrect & action success | "
               "QA incorrect & action failure | QA excluded |\n|---|---|---|---|---:|---:|---:|---:|---:|")
    agg: dict = {}
    for r in rows:
        if r["lane"] not in lanes or r["qa"] == "unmatched_or_missing":
            continue
        k = (r["lane"], r["test"], r["action_outcome_field"], r["stratum"])
        agg.setdefault(k, {})[(r["qa"], r["action"])] = int(r["n"])
    for (lane, test, field, stratum), v in sorted(agg.items()):
        excl = v.get(("qa_excluded", "action_success"), 0) + v.get(("qa_excluded", "action_failure"), 0)
        out.append(f"| {lane} | {test} | {field} | {stratum} | {v.get(('qa_correct', 'action_success'), 0)} | "
                   f"{v.get(('qa_correct', 'action_failure'), 0)} | {v.get(('qa_incorrect', 'action_success'), 0)} | "
                   f"{v.get(('qa_incorrect', 'action_failure'), 0)} | {excl} |")
    pol = results.get("policy_wording_contrasts_reference", [])
    out.append("\n### Existing policy wording contrast (TF − RF = S − I), reproduced from the paper analysis for comparison\n")
    out.append("| Policy | Stratum | Endpoint | Difference pp | 95% CI | Pairs |\n|---|---|---|---|---|---|")
    for r in pol:
        out.append(f"| {r['model']} | {r['stratum']} | {r['endpoint']} | {100 * float(r['difference']):+.1f} | "
                   f"[{100 * float(r['ci_low']):+.1f}, {100 * float(r['ci_high']):+.1f}] | {r['n_pairs']} |")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    sys.exit(main())
