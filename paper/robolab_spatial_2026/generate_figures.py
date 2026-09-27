#!/usr/bin/env python3
"""Reproduce the paper's action-only tables and vector figures from committed data.

Requirements: Python >=3.10, numpy, matplotlib. Run from any directory:
    python paper/robolab_spatial_2026/generate_figures.py

The original feature table is never changed. Initial-goal status is taken from
the frozen accepted-state registry, not the transient episode reset contacts.
The original all-episode stable-ever contrasts remain the confirmatory tests.
Corrected-stratum summaries and final-state contrasts are sensitivity analyses.
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Rectangle
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DATA = ROOT / "artifacts/robolab_workshop_20260926"
FEATURES = DATA / "analysis/conf_features.jsonl"
REGISTRY = DATA / "states/accepted_states.json"
MODELS = ("N3", "E3", "F3")
SCENES = ("S1", "S3", "S4", "S5")
GOALS = {"S1": ("L", "R", "F", "B"), "S3": ("TOP", "L", "R"),
         "S4": ("TOP", "L", "R"), "S5": ("LR", "RL")}
DISPLAY = {"N3": "Nano", "E3": "Edge", "F3": "FLUX", "pooled": "Pooled"}
COLORS = {"N3": "#087F8C", "E3": "#D97926", "F3": "#7856A5", "pooled": "#20252B"}
N_BOOT, N_FLIP = 10000, 100000
SEED_BOOT, SEED_FLIP = 8401, 8402


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_csv(path, rows):
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def bootstrap_cluster_means(means):
    """Each scene receives equal weight, and its eight states are resampled.

    All models, goals and wording forms belonging to one physical state remain
    together. The loop and seed reproduce the frozen analyze.py bootstrap.
    """
    rng = np.random.default_rng(SEED_BOOT)
    by_scene = {s: np.array([v for (sc, _), v in sorted(means.items()) if sc == s])
                for s in sorted({k[0] for k in means})}
    draws = np.empty(N_BOOT)
    for d in range(N_BOOT):
        vals = [v[rng.choice(len(v), size=len(v), replace=True)].mean() for v in by_scene.values()]
        draws[d] = np.mean(vals)
    return np.percentile(draws, [2.5, 97.5]).tolist()


def cluster_means(rows, field):
    groups = defaultdict(list)
    for r in rows:
        groups[(r["scene_id"], r["state_slot"])].append(float(r[field]))
    return {k: float(np.mean(v)) for k, v in groups.items()}


def rate(rows, field, interval=False):
    means = cluster_means(rows, field)
    out = {"n": len(rows), "successes": sum(bool(r[field]) for r in rows),
           "raw_rate": float(np.mean([r[field] for r in rows])),
           "scene_goal_weighted_rate": float(np.mean(list(means.values())))}
    if interval:
        out["ci95_state_bootstrap"] = bootstrap_cluster_means(means)
    return out


def contrast(rows, a, b, field):
    pairs = defaultdict(dict)
    for r in rows:
        pairs[(r["model_id"], r["scene_id"], r["state_slot"], r["goal_id"])][r["form"]] = r
    grouped = defaultdict(list)
    positive = negative = 0
    for (_, scene, state, _), forms in pairs.items():
        assert set(forms) == {"D", "S", "I"}, "Incomplete paired triplet"
        d = float(forms[a][field]) - float(forms[b][field])
        grouped[(scene, state)].append(d)
        positive += d > 0
        negative += d < 0
    means = {k: float(np.mean(v)) for k, v in grouped.items()}
    vals = np.array(list(means.values()))
    effect = float(vals.mean())
    rng = np.random.default_rng(SEED_FLIP)
    null = np.abs((rng.choice([-1.0, 1.0], size=(N_FLIP, len(vals))) * vals).mean(axis=1))
    p = float((np.sum(null >= abs(effect) - 1e-12) + 1) / (N_FLIP + 1))
    return {"contrast": f"{a}-{b}", "endpoint": field, "n_pairs": len(pairs),
            "n_state_clusters": len(means), "difference": effect,
            "ci95_state_bootstrap": bootstrap_cluster_means(means),
            "a_only": int(positive), "b_only": int(negative), "p_sign_flip": p}


def holm(contrasts):
    order = np.argsort([x["p_sign_flip"] for x in contrasts])
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, min(1., (len(order) - rank) * contrasts[index]["p_sign_flip"]))
        contrasts[index]["p_holm_two_contrasts"] = running


def analyze(rows):
    results = {"provenance": {
        "features_path": str(FEATURES.relative_to(ROOT)), "features_sha256": sha256(FEATURES),
        "accepted_states_path": str(REGISTRY.relative_to(ROOT)), "accepted_states_sha256": sha256(REGISTRY),
        "analysis_script_sha256": sha256(Path(__file__)),
        "initial_stratum_source": "accepted_states.scenes[scene].slots[state].initial_study[goal].goal",
        "outcome_fields": "Original frozen stable_ever and stable_at_final values; not rescored.",
        "weighting": "Equal models, scenes and goals within scene; paired physical states. Eight states per scene.",
        "bootstrap": {"draws": N_BOOT, "seed": SEED_BOOT, "unit": "scene x state; stratified by scene"},
        "sign_flip": {"draws": N_FLIP, "seed": SEED_FLIP, "unit": "scene x state"},
        "multiple_testing": "Holm across S-I and D-S in the pooled confirmatory family. Per-model p-values are descriptive.",
        "sensitivity_note": "Corrected-stratum subgroup and final-state analyses are post-hoc sensitivity analyses; they do not replace the original all-episode stable-ever tests."
    }, "coverage": {"episodes": len(rows), "models": 3, "scenes": 4, "physical_states": 32,
                     "goals": 12, "forms_per_goal": 3,
                     "corrected_initially_satisfied": sum(r["initial_goal_true_registry"] for r in rows),
                     "corrected_achievement": sum(not r["initial_goal_true_registry"] for r in rows),
                     "stratum_reclassifications": sum(r["stratum_original"] != r["stratum_corrected"] for r in rows)},
               "outcomes": {}, "contrasts": {}, "paired_state_effects": []}
    count_csv, wording_csv, goals_csv = [], [], []
    for model in ("pooled", *MODELS):
        model_rows = [r for r in rows if model == "pooled" or r["model_id"] == model]
        results["outcomes"][model] = {}
        results["contrasts"][model] = {}
        for stratum in ("all", "achievement", "maintenance"):
            subset = [r for r in model_rows if stratum == "all" or r["stratum_corrected"] == stratum]
            results["outcomes"][model][stratum] = {}
            for form in ("all", "D", "S", "I"):
                form_rows = [r for r in subset if form == "all" or r["form"] == form]
                result = {f: rate(form_rows, f) for f in ("stable_ever", "stable_at_final")}
                results["outcomes"][model][stratum][form] = result
                for endpoint, counts in result.items():
                    count_csv.append({"model": model, "stratum": stratum, "form": form,
                                      "endpoint": endpoint, **counts})
            if stratum == "maintenance":
                continue
            results["contrasts"][model][stratum] = {}
            for endpoint in ("stable_ever", "stable_at_final"):
                contrasts = [contrast(subset, a, b, endpoint) for a, b in (("S", "I"), ("D", "S"))]
                if model == "pooled":
                    holm(contrasts)
                results["contrasts"][model][stratum][endpoint] = {c["contrast"]: c for c in contrasts}
                for c in contrasts:
                    flat = {k: v for k, v in c.items() if k != "ci95_state_bootstrap"}
                    lo, hi = c["ci95_state_bootstrap"]
                    wording_csv.append({"model": model, "stratum": stratum, **flat,
                                        "ci_low": lo, "ci_high": hi,
                                        "p_holm_two_contrasts": c.get("p_holm_two_contrasts", "")})
    for model in MODELS:
        for scene in SCENES:
            for goal in GOALS[scene]:
                subset = [r for r in rows if (r["model_id"], r["scene_id"], r["goal_id"]) == (model, scene, goal)]
                achievement = [r for r in subset if r["stratum_corrected"] == "achievement"]
                goals_csv.append({"model": model, "scene": scene, "goal": goal, "n_all": len(subset),
                                  "n_achievement": len(achievement), "n_maintenance": len(subset)-len(achievement),
                                  "achievement_stable_ever": sum(r["stable_ever"] for r in achievement),
                                  "achievement_stable_at_final": sum(r["stable_at_final"] for r in achievement),
                                  "achievement_rate": float(np.mean([r["stable_ever"] for r in achievement])) if achievement else None})
    results["goal_response"] = goals_csv
    results["goal_response_by_form"] = []
    for model in MODELS:
        for scene in SCENES:
            for goal in GOALS[scene]:
                for form in ("D", "S", "I"):
                    subset = [r for r in rows if (r["model_id"], r["scene_id"], r["goal_id"], r["form"])
                              == (model, scene, goal, form) and r["stratum_corrected"] == "achievement"]
                    results["goal_response_by_form"].append({"model": model, "scene": scene, "goal": goal, "form": form,
                        "n_achievement": len(subset), "stable_ever": sum(r["stable_ever"] for r in subset),
                        "stable_at_final": sum(r["stable_at_final"] for r in subset),
                        "rate": float(np.mean([r["stable_ever"] for r in subset])) if subset else None})
    for model in (*MODELS, "pooled"):
        pairs = defaultdict(dict)
        for r in rows:
            if model == "pooled" or r["model_id"] == model:
                pairs[(r["model_id"], r["scene_id"], r["state_slot"], r["goal_id"])][r["form"]] = r
        for a, b in (("S", "I"), ("D", "S")):
            grouped = defaultdict(list)
            for (_, scene, state, _), forms in pairs.items():
                grouped[(scene, state)].append(float(forms[a]["stable_ever"]) - float(forms[b]["stable_ever"]))
            assert len(grouped) == 32
            for (scene, state), differences in sorted(grouped.items()):
                results["paired_state_effects"].append({"model": model, "scene": scene, "state": state,
                    "contrast": f"{a}-{b}", "n_goal_model_pairs": len(differences),
                    "mean_paired_difference": float(np.mean(differences))})
    results["provenance"]["violin_display"] = {
        "unit": "One observed paired mean per physical state; 32 points per model/contrast; pooled points average models and goals within the same state.",
        "support": "Discrete bounded paired means in [-1,1]; KDE is a display aid, not a continuous-response model.",
        "density": "Gaussian KDE with bandwidth factor 0.4, clipped to observed data extrema (and thus to [-1,1]); constant distributions use a line without KDE.",
        "jitter": "Vertical-only deterministic jitter, seed 8500; measured horizontal values are unchanged.",
        "summary": "Diamond and horizontal interval: unchanged mean and stratified state-bootstrap 95% CI."
    }
    return results, count_csv, wording_csv, goals_csv


def figures(results):
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9,
                         "axes.labelsize": 9, "axes.titlesize": 9.5, "xtick.labelsize": 8,
                         "ytick.labelsize": 9, "pdf.fonttype": 42, "ps.fonttype": 42,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "savefig.facecolor": "white"})
    fig, axes = plt.subplots(1, 2, figsize=(5.5, 2.25), sharey=True)
    for ax, key, title in zip(axes, ("S-I", "D-S"),
                             ("(a) Reference inversion (S − I)", "(b) Ordinary rephrasing (D − S)")):
        for y, model in enumerate((*MODELS, "pooled")):
            c = results["contrasts"][model]["all"]["stable_ever"][key]
            effect = 100*c["difference"]
            lo, hi = (100*v for v in c["ci95_state_bootstrap"])
            ax.errorbar(effect, y, xerr=[[effect-lo], [hi-effect]], fmt="D" if model == "pooled" else "o",
                        color=COLORS[model], markersize=5.1, capsize=3, elinewidth=1.5, zorder=3)
            ax.text(31.8, y, f"{effect:+.1f}", va="center", ha="right", fontsize=8.5, color=COLORS[model])
        ax.axvline(0, ls=(0, (3, 3)), color="#8E959A", lw=.8, zorder=1)
        ax.axhline(2.5, lw=.6, color="#D5D9DD", zorder=1)
        ax.set(title=title, xlim=(-10, 34), ylim=(3.5, -.5), xticks=(-10, 0, 10, 20, 30))
        ax.spines["left"].set_visible(False)
        ax.tick_params(axis="y", length=0)
        ax.grid(axis="x", color="#EDEFF1", lw=.5)
        ax.set_xlabel("Outcome difference (percentage points)", fontsize=8)
    axes[0].set_yticks(range(4), [DISPLAY[m] for m in (*MODELS, "pooled")])
    fig.text(.5, .975, "Requested arrangement held for at least one second", ha="center", va="top", fontsize=9)
    fig.subplots_adjust(left=.115, right=.985, top=.77, bottom=.24, wspace=.24)
    fig.savefig(HERE / "figures/wording_effect_forest.pdf")
    fig.savefig(HERE / "figures/wording_effect_forest.png", dpi=220)
    plt.close(fig)

    # Paired-state distributions, not pseudo-continuous binary episode outcomes.
    # Matplotlib evaluates each KDE only from its observed minimum to maximum.
    fig, axes = plt.subplots(1, 2, figsize=(5.5, 2.45), sharey=True)
    rng = np.random.default_rng(8500)
    for ax, key, title in zip(axes, ("S-I", "D-S"),
                             ("(a) Reference inversion (S − I)", "(b) Ordinary rephrasing (D − S)")):
        for y, model in enumerate((*MODELS, "pooled")):
            observed = np.array([100*r["mean_paired_difference"] for r in results["paired_state_effects"]
                                 if r["model"] == model and r["contrast"] == key])
            c = results["contrasts"][model]["all"]["stable_ever"][key]
            effect = 100*c["difference"]
            assert observed.shape == (32,) and np.isfinite(observed).all()
            assert np.all((-100 <= observed) & (observed <= 100))
            assert np.isclose(observed.mean(), effect, atol=1e-12)
            if np.ptp(observed) > 1e-12:
                violin = ax.violinplot([observed], positions=[y], orientation="horizontal", widths=.74,
                                      showmeans=False, showextrema=False, showmedians=False, points=160, bw_method=.4)
                for body in violin["bodies"]:
                    body.set_facecolor(COLORS[model])
                    body.set_edgecolor(COLORS[model])
                    body.set_alpha(.23)
                    body.set_linewidth(.7)
            else:
                ax.vlines(observed[0], y-.30, y+.30, color=COLORS[model], alpha=.35, lw=3)
            # Within each repeated value, spread points vertically; never perturb the measured effect.
            offsets = np.zeros(len(observed))
            for value in np.unique(observed):
                indices = np.flatnonzero(observed == value)
                offsets[indices] = rng.permutation(np.linspace(-.23, .23, len(indices))) if len(indices) > 1 else 0
            ax.scatter(observed, y+offsets, s=6, color=COLORS[model], alpha=.70, linewidths=0, zorder=3)
            lo, hi = (100*v for v in c["ci95_state_bootstrap"])
            ax.errorbar(effect, y+.29, xerr=[[effect-lo], [hi-effect]], fmt="D", color="#161A1D",
                        markerfacecolor="white", markeredgewidth=.8, markersize=3.2,
                        capsize=2, elinewidth=1.2, zorder=5)
            ax.text(113, y-.22, f"{effect:+.1f}", va="center", ha="right", fontsize=8, color=COLORS[model])
        ax.axvline(0, ls=(0, (3, 3)), color="#8E959A", lw=.8, zorder=1)
        ax.axhline(2.5, lw=.6, color="#D5D9DD", zorder=1)
        ax.set(title=title, xlim=(-60, 118), ylim=(3.55, -.5), xticks=(-50, 0, 50, 100))
        ax.spines["left"].set_visible(False)
        ax.tick_params(axis="y", length=0)
        ax.grid(axis="x", color="#EDEFF1", lw=.5)
        ax.set_xlabel("Paired state difference (percentage points)", fontsize=7.7)
    axes[0].set_yticks(range(4), [DISPLAY[m] for m in (*MODELS, "pooled")])
    fig.text(.5, .985, "Requested arrangement held for at least one second", ha="center", va="top", fontsize=9)
    fig.text(.115, .045, "32 matched starts per row · ◇ mean and 95% confidence interval", fontsize=7.7)
    fig.subplots_adjust(left=.115, right=.985, top=.80, bottom=.265, wspace=.24)
    fig.savefig(HERE / "figures/wording_effect.pdf")
    fig.savefig(HERE / "figures/wording_effect.png", dpi=220)
    plt.close(fig)

    goals = [(s, g) for s in SCENES for g in GOALS[s]]
    lookup = {(r["model"], r["scene"], r["goal"]): r for r in results["goal_response"]}
    values = np.full((3, len(goals)), np.nan)
    for i, model in enumerate(MODELS):
        for j, (scene, goal) in enumerate(goals):
            rate = lookup[model, scene, goal]["achievement_rate"]
            if rate is not None:
                values[i, j] = rate
    cmap = LinearSegmentedColormap.from_list("paper_teal", ["#F3F8F8", "#97CDCD", "#087F8C", "#034E58"])
    cmap.set_bad("#E8E8E8")
    fig, ax = plt.subplots(figsize=(5.5, 2.2))
    im = ax.imshow(values, cmap=cmap, vmin=0, vmax=1, aspect="auto")
    for i, model in enumerate(MODELS):
        for j, (scene, goal) in enumerate(goals):
            row = lookup[model, scene, goal]
            if row["n_achievement"]:
                value = row["achievement_rate"]
                ax.text(j, i, f"{int(100*value+.5)}", ha="center", va="center", fontsize=9,
                        color="white" if value >= .57 else "#17383D")
            else:
                ax.add_patch(Rectangle((j-.5, i-.5), 1, 1, fill=False, hatch="////", edgecolor="#B8B8B8", linewidth=0))
                ax.text(j, i, "—", ha="center", va="center", fontsize=9, color="#50555A",
                        bbox={"facecolor": "#E8E8E8", "edgecolor": "none", "pad": 0.1})
    ax.set_yticks(range(3), [DISPLAY[m] for m in MODELS])
    labels = {"L": "Left", "R": "Right", "F": "Front", "B": "Behind", "TOP": "On\ntop", "LR": "L on\nR", "RL": "R on\nL"}
    ax.set_xticks(range(len(goals)), [labels[g] for _, g in goals], fontsize=7.2)
    ax.tick_params(axis="both", length=0)
    ax.set_xticks(np.arange(-.5, len(goals)), minor=True)
    ax.set_yticks(np.arange(-.5, 3), minor=True)
    ax.grid(which="minor", color="white", linewidth=1.2)
    ax.tick_params(which="minor", bottom=False, left=False)
    offset = 0
    for scene, title in zip(SCENES, ("Cube / bowl", "Butter / raisin", "Mustard / raisin", "Bowl stacking")):
        n = len(GOALS[scene])
        ax.text(offset+(n-1)/2, -.78, title, ha="center", va="bottom", fontsize=8, weight="medium")
        if offset:
            ax.axvline(offset-.5, color="white", lw=3)
        offset += n
    for spine in ax.spines.values():
        spine.set_visible(False)
    fig.subplots_adjust(left=.105, right=.88, top=.73, bottom=.32)
    cbax = fig.add_axes([.905, .32, .016, .41])
    cb = fig.colorbar(im, cax=cbax, ticks=(0, .5, 1))
    cb.ax.set_yticklabels(("0", "50", "100"), fontsize=7.5)
    cb.outline.set_visible(False)
    fig.text(.105, .065, "Requested arrangement held for at least one second (%)\nHatched: goal already satisfied at the frozen start.", fontsize=8, linespacing=1.3)
    fig.savefig(HERE / "figures/goal_response.pdf")
    fig.savefig(HERE / "figures/goal_response.png", dpi=220)
    plt.close(fig)

    # Overall rates use the same equal-scene weighting as the paired contrasts.
    # Goal cells retain the eight-start breakdown and mark initially true goals.
    by_form = {(r["model"], r["scene"], r["goal"], r["form"]): r
               for r in results["goal_response_by_form"]}
    fig, axes = plt.subplots(3, 1, figsize=(6.2, 3.0), sharex=True)
    for model, ax in zip(MODELS, axes):
        overall = np.array([[results["outcomes"][model]["all"][f][endpoint]["scene_goal_weighted_rate"]
                             for endpoint in ("stable_ever", "stable_at_final")] for f in ("D", "S", "I")])
        per_goal = np.array([[np.nan if by_form[model, s, g, f]["rate"] is None
                              else by_form[model, s, g, f]["rate"] for s, g in goals] for f in ("D", "S", "I")])
        values = np.column_stack((overall, per_goal))
        assert values.shape == (3, 14) and np.all(overall[:, 1] <= overall[:, 0])
        im = ax.imshow(values, cmap=cmap, vmin=0, vmax=1, aspect="auto")
        for i in range(3):
            for j in range(values.shape[1]):
                value = values[i, j]
                if np.isfinite(value):
                    label = f"{100*value:.1f}" if j < 2 else f"{int(100*value+.5)}"
                    ax.text(j, i, label, ha="center", va="center", fontsize=7.5,
                            color="white" if value >= .57 else "#17383D")
                else:
                    ax.add_patch(Rectangle((j-.5, i-.5), 1, 1, fill=False, hatch="////", edgecolor="#B8B8B8", linewidth=0))
        ax.set_yticks((0, 1, 2), ("D", "S", "I"), fontsize=8)
        ax.set_ylabel(DISPLAY[model], rotation=0, ha="right", va="center", labelpad=12,
                      fontsize=9, color=COLORS[model], weight="medium")
        ax.tick_params(axis="both", length=0)
        ax.set_xticks(np.arange(-.5, values.shape[1]), minor=True)
        ax.set_yticks(np.arange(-.5, 3), minor=True)
        ax.grid(which="minor", color="white", linewidth=.8)
        ax.tick_params(which="minor", bottom=False, left=False)
        for boundary in (1.5, 5.5, 8.5, 11.5):
            ax.axvline(boundary, color="white", lw=2.5)
        ax.axvline(1.5, color="#52656B", lw=.7)
        for spine in ax.spines.values():
            spine.set_visible(False)
    axes[-1].set_xticks(range(values.shape[1]), ["Any\ntime", "At\nend"] + [labels[g] for _, g in goals], fontsize=7)
    axes[0].text(.5, -.9, "Overall", ha="center", va="bottom", fontsize=7.5, weight="bold")
    offset = 2
    for scene, title in zip(SCENES, ("Cube / bowl", "Butter / raisin", "Mustard / raisin", "Bowl stacking")):
        n = len(GOALS[scene])
        axes[0].text(offset+(n-1)/2, -.9, title, ha="center", va="bottom", fontsize=7.5)
        offset += n
    fig.subplots_adjust(left=.12, right=.905, top=.87, bottom=.25, hspace=.16)
    cbax = fig.add_axes([.925, .25, .012, .62])
    cb = fig.colorbar(im, cax=cbax, ticks=(0, .5, 1))
    cb.ax.set_yticklabels(("0", "50", "100"), fontsize=7.5)
    cb.outline.set_visible(False)
    fig.text(.12, .045, "Stable-placement rate (%) · goal columns: any time during the episode", fontsize=8)
    fig.savefig(HERE / "figures/goal_response_by_form.pdf")
    fig.savefig(HERE / "figures/goal_response_by_form.png", dpi=220)
    plt.close(fig)


def main():
    for name in ("analysis", "figures"):
        (HERE / name).mkdir(exist_ok=True)
    raw = [json.loads(line) for line in FEATURES.read_text().splitlines() if line.strip()]
    assert len(raw) == 864 and len({r["episode_id"] for r in raw}) == 864
    assert all(r["status"] == "valid" and r["phase"] == "confirmation" for r in raw)
    registry = json.loads(REGISTRY.read_text())
    states = {slot["slot"]: slot for scene in registry["scenes"].values() for slot in scene["slots"]}
    rows = []
    for original in raw:
        r = dict(original)
        r["stratum_original"] = original["stratum"]
        r["initial_goal_true_registry"] = bool(states[r["state_slot"]]["initial_study"][r["goal_id"]]["goal"])
        r["stratum_corrected"] = "maintenance" if r["initial_goal_true_registry"] else "achievement"
        rows.append(r)
    assert len(states) == 32
    assert sum(r["initial_goal_true_registry"] for r in rows) == 216
    assert all(len([r for r in rows if r["model_id"] == m]) == 288 for m in MODELS)
    results, counts, contrasts, goals = analyze(rows)
    # Frozen confirmatory estimates must stay unchanged when only strata are corrected.
    published = json.loads((DATA / "results/results.json").read_text())
    for key, old in (("S-I", "E2_S_minus_I"), ("D-S", "E3_D_minus_S")):
        got = results["contrasts"]["pooled"]["all"]["stable_ever"][key]
        assert np.isclose(got["difference"], published[old]["mean_signed_difference"], atol=1e-12)
        assert np.allclose(got["ci95_state_bootstrap"], published[old]["ci95_state_bootstrap"], atol=1e-12)
        assert np.isclose(got["p_holm_two_contrasts"], published[old]["p_holm"], atol=1e-12)
    (HERE / "analysis/paper_results.json").write_text(json.dumps(results, indent=2) + "\n")
    keys = ("episode_id", "model_id", "scene_id", "state_slot", "goal_id", "form", "stratum_original",
            "initial_goal_true_registry", "stratum_corrected", "stable_ever", "stable_at_final")
    write_csv(HERE / "analysis/episode_outcomes_corrected.csv", [{k: r[k] for k in keys} for r in rows])
    write_csv(HERE / "analysis/outcome_counts.csv", counts)
    write_csv(HERE / "analysis/wording_contrasts.csv", contrasts)
    write_csv(HERE / "analysis/goal_response.csv", goals)
    write_csv(HERE / "analysis/goal_response_by_form.csv", results["goal_response_by_form"])
    write_csv(HERE / "analysis/paired_state_effects.csv", results["paired_state_effects"])
    (HERE / "analysis/README.md").write_text(
        "# Paper analysis\n\nRun `python paper/robolab_spatial_2026/generate_figures.py` from the repository root "
        "(Python 3.10+, NumPy and Matplotlib). The script reads only committed source evidence and writes this "
        "directory plus `../figures/`. It records source SHA-256 hashes in `paper_results.json`.\n\n"
        "The accepted-state registry supplies initial-goal status consistently across paired forms and models. "
        "The original per-episode stratum remains in `episode_outcomes_corrected.csv`; source artifacts are unchanged. "
        "Both outcome fields remain the frozen values. `stable_ever` means the full goal held for one continuous "
        "second at any time; `stable_at_final` requires the final continuous second. Neither is a new rescoring.\n\n"
        "All-episode stable-ever S-I and D-S are the original confirmatory contrasts, with Holm correction across "
        "the two pooled tests. Corrected-stratum subgroup results, per-model contrasts and final-state results "
        "must be identified as descriptive or sensitivity analyses. Confidence intervals resample physical starts "
        "within scene, keeping all model/goal/form observations together. Scenes and goals receive equal weight.\n\n"
        "`outcome_counts.csv` includes raw numerators/denominators and equally weighted rates; they need not agree "
        "because scenes have different numbers of goals. The heatmap has no achievement observations for S1-R, "
        "S3-R or S4-L; these are hatched, never displayed as zero success.\n\n"
        "The first two columns of `goal_response_by_form.pdf` show overall stable-ever and final-state rates "
        "for every model and instruction form, including initially satisfied goals. These rates give equal weight "
        "to scenes, averaging goals within each scene; each model/form has 96 episodes. The remaining columns "
        "show the original eight-start per-goal stable-ever rates. No outcomes or paired effects are changed.\n\n"
        "`paired_state_effects.csv` contains the 32 physical-state paired mean differences for each model and "
        "contrast, plus pooled state means (256 rows). The violin figure shows these observed discrete bounded "
        "means, vertical-only deterministic jitter, and an illustrative Gaussian KDE restricted to each group's "
        "observed extrema. It does not treat individual Bernoulli outcomes as continuous observations. Diamonds "
        "and intervals retain the unchanged paired means and state-bootstrap 95% intervals. The original forest "
        "display is retained as `wording_effect_forest.pdf`.\n")
    figures(results)
    print(json.dumps({"coverage": results["coverage"], "confirmatory": results["contrasts"]["pooled"]["all"]["stable_ever"],
                      "achievement_outcomes": {m: results["outcomes"][m]["achievement"]["all"] for m in MODELS}}, indent=2))


if __name__ == "__main__":
    main()
