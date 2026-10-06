import numpy as np

from experiments.robolab_vqa import analyze as A


def item(scene, start, goal, form, correct, test="C", bank="initial", answerable=True, gold="no", answer=None):
    it = A.Item(lane="L", query_id=f"{scene}{start}{goal}{form}", test=test, bank=bank, family="original", scene=scene,
                start=f"{scene}-C0{start}", frame=f"{scene}-C0{start}-initial", goal=goal, prompt_id=f"{scene}-{goal}-{form}",
                form=form, pair_id=f"P.{scene}.{start}.{goal}", gold=gold, answerable=answerable, exclusion=None,
                status="delivered", valid=True, answer=answer if answer is not None else ("no" if correct else "yes"),
                correct=float(correct))
    return it


def test_hand_calculated_paired_gap_and_macro_weighting():
    # S1: goal L TF correct at starts 1..2, RF correct at start 1 only -> L gap = (0 + 1)/2 = 0.5
    #     goal R: TF and RF both correct at start 1 -> gap 0 ; start 2 missing -> R gap 0
    # S3: goal L: TF wrong, RF correct at start 1 -> gap -1
    items = [item("S1", 1, "L", "TF", 1), item("S1", 1, "L", "RF", 1), item("S1", 2, "L", "TF", 1), item("S1", 2, "L", "RF", 0),
             item("S1", 1, "R", "TF", 1), item("S1", 1, "R", "RF", 1),
             item("S3", 1, "L", "TF", 0), item("S3", 1, "L", "RF", 1)]
    res = A.paired_metrics(items, "C", ("TF", "RF"), ("S1", "S3"), None)
    # scene S1 = mean(goal L 0.5, goal R 0.0) = 0.25 ; scene S3 = -1 ; macro = (0.25 - 1)/2 = -0.375
    assert abs(res["gap"]["estimate"] - (-0.375)) < 1e-12
    # TF accuracy: S1 = mean(L 1.0, R 1.0) = 1 ; S3 = 0 -> 0.5 ; RF: S1 = mean(L .5, R 1) = .75 ; S3 = 1 -> .875
    assert abs(res["accuracy_TF"]["estimate"] - 0.5) < 1e-12
    assert abs(res["accuracy_RF"]["estimate"] - 0.875) < 1e-12
    # both-correct: S1 L (1 + 0)/2 = .5, R 1 -> .75 ; S3 0 -> .375
    assert abs(res["both_correct"]["estimate"] - 0.375) < 1e-12
    assert res["discordant_counts"] == {"TF_only_correct": 1, "RF_only_correct": 1, "both_correct": 2, "both_incorrect": 0}


def test_joint_exclusion_and_missing_response_handling():
    a, b = item("S1", 1, "L", "TF", 1), item("S1", 1, "L", "RF", 0, answerable=False)
    c, d = item("S1", 2, "L", "TF", 1), item("S1", 2, "L", "RF", 1)
    d.status, d.correct = "missing", None
    res = A.paired_metrics([a, b, c, d], "C", ("TF", "RF"), ("S1",), None)
    assert res["pairs_complete"] == 0 and res["pairs_excluded_jointly"] == 1 and res["pairs_missing_response"] == 1


def test_bootstrap_resamples_whole_starts_within_scene():
    rng = np.random.default_rng(0)
    idx = {s: rng.integers(0, 8, size=(2000, 8)) for s in ("S1", "S3", "S4", "S5")}
    start_effect = rng.random(8)
    # identical per-start values for two goals: a clustered (start-level) resample keeps their difference exactly 0
    t1 = {("S1", "L"): start_effect.copy()}
    t2 = {("S1", "L"): start_effect.copy()}
    d = A.macro_boot(t1, ("S1",), idx) - A.macro_boot(t2, ("S1",), idx)
    assert np.all(d == 0)
    # goals within the same start move together: L and R share the sampled starts
    t = {("S1", "L"): start_effect, ("S1", "R"): start_effect}
    boot = A.macro_boot(t, ("S1",), idx)
    assert np.allclose(boot, start_effect[idx["S1"]].mean(axis=1))
    # point estimate and a degenerate interval when all starts agree
    flat = {("S1", "L"): np.ones(8)}
    s = A.summarize(flat, ("S1",), idx, 8)
    assert s["estimate"] == 1.0 and s["ci95"] == [1.0, 1.0]


def test_balanced_accuracy_undefined_when_one_class_absent():
    items = [item("S5", i, "LR", "TF", 1, gold="no", answer="no") for i in range(1, 9)]
    ba = A.balanced_accuracy(items, ("S5",), None)
    assert ba["balanced_accuracy"]["estimate"] is None
    items.append(item("S5", 1, "RL", "TF", 0, gold="yes", answer="no"))
    ba = A.balanced_accuracy(items, ("S5",), None)
    assert abs(ba["balanced_accuracy"]["estimate"] - 0.5) < 1e-12
