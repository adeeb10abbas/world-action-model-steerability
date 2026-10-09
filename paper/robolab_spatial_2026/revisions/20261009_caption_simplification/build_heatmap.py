#!/usr/bin/env python3
"""Redraw the goal heatmap from saved outcomes, without rerunning statistics.

Goals already true at reset use gray columns labeled "True at start" instead
of displaying 100 as if a new placement were achieved. All underlying rates,
rounding, model colors, and the teal scale are unchanged.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Rectangle
import numpy as np

HERE = Path(__file__).resolve().parent
PAPER = HERE.parents[1]
RESULTS = PAPER / "analysis/paper_results.json"
EPISODES = PAPER / "analysis/episode_outcomes_corrected.csv"
OUT = PAPER / "revision_assets"

MODELS = ("N3", "E3", "F3")
FORMS = ("D", "S", "I")
DISPLAY = {"N3": "Nano", "E3": "Edge", "F3": "FLUX"}
COLORS = {"N3": "#087F8C", "E3": "#D97926", "F3": "#7856A5"}
GOALS = [("S1", g) for g in ("L", "R", "F", "B")]
GOALS += [(s, g) for s in ("S3", "S4") for g in ("TOP", "L", "R")]
GOALS += [("S5", "LR"), ("S5", "RL")]
INITIAL_GOALS = {("S1", "R"), ("S3", "R"), ("S4", "L")}
GROUPS = ((0, 2, "Overall"), (2, 4, "Cube /\nbowl"),
          (6, 3, "Butter /\nraisin box"), (9, 3, "Mustard /\nraisin box"),
          (12, 2, "Bowl\nstacking"))
LABELS = ["Any\ntime", "At\nend", "Left", "Right", "Front", "Behind",
          "On\ntop", "Left", "Right", "On\ntop", "Left", "Right",
          "Left\nonto\nright", "Right\nonto\nleft"]


def main():
    results = json.loads(RESULTS.read_text())
    with EPISODES.open(newline="") as f:
        episodes = list(csv.DictReader(f))
    assert len(episodes) == 864
    assert len({r["episode_id"] for r in episodes}) == 864
    saved = {(r["model"], r["scene"], r["goal"], r["form"]): r
             for r in results["goal_response_by_form"]}
    validation = {"statistical_analysis_rerun": False, "inputs": {}, "cells": []}
    for path in (RESULTS, EPISODES):
        validation["inputs"][str(path.relative_to(PAPER))] = hashlib.sha256(path.read_bytes()).hexdigest()

    cmap = LinearSegmentedColormap.from_list(
        "paper_teal", ["#F3F8F8", "#97CDCD", "#087F8C", "#034E58"])
    plt.rcParams.update({"font.family": "DejaVu Sans", "pdf.fonttype": 42,
                         "ps.fonttype": 42})
    fig, axes = plt.subplots(3, 1, figsize=(6.2, 3.85), sharex=True)
    for model, ax in zip(MODELS, axes):
        overall = np.array([[results["outcomes"][model]["all"][form][endpoint]["scene_goal_weighted_rate"]
                             for endpoint in ("stable_ever", "stable_at_final")]
                            for form in FORMS])
        values = np.zeros((3, 14))
        values[:, :2] = overall
        for i, form in enumerate(FORMS):
            for j, (scene, goal) in enumerate(GOALS, start=2):
                cell = saved[model, scene, goal, form]
                rows = [r for r in episodes if
                        (r["model_id"], r["scene_id"], r["goal_id"], r["form"])
                        == (model, scene, goal, form)]
                assert len(rows) == 8
                initially_true = (scene, goal) in INITIAL_GOALS
                assert all((r["initial_goal_true_registry"] == "True") == initially_true for r in rows)
                successes = sum(r["stable_ever"] == "True" for r in rows)
                raw_rate = successes / 8
                if initially_true:
                    assert cell["rate"] is None and cell["n_achievement"] == 0
                    assert successes == 8, (model, scene, goal, form, successes)
                else:
                    assert cell["n_achievement"] == 8
                    assert cell["stable_ever"] == successes
                    assert cell["rate"] == raw_rate
                values[i, j] = raw_rate
                validation["cells"].append({"model": DISPLAY[model], "scene": scene,
                    "goal": goal, "form": {"D": "DIR", "S": "TF", "I": "RF"}[form],
                    "initially_true": initially_true, "n": 8, "successes": successes,
                    "rate": raw_rate, "saved_achievement_rate": cell["rate"]})
        assert np.all(overall[:, 1] <= overall[:, 0])
        im = ax.imshow(values, cmap=cmap, vmin=0, vmax=1, aspect="auto")
        for i in range(3):
            for j in range(14):
                value = values[i, j]
                if j >= 2 and GOALS[j-2] in INITIAL_GOALS:
                    continue
                label = f"{100*value:.1f}" if j < 2 else f"{int(100*value+.5)}"
                ax.text(j, i, label, ha="center", va="center", fontsize=7.4,
                    color="white" if value >= .57 else "#17383D", zorder=3)
        for j, goal in enumerate(GOALS, start=2):
            if goal in INITIAL_GOALS:
                ax.add_patch(Rectangle((j-.5, -.5), 1, 3, facecolor="#E5E7E9",
                    edgecolor="white", linewidth=.65, zorder=3))
                ax.text(j, 1, "True\nat\nstart", ha="center", va="center",
                    fontsize=7.1, linespacing=1.05, color="#424A50", zorder=4)
        ax.set_yticks((0, 1, 2), ("DIR", "TF", "RF"), fontsize=8)
        ax.set_ylabel(DISPLAY[model], rotation=0, ha="right", va="center",
                      labelpad=12, fontsize=9, color=COLORS[model], weight="normal")
        ax.tick_params(axis="both", length=0)
        ax.set_xticks(np.arange(-.5, 14), minor=True)
        ax.set_yticks(np.arange(-.5, 3), minor=True)
        ax.grid(which="minor", color="white", linewidth=.65)
        ax.tick_params(which="minor", bottom=False, left=False)
        for boundary in (1.5, 5.5, 8.5, 11.5):
            # The dark middle remains visible even beside a zero-rate cell.
            ax.axvline(boundary, color="white", lw=3.0, zorder=4)
            ax.axvline(boundary, color="#647579", lw=.8, zorder=5)
        for spine in ax.spines.values():
            spine.set_visible(False)

    axes[-1].set_xticks(range(14), LABELS, fontsize=6.8)
    for start, width, label in GROUPS:
        center = start + (width-1)/2
        axes[0].text(center, -.86, label, ha="center", va="bottom",
                     fontsize=7.7, weight="bold")
        axes[0].plot([start-.45, start+width-.55], [-.71, -.71],
                     color="#647579", lw=.65, clip_on=False)
    fig.subplots_adjust(left=.13, right=.905, top=.80, bottom=.145, hspace=.16)
    cbax = fig.add_axes([.925, .145, .012, .655])
    cb = fig.colorbar(im, cax=cbax, ticks=(0, .5, 1))
    cb.ax.set_yticklabels(("0", "50", "100"), fontsize=7.5)
    cb.outline.set_visible(False)
    # Starting conditions are labeled directly, not encoded as apparent successes.
    for extension in ("pdf", "png"):
        fig.savefig(OUT / f"rev_goal_response_by_form.{extension}", dpi=260,
            bbox_inches="tight", pad_inches=.025,
            metadata={"Title": "Placement rates by instruction form", "Author": ""}
            if extension == "pdf" else None)
    plt.close(fig)
    validation["summary"] = {
        "goal_cells": len(validation["cells"]),
        "previously_displayed_goal_cells_unchanged": sum(not c["initially_true"] for c in validation["cells"]),
        "initially_true_cells_replaced_with_labels": sum(c["initially_true"] for c in validation["cells"]),
        "initially_true_episode_outcomes": sum(c["n"] for c in validation["cells"] if c["initially_true"]),
        "initially_true_anytime_passes": sum(c["successes"] for c in validation["cells"] if c["initially_true"]),
        "overall_values_from_saved_results": 18,
        "zero_goal_cells": sum(c["successes"] == 0 for c in validation["cells"]),
        "zero_meaning": "0 of 8 starts reached a one-second stable-placement pass at any time",
    }
    (HERE / "heatmap_numeric_validation.json").write_text(json.dumps(validation, indent=2) + "\n")
    print(json.dumps(validation["summary"], indent=2))
    print(OUT / "rev_goal_response_by_form.png")


if __name__ == "__main__":
    main()
