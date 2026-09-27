"""Prespecified confirmation analyses (CLUSTER_EXECUTION_SPEC section 8) on the rescored feature table.

usage: python -m experiments.robolab_workshop.analyze --features <features.jsonl> --out <dir>
         [--labels <forecast_labels.jsonl>]

E1/A2/A3/A4 need frozen, blinded forecast labels; without them they are reported as pending, never imputed.
"""
from __future__ import annotations

import argparse
import itertools
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

NUM = ["mover_rel_ref_x_m", "mover_rel_ref_y_m", "mover_rel_ref_z_m", "mover_dist_to_goal_region_m", "goal_true_now",
       "gripper_closed_fraction", "chunk_fk_min_dist_m", "prior_target_contact", "prior_target_lift"]
CAT = ["model_id", "scene_id", "goal_id", "chunk_fk_nearest_object_role"]
FC = ["fc_moving_object_role", "fc_direction", "fc_visible_final_relation", "fc_possible_release",
      "fc_missing_object", "fc_hallucinated_object"]
SEED_SOLVER, SEED_BOOT, SEED_FLIP = 8400, 8401, 8402
A4_SEEDS = range(8403, 8503)


def load(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def slot_index(r: dict) -> str:
    return r["state_slot"].split("-")[-1]


def cell_weights(rows: list[dict]) -> np.ndarray:
    """Models equal; scenes equal within model; goals equal within scene; rows equal within goal cell."""
    by_model = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    for r in rows:
        by_model[r["model_id"]][r["scene_id"]][r["goal_id"]] += 1
    w = []
    for r in rows:
        m = by_model[r["model_id"]]
        w.append(1.0 / (len(by_model) * len(m) * len(m[r["scene_id"]]) * m[r["scene_id"]][r["goal_id"]]))
    w = np.array(w)
    return w / w.sum()


def design(rows, fit_rows, cats, nums):
    """Train-fold standardization and one-hot (categories from the training fold only)."""
    mu = {n: np.mean([fr[n] for fr in fit_rows]) for n in nums}
    sd = {n: np.std([fr[n] for fr in fit_rows]) or 1.0 for n in nums}
    levels = {c: sorted({str(fr[c]) for fr in fit_rows}) for c in cats}
    X = []
    for r in rows:
        v = [(r[n] - mu[n]) / sd[n] for n in nums]
        for c in cats:
            v += [1.0 if str(r[c]) == lv else 0.0 for lv in levels[c]]
        X.append(v)
    return np.array(X)


def flat(r: dict, labels: dict | None, persistence: bool = False, missing_only: bool = False) -> dict:
    out = {k: r[k] for k in ("model_id", "scene_id", "goal_id")}
    out.update(r["features"])
    if labels is not None:
        lab = labels.get(r["episode_id"])
        if persistence:
            lab = {"fc_moving_object_role": "none", "fc_direction": "none",
                   "fc_visible_final_relation": "goal" if r["features"]["goal_true_now"] else "not_goal",
                   "fc_possible_release": "no", "fc_missing_object": "no", "fc_hallucinated_object": "no"}
        for f in FC:
            out[f] = "missing" if lab is None else str(lab.get(f, "unknown"))
        out["fc_missing_indicator"] = "missing" if lab is None else "present"
        if missing_only:
            for f in FC:
                out.pop(f)
    return out


def cv_brier(rows: list[dict], labels: dict | None, mode: str = "forecast", donor_fn=None) -> dict:
    from sklearn.linear_model import LogisticRegression

    y = np.array([r["event"] for r in rows], dtype=float)
    w = cell_weights(rows)
    folds = sorted({slot_index(r) for r in rows})
    loss_b, loss_a = np.zeros(len(rows)), np.zeros(len(rows))
    degenerate = []
    for fold in folds:
        test = [i for i, r in enumerate(rows) if slot_index(r) == fold]
        train = [i for i, r in enumerate(rows) if slot_index(r) != fold]
        ytr = y[train]
        donor = donor_fn(fold) if donor_fn is not None else None
        for kind in ("baseline", "augmented"):
            if kind == "augmented" and labels is None:
                continue
            fr = []
            for i in range(len(rows)):
                r = rows[i]
                src = r
                if kind == "augmented" and donor is not None:
                    src = donor.get(r["episode_id"], r)
                f = flat(src if kind == "augmented" else r, labels if kind == "augmented" else None,
                         persistence=(mode == "persistence"), missing_only=(mode == "missing_only"))
                if kind == "augmented":
                    f.update({k: v for k, v in flat(r, None).items()})  # baseline features stay with the row
                fr.append(f)
            cats = CAT + ([c for c in fr[0] if c.startswith("fc_")] if kind == "augmented" else [])
            if len(set(ytr)) < 2:
                p = np.full(len(test), (ytr.sum() + 0.5) / (len(ytr) + 1))
                degenerate.append(fold)
            else:
                Xtr = design([fr[i] for i in train], [fr[i] for i in train], cats, NUM)
                Xte = design([fr[i] for i in test], [fr[i] for i in train], cats, NUM)
                clf = LogisticRegression(C=1.0, class_weight=None, random_state=SEED_SOLVER, max_iter=5000)
                clf.fit(Xtr, ytr)
                p = clf.predict_proba(Xte)[:, 1]
            (loss_b if kind == "baseline" else loss_a)[test] = (p - y[test]) ** 2
    out = {"n": len(rows), "events": int(y.sum()), "folds": folds, "degenerate_folds": sorted(set(degenerate)),
           "brier_baseline": float(np.sum(w * loss_b))}
    if labels is not None:
        out["brier_augmented"] = float(np.sum(w * loss_a))
        out["delta"] = out["brier_baseline"] - out["brier_augmented"]
    out["_losses"] = (loss_b, loss_a, w)
    return out


def cluster_bootstrap(rows: list[dict], stat, draws: int = 10000, seed: int = SEED_BOOT) -> list[float]:
    """Resample state clusters (scene x slot) within scene; all forms/models/goals of a state move together."""
    rng = np.random.default_rng(seed)
    by_scene = defaultdict(list)
    for key in sorted({(r["scene_id"], r["state_slot"]) for r in rows}):
        by_scene[key[0]].append(key)
    idx = defaultdict(list)
    for i, r in enumerate(rows):
        idx[(r["scene_id"], r["state_slot"])].append(i)
    vals = []
    for _ in range(draws):
        sel = []
        for sc, keys in by_scene.items():
            for k in rng.choice(len(keys), size=len(keys), replace=True):
                sel.append(idx[keys[k]])
        v = stat(sel)
        if v is not None and np.isfinite(v):
            vals.append(v)
    return [float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))] if vals else [None, None]


