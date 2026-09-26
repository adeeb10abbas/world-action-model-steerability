"""Small, separate stock-scene diagnostic; not an SGW study release."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

ROBOLAB_COMMIT = "0aef241fb088ca21bb4ebd24448940ed56620d17"
COSMOS_COMMIT = "411d25b2e35bc441126f48c44a4b93e1c0564274"
CHECKPOINT = "nvidia/Cosmos3-Nano-Policy-DROID"
REVISION = "6706d7680581c255ff61e0f3bb49d90eac55c79e"
SEED = 6100
STEPS = 450
SERVER_CONFIG = {
    "seed": SEED, "deterministic_seed": True, "decode_video": True,
    "guidance": 3.0, "num_steps": 4, "shift": 5.0, "resolution": "480",
    "conditioning_fps": 15.0, "action_chunk_size": 32, "action_dim": 8,
    "action_space": "joint_pos", "history_length": 1, "use_state": True,
    "domain_name": "droid_lerobot", "image_height": 540, "image_width": 640,
}
PROMPTS = {
    "D-left": "Put the Rubik's cube to the left of the bowl.",
    "D-right": "Put the Rubik's cube to the right of the bowl.",
    "C-left": "Place the Rubik's cube so that the Rubik's cube is to the left of the bowl.",
    "C-right": "Place the Rubik's cube so that the Rubik's cube is to the right of the bowl.",
    "I-left": "Place the Rubik's cube so that the bowl is to the right of the Rubik's cube.",
    "I-right": "Place the Rubik's cube so that the bowl is to the left of the Rubik's cube.",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def dump(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def verify_revision(root: Path, expected: str) -> None:
    actual = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    if actual != expected:
        raise RuntimeError(f"Source revision differs at {root}: {actual} != {expected}")
    dirty = subprocess.check_output(["git", "-C", str(root), "diff", "HEAD", "--name-only"], text=True).strip()
    if dirty:
        raise RuntimeError(f"Tracked source modifications at {root}: {dirty}")


def plan() -> dict:
    return {
        "study": "stock-nano-wording-diagnostic-20260926",
        "scope": "One stock physical scene, one environment and policy seed; six related cells, not six independent trials.",
        "scene": "rubiks_cube_banana_bowl.usda",
        "stock_base_task": "RubiksCubeLeftOfBowlTask",
        "cameras": "original WRIST_LEFT_RIGHT_HEAD",
        "environment_seed": SEED, "policy_seed": SEED,
        "termination": "450 control actions at 15 Hz; goal termination disabled",
        "cells": [{"cell_id": key, "physical_goal": key.split("-")[1], "form": key[0],
                   "prompt": prompt, "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest()}
                  for key, prompt in PROMPTS.items()],
        "server_config": SERVER_CONFIG,
        "robolab_commit": ROBOLAB_COMMIT, "cosmos_commit": COSMOS_COMMIT,
        "checkpoint": CHECKPOINT, "checkpoint_revision": REVISION,
        "forecast_scoring": "Raw same-request futures only; physical time and camera correspondence remain unqualified.",
    }
