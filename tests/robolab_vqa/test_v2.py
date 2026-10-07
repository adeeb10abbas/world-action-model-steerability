"""CPU checks for RQA V2 (spec section 8)."""
import json
from pathlib import Path

import numpy as np
import pytest

from experiments.robolab_vqa import common as C
from experiments.robolab_vqa import prompts as P
from experiments.robolab_vqa.v2 import config as V
from experiments.robolab_vqa.v2 import scoring as S
from experiments.robolab_vqa.v2.prepare import parse_instruction, remove_headers, remove_images, replace_c_body, verify_tuples


def test_counterbalanced_codes_map_to_identical_semantics():
    for order in (0, 1):
        text = V.c2_body("Put the rubiks cube to the left of the bowl", order)
        lines = dict(l.split(": ", 1) for l in text.splitlines() if l[:3] in ("A: ", "B: ", "U: "))
        sem = {V.OPTION_MATCH: "match", V.OPTION_NONMATCH: "nonmatch", V.OPTION_UNKNOWN: "unknown"}
        assert {code: sem[lines[code]] for code in "ABU"} == V.C2_ORDERS[order]
    assert V.C2_ORDERS[0]["A"] == V.C2_ORDERS[1]["B"] == "match" and V.C2_ORDERS[0]["U"] == V.C2_ORDERS[1]["U"] == "unknown"
    assert V.c2_body("x", 0).replace("A: ", "#").count("#") == 1


def test_c2_parse_unknown_invalid_and_missing_accounting():
    m = V.C2_ORDERS[1]
    assert S.parse_c2("B", m)["semantic"] == "match"
    assert S.parse_c2(" U\n", m)["semantic"] == "unknown"
    for bad in ("AB", "a", "A.", "", "The answer is A"):
        assert not S.parse_c2(bad, m)["valid"]
    assert S.parse_c2(None, m)["reason"] == "no_text"


def test_b2_parser_rejects_duplicate_extra_missing_and_out_of_vocab():
    objs = ["banana", "bowl", "rubiks_cube"]
    ok = '{"target": "rubiks_cube", "reference": "bowl", "relation": "left_of"}'
    assert S.parse_b2(ok, objs)["valid"]
    assert S.parse_b2('{"target": "bowl", "target": "bowl", "reference": "bowl", "relation": "left_of"}', objs)["reason"] == "duplicate_key"
    for bad in ('{"target": "rubiks_cube", "reference": "bowl", "relation": "left_of", "x": "y"}',
                '{"target": "rubiks_cube", "relation": "left_of"}', '[' + ok + ']',
                '{"target": "Rubik\'s cube", "reference": "bowl", "relation": "left_of"}', "```json\n" + ok + "\n```"):
        assert not S.parse_b2(bad, objs)["valid"]


def test_b2_schema_keeps_complete_distractor_vocabulary_and_no_pruning():
    sch = V.b2_schema(["rubiks_cube", "banana", "bowl"])
    assert sch["properties"]["target"]["enum"] == ["banana", "bowl", "rubiks_cube"] == sch["properties"]["reference"]["enum"]
    assert sch["properties"]["relation"]["enum"] == list(C.RELATION_VOCABULARY)
    assert sch["additionalProperties"] is False and sch["required"] == ["target", "reference", "relation"]


def _ih(instr="Put the rubiks cube to the left of the bowl", seed="a"):
    views = {v: f"img-{seed}{i}" for i, v in enumerate(C.VIEW_KEYS)}
    return P.build_segments(test="B", instruction=instr, objects=["rubiks_cube", "banana", "bowl"], current=views)


def test_paired_header_and_pixel_contrasts_are_exact():
    ih = _ih()
    i, h = remove_headers(ih), remove_images(ih)
    t = remove_images(remove_headers(ih))
    assert P.full_prompt_text(remove_images(ih)) == P.full_prompt_text(h)
    assert P.full_prompt_text(remove_images(i)) == P.full_prompt_text(t)
    diff = P.full_prompt_text(ih)
    for hs in V.HEADER_STRINGS:
        assert diff.count(hs) == 1
        diff = diff.replace(hs, "")
    assert diff == P.full_prompt_text(i)
    assert [s["image_id"] for s in ih if s["type"] == "image"] == [s["image_id"] for s in i if s["type"] == "image"]
    assert "Camera views of the current scene" in P.full_prompt_text(t)


def test_no_image_payloads_deduplicate_across_starts():
    a, b = _ih(seed="a"), _ih(seed="b")
    assert a != b
    assert remove_images(a) == remove_images(b) and remove_images(remove_headers(a)) == remove_images(remove_headers(b))
    ca = replace_c_body(P.build_segments(test="C", instruction="Put the banana behind the bowl",
                                         current={v: f"img-a{i}" for i, v in enumerate(C.VIEW_KEYS)}), "Put the banana behind the bowl", 1)
    cb = replace_c_body(P.build_segments(test="C", instruction="Put the banana behind the bowl",
                                         current={v: f"img-b{i}" for i, v in enumerate(C.VIEW_KEYS)}), "Put the banana behind the bowl", 1)
    assert remove_images(ca) == remove_images(cb)
    assert all(h in P.full_prompt_text(remove_images(ca)) for h in V.HEADER_STRINGS)