def wording(rows: list[dict], a: str, b: str) -> dict:
    """State-paired signed difference a - b in stable success; cluster sign-flip test over state clusters."""
    pairs = defaultdict(dict)
    for r in rows:
        pairs[(r["model_id"], r["scene_id"], r["state_slot"], r["goal_id"])][r["form"]] = r
    diffs = defaultdict(list)
    disc = {"a_only": 0, "b_only": 0}
    strata = defaultdict(list)
    for (m, s, slot, g), f in pairs.items():
        if a in f and b in f:
            d = float(f[a]["stable_ever"]) - float(f[b]["stable_ever"])
            diffs[(s, slot)].append(d)
            strata[f[a]["stratum"]].append(d)
            disc["a_only"] += int(d > 0)
            disc["b_only"] += int(d < 0)
    cl = np.array([np.mean(v) for v in diffs.values()]) if diffs else np.array([])
    if cl.size == 0:
        return {"contrast": f"{a}-{b}", "n_pairs": 0}
    obs = float(cl.mean())
    rng = np.random.default_rng(SEED_FLIP)
    n = 100000
    flips = rng.choice([-1.0, 1.0], size=(n, cl.size))
    null = np.abs((flips * cl).mean(axis=1))
    p = float((np.sum(null >= abs(obs) - 1e-12) + 1) / (n + 1))
    return {"contrast": f"{a}-{b}", "n_pairs": int(sum(len(v) for v in diffs.values())), "n_state_clusters": int(cl.size),
            "mean_signed_difference": obs, "discordant": disc, "p_sign_flip": p,
            "by_stratum": {k: {"n": len(v), "mean": float(np.mean(v))} for k, v in strata.items()}}


