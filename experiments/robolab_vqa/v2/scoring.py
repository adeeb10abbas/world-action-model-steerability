"""Frozen V2 scoring rules (parser rqa-v2-parse-1). Pure Python + numpy; frozen before the first V2 evaluation query.

Correctness
  B2: strict parse of exactly one JSON object with exactly target/reference/relation (no duplicate or extra keys, values
      in the scene/relation vocabularies). Field and tuple correctness vs the catalog tuple; invalid -> all fields wrong.
  C2: output must be exactly one code A/B/U (surrounding whitespace ignored); mapped to match/nonmatch/unknown with the
      row's order mapping. On answerable items unknown and delivered-invalid answers are incorrect; missing
      infrastructure responses stay missing.
Aggregation (spec section 7)
  Items are averaged within (scene, goal, physical start) cells (C2: both option orders of an item are averaged first;
  an item needs both orders delivered), cells averaged over starts within goal, goals equally within scene, scenes
  equally. Class recalls use the same declared item weights normalised within each gold class; balanced accuracy is
  the mean of the two recalls and is undefined when one class is absent.
Uncertainty
  10,000 percentile bootstrap replicates, seed 6106, resampling the 8 physical starts within each of S1, S3, S4 (drawn
  in that order); every condition, goal, frame, order and lane of a sampled start is retained; all paired comparisons
  reuse the same resamples.
Review masks
  original = R1 mask. revised = original AND review-answerable. Review-answerable: both objects identifiable, relation
  discernible, required support/contact visible, no ambiguity flag, confidence not low; for C also no transit/gripper
  ambiguity. Discrepancies with geometry are flagged (second review required); the strict variant also excludes them.
"""
from __future__ import annotations

import json
import math
from collections import defaultdict

import numpy as np

from .. import common as C
from . import config as V

SCENES = tuple(V.SCENES)
N_STARTS = 8


# ---------------------------------------------------------------- parsing
class _Dup(ValueError):
    pass


