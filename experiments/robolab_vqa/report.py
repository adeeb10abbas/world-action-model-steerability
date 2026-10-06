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
    rows = ["| Readout (distinct weights) | B tuple acc. text / image | A both-correct | C TF acc. | C RF acc. | "
            "C TF−RF gap, pp [95% CI] | C both-correct | C balanced acc. (TF+RF) | Coverage (delivered / valid, answerable C pairs) |",
            "|---|---|---|---|---|---|---|---|---|"]
    for lane in evaluated(results):
        r = results["per_lane"][lane]
        m = r["initial"]["main_S1_S3_S4"]
        tb = r["text_only_B"]["original"]
        main_text = [x for x in tb["paired_rows"] if x["scene"] in C.MAIN_POOL_SCENES]
        n_text = sum(1 for _ in main_text) * 2
        n_text_ok = sum((x.get("TF_correct") or 0) + (x.get("RF_correct") or 0) for x in main_text)
        group = results["lanes"][lane].get("identity_group") or [lane]
        name = " ≡ ".join(READOUT_LABEL.get(g, g) for g in group)
        cov = results["coverage_summary"].get(lane, {})
        rows.append(
            f"| {name} | {n_text_ok}/{n_text} TF+RF / {pct(est(m['B_image_tuple_accuracy']))}% | "
            f"{pct(est(m['A_pairs']['both_correct']))}% | {pct(est(m['C_TF_RF']['accuracy_TF']))}% | "
            f"{pct(est(m['C_TF_RF']['accuracy_RF']))}% | {pp(est(m['C_TF_RF']['gap']))} {ci(m['C_TF_RF']['gap'], signed=True)} | "
            f"{pct(est(m['C_TF_RF']['both_correct']))}% | {pct(est(m['C_balanced_all_forms']['balanced_accuracy']))}% | "
            f"{cov.get('delivered', 'n/a')}/{cov.get('valid', 'n/a')} of {cov.get('proposed', 'n/a')}; "
            f"{m['C_TF_RF']['pairs_complete']} C pairs |")
    return "\n".join(rows)


