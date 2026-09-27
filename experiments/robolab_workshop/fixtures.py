"""Offline adapter fixtures: saved first observations -> one request each. Logs adapter_calls.jsonl.

Budget: at most six calls/model (N3 2, E3 2, F3 4 = S1/S5 x capture off/on).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np

from . import client as C
from .catalog import load_planned_episodes

SEED = 6100
FIXTURE_EPISODES = {"S1": "S1-L-S", "S5": "S5-LR-I"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--url", required=True)
    ap.add_argument("--tag", default="")
    ap.add_argument("--first-obs-dir", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--scenes", default="S1,S5")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    policy = C.HttpPolicy(args.url)
    info = policy.info()
    log = args.out / "adapter_calls.jsonl"
    for scene in args.scenes.split(","):
        raw = dict(np.load(args.first_obs_dir / f"{scene}-first.npz"))
        req = C.request_from_raw(raw)
        prompt = fixture_prompt(args.model, scene)
        header = {"prompt": prompt, "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(), "seed": SEED,
                  "episode_id": f"fixture-{args.model}{args.tag}-{scene}", "request_index": 0,
                  "attempt_id": f"fixture-{args.model}{args.tag}-{scene}-{int(time.time())}",
                  "future_path": str(args.out / f"{args.model}{args.tag}-{scene}-future.npz")}
        rec = {"t": time.time(), "model": args.model, "tag": args.tag, "scene": scene, "url": args.url,
               "server_pid": info.get("pid"), "composite_sha256": C_sha(req["image"]), "header": header}
        try:
            reset = policy.reset(SEED, header["episode_id"], header["attempt_id"])
            action, meta, rtt = policy.infer(req, header)
            np.savez(args.out / f"{args.model}{args.tag}-{scene}-io.npz", composite=req["image"],
                     joint_position=req["joint_position"], gripper_position=req["gripper_position"],
                     returned=action, postprocessed=C.postprocess_chunk(action))
            rec.update(ok=True, reset=reset, meta=meta, rtt_s=rtt, returned_sha256=C_sha(action),
                       request_bytes=int(req["image"].nbytes), action_first=action[0].tolist())
        except Exception as error:
            rec.update(ok=False, error=f"{type(error).__name__}: {error}")
        with log.open("a") as f:
            f.write(json.dumps(rec, default=str) + "\n")
        print(json.dumps({k: rec.get(k) for k in ("model", "tag", "scene", "ok", "rtt_s", "error")}), flush=True)


def C_sha(a: np.ndarray) -> str:
    a = np.ascontiguousarray(a)
    return hashlib.sha256(f"{a.dtype.str}{a.shape}".encode() + a.tobytes()).hexdigest()


def fixture_prompt(model: str, scene: str) -> str:
    """Prompt of the model's development cell for this scene's integration goal (S1-L-S / S5-LR-I)."""
    target = FIXTURE_EPISODES[scene]
    for row in load_planned_episodes():
        if row["phase"] == "development" and row["model_id"] == model and row["prompt_id"] == target:
            return row["prompt"]
    raise KeyError(target)


if __name__ == "__main__":
    main()
