"""Synthetic-data checks for the frozen RWS analysis code (no simulator)."""
import json
import math
import tempfile
from pathlib import Path

import numpy as np
import pytest

from experiments.robolab_workshop import analyze, kinematics
from experiments.robolab_workshop.scripted import fold_yaw


def _rows(seed=0, n_slots=8):
    rng = np.random.default_rng(seed)
    rows = []
    for m in ("N3", "E3"):
        for s, goals in (("S1", "LRFB"), ("S4", ["TOP", "L", "R"])):
            for k in range(1, n_slots + 1):
                for g in goals:
                    for f in "DSI":
                        ev = int(rng.random() < 0.3)
                        rows.append({
                            "episode_id": f"RWS-{m}-{s}-C{k:02d}-{g}-{f}", "model_id": m, "scene_id": s, "goal_id": g,
                            "form": f, "state_slot": f"{s}-C{k:02d}", "phase": "confirmation", "status": "valid",
                            "stable_ever": bool(rng.random() < 0.2), "stable_at_final": False, "stratum": "achievement",
                            "study_goal_first_hit": None, "native_matched_task": None,
                            "native_matched_task_first_hit": None, "failure_stage": "lift_no_goal",
                            "mover_final_xy": [0.4, 0.1], "mover_final_displacement_m": 0.1, "event": ev,
                            "primary_window": {"fallback": False}, "window_primary": {"event": ev},
                            "features": {n: float(rng.normal()) for n in analyze.NUM} | {"chunk_fk_nearest_object_role": "mover"},
                        })
    return rows


def test_cell_weights_balance_models_scenes_goals():
    rows = _rows()
    w = analyze.cell_weights(rows)
    assert math.isclose(w.sum(), 1.0)
    for m in ("N3", "E3"):
        assert math.isclose(sum(wi for wi, r in zip(w, rows) if r["model_id"] == m), 0.5)
        for s in ("S1", "S4"):
            assert math.isclose(sum(wi for wi, r in zip(w, rows) if r["model_id"] == m and r["scene_id"] == s), 0.25)


def test_holm():
    assert analyze.holm([0.01, 0.04]) == [0.02, 0.04]
    assert analyze.holm([0.04, 0.01]) == [0.04, 0.02]


def test_wording_identical_forms_have_zero_difference():
    rows = _rows()
    for r in rows:
        r["stable_ever"] = r["state_slot"].endswith("1")
    out = analyze.wording(rows, "S", "I")
    assert out["mean_signed_difference"] == 0.0 and out["p_sign_flip"] == 1.0


def test_end_to_end_with_labels_and_degenerate_fold(tmp_path):
    pytest.importorskip("sklearn")
    rows = _rows()
    for r in rows:
        if r["state_slot"].endswith("C01"):
            r["event"] = 0
    labels = [{"episode_id": r["episode_id"], "fc_moving_object_role": "mover", "fc_direction": "left",
               "fc_visible_final_relation": "none", "fc_possible_release": "no", "fc_missing_object": "no",
               "fc_hallucinated_object": "no"} for r in rows[::2]]
    f = tmp_path / "f.jsonl"
    f.write_text("".join(json.dumps(r) + "\n" for r in rows))
    lab = tmp_path / "l.jsonl"
    lab.write_text("".join(json.dumps(x) + "\n" for x in labels))
    base = analyze.cv_brier([r for r in rows], {x["episode_id"]: x for x in labels})
    base.pop("_losses")
    assert "delta" in base and base["n"] == len(rows)


def test_fk_matches_home_tcp():
    calib = {"base": [0, 0, 0], "offset": [0, -0.000145, 0.1397]}
    q = [0.0, -0.6283185, 0.0, -2.5132742, 0.0, 1.8849556, 0.0]
    p = kinematics.tcp(q, calib)
    assert np.allclose(p, [0.35970, 0.000145, 0.35022], atol=2e-3)


def test_fold_yaw_centres_on_start_closing_yaw():
    for y in np.linspace(-4, 4, 33):
        f = fold_yaw(y, math.pi / 2)
        assert 0 - 1e-9 <= f < math.pi + 1e-9
        assert math.isclose(math.cos(2 * f), math.cos(2 * y), abs_tol=1e-9)


def test_canonical_frame_blinds_resolution():
    pytest.importorskip("PIL")
    from experiments.robolab_workshop.annotation import canonical_frame

    for h in (528, 544):
        assert canonical_frame(np.zeros((h, 640, 3), np.uint8)).shape == (544, 640, 3)


def test_unblind_semantics_goal_alternative_and_roles():
    from experiments.robolab_workshop.annotation import semantics

    k = {"episode_id": "e", "annotation_id": "a", "scene_id": "S3", "goal_id": "L",
         "legend_numbers": {"butter": 1, "raisin_box": 2}, "roles": {"mover": "butter", "reference": "raisin_box"}}
    lab = {"moving_object": "1", "direction": "left", "visible_final_relation": "left_of", "relation_object": "2",
           "possible_release": "yes", "missing_object": "no", "hallucinated_object": "no"}
    s = semantics(lab, k)
    assert s["fc_moving_object_role"] == "mover" and s["fc_direction"] == "goal_direction"
    assert s["fc_visible_final_relation"] == "goal"
    s = semantics(lab | {"visible_final_relation": "on_top_of", "direction": "right"}, k)
    assert s["fc_visible_final_relation"] == "alternative_goal" and s["fc_direction"] == "other_direction"
    s = semantics(lab | {"moving_object": "2"}, k)
    assert s["fc_moving_object_role"] == "reference" and s["fc_visible_final_relation"] == "not_goal"
    s = semantics(lab | {"visible_final_relation": "unknown"}, k)
    assert s["fc_visible_final_relation"] == "unknown"


def test_analysis_inputs_exclude_outcomes_and_form():
    r = _rows()[0]
    f0 = analyze.flat(r, None)
    r2 = dict(r, stable_ever=not r["stable_ever"], form="I", stable_at_final=True)
    assert analyze.flat(r2, None) == f0
    assert "form" not in f0 and "stable_ever" not in f0
