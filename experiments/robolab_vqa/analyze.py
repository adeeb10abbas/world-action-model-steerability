"""Score and analyse RQA-20261006 responses (CPU).

python -m experiments.robolab_vqa.analyze --release <release-dir>/release.json --responses <results-dir> \
    --lanes <results-dir>/lanes.json --output <analysis-dir>

Frozen parsers (parse.py) and gold labels (release) only. Estimates follow the paper's weighting: average items within
(start, goal) cells, starts within goal, goals equally within scene, then scenes equally. Uncertainty: 10,000
percentile bootstrap replicates (seed 6106) resampling physical starts within scene, retaining every frame/goal/form
and checkpoint of a sampled start; the same resamples are used for all lanes and paired checkpoint differences.
Intervals are conditional on four fixed scene types and fixed prompt templates.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import numpy as np

from . import common as C
from . import parse as PARSE

GOAL_ORDER = {"S1": ["L", "R", "F", "B"], "S3": ["TOP", "L", "R"], "S4": ["TOP", "L", "R"], "S5": ["LR", "RL"]}
FORM_PAIRS = {"A": ("target_subject", "reference_subject"), "C": ("TF", "RF"), "B": ("TF", "RF"),
              "placement": ("reference_early", "reference_late")}
ANALYSIS_VERSION = "rqa-analysis-1"


@dataclass
class Item:
    lane: str
    query_id: str
    test: str
    bank: str
    family: str
    scene: str
    start: str | None
    frame: str | None
    goal: str
    prompt_id: str | None
    form: str
    pair_id: str | None
    gold: Any
    answerable: bool
    exclusion: str | None
    status: str
    valid: bool = False
    answer: Any = None
    correct: float | None = None
    fields: dict = field(default_factory=dict)
    reason: str | None = None
    reused_from: str | None = None
    boundary_only: bool = False
    intended_gold: Any = None


def start_index(start: str) -> int:
    return int(start.split("-C")[1]) - 1


def _boundary_only(reason: str | None) -> bool:
    return bool(reason) and all(r.startswith("cone_") for r in reason.split(";"))


def score_row(q: dict, resp: dict | None, lane: str, objects: dict[str, list[str]]) -> Item:
    it = Item(lane=lane, query_id=q["query_id"], test=q["test"], bank=q["bank"], family=q["family"], scene=q["scene_id"],
              start=q["physical_start_id"], frame=q["frame_id"], goal=q["goal_id"], prompt_id=q["original_prompt_id"],
              form=q["display_form"], pair_id=q["pair_id"], gold=q["gold_answer"], answerable=bool(q["answerable"]),
              exclusion=q["exclusion_reason"], status="missing", boundary_only=_boundary_only(q["exclusion_reason"]))
    if resp is None or resp.get("status") != "delivered":
        return it
    it.status = "delivered"
    text = resp.get("raw_response")
    if q["test"] == "B":
        p = PARSE.parse_b(text, objects[q["scene_id"]], list(C.RELATION_VOCABULARY))
        it.valid, it.reason = p["valid"], p["reason"]
        it.answer = p["answer"] if p["valid"] else None
        gold = q["gold_answer"]
        f = {k: float(bool(p["valid"]) and p["answer"][k] == gold[k]) for k in ("target", "reference", "relation")}
        f["tuple"] = float(all(v == 1.0 for v in f.values()))
        it.fields = f
        it.correct = f["tuple"]
    else:
        p = PARSE.parse_yes_no(text)
        it.valid, it.reason, it.answer = p["valid"], p["reason"], p["answer"]
        if q["gold_answer"] is not None:
            it.correct = float(p["valid"] and p["answer"] == q["gold_answer"])
    return it


def expand_no_image(items: list[Item], manifest: list[dict]) -> list[Item]:
    """Reuse each no-image C answer against every initial frame's label for that instruction (not new generations)."""
    initial_c = defaultdict(list)
    for q in manifest:
        if q["test"] == "C" and q["bank"] == "initial" and q["family"] == "original":
            initial_c[q["original_prompt_id"]].append(q)
    out = []
    for it in items:
        if not (it.test == "C" and it.bank == "no_image"):
            continue
        for q in initial_c[it.prompt_id]:
            e = Item(lane=it.lane, query_id=f"{it.query_id}@{q['frame_id']}", test="C", bank="no_image_reuse",
                     family="original", scene=q["scene_id"], start=q["physical_start_id"], frame=q["frame_id"], goal=q["goal_id"],
                     prompt_id=it.prompt_id, form=it.form, pair_id=q["pair_id"].replace("C.initial", "C.no_image_reuse"),
                     gold=q["gold_answer"], answerable=bool(q["answerable"]), exclusion=q["exclusion_reason"], status=it.status,
                     valid=it.valid, answer=it.answer, reason=it.reason, reused_from=it.query_id,
                     boundary_only=_boundary_only(q["exclusion_reason"]))
            if it.status == "delivered":
                e.correct = float(it.valid and it.answer == q["gold_answer"])
            out.append(e)
    return out


