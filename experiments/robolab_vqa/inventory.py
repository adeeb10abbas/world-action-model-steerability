"""Resolve and verify the saved RWS-20260926 evidence used by RQA-20261006 (runs on the cluster, CPU only).

python -m experiments.robolab_vqa.inventory --source-root /data/users/ali/rws-20260926 --output <dir>

Checks (no model outputs, no outcomes read):
  * 864 bound rows -> COMPLETE.json -> attempt dir; result.json hash and status;
  * every cell's cached request-0 observation equals its start's registered first observation (array hashes
    of wrist/left/right views; requests.jsonl r0 input_source == cached_first_observation; r00_input.npz views);
  * 64 secondary frame bindings: source attempt, scheduled horizon, tick time, lossless composite frame decoded
    and hash-matched against the per-frame stream receipt; tick records saved for gold labels.
Outputs: inventory.json, initial_ticks.json, secondary_ticks.json, secondary_camera.json
"""
from __future__ import annotations

import argparse
import gzip
import json
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from . import common as C

FFMPEG = "/data/users/ali/vla_wam/envs/robolab-v2-isaac50/lib/python3.11/site-packages/imageio_ffmpeg/binaries/ffmpeg-linux-x86_64-v7.0.2"
COMPOSITE_HW = (540, 640)


def decode_frame(path: Path, index: int, height: int, width: int, ffmpeg: str = FFMPEG) -> np.ndarray:
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-i", str(path), "-vf", f"select=eq(n\\,{index})",
           "-vsync", "0", "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    raw = subprocess.run(cmd, check=True, capture_output=True).stdout
    if len(raw) != height * width * 3:
        raise RuntimeError(f"decode {path} frame {index}: got {len(raw)} bytes")
    return np.frombuffer(raw, dtype=np.uint8).reshape(height, width, 3)


def resolve_attempt(source_root: Path, episode_id: str) -> dict:
    edir = source_root / "runs/episodes" / episode_id
    complete = edir / "COMPLETE.json"
    if not complete.exists():
        return {"episode_id": episode_id, "status": "missing_complete"}
    rec = json.loads(complete.read_text())
    adir = Path(rec["attempt_dir"])
    attempts = sorted(p.name for p in (edir / "attempts").iterdir()) if (edir / "attempts").exists() else []
    result_sha = C.sha256_file(adir / "result.json")
    return {"episode_id": episode_id, "status": "complete", "attempt_id": rec["attempt_id"], "attempt_dir": str(adir),
            "complete_sha256": C.sha256_file(complete), "result_sha256": result_sha,
            "result_sha256_matches_complete": result_sha == rec["result_sha256"], "attempts_on_disk": attempts}


def check_cell(args: tuple) -> dict:
    source_root, row, expected = args
    source_root = Path(source_root)
    out = resolve_attempt(source_root, row["episode_id"])
    if out["status"] != "complete":
        return out
    adir = Path(out["attempt_dir"])
    result = json.loads((adir / "result.json").read_text())
    init = json.loads((adir / "initial_state.json").read_text())
    with np.load(adir / "first_observation.npz") as z:
        first = {k: C.array_sha256(z[k]) for k in C.VIEW_KEYS}
    with np.load(adir / "requests/r00_input.npz") as z:
        r00 = {k: C.array_sha256(z[k]) for k in C.VIEW_KEYS}
        r00_comp = C.array_sha256(z["composite"])
    with open(adir / "requests.jsonl") as f:
        q0 = json.loads(f.readline())
    out.update({
        "result_status": result.get("status"), "state_slot": result.get("state_slot"),
        "result_identity_matches_row": all(result.get(k) == row[k] for k in ("state_slot", "goal_id", "form", "prompt_sha256")),
        "initial_state_sha256": init.get("state_sha256"), "initial_first_obs_sha256": init.get("first_obs_sha256"),
        "first_observation_views_match_state": all(first[k] == expected[k] for k in C.VIEW_KEYS),
        "r00_input_views_match_state": all(r00[k] == expected[k] for k in C.VIEW_KEYS),
        "r00_composite_array_sha256": r00_comp, "r0_input_source": q0.get("input_source"),
        "r0_composite_sha256": q0.get("composite_sha256"), "r0_prompt_sha256": q0.get("prompt_sha256"),
        "role_binding": init.get("role_binding"),
    })
    return out


