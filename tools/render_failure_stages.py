"""Render exploratory stage proportions and conditional timelines as portable SVG."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments.workshops.spatial_grounding_v1.contract import load_json, sha256_file
from experiments.workshops.spatial_grounding_v1.failure_stages import EVENTS, SCHEMA, STAGES

COLORS = ("#237a57", "#b84135", "#d69b26", "#804eaa", "#337dad", "#bb647e", "#949ba3", "#596e27", "#333333")
MODELS = ("N3", "E3", "F3")
FORMS = ("D", "C", "I")
WIDTH, HEIGHT = 1560, 1580


def _element(parent: ET.Element, tag: str, **attrs: Any) -> ET.Element:
    return ET.SubElement(parent, tag, {key.replace("_", "-"): str(value) for key, value in attrs.items()})


def _text(parent: ET.Element, x: float, y: float, value: str, **attrs: Any) -> None:
    _element(parent, "text", x=x, y=y, **attrs).text = value


def render_figures(report: Mapping[str, Any], *, stage: str, report_sha256: str) -> dict[str, str]:
    if stage not in ("P", "D", "C"):
        raise ValueError("choose one stage P/D/C; stages are never pooled")
    analysis = report.get("failure_stage_analysis")
    if not isinstance(analysis, Mapping) or analysis.get("schema_version") != SCHEMA:
        raise ValueError("report lacks supported exploratory failure-stage analysis")
    groups = {}
    for row in analysis["groups"]:
        if row["stage"] == stage:
            key = (row["family"], row["physical_goal_sign"], row["model"], row["form"])
            if key in groups:
                raise ValueError("duplicate stage plot group")
            groups[key] = row
    figures = {}
    for kind in ("stage-proportions", "median-timelines"):
        svg = ET.Element("svg", {"xmlns": "http://www.w3.org/2000/svg", "width": str(WIDTH),
                                "height": str(HEIGHT), "viewBox": f"0 0 {WIDTH} {HEIGHT}",
                                "role": "img", "aria-label": kind})
        _element(svg, "style").text = "text{font-family:Arial,sans-serif;font-size:13px;fill:#202630}.heading{font-size:24px;font-weight:bold}"
        _element(svg, "rect", width=WIDTH, height=HEIGHT, fill="white")
        _element(svg, "metadata").text = json.dumps({
            "cohort_id": report["cohort_id"], "report_sha256": report_sha256,
            "definition": analysis["definition"], "stage": stage, "exploratory": True,
        }, sort_keys=True)
        title = "Recorded primary failure stages" if kind == "stage-proportions" else "Conditional median event timelines"
        _text(svg, 32, 38, f"{title} | {stage} | exploratory", **{"class": "heading"})
        _text(svg, 32, 65, f"Cohort: {report['cohort_id']} | {'complete' if report['complete'] else 'INCOMPLETE CHECKPOINT'}")
        caption = ("Bars: valid non-censored model episodes only. n/N = eligible/planned; T=technical, Z=safety censored, M=missing."
                   if kind == "stage-proportions" else
                   "Dots: exact observed events only, in recorded simulated seconds. Absent events are not time zero; event counts remain separate.")
        _text(svg, 32, 89, caption)
        labels = STAGES if kind == "stage-proportions" else EVENTS
        for index, label in enumerate(labels):
            x, y = 32 + (index % 5) * 300, 118 + (index // 5) * 27
            _element(svg, "rect", x=x, y=y - 11, width=12, height=12, fill=COLORS[index])
            _text(svg, x + 18, y, label)
        for family_index, family in enumerate(("LAT", "HEIGHT", "DIST")):
            for sign_index, sign in enumerate((-1, 1)):
                x, y = 32 + sign_index * 770, 205 + family_index * 440
                panel = _element(svg, "g", **{"data-family": family, "data-sign": sign})
                _text(panel, x, y, f"{family} | goal sign {sign:+d}", font_weight="bold", font_size=18)
                plot_x, plot_width = x + 76, 510
                selected = [groups.get((family, sign, model, form)) for model in MODELS for form in FORMS]
                max_time = max([30.] + [metric["median_sim_time_s"] for row in selected if row
                                       for metric in row["median_timelines"].values()
                                       if metric["median_sim_time_s"] is not None])
                for tick in range(5):
                    tx = plot_x + tick * plot_width / 4
                    _element(panel, "line", x1=tx, y1=y + 25, x2=tx, y2=y + 378, stroke="#e4e7eb")
                    _text(panel, tx, y + 398,
                          f"{tick * 25}%" if kind == "stage-proportions" else f"{tick * max_time / 4:g}s",
                          text_anchor="middle")
                for index, (model, form) in enumerate((model, form) for model in MODELS for form in FORMS):
                    row = groups.get((family, sign, model, form))
                    row_y = y + 43 + index * 38
                    _text(panel, x, row_y, f"{model} {form}")
                    if not row or not row["valid_model"]:
                        _text(panel, plot_x + 5, row_y, "unobservable: no eligible model episodes", fill="#777")
                        if row:
                            _text(panel, x + 600, row_y, f"n=0/{row['planned']}")
                        continue
                    counts = row["counts"]
                    if kind == "stage-proportions":
                        cursor = plot_x
                        for stage_index, label in enumerate(STAGES):
                            metric = row["stage_proportions"][label]
                            if metric["denominator"] != row["valid_model"]:
                                raise ValueError("stage proportion denominator differs from eligible count")
                            width = plot_width * metric["numerator"] / metric["denominator"]
                            if not width:
                                continue
                            rect = _element(panel, "rect", x=cursor, y=row_y - 15, width=width, height=19,
                                            fill=COLORS[stage_index], **{"data-stage": label})
                            _element(rect, "title").text = f"{model}/{form}/{label}: {metric['numerator']}/{metric['denominator']}"
                            cursor += width
                        _text(panel, x + 600, row_y, f"n={row['valid_model']}/{row['planned']}")
                        _text(panel, plot_x, row_y + 19,
                              f"T={counts['technical_invalid']} Z={counts['safety_censored']} M={counts['not_run']}",
                              font_size=11)
                    else:
                        observed_counts, unknown_counts = [], []
                        for event_index, event in enumerate(EVENTS):
                            metric = row["median_timelines"][event]
                            observed_counts.append(str(metric["observed"]))
                            unknown_counts.append(str(metric["unobservable"]))
                            if metric["median_sim_time_s"] is None:
                                continue
                            dot = _element(panel, "circle",
                                           cx=plot_x + plot_width * metric["median_sim_time_s"] / max_time,
                                           cy=row_y - 6 + (event_index % 3 - 1) * 4, r=4,
                                           fill=COLORS[event_index], **{"data-event": event})
                            _element(dot, "title").text = (
                                f"{model}/{form}/{event}: {metric['median_sim_time_s']:g}s; "
                                f"observed={metric['observed']}/{metric['eligible']}, "
                                f"not_observed={metric['not_observed']}, unobservable={metric['unobservable']}")
                        _text(panel, x + 600, row_y, f"eligible={row['valid_model']}")
                        _text(panel, plot_x, row_y + 17,
                              f"event n={'/'.join(observed_counts)}; unknown={'/'.join(unknown_counts)}",
                              font_size=10)
        _text(svg, 32, 1550, "Event counts follow legend order. No family/sign pooling, causal inference, or new primary-score claims.")
        figures[f"{kind}.svg"] = ET.tostring(svg, encoding="unicode") + "\n"
    return figures


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--report-sha256", required=True)
    parser.add_argument("--stage", choices=("P", "D", "C"), required=True)
    parser.add_argument("--output-dir", type=Path, required=True, help="new directory for two SVG figures")
    args = parser.parse_args(argv)
    try:
        if sha256_file(args.report) != args.report_sha256:
            raise ValueError("cohort report hash mismatch")
        report = load_json(args.report, "cohort report")
        if report.get("schema_version") != "sgw-01-cohort-analysis-v1":
            raise ValueError("not a cohort compiler report")
        figures = render_figures(report, stage=args.stage, report_sha256=args.report_sha256)
        args.output_dir.mkdir(parents=True, exist_ok=False)
        for name, text in figures.items():
            with (args.output_dir / name).open("x", encoding="utf-8") as stream:
                stream.write(text)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