def figures(results: dict, out: Path) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    files = []
    lanes = evaluated(results)
    labels = [READOUT_LABEL.get(l, l).split(" (")[0].replace(" = ", "\n= ") for l in lanes]
    # Figure 1: primary endpoint
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.6), gridspec_kw={"width_ratios": [1.3, 1]})
    ax = axes[0]
    w = 0.35
    for j, (form, color) in enumerate((("TF", "#1f77b4"), ("RF", "#d62728"))):
        xs, ys, lo, hi = [], [], [], []
        for i, lane in enumerate(lanes):
            d = results["per_lane"][lane]["initial"]["main_S1_S3_S4"]["C_TF_RF"][f"accuracy_{form}"]
            xs.append(i + (j - 0.5) * w)
            ys.append(100 * d["estimate"])
            lo.append(100 * (d["estimate"] - d["ci95"][0]))
            hi.append(100 * (d["ci95"][1] - d["estimate"]))
        ax.bar(xs, ys, w, yerr=[lo, hi], color=color, alpha=0.85, label=form, capsize=3)
    ax.axhline(50, color="grey", lw=0.8, ls=":")
    ax.set_xticks(range(len(lanes)))
    ax.set_xticklabels(labels, fontsize=7)
    ax.set_ylabel("C accuracy, initial S1/S3/S4 (%)")
    ax.set_ylim(0, 100)
    ax.legend(fontsize=8)
    ax.set_title("Instruction + scene (C): TF vs RF", fontsize=9)
    ax = axes[1]
    for i, lane in enumerate(lanes):
        d = results["per_lane"][lane]["initial"]["main_S1_S3_S4"]["C_TF_RF"]["gap"]
        ax.errorbar(100 * d["estimate"], i, xerr=[[100 * (d["estimate"] - d["ci95"][0])], [100 * (d["ci95"][1] - d["estimate"])]],
                    fmt="o", color="k", capsize=3)
    pol = {r["model"]: r for r in results.get("policy_wording_contrasts_reference", [])
           if r["stratum"] == "all" and r["endpoint"] == "stable_ever"}
    for i, lane in enumerate(lanes):
        fam = FAMILY_POLICY.get(lane)
        if fam and fam in pol:
            r = pol[fam]
            ax.errorbar(100 * float(r["difference"]), i + 0.25,
                        xerr=[[100 * (float(r["difference"]) - float(r["ci_low"]))], [100 * (float(r["ci_high"]) - float(r["difference"]))]],
                        fmt="s", color="#2ca02c", ms=4, capsize=2)
    ax.axvline(0, color="grey", lw=0.8)
    ax.set_yticks(range(len(lanes)))
    ax.set_yticklabels(labels, fontsize=7)
    ax.set_xlabel("TF − RF (pp); black: VQA C; green: policy stable-ever (existing)")
    ax.set_title("Wording gap with 95% start-bootstrap CI", fontsize=9)
    fig.tight_layout()
    for ext in ("png", "pdf"):
        p = out / f"fig1_primary_C_TF_RF.{ext}"
        fig.savefig(p, dpi=170)
        files.append(p.name)
    plt.close(fig)
    # Figure 2: test overview (initial bank, main pool + S5) and secondary
    metrics = [("A acc.", lambda m: m["A_accuracy"]), ("B img tuple", lambda m: m.get("B_image_tuple_accuracy")),
               ("C DIR", lambda m: m["C_accuracy_DIR"]), ("C TF", lambda m: m["C_accuracy_TF"]), ("C RF", lambda m: m["C_accuracy_RF"]),
               ("C no-image", lambda m: m.get("C_no_image_reuse_accuracy"))]
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.6), sharey=True)
    for ax, (bank, pool, title) in zip(axes, (("initial", "main_S1_S3_S4", "Initial, S1/S3/S4"),
                                               ("initial", "S5", "Initial, S5 (separate)"),
                                               ("secondary", "main_S1_S3_S4", "Saved rollout frames, S1/S3/S4"))):
        width = 0.8 / max(len(lanes), 1)
        for i, lane in enumerate(lanes):
            m = results["per_lane"][lane][bank][pool]
            ys, errs = [], [[], []]
            for name, fn in metrics:
                d = fn(m)
                if d is None or d.get("estimate") is None:
                    ys.append(float("nan"))
                    errs[0].append(0)
                    errs[1].append(0)
                    continue
                ys.append(100 * d["estimate"])
                c = d.get("ci95") or [d["estimate"], d["estimate"]]
                errs[0].append(100 * (d["estimate"] - c[0]))
                errs[1].append(100 * (c[1] - d["estimate"]))
            xs = [k + (i - (len(lanes) - 1) / 2) * width for k in range(len(metrics))]
            ax.bar(xs, ys, width, yerr=errs, capsize=2, label=labels[i].replace("\n", " "))
        ax.axhline(50, color="grey", lw=0.8, ls=":")
        ax.set_xticks(range(len(metrics)))
        ax.set_xticklabels([n for n, _ in metrics], fontsize=7, rotation=20)
        ax.set_title(title, fontsize=9)
        ax.set_ylim(0, 100)
    axes[0].set_ylabel("accuracy (%), macro-weighted")
    axes[0].legend(fontsize=6, loc="lower left")
    fig.tight_layout()
    for ext in ("png", "pdf"):
        p = out / f"fig2_tests_overview.{ext}"
        fig.savefig(p, dpi=170)
        files.append(p.name)
    plt.close(fig)
    # Figure 3: answer distributions
    fig, ax = plt.subplots(figsize=(11, 3.4))
    cats = ["yes", "no", "unknown", "invalid", "infrastructure_missing"]
    colors = ["#2ca02c", "#1f77b4", "#bcbd22", "#d62728", "#7f7f7f"]
    rows = []
    for lane in lanes:
        r = results["per_lane"][lane]
        for bank, key in (("initial", "answer_distribution_A"), ("initial", "answer_distribution_C"),
                          ("secondary", "answer_distribution_A"), ("secondary", "answer_distribution_C")):
            dist = r[bank]["all_scenes"][key]
            rows.append((f"{labels[lanes.index(lane)].split(chr(10))[0][:22]} {key[-1]}-{bank[:4]}", dist))
        rows.append((f"{labels[lanes.index(lane)].split(chr(10))[0][:22]} C-noimg", r["C_no_image_answers"]))
    left = [0] * len(rows)
    for cat, color in zip(cats, colors):
        vals = []
        for _, dist in rows:
            tot = sum(dist.values()) or 1
            vals.append(100 * dist.get(cat, 0) / tot)
        ax.barh(range(len(rows)), vals, left=left, color=color, label=cat)
        left = [a + b for a, b in zip(left, vals)]
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([r[0] for r in rows], fontsize=6)
    ax.set_xlabel("% of queries")
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
    files = figures(results, args.output / "figures")
    table = paper_table(results)
    (args.output / "PAPER_TABLE.md").write_text(
        "# RQA-20261006 candidate compact table (not inserted into any manuscript)\n\n"
        f"Run `{args.run_id}`; initial-state bank; headline pool S1/S3/S4 (24 starts, 10 goals). Estimates are macro-weighted "
        "(items within start×goal cell → starts → goals → scenes); 95% intervals: 10,000 percentile bootstrap replicates "
        "(seed 6106) resampling physical starts within scene, conditional on the four fixed scenes and prompt templates. "
        "Text-only B is a finite set (counts, no interval). Answerability labels are provisional (no human review). "
        "Rows are distinct reasoner weights; tensor-identical readouts share one row.\n\n" + table + "\n")
    print(table)
    print(json.dumps(files))


if __name__ == "__main__":
    sys.exit(main())
