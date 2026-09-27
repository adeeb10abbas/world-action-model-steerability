"""Freeze the confirmation release: bind planned confirmation rows to registered starts and hash every frozen input.

usage: python -m experiments.robolab_workshop.release --state-root <root> --servers <root>/dev/servers --out <root>/release

Writes release.json and bound_confirmation_episodes.jsonl once; refuses to overwrite an existing release.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from . import scoring
from .catalog import (CHUNK, CONTROL_HZ, POLICY_SEED, PROTOCOL_VERSION, ROBOLAB_COMMIT, SPEC_DIR, STATE_SEED,
                      STUDY_ID, THRESHOLDS, canonical_json, load_planned_episodes, sha256_bytes, sha256_file)

CODE_DIR = Path(__file__).resolve().parent
FROZEN_SPEC = ("prompt_matrix.json", "planned_blocks.json", "planned_episodes.jsonl", "MODEL_CONFIGS.json",
               "study_manifest.json", "CLUSTER_EXECUTION_SPEC.md", "EXPERIMENT_SPEC.md")


def model_receipts(servers: Path) -> dict:
    out: dict[str, dict] = {}
    for d in sorted(servers.iterdir()):
        rec = d / "server_receipt.json"
        if d.name.startswith("_") or not rec.exists():
            continue
        r = json.loads(rec.read_text())
        key = {k: r.get(k) for k in ("model", "source_head", "source_dirty", "checkpoint", "base", "revision")}
        k = sha256_bytes(canonical_json(key))
        out.setdefault(r["model"], {}).setdefault(k, {"identity": key, "config_sha256":
                                                      sha256_bytes(canonical_json(r.get("config"))), "lanes": []})
        cfg = sha256_bytes(canonical_json(r.get("config")))
        if cfg != out[r["model"]][k]["config_sha256"]:
            raise RuntimeError(f"{d.name}: config differs from other {r['model']} lanes")
        out[r["model"]][k]["lanes"].append({"server": d.name, "host": r.get("host"), "port": r.get("port"),
                                           "receipt_sha256": sha256_file(rec)})
    for m, ids in out.items():
        if len(ids) != 1:
            raise RuntimeError(f"{m}: servers disagree on model identity: {list(ids)}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-root", type=Path, required=True)
    ap.add_argument("--servers", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    rel = args.out / "release.json"
    if rel.exists():
        raise SystemExit(f"release already frozen: {rel}")
    reg_path = args.state_root / "accepted_states.json"
    reg = json.loads(reg_path.read_text())
    slots = {s["slot"]: s for sc in reg["scenes"].values() for s in sc["slots"]}
    for slot, s in slots.items():
        got = json.loads((args.state_root / slot / "receipt.json").read_text())["state_sha256"]
        if got != s["state_sha256"] or sha256_file(args.state_root / slot / "state.npz") != got:
            raise RuntimeError(f"{slot}: registered state hash mismatch")
    bound, omitted = [], []
    for r in load_planned_episodes():
        if r["phase"] != "confirmation":
            continue
        s = slots.get(r["state_slot"])
        if s is None:
            omitted.append(r["episode_id"])
            continue
        bound.append({**r, "physical_state_bound": True, "state_snapshot_sha256": s["state_sha256"],
                      "first_observation_sha256": s["first_obs_sha256"], "proposal_id": s["proposal_id"]})
    args.out.mkdir(parents=True, exist_ok=True)
    rows_path = args.out / "bound_confirmation_episodes.jsonl"
    rows_path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in bound))
    code = {p.name: sha256_file(p) for p in sorted(CODE_DIR.rglob("*"))
            if p.is_file() and p.suffix in (".py", ".sh", ".json") and "__pycache__" not in p.parts}
    release = {
        "study_id": STUDY_ID, "protocol_version": PROTOCOL_VERSION, "created_unix": time.time(),
        "robolab_commit": ROBOLAB_COMMIT, "control_hz": CONTROL_HZ, "chunk": CHUNK, "policy_seed": POLICY_SEED,
        "state_seed": STATE_SEED,
        "code_sha256": code, "spec_sha256": {n: sha256_file(SPEC_DIR / n) for n in FROZEN_SPEC},
        "accepted_states_sha256": sha256_file(reg_path),
        "state_candidates_sha256": sha256_file(args.state_root / "state_candidates.jsonl"),
        "amendments": {"path": "docs/robolab-workshop-20260926/EXECUTION_RECORD.md",
                       "sha256": sha256_file(SPEC_DIR / "EXECUTION_RECORD.md"), "pre_confirmation": ["A1-A9"]},
        "starts": {sid: {"accepted": sc["accepted"], "shortfall": sc["shortfall"],
                         "slots": {s["slot"]: s["state_sha256"] for s in sc["slots"]}}
                   for sid, sc in reg["scenes"].items()},
        "scorer": {"version": scoring.SCORER_VERSION, "speed_definition": scoring.SPEED_DEFINITION,
                   "thresholds": THRESHOLDS, "source_sha256": sha256_file(CODE_DIR / "scoring.py")},
        "annotation_rubric_sha256": sha256_file(CODE_DIR / "annotation_rubric.json"),
        "feature_schema_sha256": sha256_file(CODE_DIR / "feature_schema.json"),
        "model_receipts": model_receipts(args.servers),
        "bound_rows": {"path": rows_path.name, "sha256": sha256_file(rows_path), "episodes": len(bound),
                       "omitted_for_start_shortfall": len(omitted), "omitted_reason": "no accepted start (EXECUTION_RECORD A1)",
                       "omitted_episode_ids": omitted},
    }
    rel.write_text(json.dumps(release, indent=2, sort_keys=True, default=str))
    print(json.dumps({"episodes": len(bound), "omitted": len(omitted), "release_sha256": sha256_file(rel)}))


if __name__ == "__main__":
    main()