def _no_dupes(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise _Dup(k)
        out[k] = v
    return out


def parse_b2(text: str | None, objects: list[str], relations: list[str] | None = None) -> dict:
    relations = relations or V.RELATIONS
    if text is None:
        return {"valid": False, "answer": None, "reason": "no_text"}
    s = text.strip()
    try:
        obj = json.loads(s, object_pairs_hook=_no_dupes)
    except _Dup:
        return {"valid": False, "answer": None, "reason": "duplicate_key"}
    except (json.JSONDecodeError, ValueError):
        return {"valid": False, "answer": None, "reason": "not_exactly_one_json_object"}
    if not isinstance(obj, dict):
        return {"valid": False, "answer": None, "reason": "json_not_object"}
    if set(obj) != {"target", "reference", "relation"}:
        return {"valid": False, "answer": None, "reason": "keys_not_exactly_target_reference_relation"}
    if not all(isinstance(v, str) for v in obj.values()):
        return {"valid": False, "answer": None, "reason": "non_string_value"}
    if obj["target"] not in objects or obj["reference"] not in objects:
        return {"valid": False, "answer": obj, "reason": "object_not_in_vocabulary"}
    if obj["relation"] not in relations:
        return {"valid": False, "answer": obj, "reason": "relation_not_in_vocabulary"}
    return {"valid": True, "answer": {k: obj[k] for k in ("target", "reference", "relation")}, "reason": None}


def parse_c2(text: str | None, mapping: dict) -> dict:
    if text is None:
        return {"valid": False, "code": None, "semantic": None, "reason": "no_text"}
    s = text.strip()
    if s in ("A", "B", "U"):
        return {"valid": True, "code": s, "semantic": mapping[s], "reason": None}
    return {"valid": False, "code": None, "semantic": None, "reason": "not_exactly_one_code"}


def b2_fields(parsed: dict, gold: dict) -> dict:
    ok = parsed["valid"]
    a = parsed["answer"] if ok else None
    f = {k: float(bool(ok) and a[k] == gold[k]) for k in ("target", "reference", "relation")}
    f["tuple"] = float(all(v == 1.0 for v in f.values()))
    return f


CONVERSE = {"left_of": "right_of", "right_of": "left_of", "in_front_of": "behind", "behind": "in_front_of"}


def b2_error_class(parsed: dict, gold: dict) -> str:
    if not parsed["valid"]:
        return "invalid_format"
    a = parsed["answer"]
    if a == gold:
        return "correct"
    if a["target"] == gold["reference"] and a["reference"] == gold["target"]:
        objs = "target_reference_swapped"
    elif a["target"] != gold["target"] or a["reference"] != gold["reference"]:
        objs = "object_error"
    else:
        objs = None
    if a["relation"] == gold["relation"]:
        rel = None
    elif CONVERSE.get(gold["relation"]) == a["relation"]:
        rel = "converse_relation"
    elif {gold["relation"], a["relation"]} == {"on_top_supported", "stacked_on"}:
        rel = "support_label_swap"
    elif a["relation"] == "unknown":
        rel = "unknown_relation"
    else:
        rel = "other_relation"
    return "+".join(x for x in (objs, rel) if x)


# ---------------------------------------------------------------- bootstrap and weighting
def bootstrap_index(replicates: int = C.BOOTSTRAP_REPLICATES, seed: int = C.BOOTSTRAP_SEED) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(seed)
    return {s: rng.integers(0, N_STARTS, size=(replicates, N_STARTS)) for s in SCENES}


def start_index(start: str) -> int:
    return int(start.split("-C")[1]) - 1


def _cells(units):
    cells = defaultdict(list)
    for scene, goal, start, *rest in units:
        cells[(scene, goal, start_index(start) if isinstance(start, str) else start)].append(rest)
    return cells


def _goal_arrays(cell_values: dict) -> dict[str, np.ndarray]:
    """{(scene, goal, k): value} -> {scene: array (n_goals, 8)} with NaN for absent cells."""
    out = {}
    for s in SCENES:
        goals = sorted({g for (sc, g, _) in cell_values if sc == s})
        arr = np.full((len(goals), N_STARTS), np.nan)
        for gi, g in enumerate(goals):
            for k in range(N_STARTS):
                if (s, g, k) in cell_values:
                    arr[gi, k] = cell_values[(s, g, k)]
        out[s] = arr
    return out


def _agg_point(arrs: dict) -> float:
    scene_vals = []
    for s, a in arrs.items():
        if a.size == 0 or not np.isfinite(a).any():
            continue
        with np.errstate(all="ignore"):
            g = np.nanmean(a, axis=1)
        g = g[np.isfinite(g)]
        if g.size:
            scene_vals.append(float(np.mean(g)))
    return float(np.mean(scene_vals)) if scene_vals else float("nan")


def _agg_boot(arrs: dict, idx: dict) -> np.ndarray:
    per_scene = []
    for s, a in arrs.items():
        if a.size == 0 or not np.isfinite(a).any():
            continue
        samp = a[:, idx[s]]                       # (G, R, 8)
        with np.errstate(all="ignore"):
            g = np.nanmean(samp, axis=2)          # (G, R)
            per_scene.append(np.nanmean(g, axis=0))
    if not per_scene:
        return np.full(next(iter(idx.values())).shape[0], np.nan)
    S = np.vstack(per_scene)
    return np.where(np.isfinite(S).all(axis=0), S.mean(axis=0), np.nan)


def _ci(boot: np.ndarray) -> list | None:
    f = boot[np.isfinite(boot)]
    return [float(np.percentile(f, 2.5)), float(np.percentile(f, 97.5))] if f.size else None


def hier_mean(units, idx: dict | None) -> dict:
    """units: (scene, goal, start, value). Cell mean -> starts -> goals -> scenes."""
    cells = _cells(units)
    if not cells:
        return {"estimate": None, "n_items": 0, "n_cells": 0, "status": "no_items"}
    cv = {k: float(np.mean([r[0] for r in v])) for k, v in cells.items()}
    arrs = _goal_arrays(cv)
    out = {"estimate": _agg_point(arrs), "n_items": int(sum(len(v) for v in cells.values())), "n_cells": len(cells),
           "raw_sum": float(sum(r[0] for v in cells.values() for r in v))}
    if idx is not None:
        boot = _agg_boot(arrs, idx)
        out["ci95"] = _ci(boot)
        out["bootstrap_undefined"] = int((~np.isfinite(boot)).sum())
        out["_boot"] = boot
    return out


def class_recall(units, classes: tuple[str, str], idx: dict | None) -> dict:
    """units: (scene, goal, start, gold_class, value). Declared item weights 1/(S*G_s*K_sg*N_cell), normalised per class."""
    cells = _cells(units)
    out: dict = {}
    nums, dens = {}, {}
    for cls in classes:
        num = {k: sum(r[1] for r in v if r[0] == cls) / len(v) for k, v in cells.items()}
        den = {k: sum(1 for r in v if r[0] == cls) / len(v) for k, v in cells.items()}
        nums[cls], dens[cls] = _goal_arrays(num), _goal_arrays(den)
        support = sum(1 for v in cells.values() for r in v if r[0] == cls)
        n, d = _agg_point(nums[cls]), _agg_point(dens[cls])
        out[f"recall_{cls}"] = {"estimate": (n / d) if d and d > 0 else None, "support": support,
                                "raw_correct": float(sum(r[1] for v in cells.values() for r in v if r[0] == cls)),
                                "declared_weight_share": d}
    if any(out[f"recall_{c}"]["support"] == 0 for c in classes):
        out["balanced_accuracy"] = {"estimate": None, "status": "undefined_one_class_absent"}
        return out
    ba = {"estimate": float(np.mean([out[f"recall_{c}"]["estimate"] for c in classes]))}
    if idx is not None:
        rec = []
        for cls in classes:
            n, d = _agg_boot(nums[cls], idx), _agg_boot(dens[cls], idx)
            with np.errstate(all="ignore"):
                rec.append(np.where(d > 0, n / d, np.nan))
            out[f"recall_{cls}"]["ci95"] = _ci(rec[-1])
        boot = (rec[0] + rec[1]) / 2
        ba["ci95"] = _ci(boot)
        ba["bootstrap_undefined"] = int((~np.isfinite(boot)).sum())
        ba["_boot"] = boot
    out["balanced_accuracy"] = ba
    return out


def paired_diff(a: dict, b: dict) -> dict | None:
    if not a or not b or a.get("estimate") is None or b.get("estimate") is None:
        return None
    out = {"estimate": a["estimate"] - b["estimate"]}
    if "_boot" in a and "_boot" in b:
        out["ci95"] = _ci(a["_boot"] - b["_boot"])
    return out


def strip_boot(obj):
    if isinstance(obj, dict):
        return {k: strip_boot(v) for k, v in obj.items() if k != "_boot"}
    if isinstance(obj, list):
        return [strip_boot(v) for v in obj]
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    return obj


# ---------------------------------------------------------------- review masks
REVIEW_TOP_GOALS = {"TOP"}
TABLE_SUPPORT_GOALS = {("S3", "L"), ("S3", "R"), ("S4", "L"), ("S4", "R")}


def review_answerable(row: dict, test: str) -> tuple[bool, list[str]]:
    """row: one frame-goal review ledger row (adjudicated or single reviewer)."""
    reasons = []
    if row.get("objects_identifiable") != "yes":
        reasons.append("objects_not_identifiable")
    if row.get("relation_discernible") != "yes":
        reasons.append("relation_not_discernible")
    if row.get("ambiguity") not in (None, "", "none"):
        reasons.append(f"ambiguity:{row.get('ambiguity')}")
    if row.get("confidence") == "low":
        reasons.append("low_confidence")
    if test == "C" and (row["scene_id"], row["goal_id"]) in TABLE_SUPPORT_GOALS and row.get("support_visible") != "yes":
        reasons.append("required_table_support_not_visible")
    if row["goal_id"] in REVIEW_TOP_GOALS and row.get("support_visible") != "yes":
        reasons.append("support_not_visible")
    if test == "C" and row.get("transit_or_gripper") == "yes":
        reasons.append("transit_or_gripper_contact")
    return (not reasons), reasons