# ---------------------------------------------------------------------- aggregation
def cell_table(units: list[tuple[str, str, str, float]]) -> dict[tuple[str, str], np.ndarray]:
    """units: (scene, goal, start, value) -> {(scene, goal): array(8) of cell means (nan = no data)}."""
    acc: dict = defaultdict(lambda: defaultdict(list))
    for scene, goal, start, value in units:
        acc[(scene, goal)][start_index(start)].append(value)
    out = {}
    for key, cells in acc.items():
        arr = np.full(8, np.nan)
        for i, vals in cells.items():
            arr[i] = float(np.mean(vals))
        out[key] = arr
    return out


def macro_point(table: dict, scenes: tuple[str, ...]) -> float:
    scene_vals = []
    for s in scenes:
        goal_vals = [float(np.nanmean(table[(s, g)])) for g in GOAL_ORDER[s]
                     if (s, g) in table and np.isfinite(table[(s, g)]).any()]
        if goal_vals:
            scene_vals.append(float(np.mean(goal_vals)))
    return float(np.mean(scene_vals)) if scene_vals else float("nan")


def macro_boot(table: dict, scenes: tuple[str, ...], idx: dict[str, np.ndarray]) -> np.ndarray:
    per_scene = []
    for s in scenes:
        goals = []
        for g in GOAL_ORDER[s]:
            v = table.get((s, g))
            if v is None or not np.isfinite(v).any():
                continue
            sample = v[idx[s]]
            with np.errstate(all="ignore"):
                cnt = np.isfinite(sample).sum(axis=1)
                tot = np.nansum(sample, axis=1)
                goals.append(np.where(cnt > 0, tot / np.maximum(cnt, 1), np.nan))
        if goals:
            G = np.vstack(goals)
            with np.errstate(all="ignore"):
                cnt = np.isfinite(G).sum(axis=0)
                per_scene.append(np.where(cnt > 0, np.nansum(G, axis=0) / np.maximum(cnt, 1), np.nan))
    if not per_scene:
        return np.full(next(iter(idx.values())).shape[0], np.nan)
    S = np.vstack(per_scene)
    with np.errstate(all="ignore"):
        cnt = np.isfinite(S).sum(axis=0)
        return np.where(cnt == len(per_scene), np.nansum(S, axis=0) / np.maximum(cnt, 1), np.nan)


def summarize(table: dict, scenes: tuple[str, ...], idx: dict | None, n_units: int, extra: dict | None = None) -> dict:
    point = macro_point(table, scenes)
    out = {"estimate": point, "n_units": n_units, "scenes": list(scenes)}
    if idx is not None and n_units:
        boot = macro_boot(table, scenes, idx)
        finite = boot[np.isfinite(boot)]
        out["ci95"] = [float(np.percentile(finite, 2.5)), float(np.percentile(finite, 97.5))] if finite.size else None
        out["bootstrap_undefined_replicates"] = int((~np.isfinite(boot)).sum())
        out["_boot"] = boot
    if extra:
        out.update(extra)
    return out


def item_units(items: list[Item], pred: Callable[[Item], bool], value: Callable[[Item], float | None]) -> list:
    units = []
    for it in items:
        if it.start is None or not pred(it):
            continue
        v = value(it)
        if v is not None:
            units.append((it.scene, it.goal, it.start, v))
    return units


def pairs_of(items: list[Item], test: str, forms: tuple[str, str], pred: Callable[[Item], bool]) -> list[tuple[Item, Item]]:
    groups = defaultdict(dict)
    for it in items:
        if it.test == test and it.form in forms and it.pair_id and pred(it):
            groups[it.pair_id][it.form] = it
    return [(g[forms[0]], g[forms[1]]) for g in groups.values() if forms[0] in g and forms[1] in g]


def scored(it: Item, all_geometry: bool = False) -> bool:
    ok = it.answerable or (all_geometry and it.boundary_only)
    return ok and it.status == "delivered" and it.correct is not None


