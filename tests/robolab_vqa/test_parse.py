from experiments.robolab_vqa import parse as P

OBJ = ["banana", "bowl", "rubiks_cube"]
REL = ["left_of", "right_of", "in_front_of", "behind", "on_top_supported", "stacked_on", "unknown"]


def test_yes_no_accepts_exact_case_insensitive_and_one_terminal_punctuation():
    for raw, want in [("yes", "yes"), (" No. ", "no"), ("UNKNOWN", "unknown"), ("Yes!", "yes"), ("no\n", "no")]:
        r = P.parse_yes_no(raw)
        assert r["valid"] and r["answer"] == want


def test_yes_no_rejects_verbose_conflicting_and_double_punctuation():
    for raw in ["Yes, the cube is left.", "yes/no", "no..", "", None, "maybe", "The answer is yes", "**yes**"]:
        assert not P.parse_yes_no(raw)["valid"]


def test_b_accepts_exact_object_and_frozen_fence():
    ok = '{"target": "rubiks_cube", "reference": "bowl", "relation": "left_of"}'
    assert P.parse_b(ok, OBJ, REL)["answer"] == {"target": "rubiks_cube", "reference": "bowl", "relation": "left_of"}
    fenced = "```json\n" + ok + "\n```"
    r = P.parse_b(fenced, OBJ, REL)
    assert r["valid"] and r["fence_removed"]


def test_b_rejects_duplicates_missing_extra_vocab_and_trailing_text():
    bad = [
        '{"target": "bowl", "target": "bowl", "reference": "bowl", "relation": "left_of"}',
        '{"target": "rubiks_cube", "relation": "left_of"}',
        '{"target": "rubiks_cube", "reference": "bowl", "relation": "left_of", "why": "x"}',
        '{"target": "Rubik\'s cube", "reference": "bowl", "relation": "left_of"}',
        '{"target": "rubiks_cube", "reference": "bowl", "relation": "left"}',
        '{"target": "rubiks_cube", "reference": "bowl", "relation": "left_of"} done',
        '[{"target": "rubiks_cube", "reference": "bowl", "relation": "left_of"}]',
        "not json",
    ]
    for raw in bad:
        assert not P.parse_b(raw, OBJ, REL)["valid"], raw
    assert P.parse_b(bad[0], OBJ, REL)["reason"] == "duplicate_key"