def load_ticks(attempt_dir: Path) -> list[dict]:
    with gzip.open(attempt_dir / "states.jsonl.gz", "rt") as f:
        return [json.loads(line) for line in f]


def check_secondary(args: tuple) -> dict:
    source_root, sel, row = args
    source_root = Path(source_root)
    out = {"frame_id": sel["frame_id"], "source_episode_id": sel["source_episode_id"]}
    att = resolve_attempt(source_root, sel["source_episode_id"])
    out.update({k: att.get(k) for k in ("status", "attempt_id", "attempt_dir", "result_sha256", "result_sha256_matches_complete")})
    if att["status"] != "complete":
        out["binding_status"] = "unavailable_missing_completed_attempt"
        return out
    adir = Path(att["attempt_dir"])
    horizon = int(row["maximum_control_actions"])
    hashes = json.loads((adir / "stream_frame_hashes.json").read_text())["composite"]
    ticks = load_ticks(adir)
    req_time = float(sel["requested_time_s"])
    req_tick = int(sel["requested_tick"])
    # first saved synchronized observation at or after the requested time, within one control tick
    candidates = [k for k, t in enumerate(ticks) if t["t"] >= req_time - 1e-9]
    k = candidates[0] if candidates else None
    out.update({"scheduled_horizon_ticks": horizon, "n_ticks": len(ticks), "composite_frames": hashes["frames"],
                "requested_time_s": req_time, "requested_tick": req_tick})
    if k is None or ticks[k]["t"] - req_time > C.TICK_S + 1e-9 or k >= hashes["frames"]:
        out["binding_status"] = "unavailable_no_observation_within_one_tick"
        return out
    frame = decode_frame(Path(hashes["uri"]), k, *COMPOSITE_HW)
    sha = C.raw_rgb_sha256(frame)
    out.update({"observed_tick": k, "observed_time_s": float(ticks[k]["t"]), "tick_step": ticks[k]["step"],
                "observation_after_last_executed_action": k == horizon,
                "composite_uri": hashes["uri"], "composite_file_sha256": C.sha256_file(hashes["uri"]),
                "composite_frame_sha256_recorded": hashes["frame_sha256"][k], "composite_frame_sha256_decoded": sha,
                "frame_hash_verified": sha == hashes["frame_sha256"][k], "composite_codec": hashes["codec"]})
    reqs = [json.loads(l) for l in (adir / "requests.jsonl").read_text().splitlines() if l.strip()]
    prior = [q for q in reqs if q["pre_tick"] <= k]
    nearest = prior[-1] if prior else None
    out["wrist_camera_pose_source"] = ({"request_index": nearest["request_index"], "pre_tick": nearest["pre_tick"],
                                        "tick_offset": k - nearest["pre_tick"]} if nearest else None)
    out["binding_status"] = "bound" if out["frame_hash_verified"] else "unavailable_frame_hash_mismatch"
    out["_tick"] = ticks[k]
    out["_tick0"] = ticks[0]
    out["_camera"] = nearest["camera_transforms"] if nearest else None
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-root", type=Path, default=C.DEFAULT_SOURCE_ROOT)
    ap.add_argument("--spec-dir", type=Path, default=C.SPEC_DIR)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--workers", type=int, default=16)
    args = ap.parse_args()
    t0 = time.time()
    src = args.source_root
    args.output.mkdir(parents=True, exist_ok=True)
    protocol = C.load_protocol(args.spec_dir)
    selection = C.load_frame_selection(args.spec_dir)
    catalog = C.load_catalog(args.spec_dir)
    release_path = src / "release/release.json"
    release = json.loads(release_path.read_text())
    rows = [json.loads(l) for l in (src / "release/bound_confirmation_episodes.jsonl").read_text().splitlines() if l.strip()]
    pinned = {f["path"]: f["sha256"] for f in protocol["source_files"]}
    inv: dict = {"study_id": C.STUDY_ID, "created_utc": C.utc_now(), "source_root": str(src),
                 "release_json": {"path": str(release_path), "sha256": C.sha256_file(release_path),
                                  "protocol_pinned_sha256": pinned.get("artifacts/robolab_workshop_20260926/release/release.json")},
                 "bound_rows": {"path": str(src / "release/bound_confirmation_episodes.jsonl"),
                                "sha256": C.sha256_file(src / "release/bound_confirmation_episodes.jsonl"), "n": len(rows)}}
    inv["release_json"]["matches_protocol_pin"] = inv["release_json"]["sha256"] == inv["release_json"]["protocol_pinned_sha256"]
    # prompt bytes
    cat_prompts = {i["prompt_id"]: i for i in catalog["original_instructions"]}
    prompt_checks = []
    for r in rows:
        item = cat_prompts.get(r["prompt_id"])
        prompt_checks.append(bool(item) and item["prompt"] == r["prompt"] and C.sha256_text(r["prompt"]) == r["prompt_sha256"] == item["prompt_sha256"])
    inv["prompt_bytes"] = {"rows_checked": len(rows), "rows_matching_catalog_bytes_and_hash": int(sum(prompt_checks)),
                           "unique_prompts": len({r["prompt_id"] for r in rows})}
    # starts
    starts = []
    expected = {}
    for sel in selection["initial"]:
        slot = sel["physical_start_id"]
        sdir = src / "states" / slot
        rc = json.loads((sdir / "receipt.json").read_text())
        state_sha = C.sha256_file(sdir / "state.npz")
        fobs_sha = C.sha256_file(sdir / "first_obs.npz")
        with np.load(sdir / "first_obs.npz") as z:
            arr = {k: C.array_sha256(z[k]) for k in C.VIEW_KEYS}
            shapes = {k: list(z[k].shape) for k in C.VIEW_KEYS}
        expected[slot] = arr
        starts.append({"physical_start_id": slot, "scene_id": sel["scene_id"], "state_npz_sha256": state_sha,
                       "release_state_sha256": release["starts"][sel["scene_id"]]["slots"].get(slot),
                       "selection_state_sha256": sel["original_state_sha256"], "receipt_state_sha256": rc.get("state_sha256"),
                       "first_obs_npz_sha256": fobs_sha, "receipt_first_obs_sha256": rc.get("first_obs_sha256"),
                       "view_array_sha256": arr, "receipt_view_array_sha256": {k: rc["first_obs_array_sha256"].get(k) for k in C.VIEW_KEYS},
                       "view_shapes": shapes, "camera_calibration": rc.get("camera_calibration"),
                       "role_binding": rc.get("role_binding"), "receipt_sha256": C.sha256_file(sdir / "receipt.json"),
                       "tick0_source": f"states/{slot}/receipt.json:tick0"})
        (args.output / "initial_ticks").mkdir(exist_ok=True)
        C.write_json_atomic(args.output / "initial_ticks" / f"{slot}.json", rc["tick0"], indent=None)
    by_slot = {s["physical_start_id"]: s for s in starts}
    for s in starts:
        s["identity_checks"] = {
            "state_npz_matches_release": s["state_npz_sha256"] == s["release_state_sha256"] == s["selection_state_sha256"],
            "first_obs_npz_matches_receipt": s["first_obs_npz_sha256"] == s["receipt_first_obs_sha256"],
            "view_arrays_match_receipt": s["view_array_sha256"] == s["receipt_view_array_sha256"],
            "native_resolution_720x1280": all(v[:2] == [720, 1280] for v in s["view_shapes"].values())}
    # cells
    jobs = [(str(src), r, expected[r["state_slot"]]) for r in rows if r["state_slot"] in expected]
    with ProcessPoolExecutor(args.workers) as pool:
        cells = list(pool.map(check_cell, jobs, chunksize=4))
    agg: dict = {}
    for c in cells:
        slot = c.get("state_slot") or next(r["state_slot"] for r in rows if r["episode_id"] == c["episode_id"])
        a = agg.setdefault(slot, {"cells": 0, "complete": 0, "valid": 0, "first_obs_views_match": 0, "r00_views_match": 0,
                                  "r0_cached_first_observation": 0, "initial_state_sha_matches": 0, "r0_composite_sha256": set(),
                                  "role_bindings": set()})
        a["cells"] += 1
        if c["status"] != "complete":
            continue
        a["complete"] += 1
        a["valid"] += c.get("result_status") == "valid" and c.get("result_sha256_matches_complete") and c.get("result_identity_matches_row")
        a["first_obs_views_match"] += bool(c.get("first_observation_views_match_state"))
        a["r00_views_match"] += bool(c.get("r00_input_views_match_state"))
        a["r0_cached_first_observation"] += c.get("r0_input_source") == "cached_first_observation"
        a["initial_state_sha_matches"] += c.get("initial_state_sha256") == by_slot[slot]["state_npz_sha256"]
        a["r0_composite_sha256"].add(c.get("r0_composite_sha256"))
        a["role_bindings"].add(json.dumps(c.get("role_binding"), sort_keys=True))
    for slot, a in agg.items():
        by_slot[slot]["cells"] = {**{k: v for k, v in a.items() if not isinstance(v, set)},
                                  "distinct_r0_composite_sha256": sorted(x for x in a["r0_composite_sha256"] if x),
                                  "distinct_role_bindings": sorted(a["role_bindings"])}
        by_slot[slot]["primary_bank_status"] = (
            "verified_common_request0_observation" if a["cells"] == a["complete"] == a["valid"] == a["first_obs_views_match"]
            == a["r00_views_match"] == a["r0_cached_first_observation"] and len(a["r0_composite_sha256"]) == 1
            and all(by_slot[slot]["identity_checks"].values()) else "provenance_mismatch_investigate")
    inv["starts"] = starts
    inv["episodes"] = {"bound": len(rows), "complete": sum(c["status"] == "complete" for c in cells),
                       "valid": sum(c.get("result_status") == "valid" for c in cells),
                       "result_hash_matches": sum(bool(c.get("result_sha256_matches_complete")) for c in cells),
                       "multiple_attempts_on_disk": sorted(c["episode_id"] for c in cells if len(c.get("attempts_on_disk") or []) > 1)}
    C.write_jsonl(args.output / "cells.jsonl", cells)
    # secondary
    row_by_ep = {r["episode_id"]: r for r in rows}
    jobs = [(str(src), sel, row_by_ep[sel["source_episode_id"]]) for sel in selection["secondary"]]
    with ProcessPoolExecutor(min(args.workers, 16)) as pool:
        sec = list(pool.map(check_secondary, jobs))
    ticks, cams = {}, {}
    for s in sec:
        if "_tick" in s:
            ticks[s["frame_id"]] = {"tick": s.pop("_tick"), "tick0": s.pop("_tick0")}
            cams[s["frame_id"]] = s.pop("_camera")
    C.write_json_atomic(args.output / "secondary_ticks.json", ticks, indent=None)
    C.write_json_atomic(args.output / "secondary_camera.json", cams, indent=None)
    inv["secondary"] = sec
    inv["summary"] = {
        "starts_verified": sum(s.get("primary_bank_status") == "verified_common_request0_observation" for s in starts),
        "secondary_bound": sum(s.get("binding_status") == "bound" for s in sec),
        "secondary_unavailable": [s["frame_id"] for s in sec if s.get("binding_status") != "bound"],
        "elapsed_s": time.time() - t0}
    C.write_json_atomic(args.output / "inventory.json", inv)
    print(json.dumps(inv["summary"], indent=1))
    print(json.dumps({k: inv[k] for k in ("release_json", "prompt_bytes", "episodes")}, indent=1))


if __name__ == "__main__":
    sys.exit(main())
