"""Assemble the registered confirmation starts (C01-C08) from seeded proposals and scripted receipts.

Pure Python (no simulator). Proposal order is fixed by `states.make_proposals`; a candidate is accepted only when
it is model-blind valid and every one of its physical goals has a passing scripted receipt. The first eight
accepted candidates per scene become C01..C08. A failed goal rejects the candidate for all models and forms.

usage: python -m experiments.robolab_workshop.registry {status|next|materialize} --state-root <root>
"""
from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path

from .catalog import SCENES, sha256_file

TARGET = 8
SCENE_IDS = ("S1", "S2", "S3", "S4", "S5")


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()] if path.exists() else []


def scripted_dir(state_root: Path, scene_id: str, pid: str) -> Path:
    return state_root / "_scripted" / f"_candidates__{scene_id}__{pid}"


def candidate_status(state_root: Path, scene_id: str, pid: str) -> dict:
    goals = list(SCENES[scene_id]["goals"])
    recs = [r for r in _jsonl(scripted_dir(state_root, scene_id, pid) / "scripted_attempts.jsonl")
            if r.get("judge_version", 0) >= 3]
    by_goal = {}
    for r in recs:
        by_goal.setdefault(r["goal_id"], r)  # first attempt only: unchanged candidates are never retried
    failed = [g for g in goals if g in by_goal and by_goal[g]["status"] != "pass"]
    if failed:
        return {"status": "rejected_scripted", "failed_goal": failed[0], "reason": by_goal[failed[0]].get("reason"),
                "receipts": by_goal}
    if all(g in by_goal for g in goals):
        return {"status": "accepted", "receipts": by_goal}
    return {"status": "pending", "receipts": by_goal, "missing": [g for g in goals if g not in by_goal]}


def scene_table(state_root: Path, scene_id: str) -> dict:
    props = _jsonl(state_root / "_candidates" / scene_id / "proposals.jsonl")
    rows, accepted, pending = [], [], []
    for p in props:
        row = {"proposal_id": p["proposal_id"], "index": p["index"], "valid": p["valid"], "checks": p.get("checks"),
               "error": p.get("error")}
        if not p["valid"]:
            row["status"] = "rejected_validity"
        elif len(accepted) >= TARGET:
            row["status"] = "not_needed"
        else:
            st = candidate_status(state_root, scene_id, p["proposal_id"])
            row.update(st)
            if st["status"] == "accepted":
                accepted.append(row)
            elif st["status"] == "pending":
                pending.append(row)
        rows.append(row)
    return {"scene_id": scene_id, "proposals": len(props), "rows": rows, "accepted": accepted, "pending": pending,
            "complete": len(accepted) >= TARGET and all(r["index"] > accepted[TARGET - 1]["index"] for r in pending)}


def next_candidates(state_root: Path, scene_id: str) -> list[str]:
    """Valid, unresolved candidates to check now: just enough, in proposal order, to reach eight if all pass."""
    t = scene_table(state_root, scene_id)
    need = TARGET - len(t["accepted"])
    out = []
    for r in t["rows"]:
        if need <= 0:
            break
        if r.get("status") == "pending":
            out.append(r["proposal_id"])
            need -= 1
    return out


def materialize(state_root: Path) -> dict:
    registry = {"created": time.time(), "target_per_scene": TARGET, "scenes": {}}
    cand_rows = []
    for sid in SCENE_IDS:
        t = scene_table(state_root, sid)
        slots = []
        first_pending = min((r["index"] for r in t["pending"]), default=None)
        for k, row in enumerate(t["accepted"][:TARGET]):
            if first_pending is not None and first_pending < row["index"]:
                break  # an earlier candidate is unresolved; acceptance order is not yet final
            slot = f"{sid}-C{k + 1:02d}"
            src = state_root / "_candidates" / sid / row["proposal_id"]
            dst = state_root / slot
            if not dst.exists():
                shutil.copytree(src, dst)
            receipt = json.loads((dst / "receipt.json").read_text())
            if sha256_file(dst / "state.npz") != receipt["state_sha256"]:
                raise RuntimeError(f"{slot}: state hash mismatch")
            (dst / "slot.json").write_text(json.dumps({"slot": slot, "proposal_id": row["proposal_id"]}, indent=2))
            slots.append({
                "slot": slot, "proposal_id": row["proposal_id"], "proposal_index": row["index"],
                "state_sha256": receipt["state_sha256"], "first_obs_sha256": receipt["first_obs_sha256"],
                "first_obs_array_sha256": receipt["first_obs_array_sha256"], "seed": receipt["seed"],
                "proposal": receipt["proposal"], "role_binding": receipt["role_binding"],
                "initial_native": receipt["initial_native"], "initial_study": receipt["initial_study"],
                "camera_calibration": receipt["camera_calibration"], "tcp_definition": receipt["tcp_definition"],
                "validity": receipt["validity"], "base_state_sha256": receipt["base_state_sha256"],
                "scripted_receipts": {g: {k2: v for k2, v in r.items() if k2 != "traceback"}
                                      for g, r in row["receipts"].items()},
            })
        registry["scenes"][sid] = {"accepted": len(slots), "slots": slots, "proposals_evaluated": t["proposals"],
                                   "shortfall": max(0, TARGET - len(slots)), "complete": len(slots) >= TARGET}
        for r in t["rows"]:
            cand_rows.append({"scene_id": sid, **{k: v for k, v in r.items() if k not in ("receipts",)},
                              "scripted": {g: {"status": x["status"], "reason": x.get("reason")}
                                           for g, x in (r.get("receipts") or {}).items()}})
    tokens = sorted(p.name for p in (state_root / "_budget" / "scripted").glob("[0-9]*")) \
        if (state_root / "_budget" / "scripted").exists() else []
    registry["scripted_attempts_charged"] = len(tokens)
    (state_root / "accepted_states.json").write_text(json.dumps(registry, indent=2, sort_keys=True, default=str))
    with (state_root / "state_candidates.jsonl").open("w") as f:
        for r in cand_rows:
            f.write(json.dumps(r, sort_keys=True, default=str) + "\n")
    return registry


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=("status", "next", "materialize"))
    ap.add_argument("--state-root", type=Path, required=True)
    ap.add_argument("--scene", default=None)
    args = ap.parse_args()
    scenes = [args.scene] if args.scene else list(SCENE_IDS)
    if args.mode == "status":
        for sid in scenes:
            t = scene_table(args.state_root, sid)
            counts = {}
            for r in t["rows"]:
                counts[r.get("status", "?")] = counts.get(r.get("status", "?"), 0) + 1
            print(sid, json.dumps(counts), "accepted:", [r["proposal_id"] for r in t["accepted"]])
    elif args.mode == "next":
        for sid in scenes:
            print(sid, " ".join(next_candidates(args.state_root, sid)))
    else:
        reg = materialize(args.state_root)
        print(json.dumps({s: {k: v[k] for k in ("accepted", "shortfall")} for s, v in reg["scenes"].items()}),
              "charged", reg["scripted_attempts_charged"])


if __name__ == "__main__":
    main()