def holm(ps: list[float]) -> list[float]:
    order = np.argsort(ps)
    adj, running = [0.0] * len(ps), 0.0
    for k, i in enumerate(order):
        running = max(running, min(1.0, (len(ps) - k) * ps[i]))
        adj[i] = running
    return adj


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--features", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--labels", type=Path, default=None)
    ap.add_argument("--bootstrap-draws", type=int, default=10000)
    ap.add_argument("--phase", default="confirmation", help="development only for code verification")
    args = ap.parse_args()
    allrows = load(args.features)
    rows = [r for r in allrows if r.get("status") == "valid" and r.get("phase") == args.phase]
    invalid = [r["episode_id"] for r in allrows if r.get("status") != "valid"]
    res: dict = {"n_rows": len(allrows), "n_valid_confirmation": len(rows), "invalid_or_incomplete": invalid}

    # Descriptive endpoints
    tab = defaultdict(lambda: [0, 0])
    for r in rows:
        for key in [(r["model_id"], r["scene_id"], r["form"]), (r["model_id"], r["scene_id"], "*"), (r["model_id"], "*", "*")]:
            tab[key][0] += int(r["stable_ever"])
            tab[key][1] += 1
    res["stable_success"] = {"|".join(k): {"successes": v[0], "n": v[1], "rate": v[0] / v[1]} for k, v in sorted(tab.items())}
    res["stable_at_final"] = sum(int(r["stable_at_final"]) for r in rows)
    ev = [r for r in rows if r.get("event") is not None]
    res["events"] = {"scorable": len(ev), "unknown": len(rows) - len(ev), "positive": sum(r["event"] for r in ev),
                     "neutral_no_decision": sum(bool((r.get("window_primary") or {}).get("neutral_no_decision")) for r in ev),
                     "goal_consistent_interaction": sum(bool((r.get("window_primary") or {}).get("goal_consistent_interaction")) for r in ev),
                     "physical_failure": sum(bool((r.get("window_primary") or {}).get("physical_failure")) for r in ev),
                     "primary_fallback": sum(bool((r.get("primary_window") or {}).get("fallback")) for r in rows)}
    res["failure_stage"] = {}
    for r in rows:
        res["failure_stage"][r["failure_stage"]] = res["failure_stage"].get(r["failure_stage"], 0) + 1

    # E2 / E3 wording
    e2, e3 = wording(rows, "S", "I"), wording(rows, "D", "S")
    if "p_sign_flip" in e2 and "p_sign_flip" in e3:
        e2["p_holm"], e3["p_holm"] = holm([e2["p_sign_flip"], e3["p_sign_flip"]])
    for e, (a, b) in ((e2, ("S", "I")), (e3, ("D", "S"))):
        if e.get("n_pairs"):
            def stat(clusters, a=a, b=b):
                means = [wording_mean([rows[i] for i in c], a, b) for c in clusters]
                means = [x for x in means if x is not None]
                return float(np.mean(means)) if means else None
            e["ci95_state_bootstrap"] = cluster_bootstrap(rows, stat, draws=args.bootstrap_draws)
    res["E2_S_minus_I"], res["E3_D_minus_S"] = e2, e3

    # E4 goal separation: stable success and final mover position by goal within scene
    e4 = defaultdict(dict)
    for (m, s), grp in itertools.groupby(sorted(rows, key=lambda r: (r["model_id"], r["scene_id"], r["goal_id"])),
                                         key=lambda r: (r["model_id"], r["scene_id"])):
        grp = list(grp)
        for g in sorted({r["goal_id"] for r in grp}):
            gg = [r for r in grp if r["goal_id"] == g]
            xy = np.array([r["mover_final_xy"] for r in gg])
            e4[f"{m}|{s}"][g] = {"n": len(gg), "stable": sum(r["stable_ever"] for r in gg),
                                 "mean_final_xy": xy.mean(axis=0).tolist(), "mean_displacement_m": float(np.mean([r["mover_final_displacement_m"] for r in gg]))}
    res["E4_goal_separation"] = e4

    # A1 native matched first-hit vs stable release
    a1 = defaultdict(lambda: {"native_hit_stable": 0, "native_hit_not_stable": 0, "no_native_hit_stable": 0, "neither": 0})
    for r in rows:
        if r["native_matched_task"] is None:
            continue
        hit = r["native_matched_task_first_hit"] is not None
        a1[r["model_id"]][("native_hit_" if hit else "no_native_hit_") + ("stable" if r["stable_ever"] else "not_stable")
                          if hit or r["stable_ever"] else "neither"] += 1
    res["A1_native_first_hit_vs_stable"] = a1
    goalhit = defaultdict(lambda: [0, 0])
    for r in rows:
        goalhit[r["model_id"]][0] += int(r["study_goal_first_hit"] is not None)
        goalhit[r["model_id"]][1] += int(r["stable_ever"])
    res["A1_study_goal_first_hit_vs_stable"] = {m: {"first_hit": v[0], "stable": v[1]} for m, v in goalhit.items()}

    # E1 baseline / forecast
    scorable = [r for r in ev if r.get("features")]
    labels = None
    if args.labels and args.labels.exists():
        labels = {x["episode_id"]: x for x in load(args.labels)}
    if scorable and len({r["event"] for r in scorable}) > 1:
        base = cv_brier(scorable, labels)
        loss_b, loss_a, w = base.pop("_losses")
        res["E1"] = base
        if labels is not None:
            idx = {i: r for i, r in enumerate(scorable)}

            def dstat(clusters):
                sel = np.concatenate([np.array(c, dtype=int) for c in clusters])
                ww = w[sel] / w[sel].sum()
                return float(np.sum(ww * (loss_b[sel] - loss_a[sel])))
            res["E1"]["ci95_conditional_bootstrap"] = cluster_bootstrap(scorable, dstat, draws=args.bootstrap_draws)
            for m in sorted({r["model_id"] for r in scorable}):
                sub = [r for r in scorable if r["model_id"] == m]
                if len({r["event"] for r in sub}) > 1:
                    x = cv_brier(sub, labels)
                    x.pop("_losses")
                    res.setdefault("E1_by_model", {})[m] = x
            for mode in ("persistence", "missing_only"):
                x = cv_brier(scorable, labels, mode=mode)
                x.pop("_losses")
                res[f"A3_{mode}" if mode == "persistence" else "E1_missingness_only"] = x
            res["A4"] = a4(scorable, labels)
            res["A2"] = a2_table(ev, labels)
        else:
            res["E1"]["status"] = "forecast_labels_pending: blinded human annotation not yet collected"
    else:
        res["E1"] = {"status": "no_informative_events", "scorable": len(scorable),
                     "positives": sum(r["event"] for r in scorable)}
    if labels is None:
        for k in ("A2", "A3_persistence", "A4"):
            res[k] = {"status": "forecast_labels_pending"}
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "results.json").write_text(json.dumps(res, indent=2, default=float))
    print(json.dumps({k: res[k] for k in ("n_valid_confirmation", "events")}, default=float))


