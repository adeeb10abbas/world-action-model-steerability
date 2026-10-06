import math

from experiments.robolab_vqa import common as C
from experiments.robolab_vqa import labels as L
from experiments.robolab_vqa import prompts as P


def tick(objects, contacts=None, study=None):
    return {"objects": objects, "contacts": contacts or {}, "study": study or {}}


def obj(x, y, z=0.05, half=0.03):
    return {"pos": [x, y, z], "robot_frame": [x, y, z], "centroid": [x, y, z],
            "bbox_min": [x - half, y - half, z - half], "bbox_max": [x + half, y + half, z + half]}


def test_cone_relation_robot_frame_signs_and_boundary_flags():
    t = tick({"rubiks_cube": obj(0.40, 0.10), "bowl": obj(0.40, 0.0)})
    assert L.cone_geometry(t, "rubiks_cube", "bowl", "left_of")["value"]          # +y is the robot's left
    assert not L.cone_geometry(t, "rubiks_cube", "bowl", "right_of")["value"]
    t = tick({"rubiks_cube": obj(0.30, 0.0), "bowl": obj(0.45, 0.0)})
    assert L.cone_geometry(t, "rubiks_cube", "bowl", "in_front_of")["value"]      # closer to the robot (-x)
    angle = math.radians(43.0)
    t = tick({"rubiks_cube": obj(0.40 + 0.1 * math.sin(angle), 0.1 * math.cos(angle)), "bowl": obj(0.40, 0.0)})
    g = L.cone_geometry(t, "rubiks_cube", "bowl", "left_of")
    assert g["value"] and g["near_boundary"] and not g["centers_within_1cm"]
    t = tick({"rubiks_cube": obj(0.405, 0.004), "bowl": obj(0.40, 0.0)})
    assert L.cone_geometry(t, "rubiks_cube", "bowl", "left_of")["centers_within_1cm"]


def test_support_force_sign_and_footprint():
    t = tick({"bowl_2": obj(0.4, 0.0, 0.08), "bowl_1": obj(0.4, 0.0, 0.03, half=0.08)},
             contacts={"bowl_1__bowl_2": {"in_contact": True, "net_force": [0.0, 0.0, -2.0]}})
    # force on bowl_1 from bowl_2 points down, so bowl_2 is pushed up by bowl_1: bowl_2 supported on bowl_1
    assert L.supported_on_surface(t, "bowl_2", "bowl_1") is True
    assert L.supported_on_surface(t, "bowl_1", "bowl_2") is False
    assert L.centroid_in_footprint(t, "bowl_2", "bowl_1")


def test_table_support_requirement_only_when_stated():
    assert L.requires_table_support("Place the butter box on the table to the left of the raisin box.")
    assert not L.requires_table_support("Put the rubiks cube to the left of the bowl")


def test_wrappers_preserve_exact_instruction_bytes_and_order():
    instr = "Place the mustard on the raisin box. "
    segs = P.build_segments(test="C", instruction=instr, current={v: f"img-{v}" for v in C.VIEW_KEYS})
    text = P.full_prompt_text(segs)
    assert "Instruction:\n" + instr + "\n\n" in text
    assert [s["view"] for s in segs if s["type"] == "image"] == list(C.VIEW_KEYS)
    b = P.build_segments(test="B", instruction=instr, objects=["raisin_box", "mustard_bottle"])
    assert "Object vocabulary: mustard_bottle, raisin_box" in P.full_prompt_text(b)
    assert all(s["type"] == "text" for s in b)


def test_query_ceilings_reconcile_with_catalog():
    cat = C.load_catalog()
    goals = C.goals_by_scene(cat)
    instr = C.instructions_by_scene(cat)
    starts = 8
    a_initial = sum(2 * len(goals[s]) * starts for s in C.SCENES)
    b_image = sum(len(instr[s]) * starts for s in C.SCENES)
    placement = len(cat["placement_controls"])
    primary = a_initial + 36 + b_image + b_image + placement + 2 * placement * starts + 36
    secondary = 2 * a_initial + 2 * b_image
    assert (a_initial, b_image, primary, secondary, primary + secondary) == (192, 288, 1112, 960, 2072)
