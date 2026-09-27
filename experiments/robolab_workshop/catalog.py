"""Frozen scene/goal bindings for RWS-20260926 (pure Python; no simulator imports).

Each goal is bound to an explicit scorer built from pinned RoboLab predicate
functions (``robolab/core/task/predicate_logic.py`` and ``world_state.py`` at
RoboLab 0aef241). Native task identities are kept separate from study goals.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SPEC_DIR = ROOT / "docs/robolab-workshop-20260926"
STUDY_ID = "RWS-20260926"
PROTOCOL_VERSION = "0.2"
ROBOLAB_COMMIT = "0aef241fb088ca21bb4ebd24448940ed56620d17"
CONTROL_HZ = 15
CHUNK = 32
POLICY_SEED = 6100
STATE_SEED = 8200
GRIPPER = "gripper"

# relation scorer kinds:
#   cone:<L|R|F|B>   native robot-frame 45 degree relation cone + table support for stable placement
#   container        native open-top containment (in_opentop_container, tolerance 0.01)
#   on_top           native support-force cone + centroid-in-footprint (object_on_top)
#   stacked          native containment + mover/reference contact (BowlStacking tasks)
SCENES: dict[str, dict[str, Any]] = {
    "S1": {
        "base_task": "RubiksCubeLeftOfBowlTask",
        "asset": "rubiks_cube_banana_bowl.usda",
        "horizon_s": 30,
        "objects": ["rubiks_cube", "banana", "bowl"],
        "support": "table",
        "movable": ["rubiks_cube", "banana", "bowl"],
        "goals": {
            "L": {"mover": "rubiks_cube", "reference": "bowl", "kind": "cone:L", "native_task": "RubiksCubeLeftOfBowlTask"},
            "R": {"mover": "rubiks_cube", "reference": "bowl", "kind": "cone:R", "native_task": None},
            "F": {"mover": "rubiks_cube", "reference": "bowl", "kind": "cone:F", "native_task": "RubiksCubeInFrontOfBowlTask"},
            "B": {"mover": "rubiks_cube", "reference": "bowl", "kind": "cone:B", "native_task": "RubiksCubeBehindBowlTask"},
        },
    },
    "S2": {
        "base_task": "MustardInLeftBinTask",
        "asset": "two_bin.usda",
        "horizon_s": 30,
        "objects": ["mustard", "grey_bin_left", "grey_bin_right"],
        "support": "table",
        "movable": ["mustard"],
        "goals": {
            "L": {"mover": "mustard", "reference": "grey_bin_left", "kind": "container", "native_task": "MustardInLeftBinTask"},
            "R": {"mover": "mustard", "reference": "grey_bin_right", "kind": "container", "native_task": "MustardInRightBinTask"},
        },
    },
    "S3": {
        "base_task": "ButterAboveRaisinTask",
        "asset": "butter_raisin_box.usda",
        "horizon_s": 40,
        "objects": ["butter", "raisin_box"],
        "support": "table",
        "movable": ["butter", "raisin_box"],
        "goals": {
            "TOP": {"mover": "butter", "reference": "raisin_box", "kind": "on_top", "native_task": "ButterAboveRaisinTask"},
            "L": {"mover": "butter", "reference": "raisin_box", "kind": "cone:L", "native_task": None},
            "R": {"mover": "butter", "reference": "raisin_box", "kind": "cone:R", "native_task": None},
        },
    },
    "S4": {
        "base_task": "MustardAboveRaisinTask",
        "asset": "mustard_raisin_box.usda",
        "horizon_s": 40,
        "objects": ["mustard_bottle", "raisin_box"],
        "support": "table",
        "movable": ["mustard_bottle", "raisin_box"],
        "goals": {
            "TOP": {"mover": "mustard_bottle", "reference": "raisin_box", "kind": "on_top", "native_task": "MustardAboveRaisinTask"},
            "L": {"mover": "mustard_bottle", "reference": "raisin_box", "kind": "cone:L", "native_task": None},
            "R": {"mover": "mustard_bottle", "reference": "raisin_box", "kind": "cone:R", "native_task": None},
        },
    },
    "S5": {
        "base_task": "BowlStackingLeftOnRightTask",
        "asset": "bowls_2_table.usda",
        "horizon_s": 20,
        "objects": ["bowl_1", "bowl_2"],
        "support": "table",
        "movable": ["bowl_1", "bowl_2"],
        # Native naming: left bowl = bowl_2, right bowl = bowl_1. Roles are
        # re-derived from reset geometry and then frozen for the episode.
        "goals": {
            "LR": {"mover": "bowl_2", "reference": "bowl_1", "kind": "stacked", "native_task": "BowlStackingLeftOnRightTask",
                   "role_rule": "mover=left_bowl_at_reset"},
            "RL": {"mover": "bowl_1", "reference": "bowl_2", "kind": "stacked", "native_task": "BowlStackingRightOnLeftTask",
                   "role_rule": "mover=right_bowl_at_reset"},
        },
    },
}

# Alternative-goal regions for the contradictory-released-placement event.
ALTERNATIVES = {
    "S1": {"L": ["R", "F", "B"], "R": ["L", "F", "B"], "F": ["L", "R", "B"], "B": ["L", "R", "F"]},
    "S2": {"L": ["R"], "R": ["L"]},
    "S3": {"TOP": ["L", "R"], "L": ["TOP", "R"], "R": ["TOP", "L"]},
    "S4": {"TOP": ["L", "R"], "L": ["TOP", "R"], "R": ["TOP", "L"]},
    "S5": {"LR": [], "RL": []},
}

THRESHOLDS = {
    "lift_m": 0.02, "lift_dwell_s": 0.2,
    "stable_speed_mps": 0.02, "stable_dwell_s": 1.0,
    "reference_disturbance_m": 0.02,
    "wrong_object_contact_s": 0.2, "wrong_object_move_m": 0.02,
    "contradictory_support_s": 0.2,
    "primary_window_tcp_distance_m": 0.10,
    "contact_force_threshold_n": 0.1,
    "cone_deg": 45,
    "container_tolerance_m": 0.01,
    "footprint_tolerance_m": 0.01,
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def load_planned_episodes(spec_dir: Path = SPEC_DIR) -> list[dict]:
    return [json.loads(line) for line in (spec_dir / "planned_episodes.jsonl").read_text().splitlines() if line.strip()]


def load_planned_blocks(spec_dir: Path = SPEC_DIR) -> dict:
    return json.loads((spec_dir / "planned_blocks.json").read_text())


def load_prompt_matrix(spec_dir: Path = SPEC_DIR) -> dict:
    return json.loads((spec_dir / "prompt_matrix.json").read_text())


def scene_catalog_receipt() -> dict:
    payload = {"scenes": SCENES, "alternatives": ALTERNATIVES, "thresholds": THRESHOLDS,
               "robolab_commit": ROBOLAB_COMMIT}
    return {**payload, "sha256": sha256_bytes(canonical_json(payload))}


def verify_prompt_bytes(rows: list[dict], matrix: dict) -> None:
    catalog = {p["id"]: p for s in matrix["scenes"] for g in s.get("goals", []) for p in g["prompts"]}
    for row in rows:
        prompt = catalog[row["prompt_id"]]
        if row["prompt"] != prompt["text"] or sha256_bytes(row["prompt"].encode()) != row["prompt_sha256"] != None:
            if sha256_bytes(row["prompt"].encode()) != prompt["sha256"]:
                raise ValueError(f"prompt bytes changed for {row['episode_id']}")
        if row["prompt"] != prompt["text"]:
            raise ValueError(f"prompt text differs for {row['episode_id']}")