def wording_mean(rows, a, b):
    pairs = defaultdict(dict)
    for r in rows:
        pairs[(r["model_id"], r["scene_id"], r["state_slot"], r["goal_id"])][r["form"]] = r
    d = [float(f[a]["stable_ever"]) - float(f[b]["stable_ever"]) for f in pairs.values() if a in f and b in f]
    return float(np.mean(d)) if d else None


def execution_category(r: dict) -> str:
    w = r.get("window_primary") or {}
    if r.get("event") == 1:
        return "wrong_goal_event"
    for k in ("goal_consistent_interaction", "neutral_no_decision", "physical_failure"):
        if w.get(k):
            return k
    return "other_no_event"


def a2_table(rows: list[dict], labels: dict) -> dict:
    tab = defaultdict(lambda: defaultdict(int))
    for r in rows:
        lab = labels.get(r["episode_id"])
        fc = "missing" if lab is None else lab.get("fc_visible_final_relation", "unknown")
        tab[r["model_id"]][f"{fc}|{execution_category(r)}"] += 1
    return {m: dict(v) for m, v in tab.items()}


def a4(rows: list[dict], labels: dict) -> dict:
    """Inside each held-out fold: derange training-state IDs within scene; the held-out state gets a random
    training-state donor. One mapping per fold moves complete state associations across models/goals/forms."""
    slots_by_scene = defaultdict(set)
    for r in rows:
        slots_by_scene[r["scene_id"]].add(r["state_slot"])
    by_key = {(r["model_id"], r["scene_id"], r["state_slot"], r["goal_id"], r["form"]): r for r in rows}
    deltas = []
    for seed in A4_SEEDS:
        rng = np.random.default_rng(seed)

        def donor_fn(fold, rng=rng):
            mapping = {}
            for sc, slots in sorted(slots_by_scene.items()):
                slots = sorted(slots)
                held = [s for s in slots if s.endswith(fold)]
                train = [s for s in slots if not s.endswith(fold)]
                if len(train) >= 2:
                    while True:
                        perm = list(rng.permutation(train))
                        if all(a != b for a, b in zip(train, perm)):
                            break
                    mapping.update({(sc, a): b for a, b in zip(train, perm)})
                for h in held:
                    if train:
                        mapping[(sc, h)] = train[rng.integers(len(train))]
            donor = {}
            for r in rows:
                d = mapping.get((r["scene_id"], r["state_slot"]))
                src = by_key.get((r["model_id"], r["scene_id"], d, r["goal_id"], r["form"])) if d else None
                if src is not None:
                    donor[r["episode_id"]] = src
            return donor
        x = cv_brier(rows, labels, donor_fn=donor_fn)
        deltas.append(x["delta"])
    return {"seeds": [A4_SEEDS.start, A4_SEEDS.stop - 1], "delta_mean": float(np.mean(deltas)),
            "delta_p2_5": float(np.percentile(deltas, 2.5)), "delta_p97_5": float(np.percentile(deltas, 97.5))}


if __name__ == "__main__":
    main()