# ---------------------------------------------------------------------- metric families
def accuracy_metrics(items: list[Item], scenes, idx, all_geometry: bool = False, value=lambda it: it.correct) -> dict:
    sel = [it for it in items if scored(it, all_geometry)]
    table = cell_table(item_units(sel, lambda it: True, value))
    res = summarize(table, scenes, idx, len(sel))
    res["raw_correct"] = float(sum(value(it) for it in sel if it.start is not None) if sel else 0)
    res["raw_n"] = len(sel)
    return res


def balanced_accuracy(items: list[Item], scenes, idx, all_geometry: bool = False) -> dict:
    sel = [it for it in items if scored(it, all_geometry) and it.gold in ("yes", "no")]
    out = {}
    tables = {}
    for cls in ("yes", "no"):
        sub = [it for it in sel if it.gold == cls]
        tables[cls] = cell_table(item_units(sub, lambda it: True, lambda it: it.correct))
        pt = macro_point(tables[cls], scenes) if sub else float("nan")
        out[f"recall_{cls}"] = {"estimate": pt, "support": len(sub),
                                "raw_correct": float(sum(it.correct for it in sub))}
    if out["recall_yes"]["support"] == 0 or out["recall_no"]["support"] == 0:
        out["balanced_accuracy"] = {"estimate": None, "status": "undefined_one_class_absent"}
        return out
    point = (out["recall_yes"]["estimate"] + out["recall_no"]["estimate"]) / 2
    ba = {"estimate": point}
    if idx is not None:
        boot = (macro_boot(tables["yes"], scenes, idx) + macro_boot(tables["no"], scenes, idx)) / 2
        finite = boot[np.isfinite(boot)]
        ba["ci95"] = [float(np.percentile(finite, 2.5)), float(np.percentile(finite, 97.5))] if finite.size else None
        ba["bootstrap_undefined_replicates"] = int((~np.isfinite(boot)).sum())
        ba["_boot"] = boot
    out["balanced_accuracy"] = ba
    return out


def paired_metrics(items: list[Item], test: str, forms: tuple[str, str], scenes, idx, all_geometry: bool = False,
                   value=lambda it: it.correct) -> dict:
    pred = lambda it: it.scene in scenes  # noqa: E731
    pairs = pairs_of(items, test, forms, pred)
    complete = [(a, b) for a, b in pairs if scored(a, all_geometry) and scored(b, all_geometry)]
    excluded = [(a, b) for a, b in pairs if not ((a.answerable or (all_geometry and a.boundary_only))
                                                 and (b.answerable or (all_geometry and b.boundary_only)))]
    missing = [(a, b) for a, b in pairs if (a, b) not in complete and (a, b) not in excluded]
    units_gap, units_both, units_dis, units_a, units_b = [], [], [], [], []
    for a, b in complete:
        if a.start is None:
            continue
        va, vb = value(a), value(b)
        units_gap.append((a.scene, a.goal, a.start, va - vb))
        units_both.append((a.scene, a.goal, a.start, float(va == 1.0 and vb == 1.0)))
        da = json.dumps(a.answer, sort_keys=True) if a.valid else "<invalid>"
        db = json.dumps(b.answer, sort_keys=True) if b.valid else "<invalid>"
        units_dis.append((a.scene, a.goal, a.start, float(da != db)))
        units_a.append((a.scene, a.goal, a.start, va))
        units_b.append((a.scene, a.goal, a.start, vb))
    res = {"forms": list(forms), "pairs_proposed": len(pairs), "pairs_complete": len(complete),
           "pairs_excluded_jointly": len(excluded), "pairs_missing_response": len(missing),
           f"accuracy_{forms[0]}": summarize(cell_table(units_a), scenes, idx, len(units_a)),
           f"accuracy_{forms[1]}": summarize(cell_table(units_b), scenes, idx, len(units_b)),
           "gap": summarize(cell_table(units_gap), scenes, idx, len(units_gap)),
           "both_correct": summarize(cell_table(units_both), scenes, idx, len(units_both)),
           "disagreement": summarize(cell_table(units_dis), scenes, idx, len(units_dis)),
           "discordant_counts": {f"{forms[0]}_only_correct": sum(1 for a, b in complete if value(a) == 1 and value(b) != 1),
                                 f"{forms[1]}_only_correct": sum(1 for a, b in complete if value(b) == 1 and value(a) != 1),
                                 "both_correct": sum(1 for a, b in complete if value(a) == 1 and value(b) == 1),
                                 "both_incorrect": sum(1 for a, b in complete if value(a) != 1 and value(b) != 1)}}
    return res


