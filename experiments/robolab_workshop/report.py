"""Paper tables and figures from frozen features + analyze.py results (IMPLEMENTATION_PLAN task 5).

    python -m experiments.robolab_workshop.report --features conf_features.jsonl --results results/results.json \
        --release release.json --out results/
Writes coverage.csv, episode_outcomes.csv, paired_wording.csv, goal_response.csv, forecast_events.csv,
diagnostic_utility.csv, claims.csv and fig_goal_response.pdf, fig_wording.pdf, fig_forecast_utility.pdf.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from .catalog import SCENES


def _w(path: Path, header: list[str], rows: list[list]) -> None:
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--features", type=Path, required=True)
    ap.add_argument("--results", type=Path, required=True)
    ap.add_argument("--release", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--phase", default="confirmation")
    args = ap.parse_args()
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    feats = [json.loads(x) for x in args.features.read_text().splitlines() if x.strip()]
    rows = [r for r in feats if r.get("phase") == args.phase]
    res = json.loads(args.results.read_text())
    rel = json.loads(args.release.read_text())
    args.out.mkdir(parents=True, exist_ok=True)
    models = sorted({r["model_id"] for r in rows}) or ["N3", "E3", "F3"]

    # coverage: planned (release-bound + omitted), valid, invalid, missing
    bound = {}
    for line in (args.release.parent / rel["bound_rows"]["path"]).read_text().splitlines():
        b = json.loads(line)
        bound[b["episode_id"]] = b
    got = {r["episode_id"]: r for r in rows}
    cov = defaultdict(lambda: defaultdict(int))
    for eid, b in bound.items():
        k = (b["model_id"], b["scene_id"])
        cov[k]["planned"] += 1
        r = got.get(eid)
        cov[k]["valid" if r and r["status"] == "valid" else "invalid" if r else "missing"] += 1
        if r and r["status"] == "valid":
            cov[k]["event_scorable"] += int(r.get("event") is not None)
            cov[k]["primary_fallback"] += int(bool((r.get("primary_window") or {}).get("fallback")))
    for eid in rel["bound_rows"]["omitted_episode_ids"]:
        parts = eid.split("-")
        cov[(parts[1], parts[2])]["omitted_no_start"] += 1
    cols = ["planned", "valid", "invalid", "missing", "omitted_no_start", "event_scorable", "primary_fallback"]
    _w(args.out / "coverage.csv", ["model", "scene"] + cols,
       [[m, s] + [cov[(m, s)][c] for c in cols] for (m, s) in sorted(cov)])

    _w(args.out / "episode_outcomes.csv",
       ["episode_id", "model", "scene", "state", "goal", "form", "status", "stratum", "stable_ever", "stable_at_final",
        "study_goal_first_hit", "native_matched_task", "native_matched_first_hit", "failure_stage", "event",
        "primary_request", "primary_fallback", "mover_final_displacement_m"],
       [[r["episode_id"], r["model_id"], r["scene_id"], r["state_slot"], r["goal_id"], r["form"], r["status"],
         r.get("stratum"), int(r["stable_ever"]), int(r["stable_at_final"]), r.get("study_goal_first_hit"),
         r.get("native_matched_task"), r.get("native_matched_task_first_hit"), r.get("failure_stage"), r.get("event"),
         (r.get("primary_window") or {}).get("request_index"), int(bool((r.get("primary_window") or {}).get("fallback"))),
         r.get("mover_final_displacement_m")] for r in sorted(rows, key=lambda x: x["episode_id"])])

    # paired wording, per (model, scene, state, goal)
    pairs = defaultdict(dict)
    for r in rows:
        if r["status"] == "valid":
            pairs[(r["model_id"], r["scene_id"], r["state_slot"], r["goal_id"])][r["form"]] = r
    pw = []
    for k, f in sorted(pairs.items()):
        g = lambda x, key: (int(f[x][key]) if x in f and f[x].get(key) is not None else "")
        pw.append(list(k) + [g("D", "stable_ever"), g("S", "stable_ever"), g("I", "stable_ever"),
                             g("D", "event"), g("S", "event"), g("I", "event"), f.get("S", f.get("D", {})).get("stratum")])
    _w(args.out / "paired_wording.csv", ["model", "scene", "state", "goal", "stable_D", "stable_S", "stable_I",
                                         "event_D", "event_S", "event_I", "stratum"], pw)

    gr = []
    for key, v in sorted(res.get("E4_goal_separation", {}).items()):
        m, s = key.split("|")
        for g, x in sorted(v.items()):
            gr.append([m, s, g, x["n"], x["stable"], x["stable"] / x["n"] if x["n"] else "",
                       *[round(c, 4) for c in x["mean_final_xy"]], round(x["mean_displacement_m"], 4)])
    _w(args.out / "goal_response.csv", ["model", "scene", "goal", "n", "stable", "rate", "mean_final_x", "mean_final_y",
                                        "mean_displacement_m"], gr)

    fe = []
    for m in models:
        mr = [r for r in rows if r["model_id"] == m and r["status"] == "valid"]
        for s in sorted({r["scene_id"] for r in mr}):
            sr = [r for r in mr if r["scene_id"] == s]
            sc = [r for r in sr if r.get("event") is not None]
            wp = [r.get("window_primary") or {} for r in sc]
            fe.append([m, s, len(sr), len(sc), sum(r["event"] for r in sc),
                       sum(bool(w.get("wrong_object")) for w in wp), sum(bool(w.get("contradictory_release")) for w in wp),
                       sum(bool(w.get("neutral_no_decision")) for w in wp),
                       sum(bool(w.get("goal_consistent_interaction")) for w in wp),
                       sum(bool(w.get("physical_failure")) for w in wp)])
    _w(args.out / "forecast_events.csv", ["model", "scene", "valid", "event_scorable", "event_positive", "wrong_object",
                                          "contradictory_release", "neutral_no_decision", "goal_consistent_interaction",
                                          "physical_failure"], fe)

    du = []
    for name, key in (("E1 pooled", "E1"), ("E1 missingness-only", "E1_missingness_only"), ("A3 persistence", "A3_persistence")):
        x = res.get(key, {})
        du.append([name, x.get("status", "computed"), x.get("n"), x.get("events"), x.get("brier_baseline"),
                   x.get("brier_augmented"), x.get("delta"), *(x.get("ci95_conditional_bootstrap") or ["", ""])[:2]])
    for m, x in sorted(res.get("E1_by_model", {}).items()):
        du.append([f"E1 {m}", "computed", x.get("n"), x.get("events"), x.get("brier_baseline"), x.get("brier_augmented"),
                   x.get("delta"), "", ""])
    a4 = res.get("A4", {})
    du.append(["A4 permuted", a4.get("status", "computed"), "", "", "", "", a4.get("delta_mean"), a4.get("delta_p2_5"),
               a4.get("delta_p97_5")])
    _w(args.out / "diagnostic_utility.csv", ["comparison", "status", "n", "positives", "brier_baseline",
                                             "brier_augmented", "delta", "ci_lo", "ci_hi"], du)

    # Figures
    fig, axes = plt.subplots(1, 4, figsize=(12, 2.8))
    for ax, s in zip(axes, ("S1", "S3", "S4", "S5")):
        goals = list(SCENES[s]["goals"])
        for i, m in enumerate(models):
            v = res.get("E4_goal_separation", {}).get(f"{m}|{s}", {})
            rates = [v[g]["stable"] / v[g]["n"] if g in v and v[g]["n"] else np.nan for g in goals]
            ax.bar(np.arange(len(goals)) + (i - 1) * 0.27, rates, 0.27, label=m)
        ax.set_xticks(range(len(goals)), goals)
        ax.set_ylim(0, 1)
        ax.set_title(s)
    axes[0].set_ylabel("stable success")
    axes[-1].legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(args.out / "fig_goal_response.pdf")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(4.5, 2.8))
    for j, (name, key) in enumerate((("S−I (E2)", "E2_S_minus_I"), ("D−S (E3)", "E3_D_minus_S"))):
        x = res.get(key, {})
        if x.get("n_pairs"):
            lo, hi = x.get("ci95_state_bootstrap", [np.nan, np.nan])[:2]
            ax.errorbar([j], [x["mean_signed_difference"]], yerr=[[x["mean_signed_difference"] - lo], [hi - x["mean_signed_difference"]]],
                        fmt="o", capsize=4)
            ax.text(j + 0.08, x["mean_signed_difference"], f"p_Holm={x.get('p_holm', float('nan')):.3f}", fontsize=7)
    ax.axhline(0, color="k", lw=0.5)
    ax.set_xticks([0, 1], ["S−I (E2)", "D−S (E3)"])
    ax.set_ylabel("paired Δ stable success")
    fig.tight_layout()
    fig.savefig(args.out / "fig_wording.pdf")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(4.5, 2.8))
    labels, vals, errs = [], [], []
    for row in du:
        if row[6] not in (None, ""):
            labels.append(row[0])
            vals.append(float(row[6]))
            errs.append([float(row[6]) - float(row[7]), float(row[8]) - float(row[6])] if row[7] not in ("", None) else [0, 0])
    if vals:
        ax.errorbar(range(len(vals)), vals, yerr=np.array(errs).T, fmt="o", capsize=4)
        ax.set_xticks(range(len(vals)), labels, rotation=30, ha="right", fontsize=7)
    else:
        ax.text(0.5, 0.5, "forecast labels pending", ha="center", va="center", transform=ax.transAxes)
        ax.set_xticks([])
    ax.axhline(0, color="k", lw=0.5)
    ax.set_ylabel("Brier(base) − Brier(+forecast)")
    fig.tight_layout()
    fig.savefig(args.out / "fig_forecast_utility.pdf")
    plt.close(fig)

    e2, e3 = res.get("E2_S_minus_I", {}), res.get("E3_D_minus_S", {})
    claims = [
        ["Goal response (E4)", "goal_response.csv; fig_goal_response.pdf", "descriptive"],
        ["Equivalent-wording sensitivity (E2 S−I)", f"Δ={e2.get('mean_signed_difference')}, p_Holm={e2.get('p_holm')}",
         "confirmatory"],
        ["Rephrasing control (E3 D−S)", f"Δ={e3.get('mean_signed_difference')}, p_Holm={e3.get('p_holm')}", "confirmatory"],
        ["Forecast adds held-out information (E1)", res.get("E1", {}).get("status", f"Δ={res.get('E1', {}).get('delta')}"),
         "confirmatory (label-dependent)"],
        ["A1 native first-hit vs stable", "results.json A1_*", "descriptive"],
    ]
    _w(args.out / "claims.csv", ["claim", "evidence", "status"], claims)
    print("wrote tables and figures to", args.out)


if __name__ == "__main__":
    main()
