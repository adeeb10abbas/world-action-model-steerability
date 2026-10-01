#!/usr/bin/env python3
"""Verify and extract the two preselected forecast examples for the forecast appendix.

Read-only on study data: no policy, simulator, or VLM call is made, and nothing under the data root other than
--out is written. Inputs are the recordings named in forecast_packet_retrieval_manifest.json. Every identity and
alignment check is recorded in verification.json; exported PNGs are unmodified pixel regions of decoded frames.

Run on the cluster in the study environment (numpy, Pillow, torch, openpi_client; ffmpeg from recording.FFMPEG):

    cd <checkout of this repository>
    /data/users/ali/vla_wam/envs/robolab-v2-isaac50/bin/python \
        paper/robolab_spatial_2026/revisions/20261001/extract_forecast_examples.py \
        --out /data/users/ali/rws-20260926/revision_media/forecast_examples_20261001 --sync-videos

The figures are then built off-cluster by build_forecast_example_figures.py from the compact subset copied to
forecast_media/ (see forecast_media_provenance.json for the exact copy commands).
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import platform
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO))

from experiments.robolab_workshop import annotation as AN  # noqa: E402
from experiments.robolab_workshop import client as CL  # noqa: E402
from experiments.robolab_workshop import policy_server as PS  # noqa: E402
from experiments.robolab_workshop import recording as REC  # noqa: E402
from experiments.robolab_workshop.worker import FPS, SEED, arr_sha, file_sha  # noqa: E402

REQUEST_INDEX = 1
SELECTED_K = (0, 8, 16, 24, 32)
COMPOSITE_HW = (540, 640)
WRIST_H, CELL_H, CELL_W = 360, 180, 320
RAW_TO_CELL = 4  # 720x1280 camera -> resize_with_pad 360x640 (exact 1/2) -> bilinear 180x320 (1/2)
CROP_W, CROP_H = 160, 90
MODEL_NAMES = {"N3": "Cosmos3 Nano", "E3": "Cosmos3 Edge", "F3": "FLUX 3 Action"}
EXTERNAL = Path("/data/users/ali/sgw-01/current-20260924a/external")
SOURCE_DIRS = {"E3": "cosmos-cf5d68c", "F3": "flux-action-e2dd1d8"}
COSMOS = "cosmos-cf5d68c/cosmos_framework"
FLUX = "flux-action-e2dd1d8/src/flux_action"
# (model, path under EXTERNAL, line, text that must occur on that line, what the line establishes)
CITATIONS = [
    ("E3", f"{COSMOS}/scripts/action_policy_server_robolab.py", 579, "if image.shape[:2] != (image_h, image_w)",
     "the 540x640 request composite is not resized (configured image 540x640)"),
    ("E3", f"{COSMOS}/scripts/action_policy_server_robolab.py", 581, "t_frames = self.cfg.action_chunk_size + 1",
     "video window = 32 actions + 1 = 33 frames"),
    ("E3", f"{COSMOS}/scripts/action_policy_server_robolab.py", 583, "video[:, 0] = torch.from_numpy(image.copy())",
     "window frame 0 is the request image (conditioning frame)"),
    ("E3", f"{COSMOS}/scripts/action_policy_server_robolab.py", 664, 'action = samples["action"][0]',
     "returned actions come from the generated sample"),
    ("E3", f"{COSMOS}/scripts/action_policy_server_robolab.py", 687, 'pred_vision_latent = samples["vision"][0]',
     "returned video decodes the vision latent of the same sample"),
    ("E3", f"{COSMOS}/scripts/action_policy_server_robolab.py", 688, "video = self.model.decode(pred_vision_latent)",
     "the whole 33-frame latent window is decoded"),
    ("E3", f"{COSMOS}/data/generator/action/utils/transforms.py", 190,
     "scaling_ratio = min(target_w / orig_w, target_h / orig_h, 1.0)", "no upscaling: content stays 540x640"),
    ("E3", f"{COSMOS}/data/generator/action/utils/transforms.py", 218, 'padding_mode="reflect"',
     "canvas is reflect-padded right/bottom"),
    ("E3", f"{COSMOS}/model/generator/omni_mot_model.py", 3382, "orig_h_latent = max(orig_h // spatial_factor, 1)",
     "latent rows cropped to floor(540/16) = 33"),
    ("E3", f"{COSMOS}/model/generator/omni_mot_model.py", 3386, ":orig_h_latent, :orig_w_latent]",
     "padding latents dropped before decoding -> 528x640 frames (composite rows 0-527)"),
    ("E3", f"{COSMOS}/model/generator/tokenizers/wan2pt2_vae_4x16x16.py", 1496, "spatial_compression_factor: int = 16",
     "16x spatial compression"),
    ("E3", f"{COSMOS}/model/generator/tokenizers/wan2pt2_vae_4x16x16.py", 2172, "return (num_latent_frames - 1) * 4 + 1",
     "9 latents decode to 33 frames"),
    ("E3", f"{COSMOS}/data/generator/action/datasets/droid_lerobot_dataset.py", 159,
     "observation_ts = [i * self._dt for i in range(0, self._chunk_length + 1)]",
     "training video frame i is the observation at i*dt"),
    ("E3", f"{COSMOS}/data/generator/action/datasets/droid_lerobot_dataset.py", 160,
     "action_ts = [i * self._dt for i in range(0, self._chunk_length)]", "training action i is issued at i*dt"),
    ("E3", f"{COSMOS}/data/generator/action/datasets/droid_lerobot_dataset.py", 363,
     "bottom = torch.cat([left, right], dim=-1)", "exterior row = [left | right]"),
    ("E3", f"{COSMOS}/data/generator/action/datasets/droid_lerobot_dataset.py", 365,
     "composite = torch.cat([wrist, bottom], dim=-2)", "wrist view above the exterior row"),
    ("F3", f"{FLUX}/serving/robolab.py", 46, "COMPOSITE_HW = (540, 640)", "serving input is the 540x640 composite"),
    ("F3", f"{FLUX}/serving/robolab.py", 120, "self.policy.predict_from_composite(", "RoboLab serving path"),
    ("F3", f"{FLUX}/policy.py", 1053, "packing.pad_composite(composite[None].to(device), cfg.canvas_hw)",
     "composite placed at the top-left of the 544x736 canvas"),
    ("F3", f"{FLUX}/policy.py", 1057, "chunk = self._sample(cond, task", "one joint video/action sample per request"),
    ("F3", f"{FLUX}/policy.py", 791, 'rich_history = cfg.inference_profile == "history"',
     "checkpoint profile 'default' is not the history profile"),
    ("F3", f"{FLUX}/policy.py", 795, "packing.latent_frames(cfg.window_frames) - 1",
     "8 predicted latents follow the conditioning latent"),
    ("F3", f"{FLUX}/policy.py", 805, "fps=cfg.video_position_fps if rich_history else cfg.fps",
     "video time ids use cfg.fps = 15"),
    ("F3", f"{FLUX}/config.py", 59, "fps: float = 15.0", "15 fps"),
    ("F3", f"{FLUX}/config.py", 287, "return self.chunk_size + (self.n_obs_steps if self.inference_profile",
     "window = 32 + 1 = 33 frames"),
    ("F3", f"{FLUX}/processing/packing.py", 55, "CANVAS_HW = (544, 736)", "canvas 544x736"),
    ("F3", f"{FLUX}/processing/packing.py", 56, "LATENT_HW = (17, 20)", "latent crop 17x20 -> 544x640 decoded frames"),
    ("F3", f"{FLUX}/processing/packing.py", 239, 'mode="reflect"', "reflect padding (bottom 4 rows, right 96 columns)"),
    ("F3", f"{FLUX}/processing/packing.py", 333, "Latent frame ``i`` sits at time ``i * 4 / fps``",
     "latent i is placed at 4i/15 s"),
    ("F3", f"{FLUX}/processing/packing.py", 376, "Action ``k`` (0-based) produces frame ``k + 1``",
     "action k produces frame k+1"),
    ("F3", f"{FLUX}/models/video_vae.py", 86, "dec_causal: bool = False",
     "non-causal decoder: frame 0 is decoded jointly with the predicted latents"),
    ("F3", f"{FLUX}/models/video_vae.py", 832, "4 * T_lat - 3", "9 latents decode to 33 frames at 32x spatial scale"),
]
REPO_MODULES = ("worker.py", "policy_server.py", "client.py", "recording.py", "annotation.py", "vlm_label.py",
                "catalog.py", "scripted.py")


def sha_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def frame_sha(a: np.ndarray) -> str:
    return sha_bytes(np.ascontiguousarray(a, dtype=np.uint8).tobytes())


def psnr(a: np.ndarray, b: np.ndarray) -> float:
    mse = float(np.mean((a.astype(np.float64) - b.astype(np.float64)) ** 2))
    return float("inf") if mse == 0 else 10 * math.log10(255.0 ** 2 / mse)


def best_shift(pred: np.ndarray, ref: np.ndarray, radius: int = 4) -> dict:
    """Integer translation of pred relative to ref minimising MSE over the overlap."""
    h, w = pred.shape[:2]
    best = None
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            p = pred[max(dy, 0):h + min(dy, 0), max(dx, 0):w + min(dx, 0)].astype(np.float64)
            r = ref[max(-dy, 0):h + min(-dy, 0), max(-dx, 0):w + min(-dx, 0)].astype(np.float64)
            mse = float(np.mean((p - r) ** 2))
            if best is None or mse < best[0]:
                best = (mse, dy, dx)
    zero = float(np.mean((pred.astype(np.float64) - ref.astype(np.float64)) ** 2))
    return {"best_dy": best[1], "best_dx": best[2], "best_mse": best[0], "zero_shift_mse": zero}


def jsonl(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def save_png(path: Path, arr: np.ndarray) -> dict:
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.ascontiguousarray(arr, dtype=np.uint8)).save(path)
    return {"path": str(path), "file_sha256": file_sha(path), "pixels_sha256": arr_sha(arr), "shape": list(arr.shape)}


def git(src: Path, *args: str) -> str | None:
    try:
        return subprocess.check_output(["git", "--no-optional-locks", "-C", str(src), *args], text=True,
                                       stderr=subprocess.DEVNULL).strip()
    except Exception:
        return None


class Checks:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def __call__(self, example: str, name: str, ok, informational: bool = False, **detail) -> bool:
        self.rows.append({"example": example, "check": name, "pass": bool(ok), "informational": informational, **detail})
        return bool(ok)


def verify_citations(external: Path, checks: Checks) -> list[dict]:
    out, trees = [], {}
    for model, rel, line, text, claim in CITATIONS:
        path = external / rel
        lines = path.read_text().splitlines()
        ok = 0 < line <= len(lines) and text in lines[line - 1]
        tree = external / rel.split("/")[0]
        inner = str(path.relative_to(tree))
        if tree not in trees:
            trees[tree] = git(tree, "rev-parse", "HEAD")
        head_blob = git(tree, "rev-parse", f"HEAD:{inner}")
        work_blob = git(tree, "hash-object", inner)
        row = {"model": model, "path": str(path), "line": line, "expected_text": text, "claim": claim,
               "line_text": lines[line - 1].strip() if 0 < line <= len(lines) else None, "line_ok": ok,
               "file_sha256": file_sha(path), "tree_head": trees[tree], "head_blob": head_blob,
               "worktree_blob": work_blob, "unmodified_at_head": head_blob is not None and head_blob == work_blob}
        if not ok:
            row["found_at"] = [i + 1 for i, x in enumerate(lines) if text in x]
        checks("sources", f"citation:{Path(rel).name}:{line}", ok and row["unmodified_at_head"],
               found_at=row.get("found_at"))
        out.append(row)
    return out


def verify_example(cand: dict, args, checks: Checks) -> dict:
    model, eid, aid = cand["model"], cand["episode_id"], cand["annotation_id"]
    root = Path(args.data_root)
    adir = Path(cand["attempt_dir"])
    c = lambda name, ok, **kw: checks(model, name, ok, **kw)  # noqa: E731
    rec: dict = {"model": model, "model_name": MODEL_NAMES[model], "episode_id": eid, "annotation_id": aid,
                 "attempt_dir": str(adir), "selection_rule": cand["selection_rule"]}

    # Episode and attempt identity.
    complete = json.loads((root / "runs" / "episodes" / eid / "COMPLETE.json").read_text())
    result_sha = file_sha(adir / "result.json")
    result = json.loads((adir / "result.json").read_text())
    intent = json.loads((adir / "intent.json").read_text())
    row = intent["row"]
    c("complete_points_to_attempt", complete["attempt_dir"] == str(adir) and complete["attempt_id"] == adir.name)
    c("complete_result_sha256", complete.get("result_sha256") == result_sha)
    c("result_identity", result["status"] == "valid" and result["episode_id"] == eid
      and result["attempt_id"] == adir.name and result["model_id"] == model)
    c("prompt_sha256", sha_bytes(row["prompt"].encode()) == row["prompt_sha256"] == result["prompt_sha256"])
    rec.update({"attempt_id": adir.name, "complete_json": str(root / "runs" / "episodes" / eid / "COMPLETE.json"),
                "result_sha256": result_sha, "instruction": row["prompt"], "prompt_sha256": row["prompt_sha256"],
                "scene_id": result["scene_id"], "state_slot": result["state_slot"], "goal_id": result["goal_id"],
                "prompt_id": result["prompt_id"], "form": result["form"], "lane": intent["lane"]})
    used = ["requests.jsonl", f"futures/r{REQUEST_INDEX:02d}.npz", f"requests/r{REQUEST_INDEX:02d}_input.npz",
            f"requests/r{REQUEST_INDEX + 1:02d}_input.npz", "actions.npz", "exec_composite.mkv", "states.jsonl.gz",
            "first_observation.npz", "intent.json", "initial_state.json"]
    rec["artifacts"] = {}
    for rel in used:
        sha = file_sha(adir / rel)
        c(f"artifact_sha256:{rel}", sha == result["artifacts"].get(rel))
        rec["artifacts"][rel] = {"path": str(adir / rel), "sha256": sha, "bytes": (adir / rel).stat().st_size}
    for rel in ("exec_head_camera.mkv", "exec_viewport.mkv"):
        rec["artifacts"][rel] = {"path": str(adir / rel), "sha256": result["artifacts"].get(rel),
                                 "bytes": (adir / rel).stat().st_size, "note": "not used; hash from result.json"}
    sfh_path = adir / "stream_frame_hashes.json"
    rec["artifacts"]["stream_frame_hashes.json"] = {"path": str(sfh_path), "sha256": file_sha(sfh_path),
                                                    "note": "not listed in result.json artifacts"}
    initial = json.loads((adir / "initial_state.json").read_text())
    rec["initial_state"] = initial

    # The request record and its neighbours.
    reqs = jsonl(adir / "requests.jsonl")
    sel = [q for q in reqs if q["request_index"] == REQUEST_INDEX]
    c("request_row_unique", len(sel) == 1)
    q = sel[0]
    prev = next(x for x in reqs if x["request_index"] == REQUEST_INDEX - 1)
    nxt = next(x for x in reqs if x["request_index"] == REQUEST_INDEX + 1)
    pre, n = int(q["pre_tick"]), int(q["n_executed"])
    win = cand["recorded_execution_window"]
    c("request_identity", q["episode_id"] == eid and q["attempt_id"] == adir.name)
    c("request_matches_manifest", pre == win["pre_tick"] == cand["request"]["pre_tick"] and n == win["n_executed"]
      and win["request_index"] == REQUEST_INDEX and abs(q["t_start"] - win["t_start"]) < 1e-12
      and abs(q["t_end"] - win["t_end"]) < 1e-12)
    c("chunk_contiguity", prev["pre_tick"] + prev["n_executed"] == pre and pre + n == nxt["pre_tick"])
    c("future_decoded", q["future_status"] == "decoded" and q["future"]["uri"] == str(adir / "futures" / f"r{REQUEST_INDEX:02d}.npz"))
    c("seed", q["seed"] == SEED and q["effective_seed"] == SEED)
    rec["request"] = {k: q[k] for k in ("request_index", "pre_tick", "n_executed", "t_start", "t_end", "input_source",
                                        "input_sha256", "composite_sha256", "returned_sha256", "postprocessed_sha256",
                                        "executed_sha256", "seed", "effective_seed", "server_served_index",
                                        "future_status", "future", "effective_prompt", "sampling_kwargs", "infer_s",
                                        "future_executed_frames")}
    rec["request"]["worker_future_frame_times"] = [q["future_frame_times"][k] for k in SELECTED_K]
    rec["neighbour_requests"] = {"previous": {k: prev[k] for k in ("request_index", "pre_tick", "n_executed")},
                                 "next": {k: nxt[k] for k in ("request_index", "pre_tick", "n_executed")}}

    # Simulator ticks: frame index = tick index, t = tick/15 s.
    with gzip.open(adir / "states.jsonl.gz", "rt") as f:
        ticks = [json.loads(x) for x in f]
    dev = max(abs(t["t"] - i / FPS) for i, t in enumerate(ticks))
    c("tick_times_are_index_over_15", dev < 1e-6, max_abs_dev_s=dev, ticks=len(ticks))
    c("tick_step_equals_index", all(t["step"] == i for i, t in enumerate(ticks)))
    c("window_times_from_ticks", abs(q["t_start"] - ticks[pre]["t"]) < 1e-12 and abs(q["t_end"] - ticks[pre + n]["t"]) < 1e-12)

    # Server call log: one served call for this (attempt, request).
    matches = []
    for p in sorted(root.glob("dev/servers/*/server_calls.jsonl")):
        with p.open() as f:
            for ln, line in enumerate(f, 1):
                if adir.name in line:
                    d = json.loads(line)
                    if d.get("attempt_id") == adir.name and d.get("request_index") == REQUEST_INDEX:
                        matches.append((p, ln, d))
    c("calls_log_unique_match", len(matches) == 1, n_matches=len(matches))
    cpath, cline, call = matches[0]
    receipt_path = cpath.parent / "server_receipt.json"
    receipt = json.loads(receipt_path.read_text())
    c("calls_input_sha256", call["input_sha256"] == q["input_sha256"])
    c("calls_returned_action_sha256", call["returned_action_sha256"] == q["returned_sha256"])
    c("calls_future", call["future"]["sha256"] == q["future"]["sha256"]
      and call["future"]["array_sha256"] == q["future"]["array_sha256"] and call["future"]["shape"] == q["future"]["shape"])
    c("calls_served_index", call["served_index"] == q["server_served_index"])
    c("calls_single_sampling_call", call.get("sampling_calls") == 1)
    c("calls_seed_and_status", call["effective_seed"] == SEED and call["future_status"] == "decoded")
    c("server_identity", receipt["model"] == model and receipt["pid"] == call["server_pid"] == intent["lane"]["server_pid"]
      and receipt["host"] == intent["lane"]["server_host"])
    c("server_source_tree", Path(receipt["source"]) == args.external / SOURCE_DIRS[model] and receipt["source_dirty"] == []
      and git(Path(receipt["source"]), "rev-parse", "HEAD") == receipt["source_head"])
    rec["server_call"] = {"calls_log": str(cpath), "line": cline, "calls_log_sha256": file_sha(cpath),
                          **{k: call.get(k) for k in ("t", "served_index", "server_pid", "input_sha256",
                                                      "returned_action_sha256", "future", "latent_shape",
                                                      "sampling_calls", "effective_seed", "future_status", "infer_s")}}
    rec["server_receipt"] = {"path": str(receipt_path), "sha256": file_sha(receipt_path),
                             **{k: receipt.get(k) for k in ("model", "host", "pid", "source", "source_head",
                                                            "source_dirty", "native_module_file", "checkpoint",
                                                            "base", "revision")}}

    # Saved future.
    fpath = adir / "futures" / f"r{REQUEST_INDEX:02d}.npz"
    c("future_file_sha256", file_sha(fpath) == q["future"]["sha256"])
    with np.load(fpath) as z:
        video = z["video"]
        meta = json.loads(z["meta"].tobytes().decode())
    c("future_array_sha256", PS.array_sha256(video) == q["future"]["array_sha256"])
    c("future_shape", list(video.shape) == q["future"]["shape"] and video.dtype == np.uint8 and video.shape[0] == n + 1
      and video.shape[2] == COMPOSITE_HW[1], shape=list(video.shape))
    c("future_meta", meta == {"model": model, "episode_id": eid, "request_index": REQUEST_INDEX,
                              "input_sha256": q["input_sha256"], "effective_seed": SEED}, meta=meta)

    # Request input: hashes, and the composite rebuilt from the three raw cameras (camera order).
    with np.load(adir / "requests" / f"r{REQUEST_INDEX:02d}_input.npz") as z:
        inp = {k: z[k] for k in z.files}
    comp = inp["composite"]
    c("input_composite_sha256", arr_sha(comp) == q["composite_sha256"])
    joints = np.asarray(inp["joint_position"], dtype=np.float64).reshape(7)
    grip = np.asarray(inp["gripper_position"], dtype=np.float64).reshape(1)
    c("input_sha256_recomputed", PS.input_sha256(comp, joints, grip) == q["input_sha256"])
    rebuilt = CL.pack_composite(inp["over_shoulder_left_camera"], inp["over_shoulder_right_camera"], inp["wrist_cam"])
    swapped = CL.pack_composite(inp["over_shoulder_right_camera"], inp["over_shoulder_left_camera"], inp["wrist_cam"])
    c("composite_rebuilt_from_raw_cameras", np.array_equal(rebuilt, comp))
    c("composite_exterior_swap_differs", not np.array_equal(swapped, comp))
    with np.load(adir / "requests" / f"r{REQUEST_INDEX + 1:02d}_input.npz") as z:
        comp_next, raw_left_next = z["composite"], z["over_shoulder_left_camera"]

    # Actions: the executed commands are the first n post-processed actions of this request.
    with np.load(adir / "actions.npz") as z:
        acts = {k: z[k] for k in z.files}
    c("returned_sha256", arr_sha(acts["returned"][REQUEST_INDEX]) == q["returned_sha256"])
    c("postprocessed_sha256", arr_sha(acts["postprocessed"][REQUEST_INDEX]) == q["postprocessed_sha256"])
    c("executed_sha256", arr_sha(acts["postprocessed"][REQUEST_INDEX][:n]) == q["executed_sha256"])
    diff = float(np.abs(acts["executed"][pre:pre + n] - acts["postprocessed"][REQUEST_INDEX][:n].astype(np.float64)).max())
    c("executed_commands_equal_chunk", diff < 1e-6, max_abs_diff=diff)

    # Executed composite stream.
    sfh = json.loads(sfh_path.read_text())["composite"]
    frames = REC.decode_frames(adir / "exec_composite.mkv", *COMPOSITE_HW)
    c("exec_frame_count", len(frames) == sfh["frames"] == len(ticks), frames=len(frames))
    c("exec_frame_hashes", [frame_sha(f) for f in frames] == sfh["frame_sha256"])
    c("exec_frame_pre_tick_equals_request_input", np.array_equal(frames[pre], comp))
    c("exec_frame_chunk_end_equals_next_request_input", np.array_equal(frames[pre + n], comp_next))
    exec_win = frames[pre:pre + n + 1].copy()
    del frames

    # Generated frame 0 versus the request input: which cell is which camera, and registration.
    hv = min(video.shape[1], COMPOSITE_HW[0])
    regions = {"wrist": (slice(0, WRIST_H), slice(0, 640)), "left": (slice(WRIST_H, hv), slice(0, CELL_W)),
               "right": (slice(WRIST_H, hv), slice(CELL_W, 640))}
    f0 = video[0]
    recon = {r: psnr(f0[s], comp[s]) for r, s in regions.items()}
    cross = {"pred_left_vs_input_right": psnr(f0[WRIST_H:hv, :CELL_W], comp[WRIST_H:hv, CELL_W:]),
             "pred_right_vs_input_left": psnr(f0[WRIST_H:hv, CELL_W:], comp[WRIST_H:hv, :CELL_W])}
    shift = best_shift(f0[WRIST_H:hv, :CELL_W], comp[WRIST_H:hv, :CELL_W])
    c("frame0_cells_match_input_cameras", recon["left"] > cross["pred_left_vs_input_right"] + 3
      and recon["right"] > cross["pred_right_vs_input_left"] + 3, psnr_same=recon, psnr_swapped=cross)
    c("frame0_left_cell_registered", shift["best_dy"] == 0 and shift["best_dx"] == 0, **shift)
    rec["frame0"] = {"psnr_db_vs_input": recon, "psnr_db_swapped_cells": cross, "left_cell_shift": shift,
                     "decoded_rows": int(video.shape[1]), "composite_rows_present": hv,
                     "exterior_cell_rows_present": hv - WRIST_H}
    if video.shape[1] > COMPOSITE_HW[0]:
        pad = video.shape[1] - COMPOSITE_HW[0]
        mirror = comp[[COMPOSITE_HW[0] - 2 - i for i in range(pad)]]
        rec["frame0"]["pad_rows"] = {"rows": [COMPOSITE_HW[0], video.shape[1] - 1],
                                     "psnr_db_vs_reflect_of_input": psnr(f0[COMPOSITE_HW[0]:], mirror)}

    # Supporting-only lag diagnostic: which executed frame each generated frame resembles most.
    lag = {}
    for name in ("wrist", "left"):
        s = regions[name]
        V = video[(slice(None),) + s].astype(np.float32)
        E = exec_win[(slice(None),) + s].astype(np.float32)
        m = np.array([[float(np.mean((V[k] - E[j]) ** 2)) for j in range(n + 1)] for k in range(n + 1)])
        best = m.argmin(axis=1)
        lag[name] = {"best_exec_offset_per_k": best.tolist(),
                     "mean_abs_best_minus_k": float(np.mean(np.abs(best - np.arange(n + 1)))),
                     "psnr_db_same_k": [psnr(video[k][s], exec_win[k][s]) for k in range(n + 1)]}
    rec["lag_diagnostic"] = {"note": "supporting only: prediction errors confound timing; not a timing proof", **lag}

    # Original annotation packet and key.
    pk = {k: Path(v) for k, v in cand["packet_paths"].items()}
    c("packet_dir_is_annotation_id", all(p.parent.name == aid for p in pk.values()))
    packet = json.loads(pk["packet.json"].read_text())
    c("packet_json", packet["annotation_id"] == aid and packet["frames"] == n + 1 and packet["fps"] == FPS, packet=packet)
    key = [k for k in jsonl(root / "annotation" / "_key" / "key.jsonl") if k.get("annotation_id") == aid]
    c("key_unique", len(key) == 1)
    key = key[0]
    c("key_identity", key["episode_id"] == eid and key["window"] == "primary" and key["request_index"] == REQUEST_INDEX
      and key["model_id"] == model and key["status"] == "packet")
    c("key_future_sha256", key["future_sha256"] == q["future"]["sha256"])
    c("key_mapped_frames", key["mapped_frames"] == q["future_executed_frames"] == list(range(n + 1)))
    pframes = REC.decode_frames(pk["forecast.mkv"], WRIST_H + AN.EXT_H, AN.W)
    c("packet_video_frame_hashes", [frame_sha(f) for f in pframes] == key["forecast_frame_sha256"])
    canon = np.stack([AN.canonical_frame(video[i]) for i in key["mapped_frames"]])
    c("packet_rederived_from_future", [frame_sha(f) for f in canon] == key["forecast_frame_sha256"])
    from PIL import Image

    sheet = np.asarray(Image.open(pk["contact_sheet.png"]).convert("RGB"))
    c("contact_sheet_rederived", np.array_equal(sheet, AN.contact_sheet(canon)))
    numbers = AN.legend_numbers(result["scene_id"], list(ticks[0]["objects"]))
    c("legend_numbers", numbers == key["legend_numbers"], numbers=numbers)
    with np.load(adir / "first_observation.npz") as z:
        fo = {cam: z[cam] for cam in AN.EXTERIOR}
    legend = AN.draw_legend(fo, ticks[0], reqs[0]["camera_transforms"], numbers)
    legend_png = np.asarray(Image.open(pk["legend.png"]).convert("RGB"))
    c("legend_rederived", legend.shape == legend_png.shape and np.array_equal(legend, legend_png),
      max_abs_diff=int(np.abs(legend.astype(int) - legend_png.astype(int)).max()) if legend.shape == legend_png.shape else None)
    vlm_idx = sorted(set(np.linspace(0, len(pframes) - 1, min(8, len(pframes))).round().astype(int).tolist()))
    rec["packet"] = {"paths": {k: str(v) for k, v in pk.items()},
                     "sha256": {k: file_sha(v) for k, v in pk.items()},
                     "bytes": {k: v.stat().st_size for k, v in pk.items()}, "packet_json": packet,
                     "key_path": str(root / "annotation" / "_key" / "key.jsonl"),
                     "key": {k: v for k, v in key.items() if k != "forecast_frame_sha256"},
                     "canonical_layout": {"wrist_rows": [0, WRIST_H - 1], "exterior_rows": [WRIST_H, WRIST_H + AN.EXT_H - 1],
                                          "exterior_resampled": video.shape[1] - WRIST_H != AN.EXT_H,
                                          "exterior_source_rows": int(video.shape[1] - WRIST_H)},
                     "contact_sheet_frames": list(range(0, n + 1, 4)),
                     "vlm_frames_shown": vlm_idx,
                     "legend_source": "first_observation.npz (tick 0) with request-0 camera transforms"}

    # Labels exactly as stored on the cluster.
    labels = {}
    for tag, name in (("a", "labels_vlm_a"), ("b", "labels_vlm_b"), ("adjudicated", "labels_vlm_adjudicated")):
        row_ = [x for x in jsonl(root / "annotation" / f"{name}.jsonl") if x["annotation_id"] == aid]
        raw = [x for x in jsonl(root / "annotation" / f"{name}_raw.jsonl") if x["annotation_id"] == aid]
        same = [x for x in raw if row_ and all(x.get(f) == row_[0].get(f) for f in AN.FIELDS)]
        c(f"label_rows_unique:{tag}", len(row_) == 1 and len(same) == 1, raw_rows_for_id=len(raw))
        labels[tag] = {"row": row_[0], "file": str(root / "annotation" / f"{name}.jsonl"),
                       "raw_file": str(root / "annotation" / f"{name}_raw.jsonl"),
                       "raw": {k: same[0].get(k) for k in ("labeler", "model", "observations", "disputed")}}
    derived = [x for x in jsonl(root / "analysis" / "forecast_labels_vlm.jsonl") if x["annotation_id"] == aid]
    c("derived_label_unique", len(derived) == 1)
    labels["derived"] = {"row": derived[0], "file": str(root / "analysis" / "forecast_labels_vlm.jsonl")}
    c("labels_match_manifest", labels["a"]["row"] == cand["independent_label_a"]
      and labels["b"]["row"] == cand["independent_label_b"] and labels["derived"]["row"] == cand["derived_label"])
    rec["labels"] = labels

    # Camera choice and crop window from simulator geometry at the request tick (no predicted pixels used).
    cams = q["camera_transforms"]
    t_req = ticks[pre]
    roles = key["roles"]
    raw_h, raw_w = inp["over_shoulder_left_camera"].shape[:2]

    def centre(o):
        return (np.array(o["bbox_min"]) + np.array(o["bbox_max"])) / 2

    cam_rule = {}
    for cam in AN.EXTERIOR:
        uv = {name: AN._project(cams[cam], centre(t_req["objects"][name])) for name in numbers}
        inside = all(uv[r] is not None and 0 <= uv[r][0] < raw_w and 0 <= uv[r][1] < raw_h
                     for r in (roles["mover"], roles["reference"]))
        sep = math.dist(uv[roles["mover"]], uv[roles["reference"]]) if inside else None
        cam_rule[cam] = {"centres_raw_px": {k: list(v) if v else None for k, v in uv.items()},
                         "mover_and_reference_in_frame": inside, "mover_reference_separation_px": sep}
    chosen = max((cam for cam in AN.EXTERIOR if cam_rule[cam]["mover_and_reference_in_frame"]),
                 key=lambda cam: cam_rule[cam]["mover_reference_separation_px"])
    corners = []
    for name in numbers:
        o = t_req["objects"][name]
        lo, hi = np.array(o["bbox_min"]), np.array(o["bbox_max"])
        for x in (lo[0], hi[0]):
            for y in (lo[1], hi[1]):
                for z_ in (lo[2], hi[2]):
                    corners.append(AN._project(cams[chosen], np.array([x, y, z_])))
    us = [p[0] for p in corners if p]
    vs = [p[1] for p in corners if p]
    box_raw = [min(us), min(vs), max(us), max(vs)]
    rec["geometry"] = {"tick": pre, "roles": roles, "legend_numbers": numbers, "camera_rule": cam_rule,
                       "chosen_camera": chosen, "objects_union_box_raw_px": box_raw,
                       "objects_union_box_cell_px": [v / RAW_TO_CELL for v in box_raw],
                       "object_positions_m": {k: t_req["objects"][k]["pos"] for k in numbers}}
    rec["_arrays"] = {"video": video, "exec_win": exec_win, "comp": comp, "raw_left": inp["over_shoulder_left_camera"],
                      "raw_left_next": raw_left_next, "cams": cams, "ticks": ticks}
    rec["camera_cell"] = {"over_shoulder_left_camera": {"rows": [WRIST_H, COMPOSITE_HW[0] - 1], "cols": [0, CELL_W - 1]},
                          "over_shoulder_right_camera": {"rows": [WRIST_H, COMPOSITE_HW[0] - 1], "cols": [CELL_W, 639]},
                          "wrist_cam": {"rows": [0, WRIST_H - 1], "cols": [0, 639]}}
    return rec


def export(rec: dict, crop: dict, out: Path, sync: bool) -> dict:
    a = rec["_arrays"]
    video, exec_win = a["video"], a["exec_win"]
    pre = rec["request"]["pre_tick"]
    cam = rec["geometry"]["chosen_camera"]
    rows, cols = rec["camera_cell"][cam]["rows"], rec["camera_cell"][cam]["cols"]
    hv = rec["frame0"]["composite_rows_present"]
    odir = out / rec["model"]
    files = {"compact": {}, "cluster_only": {}}
    for k in SELECTED_K:
        files["compact"][f"pred_cell_k{k:02d}"] = save_png(odir / f"pred_{cam}_k{k:02d}.png",
                                                            video[k][rows[0]:hv, cols[0]:cols[1] + 1])
        files["compact"][f"exec_cell_tick{pre + k:03d}"] = save_png(odir / f"exec_{cam}_tick{pre + k:03d}.png",
                                                                     exec_win[k][rows[0]:rows[1] + 1, cols[0]:cols[1] + 1])
        files["cluster_only"][f"pred_composite_k{k:02d}"] = save_png(odir / "full" / f"pred_composite_k{k:02d}.png", video[k])
        files["cluster_only"][f"exec_composite_tick{pre + k:03d}"] = save_png(
            odir / "full" / f"exec_composite_tick{pre + k:03d}.png", exec_win[k])
    files["compact"]["raw_camera_request_tick"] = save_png(odir / f"raw_{cam}_tick{pre:03d}.png", a["raw_left"])
    files["cluster_only"]["raw_camera_chunk_end"] = save_png(
        odir / "full" / f"raw_{cam}_tick{pre + rec['request']['n_executed']:03d}.png", a["raw_left_next"])
    pdir = odir / "packet"
    pdir.mkdir(parents=True, exist_ok=True)
    for name, src in rec["packet"]["paths"].items():
        if name == "forecast.mkv":
            continue
        shutil.copy2(src, pdir / name)
        files["compact"][f"packet_{name}"] = {"path": str(pdir / name), "file_sha256": file_sha(pdir / name)}
    if sync:
        n = rec["request"]["n_executed"]
        s = REC.LosslessStream(odir / "sync_exterior_pred_exec.mkv", CELL_H, 2 * CELL_W)
        for k in range(n + 1):
            p = np.zeros((CELL_H, CELL_W, 3), np.uint8)
            p[:hv - rows[0]] = video[k][rows[0]:hv, cols[0]:cols[1] + 1]
            s.write(np.concatenate([p, exec_win[k][rows[0]:rows[1] + 1, cols[0]:cols[1] + 1]], 1))
        r1 = s.close()
        s = REC.LosslessStream(odir / "sync_composite_pred_exec.mkv", COMPOSITE_HW[0], 2 * COMPOSITE_HW[1])
        for k in range(n + 1):
            p = np.zeros(COMPOSITE_HW + (3,), np.uint8)
            p[:hv] = video[k][:hv]
            s.write(np.concatenate([p, exec_win[k]], 1))
        r2 = s.close()
        for r in (r1, r2):
            r["frame_sha256_list_sha256"] = sha_bytes("".join(r.pop("frame_sha256")).encode())
            r["layout"] = "left: generated frame k (black where not decoded); right: executed frame at tick pre_tick+k"
        files["cluster_only"]["sync_exterior_video"], files["cluster_only"]["sync_composite_video"] = r1, r2
    crop_px = {}
    for k in SELECTED_K:
        p = video[k][rows[0]:hv, cols[0]:cols[1] + 1][crop["y0"]:crop["y0"] + CROP_H, crop["x0"]:crop["x0"] + CROP_W]
        e = exec_win[k][rows[0]:rows[1] + 1, cols[0]:cols[1] + 1][crop["y0"]:crop["y0"] + CROP_H, crop["x0"]:crop["x0"] + CROP_W]
        crop_px[k] = {"pred_crop_pixels_sha256": arr_sha(p), "exec_crop_pixels_sha256": arr_sha(e),
                      "psnr_db_pred_vs_exec": psnr(p, e)}
    rec["crop_pixels"] = crop_px
    return files


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", type=Path, default=HERE / "forecast_packet_retrieval_manifest.json")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--data-root", type=Path, default=None)
    ap.add_argument("--external", type=Path, default=EXTERNAL)
    ap.add_argument("--code-snapshot", type=Path, default=None)
    ap.add_argument("--sync-videos", action="store_true")
    args = ap.parse_args()
    manifest = json.loads(args.manifest.read_text())
    args.data_root = args.data_root or Path(manifest["data_root"])
    args.code_snapshot = args.code_snapshot or args.data_root / "code" / "experiments" / "robolab_workshop"
    args.out.mkdir(parents=True, exist_ok=True)
    checks = Checks()
    started = time.time()

    citations = verify_citations(args.external, checks)
    modules = {}
    for m in REPO_MODULES:
        a, b = file_sha(REPO / "experiments" / "robolab_workshop" / m), file_sha(args.code_snapshot / m)
        modules[m] = {"repo_sha256": a, "cluster_snapshot_sha256": b}
        checks("code", f"module_matches_cluster_snapshot:{m}", a == b, informational=True)

    recs = [verify_example(cand, args, checks) for cand in manifest["candidates"]]
    same_start = len({json.dumps(r["initial_state"].get("state_sha256")) for r in recs}) == 1 and \
        len({json.dumps(r["initial_state"].get("first_obs_sha256")) for r in recs}) == 1
    checks("pair", "examples_share_initial_state", same_start, informational=True)
    checks("pair", "same_camera_chosen", len({r["geometry"]["chosen_camera"] for r in recs}) == 1)

    # One crop window for both examples: centred on the task objects at the request tick, inside the
    # exterior-cell rows that every decoded future contains.
    common_rows = min(r["frame0"]["exterior_cell_rows_present"] for r in recs)
    crops = {}
    for r in recs:
        x_lo, y_lo, x_hi, y_hi = r["geometry"]["objects_union_box_cell_px"]
        cx, cy = (x_lo + x_hi) / 2, (y_lo + y_hi) / 2
        x0 = int(min(max(round(cx - CROP_W / 2), 0), CELL_W - CROP_W))
        y0 = int(min(max(round(cy - CROP_H / 2), 0), common_rows - CROP_H))
        crops[r["model"]] = {"x0": x0, "y0": y0, "w": CROP_W, "h": CROP_H, "centre_cell_px": [cx, cy],
                             "rule": f"{CROP_W}x{CROP_H} window of the {CELL_W}x{CELL_H} exterior cell centred on the "
                                     f"projected 3-D boxes of all legend objects at the request tick; clamped to "
                                     f"columns [0,{CELL_W}) and rows [0,{common_rows}) present in every decoded future",
                             "raw_camera_box_px": [RAW_TO_CELL * x0, RAW_TO_CELL * y0, RAW_TO_CELL * (x0 + CROP_W),
                                                   RAW_TO_CELL * (y0 + CROP_H)]}
        checks(r["model"], "crop_contains_object_box", x0 <= x_lo and y0 <= y_lo and x_hi <= x0 + CROP_W
               and y_hi <= y0 + CROP_H, informational=True)
    files = {r["model"]: export(r, crops[r["model"]], args.out, args.sync_videos) for r in recs}

    for r in recs:
        pre = r["request"]["pre_tick"]
        ticks = r["_arrays"]["ticks"]
        r["frame_mapping"] = [{"k": k, "generated_frame_index": k, "exec_frame_index": pre + k, "tick": pre + k,
                               "t_s": ticks[pre + k]["t"], "t_after_request_s": k / FPS,
                               "actions_executed_in_chunk": k,
                               "generated_frame_role": "decoded conditioning frame (reconstruction of the request input)"
                               if k == 0 else "generated prediction"} for k in SELECTED_K]
        r["crop"] = crops[r["model"]]
        r["files"] = files[r["model"]]
        del r["_arrays"]

    import PIL
    import torch

    ff = subprocess.run([REC.FFMPEG, "-version"], capture_output=True, text=True).stdout.splitlines()[0]
    hard = [x for x in checks.rows if not x["informational"]]
    verification = {
        "generated_by": str(Path(__file__).relative_to(REPO)), "argv": sys.argv,
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)),
        "finished_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "host": socket.gethostname(), "python": platform.python_version(), "numpy": np.__version__,
        "pillow": PIL.__version__, "torch": torch.__version__, "ffmpeg": ff, "ffmpeg_path": REC.FFMPEG,
        "manifest": {"path": str(args.manifest), "sha256": file_sha(args.manifest)},
        "data_root": str(args.data_root), "out": str(args.out), "request_index": REQUEST_INDEX,
        "selected_k": list(SELECTED_K), "fps": FPS,
        "all_checks_pass": all(x["pass"] for x in hard), "n_checks": len(hard),
        "failed_checks": [x for x in hard if not x["pass"]],
        "informational_checks": [x for x in checks.rows if x["informational"]],
        "checks": checks.rows, "source_citations": citations, "repo_modules_vs_cluster_snapshot": modules,
        "examples": recs,
    }
    (args.out / "verification.json").write_text(json.dumps(verification, indent=1, default=str))
    print(json.dumps({"all_checks_pass": verification["all_checks_pass"], "n_checks": len(hard),
                      "failed": [(x["example"], x["check"]) for x in verification["failed_checks"]],
                      "crops": crops, "out": str(args.out)}, indent=1, default=str))


if __name__ == "__main__":
    main()