def finite_set_b(items: list[Item]) -> dict:
    """Text-only B: 36 (+16) unique instructions; finite-set counts, no state bootstrap."""
    out = {}
    for fam in ("original", "placement"):
        sel = [it for it in items if it.test == "B" and it.bank == "no_image" and it.family == fam]
        d = {"n": len(sel), "delivered": sum(it.status == "delivered" for it in sel),
             "valid": sum(it.valid for it in sel)}
        for k in ("tuple", "target", "reference", "relation"):
            d[f"{k}_correct"] = int(sum(it.fields.get(k, 0) for it in sel))
        by_form = defaultdict(lambda: Counter())
        by_scene = defaultdict(lambda: Counter())
        for it in sel:
            by_form[it.form]["n"] += 1
            by_form[it.form]["tuple_correct"] += int(it.fields.get("tuple", 0))
            by_scene[it.scene]["n"] += 1
            by_scene[it.scene]["tuple_correct"] += int(it.fields.get("tuple", 0))
        d["by_form"] = {k: dict(v) for k, v in by_form.items()}
        d["by_scene"] = {k: dict(v) for k, v in by_scene.items()}
        forms = FORM_PAIRS["B"] if fam == "original" else FORM_PAIRS["placement"]
        groups = defaultdict(dict)
        for it in sel:
            groups[it.pair_id][it.form] = it
        table = Counter()
        rows = []
        for pid, g in sorted(groups.items()):
            if forms[0] in g and forms[1] in g:
                a, b = g[forms[0]], g[forms[1]]
                table[(int(a.fields.get("tuple", 0)), int(b.fields.get("tuple", 0)))] += 1
                rows.append({"pair_id": pid, "scene": a.scene, "goal": a.goal,
                             forms[0]: a.answer if a.valid else f"invalid:{a.reason}",
                             forms[1]: b.answer if b.valid else f"invalid:{b.reason}",
                             f"{forms[0]}_correct": a.fields.get("tuple"), f"{forms[1]}_correct": b.fields.get("tuple")})
        d["paired_tuple_table"] = {f"{forms[0]}={k[0]},{forms[1]}={k[1]}": v for k, v in sorted(table.items())}
        d["paired_rows"] = rows
        d["invalid_reasons"] = dict(Counter(it.reason for it in sel if not it.valid and it.status == "delivered"))
        out[fam] = d
    return out


def answer_distribution(items: list[Item]) -> dict:
    c = Counter()
    for it in items:
        if it.status != "delivered":
            c["infrastructure_missing"] += 1
        elif not it.valid:
            c["invalid"] += 1
        else:
            c[str(it.answer) if it.test != "B" else "valid_json"] += 1
    return dict(c)


def coverage_rows(lane: str, items: list[Item], manifest_n: dict) -> list[dict]:
    rows = []
    keyf = lambda it: (it.family, it.test, it.bank)  # noqa: E731
    groups = defaultdict(list)
    for it in items:
        groups[keyf(it)].append(it)
    for (fam, test, bank), sel in sorted(groups.items()):
        delivered = [it for it in sel if it.status == "delivered"]
        rows.append({"lane": lane, "family": fam, "test": test, "bank": bank, "proposed": len(sel),
                     "answerable": sum(it.answerable for it in sel) if bank != "no_image" or test == "B" else "reused",
                     "excluded": sum((not it.answerable) for it in sel) if bank != "no_image" or test == "B" else 0,
                     "queried": len(sel), "delivered": len(delivered), "valid_format": sum(it.valid for it in delivered),
                     "unknown": sum(1 for it in delivered if it.valid and it.answer == "unknown"),
                     "invalid": sum(1 for it in delivered if not it.valid),
                     "infrastructure_missing": len(sel) - len(delivered),
                     "truncated_or_other_invalid_reasons": dict(Counter(it.reason for it in delivered if not it.valid))})
    return rows


def strip_boot(obj):
    if isinstance(obj, dict):
        return {k: strip_boot(v) for k, v in obj.items() if k != "_boot"}
    if isinstance(obj, list):
        return [strip_boot(v) for v in obj]
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    return obj


def diff_summary(a: dict, b: dict) -> dict | None:
    """Paired checkpoint difference a - b using identical bootstrap resamples."""
    if not a or not b or "_boot" not in a or "_boot" not in b:
        return None
    if a["estimate"] is None or b["estimate"] is None:
        return None
    boot = a["_boot"] - b["_boot"]
    finite = boot[np.isfinite(boot)]
    return {"estimate": a["estimate"] - b["estimate"],
            "ci95": [float(np.percentile(finite, 2.5)), float(np.percentile(finite, 97.5))] if finite.size else None,
            "note": "same physical-start resamples for both readouts; descriptive"}