def test_hand_calculated_balanced_accuracy_with_declared_weights_and_paired_gap():
    # S1 goal L: start1 two match items (1, 0); start2 one nonmatch item (1). S3 goal TOP: start1 nonmatch item (0).
    units = [("S1", "L", "S1-C01", "match", 1.0), ("S1", "L", "S1-C01", "match", 0.0), ("S1", "L", "S1-C02", "nonmatch", 1.0),
             ("S3", "TOP", "S3-C01", "nonmatch", 0.0)]
    res = S.class_recall(units, ("match", "nonmatch"), None)
    # declared weights: S1 cells weight 1/2 each (two starts), items in start1 1/4 each; S3 item weight 1. Scenes 1/2.
    # match: items w=1/8 each -> recall = (1/8)/(2/8) = 0.5 ; nonmatch: w(S1-C02)=1/4, w(S3)=1/2 -> recall=(1/4)/(3/4)=1/3
    assert abs(res["recall_match"]["estimate"] - 0.5) < 1e-12
    assert abs(res["recall_nonmatch"]["estimate"] - 1 / 3) < 1e-12
    assert abs(res["balanced_accuracy"]["estimate"] - (0.5 + 1 / 3) / 2) < 1e-12
    one = S.class_recall(units[:2], ("match", "nonmatch"), None)
    assert one["balanced_accuracy"]["estimate"] is None
    gap = S.hier_mean([("S1", "L", "S1-C01", 1.0), ("S1", "L", "S1-C02", 0.0), ("S1", "R", "S1-C01", 0.0),
                       ("S3", "L", "S3-C01", -1.0)], None)
    # S1 = mean(goal L 0.5, goal R 0.0) = 0.25 ; S3 = -1 ; macro = -0.375
    assert abs(gap["estimate"] + 0.375) < 1e-12


def test_bootstrap_resamples_whole_starts_and_is_shared():
    idx = S.bootstrap_index(500)
    assert set(idx) == {"S1", "S3", "S4"} and idx["S1"].shape == (500, 8)
    assert all(np.array_equal(S.bootstrap_index(500)[s], idx[s]) for s in idx)
    vals = np.random.default_rng(1).random(8)
    units = [("S1", g, f"S1-C0{k + 1}", float(vals[k])) for g in ("L", "R") for k in range(8)]
    a = S.hier_mean(units, idx)
    assert np.allclose(a["_boot"], vals[idx["S1"]].mean(axis=1))
    d = S.paired_diff(a, S.hier_mean(units, idx))
    assert d["estimate"] == 0 and d["ci95"] == [0.0, 0.0]


def test_v2_paths_never_overwrite_r1():
    with pytest.raises(ValueError):
        V.assert_not_r1_path(V.R1_RELEASE_DIR / "x")
    with pytest.raises(ValueError):
        V.assert_not_r1_path(V.R1_RUN_DIR)
    V.assert_not_r1_path(V.WORK_ROOT / "release" / "r2-final")
    V.assert_not_r1_path(V.WORK_ROOT / "runs" / "r2-final-20261007")


def test_all_46_instruction_tuples_follow_from_wording():
    rows = verify_tuples(C.load_catalog())
    assert len(rows) == 46 and all(r["matches_catalog"] for r in rows)
    rf = [r for r in rows if r["display_form"] == "RF"]
    assert len(rf) == 10 and all(r["converse_mapping"] and r["surface_subject_is_reference"] for r in rf)
    assert not any(r["converse_mapping"] for r in rows if r["display_form"] != "RF")
    assert parse_instruction("Place the mustard on the raisin box. ")["requested_relation"] == "on_top_supported"


def test_review_mask_rules():
    base = {"scene_id": "S3", "goal_id": "L", "objects_identifiable": "yes", "relation_discernible": "yes", "ambiguity": "none",
            "confidence": "high", "support_visible": "yes", "transit_or_gripper": "no"}
    assert S.review_answerable(base, "C")[0]
    assert not S.review_answerable({**base, "support_visible": "no"}, "C")[0] and S.review_answerable({**base, "support_visible": "no"}, "A")[0]
    assert not S.review_answerable({**base, "transit_or_gripper": "yes"}, "C")[0]
    assert not S.review_answerable({**base, "confidence": "low"}, "A")[0]


def test_b2_constraint_preserves_target_reference_relation_order_through_sorted_serialization():
    c = V.output_constraint("B2", ["rubiks_cube", "banana", "bowl"])
    round_trip = json.loads(json.dumps(c, sort_keys=True))
    assert V.schema_property_order(round_trip) == ["target", "reference", "relation"]
    assert V.schema_of(round_trip)["properties"]["target"]["enum"] == ["banana", "bowl", "rubiks_cube"]
