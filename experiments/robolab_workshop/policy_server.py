"""Serialized model-native policy server for N3/E3/F3 (stdlib HTTP transport).

One process = one model = one lane. Requests are handled strictly one at a time.
Each /infer returns the raw returned action chunk and writes the same-sample
future (when the released interface exposes one) directly to the shared volume.
No retries happen here or in the client.

POST /reset  JSON {"seed": int, "episode_id": str, "attempt_id": str}
POST /infer  NPZ  {image uint8 (540,640,3), joint_position (7,), gripper_position (1,), header (json bytes)}
GET  /info   JSON runtime receipt
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import socket
import subprocess
import sys
import threading
import time
import traceback
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import numpy as np

SEED = 6100


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def array_sha256(array: np.ndarray) -> str:
    array = np.ascontiguousarray(array)
    return sha256_bytes(f"{array.dtype.str}{array.shape}".encode() + array.tobytes())


def input_sha256(image: np.ndarray, joints: np.ndarray, gripper: np.ndarray) -> str:
    return sha256_bytes(b"".join(array_sha256(np.asarray(a)).encode() for a in (image, joints, gripper)))


def git_head(path: str) -> str | None:
    try:
        return subprocess.check_output(["git", "-C", path, "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return None


def git_dirty(path: str) -> list[str] | None:
    try:
        out = subprocess.check_output(["git", "-C", path, "status", "--porcelain", "--untracked-files=no"], text=True,
                                      stderr=subprocess.DEVNULL)
        return [line for line in out.splitlines() if line.strip()]
    except Exception:
        return None


def write_future(path: Path, video: np.ndarray, meta: dict) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp.npz")
    with tmp.open("wb") as stream:
        np.savez_compressed(stream, video=video, meta=np.frombuffer(json.dumps(meta, sort_keys=True).encode(), dtype=np.uint8))
    os.replace(tmp, path)
    return {"uri": str(path), "sha256": sha256_bytes(path.read_bytes()), "array_sha256": array_sha256(video),
            "shape": list(video.shape), "dtype": str(video.dtype), "bytes": path.stat().st_size}


# --------------------------------------------------------------------------- backends
class CosmosBackend:
    """N3 (411d25b retained runtime) or E3 (cf5d68c) RobolabPolicyService."""

    def __init__(self, model: str, source: str, checkpoint: str, revision: str) -> None:
        import torch  # noqa: F401
        from cosmos_framework.scripts import action_policy_server_robolab as native

        self.model = model
        self.native_file = native.__file__
        common = dict(checkpoint_path=checkpoint, hf_revision=revision, host="127.0.0.1", port=0,
                      domain_name="droid_lerobot", decode_video=True, seed=SEED, deterministic_seed=True,
                      guidance=3.0, num_steps=4, shift=5.0, resolution="480", conditioning_fps=15.0,
                      action_chunk_size=32, action_dim=8, history_length=1)
        if model == "E3":
            common.update(sampler="unipc", guidance_interval=(960, 1001), image_height=540, image_width=640,
                          action_space="joint_pos", use_state=True, format_prompt_as_json=True,
                          cfg_parallel=False, allow_dcp_checkpoint=False, output_dir=None)
        args = native.RobolabServerArgs(**common)
        self.service = native.RobolabPolicyService(args)
        cfg = self.service.cfg
        self.config = {k: (list(v) if isinstance(v, tuple) else v) for k, v in vars(cfg).items()
                       if isinstance(v, (int, float, str, bool, tuple, type(None)))}
        self.config["args"] = {k: (list(v) if isinstance(v, tuple) else v) for k, v in common.items()}
        if hasattr(self.service, "setup_args"):
            self.config["sampler"] = getattr(self.service.setup_args, "sampler", None)
            try:
                self.config["setup_args"] = json.loads(self.service.setup_args.model_dump_json())
            except Exception:
                pass
        try:
            self.config["precision"] = str(getattr(self.service.model, "precision", None) or self.service.model.config.precision)
        except Exception:
            pass
        checks = {"guidance": 3.0, "num_steps": 4, "shift": 5.0, "action_chunk_size": 32, "action_dim": 8,
                  "history_length": 1, "decode_video": True, "action_space": "joint_pos", "use_state": True,
                  "image_height": 540, "image_width": 640, "domain_name": "droid_lerobot"}
        bad = {k: getattr(cfg, k, None) for k, v in checks.items() if getattr(cfg, k, None) != v}
        if bad:
            raise RuntimeError(f"{model} resolved config differs: {bad}")
        if model == "E3" and tuple(cfg.guidance_interval or ()) != (960, 1001):
            raise RuntimeError("E3 guidance interval differs")
        self._captured_prompt: list[Any] = []
        model_obj = self.service.model
        original = model_obj.generate_samples_from_batch

        def generate(data_batch, *a, **kw):
            seeds = kw.get("seed")
            self._captured_prompt.append({"ai_caption": data_batch.get("ai_caption"),
                                          "seed": int(seeds[0]) if seeds else None,
                                          "guidance_interval": kw.get("guidance_interval"),
                                          "guidance": kw.get("guidance"), "num_steps": kw.get("num_steps"),
                                          "shift": kw.get("shift")})
            return original(data_batch, *a, **kw)

        model_obj.generate_samples_from_batch = generate
        self.config["prompt_json_formatter"] = getattr(getattr(self.service, "_transform", None), "prompt_json_formatter", None) is not None

    def reset(self, seed: int) -> dict:
        self.service.cfg = replace(self.service.cfg, seed=int(seed), deterministic_seed=True)
        self.service._rng = np.random.default_rng(int(seed))
        if hasattr(self.service, "_control_request_id"):
            self.service._control_request_id = 0
        if getattr(self.service, "_distributed_enabled", lambda: False)():
            raise RuntimeError("expected single-rank stateless service")
        return {"stateless_history_length": self.service.cfg.history_length, "seed": int(seed)}

    def infer(self, obs: dict, seed: int) -> dict:
        self.service.cfg = replace(self.service.cfg, seed=int(seed), deterministic_seed=True)
        self._captured_prompt.clear()
        result = self.service.infer(obs)
        if len(self._captured_prompt) != 1:
            raise RuntimeError("expected exactly one native generate call")
        cap = self._captured_prompt[0]
        caption = cap["ai_caption"]
        if isinstance(caption, (list, tuple)):
            caption = caption[0]
        video = result.get("video")
        return {"action": np.asarray(result["action"], dtype=np.float32),
                "future": None if video is None else np.asarray(video),
                "future_status": "decoded" if video is not None else "not_exposed",
                "effective_prompt": caption if isinstance(caption, str) else json.dumps(caption, default=str),
                "effective_seed": cap["seed"], "sampling_calls": 1,
                "sampling_kwargs": {k: cap[k] for k in ("guidance_interval", "guidance", "num_steps", "shift")}}


class FluxBackend:
    def __init__(self, source: str, checkpoint: str, base: str, capture: bool = True) -> None:
        import torch  # noqa: F401
        from flux_action.serving import robolab as native
        from flux_action import policy as policy_module
        from flux_action.models import video_vae as vae_module
        from flux_action.models import text_encoder as text_module
        from flux_action.models import positional

        self.native, self.positional = native, positional
        policy = policy_module.FluxActionPolicy.from_pretrained(
            checkpoint, device="cpu",
            video_vae=vae_module.load_video_vae(str(Path(base) / "video_vae.safetensors"), compile_model=False),
            text_encoder=text_module.load_text_encoder(str(Path(base) / "text_encoder"), compile_model=False))
        native.prepare_serving_policy(policy, device="cuda", dtype="keep", settings=None, compile_dit=False,
                                      offload_text_encoder=False, warmup=0)
        self.service = native.RoboLabPolicy(policy, seed_base=0)
        self.capture = capture
        cfg = policy.config
        names = ("torch_dtype", "quantization", "sampler", "sampler_order", "num_inference_steps", "guidance_scale",
                 "guidance_scale_action", "sampler_shift", "fps", "camera_keys", "canvas_hw", "action_scale",
                 "action_parameterization", "gripper_flip_dims", "single_frame_encode", "chunk_size",
                 "n_action_steps", "n_obs_steps", "inference_seed", "action_modality", "camera_layout", "compile_model")
        self.config = {n: (list(getattr(cfg, n)) if isinstance(getattr(cfg, n, None), tuple) else getattr(cfg, n, None)) for n in names}
        self.config = json.loads(json.dumps(self.config, default=str))
        self.config["serving_setup"] = json.loads(json.dumps(getattr(policy, "serving_setup", None), default=str))

    def reset(self, seed: int) -> dict:
        self.service.policy.reset()
        self.service.queries = 0
        p = self.service.policy
        state = {"ctx_cache": len(p._ctx_cache), "prepared_text_cache": len(p._prepared_text_cache),
                 "action_queue": len(p._action_queue), "last_command_none": p._last_command is None}
        if state["ctx_cache"] or state["prepared_text_cache"] or state["action_queue"] or not state["last_command_none"]:
            raise RuntimeError(f"FLUX reset incomplete {state}")
        return state

    def infer(self, obs: dict, seed: int) -> dict:
        import torch

        policy = self.service.policy
        captured: list = []
        original = policy._sample_prepared

        def capture(**kwargs):
            out = original(**kwargs)
            captured.append((out["x_video"].detach().clone(), {k: kwargs["fixed"][k].detach().clone()
                                                               for k in ("x_video_ids", "x_video_cond", "x_video_cond_ids")}))
            return out

        with torch.inference_mode():
            if self.capture:
                policy._sample_prepared = capture
            try:
                result = self.service.infer(obs, seed=int(seed))
            finally:
                policy._sample_prepared = original
            action = np.asarray(result["action"], dtype=np.float32)
            out = {"action": action, "future": None, "effective_prompt": str(obs.get("prompt", "")),
                   "effective_seed": int(seed), "sampling_calls": len(captured) if self.capture else 1}
            if not self.capture:
                out["future_status"] = "capture_disabled"
                return out
            if len(captured) != 1:
                raise RuntimeError(f"FLUX exposed {len(captured)} samples")
            video, fixed = captured[0]
            cond = self.positional.scatter_ids(fixed["x_video_cond"], fixed["x_video_cond_ids"])[0]
            pred = self.positional.scatter_ids(video, fixed["x_video_ids"])[0]
            latents = torch.cat((cond.float(), pred.float()), dim=2)
            try:
                decoded = policy.video_vae.decode(latents.to(device=video.device, dtype=torch.bfloat16))
                frames = ((decoded[0].clamp(-1, 1) + 1) * 127.5).to(torch.uint8).permute(1, 2, 3, 0).cpu().numpy()
                out["future"] = frames
                out["future_status"] = "decoded"
                out["latent_shape"] = list(latents.shape)
            except Exception as error:
                out["future_status"] = "decode_error"
                out["future_error"] = f"{type(error).__name__}: {error}"
            return out


# --------------------------------------------------------------------------- server
class State:
    backend: Any = None
    model: str = ""
    receipt: dict = {}
    calls_log: Path | None = None
    lock = threading.Lock()
    served = 0
    busy_since: float | None = None


def pack_npz(arrays: dict, header: dict) -> bytes:
    buf = io.BytesIO()
    np.savez(buf, header=np.frombuffer(json.dumps(header, default=str).encode(), dtype=np.uint8), **arrays)
    return buf.getvalue()


def unpack_npz(data: bytes) -> tuple[dict, dict]:
    with np.load(io.BytesIO(data), allow_pickle=False) as npz:
        arrays = {k: npz[k] for k in npz.files if k != "header"}
        header = json.loads(npz["header"].tobytes().decode()) if "header" in npz.files else {}
    return arrays, header


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("[%s] %s\n" % (time.strftime("%H:%M:%S"), fmt % args))

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj: dict) -> None:
        self._send(code, json.dumps(obj, default=str).encode(), "application/json")

    def do_GET(self) -> None:
        if self.path == "/info":
            self._json(200, {**State.receipt, "served": State.served, "busy_since": State.busy_since})
        else:
            self._json(404, {"error": "unknown"})

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        data = self.rfile.read(length)
        try:
            with State.lock:
                State.busy_since = time.time()
                try:
                    if self.path == "/reset":
                        req = json.loads(data.decode())
                        receipt = State.backend.reset(int(req["seed"]))
                        self._json(200, {"ok": True, "reset": receipt, "episode_id": req.get("episode_id"),
                                         "attempt_id": req.get("attempt_id"), "pid": os.getpid()})
                        return
                    if self.path != "/infer":
                        self._json(404, {"error": "unknown"})
                        return
                    arrays, header = unpack_npz(data)
                    self._infer(arrays, header)
                finally:
                    State.busy_since = None
        except Exception as error:
            tb = traceback.format_exc()
            sys.stderr.write(tb)
            try:
                self._json(500, {"ok": False, "error": f"{type(error).__name__}: {error}", "traceback": tb})
            except Exception:
                pass

    def _infer(self, arrays: dict, header: dict) -> None:
        import torch

        image = np.ascontiguousarray(arrays["image"]).astype(np.uint8)
        joints = np.asarray(arrays["joint_position"], dtype=np.float64).reshape(7)
        gripper = np.asarray(arrays["gripper_position"], dtype=np.float64).reshape(1)
        if image.shape != (540, 640, 3):
            raise ValueError(f"composite shape {image.shape}")
        prompt = header["prompt"]
        if sha256_bytes(prompt.encode()) != header["prompt_sha256"]:
            raise ValueError("prompt bytes changed in transport")
        seed = int(header["seed"])
        obs = {"observation/image": image, "observation/joint_position": joints,
               "observation/gripper_position": gripper, "prompt": prompt}
        in_sha = input_sha256(image, joints, gripper)
        torch.cuda.synchronize()
        torch.cuda.reset_peak_memory_stats()
        start = time.perf_counter()
        out = State.backend.infer(obs, seed)
        torch.cuda.synchronize()
        infer_s = time.perf_counter() - start
        action = out["action"]
        if action.shape != (32, 8) or not np.isfinite(action).all():
            raise ValueError(f"invalid returned actions {action.shape}")
        meta = {"model": State.model, "episode_id": header.get("episode_id"), "request_index": header.get("request_index"),
                "attempt_id": header.get("attempt_id"), "input_sha256": in_sha, "prompt_sha256": header["prompt_sha256"],
                "effective_prompt": out.get("effective_prompt"), "effective_seed": out.get("effective_seed"),
                "sampling_calls": out.get("sampling_calls"), "sampling_kwargs": out.get("sampling_kwargs"), "infer_s": infer_s,
                "peak_cuda_mem_bytes": int(torch.cuda.max_memory_allocated()),
                "future_status": out.get("future_status"), "future_error": out.get("future_error"),
                "latent_shape": out.get("latent_shape"), "returned_action_sha256": array_sha256(action),
                "server_pid": os.getpid(), "served_index": State.served}
        future = out.get("future")
        if future is not None and header.get("future_path"):
            wstart = time.perf_counter()
            meta["future"] = write_future(Path(header["future_path"]), future,
                                          {k: meta[k] for k in ("model", "episode_id", "request_index", "input_sha256", "effective_seed")})
            meta["future_write_s"] = time.perf_counter() - wstart
        elif future is not None:
            meta["future"] = {"array_sha256": array_sha256(future), "shape": list(future.shape), "uri": None}
        State.served += 1
        if State.calls_log is not None:
            with State.calls_log.open("a") as log:
                log.write(json.dumps({"t": time.time(), **meta}, default=str) + "\n")
        self._send(200, pack_npz({"action": action}, meta), "application/octet-stream")


def heartbeat(path: Path) -> None:
    while True:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"t": time.time(), "pid": os.getpid(), "served": State.served,
                                   "busy_since": State.busy_since, "model": State.model}))
        os.replace(tmp, path)
        time.sleep(60)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, choices=("N3", "E3", "F3"))
    parser.add_argument("--port", type=int, default=8600)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--base", default=None)
    parser.add_argument("--revision", default=None)
    parser.add_argument("--flux-capture", type=int, default=1)
    args = parser.parse_args()
    args.run_dir.mkdir(parents=True, exist_ok=True)
    start = time.time()
    if args.model in ("N3", "E3"):
        backend = CosmosBackend(args.model, args.source, args.checkpoint, args.revision)
        native_file = backend.native_file
    else:
        backend = FluxBackend(args.source, args.checkpoint, args.base, capture=bool(args.flux_capture))
        native_file = backend.native.__file__
    import torch

    State.backend, State.model = backend, args.model
    State.calls_log = args.run_dir / "server_calls.jsonl"
    State.receipt = {
        "model": args.model, "host": socket.gethostname(), "ip": socket.gethostbyname(socket.gethostname()),
        "port": args.port, "pid": os.getpid(), "cold_start_s": time.time() - start,
        "source": args.source, "source_head": git_head(args.source), "source_dirty": git_dirty(args.source),
        "native_module_file": native_file, "checkpoint": args.checkpoint, "base": args.base,
        "revision": args.revision, "config": backend.config, "seed": SEED,
        "gpu": torch.cuda.get_device_name(0), "torch": torch.__version__,
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "flux_capture": bool(args.flux_capture) if args.model == "F3" else None,
        "automatic_retries": 0,
    }
    (args.run_dir / "server_receipt.json").write_text(json.dumps(State.receipt, indent=2, default=str))
    threading.Thread(target=heartbeat, args=(args.run_dir / "heartbeat.json",), daemon=True).start()
    server = HTTPServer(("0.0.0.0", args.port), Handler)
    print(f"READY {State.receipt['ip']}:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