# ---------------------------------------------------------------------- lane analysis
def analyse_lane(lane: str, items: list[Item], reuse: list[Item], idx: dict) -> dict:
    res: dict = {"lane": lane}
    main, s5, all4 = C.MAIN_POOL_SCENES, ("S5",), C.SCENES
    for bank in ("initial", "secondary"):
        b: dict = {}
        A = [it for it in items if it.test == "A" and it.bank == bank]
        Cc = [it for it in items if it.test == "C" and it.bank == bank and it.family == "original"]
        for name, scenes in (("main_S1_S3_S4", main), ("S5", s5), ("all_scenes", all4)):
            d = {}
            d["A_accuracy"] = accuracy_metrics([it for it in A if it.scene in scenes], scenes, idx)
            d["A_pairs"] = paired_metrics(A, "A", FORM_PAIRS["A"], scenes, idx)
            d["A_balanced"] = balanced_accuracy([it for it in A if it.scene in scenes], scenes, idx)
            d["C_accuracy_all_forms"] = accuracy_metrics([it for it in Cc if it.scene in scenes], scenes, idx)
            for form in ("DIR", "TF", "RF"):
                d[f"C_accuracy_{form}"] = accuracy_metrics([it for it in Cc if it.scene in scenes and it.form == form], scenes, idx)
                d[f"C_balanced_{form}"] = balanced_accuracy([it for it in Cc if it.scene in scenes and it.form == form], scenes, idx)
            d["C_balanced_all_forms"] = balanced_accuracy([it for it in Cc if it.scene in scenes], scenes, idx)
            d["C_TF_RF"] = paired_metrics(Cc, "C", ("TF", "RF"), scenes, idx)
            d["C_DIR_TF"] = paired_metrics(Cc, "C", ("DIR", "TF"), scenes, idx)
            d["C_DIR_RF"] = paired_metrics(Cc, "C", ("DIR", "RF"), scenes, idx)
            d["C_TF_RF_all_geometry_sensitivity"] = paired_metrics(Cc, "C", ("TF", "RF"), scenes, idx, all_geometry=True)
            d["A_pairs_all_geometry_sensitivity"] = paired_metrics(A, "A", FORM_PAIRS["A"], scenes, idx, all_geometry=True)
            d["answer_distribution_A"] = answer_distribution([it for it in A if it.scene in scenes])
            d["answer_distribution_C"] = answer_distribution([it for it in Cc if it.scene in scenes])
            if bank == "initial":
                B = [it for it in items if it.test == "B" and it.bank == "initial" and it.family == "original"]
                for k in ("tuple", "target", "reference", "relation"):
                    d[f"B_image_{k}_accuracy"] = accuracy_metrics([it for it in B if it.scene in scenes], scenes, idx,
                                                                  value=lambda it, k=k: it.fields.get(k))
                for form in ("DIR", "TF", "RF"):
                    d[f"B_image_tuple_accuracy_{form}"] = accuracy_metrics(
                        [it for it in B if it.scene in scenes and it.form == form], scenes, idx)
                d["B_image_TF_RF"] = paired_metrics(B, "B", ("TF", "RF"), scenes, idx)
                d["B_image_DIR_TF"] = paired_metrics(B, "B", ("DIR", "TF"), scenes, idx)
                PB = [it for it in items if it.test == "B" and it.bank == "initial" and it.family == "placement"]
                PC = [it for it in items if it.test == "C" and it.bank == "initial" and it.family == "placement"]
                if name != "S5":
                    d["placement_B_image"] = paired_metrics(PB, "B", FORM_PAIRS["placement"], scenes, idx)
                    d["placement_C_image"] = paired_metrics(PC, "C", FORM_PAIRS["placement"], scenes, idx)
                    d["placement_C_image_accuracy"] = accuracy_metrics([it for it in PC if it.scene in scenes], scenes, idx)
                R = [it for it in reuse if it.scene in scenes]
                d["C_no_image_reuse_accuracy"] = accuracy_metrics(R, scenes, idx)
                d["C_no_image_reuse_accuracy"]["note"] = "36 fixed answers scored against frame labels; interval conditional on those answers"
                d["C_no_image_reuse_TF_RF"] = paired_metrics(reuse, "C", ("TF", "RF"), scenes, idx)
                d["C_no_image_reuse_balanced"] = balanced_accuracy(R, scenes, idx)
            b[name] = d
        # S5 intended-goal sensitivity: RF scored against the stacked (TF) label on the same frame
        if True:
            sens = []
            by_pair = defaultdict(dict)
            for it in Cc:
                if it.scene == "S5":
                    by_pair[it.pair_id][it.form] = it
            for g in by_pair.values():
                if "RF" in g and "TF" in g:
                    rf, tf = g["RF"], g["TF"]
                    e = Item(**{**rf.__dict__})
                    e.gold = tf.gold
                    e.answerable = tf.answerable and rf.answerable
                    if e.status == "delivered":
                        e.correct = float(e.valid and e.answer == tf.gold)
                    sens.append(e)
                    sens.append(tf)
                    if "DIR" in g:
                        sens.append(g["DIR"])
            all_sens = [it for it in Cc if it.scene in main] + sens
            b["all_scenes_intended_goal_sensitivity"] = {
                "C_TF_RF": paired_metrics(all_sens, "C", ("TF", "RF"), all4, idx),
                "note": "S5 RF scored against the stacked (intended-goal) label; declared sensitivity result"}
        res[bank] = b
    res["text_only_B"] = finite_set_b(items)
    res["C_no_image_answers"] = answer_distribution([it for it in items if it.test == "C" and it.bank == "no_image"])
    res["C_no_image_answers_by_form"] = {f: answer_distribution([it for it in items if it.test == "C" and it.bank == "no_image"
                                                                 and it.form == f]) for f in ("DIR", "TF", "RF")}
    # per-scene / per-relation breakdowns (initial + secondary), descriptive
    br = []
    for bank in ("initial", "secondary"):
        for test in ("A", "C"):
            for scene in C.SCENES:
                for goal in GOAL_ORDER[scene]:
                    for form in sorted({it.form for it in items if it.test == test and it.bank == bank and it.scene == scene}):
                        sel = [it for it in items if it.test == test and it.bank == bank and it.scene == scene and it.goal == goal
                               and it.form == form and it.family == "original"]
                        sc = [it for it in sel if scored(it)]
                        br.append({"lane": lane, "bank": bank, "test": test, "scene": scene, "goal": goal, "form": form,
                                   "proposed": len(sel), "scored": len(sc), "correct": int(sum(it.correct for it in sc)),
                                   "accuracy": (sum(it.correct for it in sc) / len(sc)) if sc else None,
                                   "gold_yes": sum(1 for it in sc if it.gold == "yes"), "gold_no": sum(1 for it in sc if it.gold == "no"),
                                   "answered_yes": sum(1 for it in sel if it.status == "delivered" and it.answer == "yes"),
                                   "answered_no": sum(1 for it in sel if it.status == "delivered" and it.answer == "no"),
                                   "answered_unknown": sum(1 for it in sel if it.status == "delivered" and it.answer == "unknown"),
                                   "invalid": sum(1 for it in sel if it.status == "delivered" and not it.valid)})
    res["breakdown_rows"] = br
    return res


