#!/usr/bin/env python3
"""Enumerate/check planned RoboLab cells on CPU. Never imports a policy or simulator."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "docs/robolab-workshop-20260926"
MODELS = ("N3", "E3", "F3")
HORIZONS = {"S1": 30, "S2": 30, "S3": 40, "S4": 40, "S5": 20}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def rank(value: str) -> str:
    return digest(f"8300:{value}".encode())


def enumerate_plan(catalog: dict, config_bytes: bytes) -> tuple[list[dict], dict]:
    rows, blocks = [], []
    core = [s for s in catalog["scenes"] if s["status"] == "core"]
    if {s["id"] for s in core} != set(HORIZONS):
        raise ValueError("Core scenes differ from the five-scene protocol")
    for model in MODELS:
        for phase, slots in (("development", ["D00"]), ("confirmation", [f"C{i:02}" for i in range(1, 9)])):
            pairs = [(s, slot) for s in core for slot in slots]
            pairs.sort(key=lambda pair: rank(f"{phase}:{pair[0]['id']}:{pair[1]}"))
            for scene, slot in pairs:
                sid = scene["id"]
                block_id = f"{model}-{sid}-{slot}"
                goal_groups = sorted(scene["goals"], key=lambda g: rank(f"{sid}:{slot}:{g['id']}"))
                block_rows = []
                for goal in goal_groups:
                    forms = sorted(goal["prompts"], key=lambda p: rank(f"{sid}:{slot}:{p['id']}"))
                    if {p["form"] for p in forms} != {"D", "S", "I"} or len(forms) != 3:
                        raise ValueError(f"Missing or duplicated D/S/I form: {sid}-{goal['id']}")
                    for prompt in forms:
                        if digest(prompt["text"].encode()) != prompt["sha256"]:
                            raise ValueError(f"Prompt hash mismatch: {prompt['id']}")
                        if phase == "development" and model != "N3" and prompt["id"] not in ("S1-L-S", "S5-LR-I"):
                            continue
                        steps = HORIZONS[sid] * 15
                        block_rows.append({
                            "study_id": "RWS-20260926", "protocol_version": "0.2",
                            "episode_id": f"RWS-{model}-{sid}-{slot}-{goal['id']}-{prompt['form']}",
                            "phase": phase, "model_id": model, "scene_id": sid,
                            "state_slot": f"{sid}-{slot}", "physical_state_bound": False,
                            "state_snapshot_sha256": None,
                            "block_id": block_id, "order_in_block": len(block_rows),
                            "base_task": scene["base_task"], "asset": scene["asset"],
                            "goal_id": goal["id"], "goal_relation": goal["relation"],
                            "mover_catalog_role": goal["mover"], "reference_catalog_role": goal["reference"],
                            "role_binding": "bind_from_reset_geometry" if sid == "S5" else "bind_to_native_asset_identity",
                            "prompt_id": prompt["id"], "form": prompt["form"],
                            "prompt": prompt["text"], "prompt_sha256": prompt["sha256"],
                            "policy_seed": 6100, "order_seed": 8300,
                            "control_hz": 15, "horizon_s": HORIZONS[sid],
                            "maximum_control_actions": steps, "maximum_requests": (steps + 31) // 32,
                            "native_success_early_termination": False,
                            "model_configs_sha256": digest(config_bytes),
                            "status": "planned_unbound_not_executable",
                        })
                if block_rows:
                    rows.extend(block_rows)
                    blocks.append({"block_id": block_id, "phase": phase, "model_id": model,
                                   "scene_id": sid, "state_slot": f"{sid}-{slot}",
                                   "episode_ids": [r["episode_id"] for r in block_rows],
                                   "maximum_control_actions": sum(r["maximum_control_actions"] for r in block_rows),
                                   "maximum_requests": sum(r["maximum_requests"] for r in block_rows)})
    summary = {
        "study_id": "RWS-20260926", "protocol_version": "0.2",
        "status": "planned_unbound_not_executable", "launch_authorized_by_this_file": False,
        "order_algorithm": "Ascending SHA256 of UTF-8 '8300:' + phase/scene/slot key, then goal key, then prompt key; model ID excluded so paired orders match.",
        "model_configs_sha256": digest(config_bytes),
        "confirmation_episode_count": sum(r["phase"] == "confirmation" for r in rows),
        "development_episode_count": sum(r["phase"] == "development" for r in rows),
        "confirmation_block_count": sum(b["phase"] == "confirmation" for b in blocks),
        "development_block_count": sum(b["phase"] == "development" for b in blocks),
        "blocks": blocks,
    }
    validate(rows, summary, catalog)
    return rows, summary


def validate(rows: list[dict], summary: dict, catalog: dict) -> None:
    prompts = {p["id"]: p for s in catalog["scenes"] if s["status"] == "core" for g in s["goals"] for p in g["prompts"]}
    if len(prompts) != 42 or len(rows) != 1054:
        raise ValueError("Expected 42 core prompts and 1054 planned cells")
    ids = [r["episode_id"] for r in rows]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate episode ID")
    for row in rows:
        p = prompts[row["prompt_id"]]
        if row["prompt"] != p["text"] or row["prompt_sha256"] != digest(row["prompt"].encode()):
            raise ValueError(f"Changed prompt: {row['episode_id']}")
        if row["physical_state_bound"] or row["state_snapshot_sha256"] is not None:
            raise ValueError("Planning inventory must not pretend that state artifacts exist")
    counts = Counter((r["model_id"], r["phase"]) for r in rows)
    expected = {(m, "confirmation"): 336 for m in MODELS}
    expected.update({("N3", "development"): 42, ("E3", "development"): 2, ("F3", "development"): 2})
    if counts != expected:
        raise ValueError(f"Wrong model/phase counts: {counts}")
    by_id = {r["episode_id"]: r for r in rows}
    flattened = [eid for b in summary["blocks"] for eid in b["episode_ids"]]
    if Counter(flattened) != Counter(ids):
        raise ValueError("Blocks omit or duplicate episodes")
    for block in summary["blocks"]:
        members = [by_id[eid] for eid in block["episode_ids"]]
        if len({r["state_slot"] for r in members}) != 1:
            raise ValueError("A block mixes physical starting states")
        if block["phase"] == "confirmation":
            groups = Counter((r["goal_id"], r["form"]) for r in members)
            for goal in {r["goal_id"] for r in members}:
                if [groups[(goal, f)] for f in ("D", "S", "I")] != [1, 1, 1]:
                    raise ValueError("Broken matched triplet")
    for model in MODELS:
        confirmation = [r for r in rows if r["model_id"] == model and r["phase"] == "confirmation"]
        if len({r["state_slot"] for r in confirmation}) != 40:
            raise ValueError("Wrong number of physical state slots")
        if sum(r["maximum_requests"] for r in confirmation) != 5376:
            raise ValueError("Wrong request budget")
        if sum(r["maximum_control_actions"] for r in confirmation) != 165600:
            raise ValueError("Wrong control action budget")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Check committed outputs without writing")
    args = parser.parse_args()
    catalog_bytes = (SPEC / "prompt_matrix.json").read_bytes()
    config_bytes = (SPEC / "MODEL_CONFIGS.json").read_bytes()
    rows, blocks = enumerate_plan(json.loads(catalog_bytes), config_bytes)
    blocks["prompt_matrix_sha256"] = digest(catalog_bytes)
    row_bytes = ("\n".join(json.dumps(r, separators=(",", ":"), ensure_ascii=False) for r in rows) + "\n").encode()
    blocks["planned_episodes_sha256"] = digest(row_bytes)
    outputs = {"planned_episodes.jsonl": row_bytes,
               "planned_blocks.json": (json.dumps(blocks, indent=2) + "\n").encode()}
    for name, data in outputs.items():
        path = SPEC / name
        if args.check:
            if not path.exists() or path.read_bytes() != data:
                raise SystemExit(f"FAIL: generated plan differs: {path}")
        else:
            path.write_bytes(data)
    print(json.dumps({"status": "checked" if args.check else "written", "confirmation": 1008,
                      "development": 46, "confirmation_blocks": 120, "development_blocks": 9,
                      "physical_state_slots": 40, "executed_episodes": 0,
                      "launch_ready": False, "planned_episodes_sha256": digest(row_bytes)}, indent=2))


if __name__ == "__main__":
    main()