def label_variation(manifest: list[dict]) -> list[dict]:
    rows = []
    groups = defaultdict(list)
    for q in manifest:
        if q["test"] in ("A", "C") and q["bank"] in ("initial", "secondary") and q["family"] == "original":
            groups[(q["bank"], q["test"], q["scene_id"], q["goal_id"], q["display_form"])].append(q)
    for (bank, test, scene, goal, form), qs in sorted(groups.items()):
        ans = [q for q in qs if q["answerable"]]
        rows.append({"bank": bank, "test": test, "scene": scene, "goal": goal, "form": form, "proposed": len(qs),
                     "answerable": len(ans), "gold_yes": sum(q["gold_answer"] == "yes" for q in ans),
                     "gold_no": sum(q["gold_answer"] == "no" for q in ans),
                     "within_goal_label_variation": len({q["gold_answer"] for q in ans}) > 1})
    return rows


def action_join(lanes_items: dict[str, list[Item]], lanes: dict, outcomes_csv: Path) -> list[dict]:
    outcomes = {}
    with open(outcomes_csv) as f:
        for r in csv.DictReader(f):
            outcomes[(r["model_id"], r["state_slot"], r["goal_id"], C.LEGACY_FORM_MAP[r["form"]])] = r
    rows = []
    for lane, items in lanes_items.items():
        fam = lanes[lane]["family"]
        for test in ("C", "B"):
            sel = [it for it in items if it.test == test and it.bank == "initial" and it.family == "original"]
            counts = Counter()
            for it in sel:
                o = outcomes.get((fam, it.start, it.goal, it.form))
                if o is None or it.status != "delivered":
                    counts[("unmatched_or_missing",)] += 1
                    continue
                ok = "qa_correct" if it.correct == 1.0 else ("qa_excluded" if not it.answerable else "qa_incorrect")
                for outcome in ("stable_ever", "stable_at_final"):
                    counts[(o["stratum_corrected"], outcome, ok, "action_success" if o[outcome] == "True" else "action_failure")] += 1
            for key, n in sorted(counts.items(), key=lambda kv: str(kv[0])):
                if key[0] == "unmatched_or_missing":
                    rows.append({"lane": lane, "family": fam, "test": test, "stratum": "-", "action_outcome_field": "-",
                                 "qa": "unmatched_or_missing", "action": "-", "n": n})
                else:
                    rows.append({"lane": lane, "family": fam, "test": test, "stratum": key[0], "action_outcome_field": key[1],
                                 "qa": key[2], "action": key[3], "n": n})
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--release", type=Path, required=True)
    ap.add_argument("--responses", type=Path, required=True)
    ap.add_argument("--lanes", type=Path, required=True, help="lanes.json: status/shared/family per lane")
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--outcomes", type=Path, default=C.REPO_ROOT / "paper/robolab_spatial_2026/analysis/episode_outcomes_corrected.csv")
    ap.add_argument("--policy-contrasts", type=Path, default=C.REPO_ROOT / "paper/robolab_spatial_2026/analysis/wording_contrasts.csv")
    ap.add_argument("--bootstrap", type=int, default=C.BOOTSTRAP_REPLICATES)
    args = ap.parse_args()
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    release = C.load_json(args.release)
    root = args.release.parent
    manifest = C.read_jsonl(root / "query_manifest.jsonl")
    lanes = C.load_json(args.lanes)["lanes"]
    catalog = C.load_catalog()
    objects = {s: next(i["object_vocabulary"] for i in catalog["original_instructions"] if i["scene"] == s) for s in C.SCENES}
    rng = np.random.default_rng(C.BOOTSTRAP_SEED)
    idx = {s: rng.integers(0, 8, size=(args.bootstrap, 8)) for s in C.SCENES}
    lanes_items: dict[str, list[Item]] = {}
    lanes_reuse: dict[str, list[Item]] = {}
    coverage = []
    scored_rows = []
    for lane, spec in lanes.items():
        if spec["status"] not in ("evaluated", "shared_tensor_identical"):
            continue
        src = spec.get("responses_from", lane)
        resp = {}
        for r in C.read_jsonl(args.responses / src / "responses.jsonl"):
            if r["status"] == "delivered" or r["query_id"] not in resp:
                resp[r["query_id"]] = r
        items = [score_row(q, resp.get(q["query_id"]), lane, objects) for q in manifest]
        reuse = expand_no_image(items, manifest)
        lanes_items[lane], lanes_reuse[lane] = items, reuse
        coverage += coverage_rows(lane, items, {})
        for it in items + reuse:
            scored_rows.append({"lane": lane, "responses_from": src, "query_id": it.query_id, "test": it.test, "bank": it.bank,
                                "family": it.family, "scene": it.scene, "physical_start_id": it.start, "frame_id": it.frame,
                                "goal": it.goal, "prompt_id": it.prompt_id, "form": it.form, "pair_id": it.pair_id,
                                "gold": json.dumps(it.gold) if isinstance(it.gold, dict) else it.gold,
                                "answerable": it.answerable, "exclusion_reason": it.exclusion, "status": it.status,
                                "valid": it.valid, "invalid_reason": it.reason,
                                "parsed_answer": json.dumps(it.answer) if isinstance(it.answer, dict) else it.answer,
                                "correct": it.correct, "b_target": it.fields.get("target"), "b_reference": it.fields.get("reference"),
                                "b_relation": it.fields.get("relation"), "reused_from": it.reused_from})
    results = {"study_id": C.STUDY_ID, "analysis_version": ANALYSIS_VERSION, "parser_version": PARSE.PARSER_VERSION,
               "release_content_sha256": release["release_content_sha256"], "created_utc": C.utc_now(),
               "bootstrap": {"replicates": args.bootstrap, "seed": C.BOOTSTRAP_SEED, "unit": "physical start within scene",
                             "interval": "percentile 95%", "conditional_on": "four fixed scene types and fixed prompt templates"},
               "weighting": "items within (start, goal) cell -> starts within goal -> goals equally within scene -> scenes equally",
               "lanes": lanes, "per_lane": {}}
    results["coverage_summary"] = {}
    for lane in lanes_items:
        results["per_lane"][lane] = analyse_lane(lane, lanes_items[lane], lanes_reuse[lane], idx)
        its = lanes_items[lane]
        results["coverage_summary"][lane] = {"proposed": len(its), "delivered": sum(it.status == "delivered" for it in its),
                                             "valid": sum(it.valid for it in its),
                                             "infrastructure_missing": sum(it.status != "delivered" for it in its),
                                             "responses_from": lanes[lane].get("responses_from", lane)}
    # checkpoint contrasts (policy - base, policy - upstream), descriptive, same resamples
    contrasts = {}
    pairs = [("N3-policy", "N3-base"), ("N3-base", "N3-upstream-qwen3vl8b"), ("N3-policy", "N3-upstream-qwen3vl8b"),
             ("E3-policy", "E3-base")]
    for a, b in pairs:
        if a in results["per_lane"] and b in results["per_lane"]:
            ra, rb = results["per_lane"][a]["initial"]["main_S1_S3_S4"], results["per_lane"][b]["initial"]["main_S1_S3_S4"]
            contrasts[f"{a}_minus_{b}"] = {
                "shared_or_identical": lanes[a].get("responses_from") == b or lanes[b].get("responses_from") == a,
                "C_TF_accuracy": diff_summary(ra["C_TF_RF"]["accuracy_TF"], rb["C_TF_RF"]["accuracy_TF"]),
                "C_RF_accuracy": diff_summary(ra["C_TF_RF"]["accuracy_RF"], rb["C_TF_RF"]["accuracy_RF"]),
                "C_TF_RF_gap": diff_summary(ra["C_TF_RF"]["gap"], rb["C_TF_RF"]["gap"]),
                "A_accuracy": diff_summary(ra["A_accuracy"], rb["A_accuracy"]),
                "B_image_tuple_accuracy": diff_summary(ra["B_image_tuple_accuracy"], rb["B_image_tuple_accuracy"])}
    results["checkpoint_contrasts_initial_main_pool"] = contrasts
    results["label_variation"] = label_variation(manifest)
    results["action_join"] = action_join(lanes_items, lanes, args.outcomes)
    if args.policy_contrasts.exists():
        with open(args.policy_contrasts) as f:
            results["policy_wording_contrasts_reference"] = [r for r in csv.DictReader(f)
                                                              if r["contrast"] == "S-I" and r["endpoint"] in ("stable_ever", "stable_at_final")]
    C.write_json_atomic(out / "results.json", strip_boot(results))
    write_csv(out / "scored_rows.csv", scored_rows)
    write_csv(out / "coverage.csv", [{**r, "truncated_or_other_invalid_reasons": json.dumps(r["truncated_or_other_invalid_reasons"])}
                                     for r in coverage])
    write_csv(out / "label_variation.csv", results["label_variation"])
    write_csv(out / "action_join_counts.csv", results["action_join"])
    write_csv(out / "breakdown.csv", [r for lane in results["per_lane"].values() for r in lane["breakdown_rows"]])
    write_csv(out / "metrics_long.csv", flatten_metrics(strip_boot(results)))
    print(json.dumps({lane: compact(results["per_lane"][lane]) for lane in results["per_lane"]}, indent=1))


def compact(lane_res: dict) -> dict:
    m = lane_res["initial"]["main_S1_S3_S4"]
    g = lambda d: None if d is None or d.get("estimate") is None else round(d["estimate"], 3)  # noqa: E731
    return {"C_TF": g(m["C_TF_RF"]["accuracy_TF"]), "C_RF": g(m["C_TF_RF"]["accuracy_RF"]),
            "C_gap": g(m["C_TF_RF"]["gap"]), "C_gap_ci": m["C_TF_RF"]["gap"].get("ci95"),
            "A_acc": g(m["A_accuracy"]), "B_img_tuple": g(m["B_image_tuple_accuracy"]),
            "B_text_tuple": lane_res["text_only_B"]["original"]["tuple_correct"]}


def flatten_metrics(results: dict) -> list[dict]:
    rows = []

    def walk(prefix: list[str], obj):
        if isinstance(obj, dict):
            if "estimate" in obj and not isinstance(obj.get("estimate"), dict):
                ci = obj.get("ci95") or [None, None]
                rows.append({"metric": "/".join(prefix), "estimate": obj.get("estimate"), "ci_low": ci[0], "ci_high": ci[1],
                             "n_units": obj.get("n_units"), "raw_correct": obj.get("raw_correct"), "raw_n": obj.get("raw_n"),
                             "support": obj.get("support"), "status": obj.get("status")})
            for k, v in obj.items():
                if k in ("breakdown_rows", "paired_rows"):
                    continue
                walk(prefix + [k], v)
    for lane, res in results["per_lane"].items():
        walk([lane], res)
    walk(["checkpoint_contrasts"], results.get("checkpoint_contrasts_initial_main_pool", {}))
    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("")
        return
    keys = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow(r)


if __name__ == "__main__":
    sys.exit(main())
