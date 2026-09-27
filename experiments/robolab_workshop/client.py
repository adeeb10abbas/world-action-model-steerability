"""Simulator-side policy client: exact RoboLab Cosmos3Client packing, HTTP transport, zero retries."""
from __future__ import annotations

import hashlib
import io
import json
import time
import urllib.request

import numpy as np

IMAGE_H, IMAGE_W = 360, 640
CHUNK = 32
VIEW_KEYS = ("over_shoulder_left_camera", "over_shoulder_right_camera", "wrist_cam")


def pack_composite(left_raw: np.ndarray, right_raw: np.ndarray, wrist_raw: np.ndarray) -> np.ndarray:
    """RoboLab 0aef241 Cosmos3Client._extract_observation + _pack_request, verbatim math."""
    import torch
    import torch.nn.functional as F
    from openpi_client import image_tools

    left = image_tools.resize_with_pad(left_raw, IMAGE_H, IMAGE_W)
    right = image_tools.resize_with_pad(right_raw, IMAGE_H, IMAGE_W)
    wrist = image_tools.resize_with_pad(wrist_raw, IMAGE_H, IMAGE_W)
    size = (IMAGE_H // 2, IMAGE_W // 2)

    def half(img: np.ndarray) -> np.ndarray:
        t = torch.from_numpy(img).permute(2, 0, 1).unsqueeze(0).float()
        t = F.interpolate(t, size=size, mode="bilinear")
        return t.squeeze(0).permute(1, 2, 0).numpy().astype(wrist.dtype)

    return np.concatenate((wrist, np.concatenate((half(left), half(right)), axis=1)))


def postprocess_chunk(chunk: np.ndarray) -> np.ndarray:
    """Cosmos3Client._postprocess_chunk: binarize gripper at 0.5."""
    chunk = np.asarray(chunk).copy()
    chunk[..., -1] = (chunk[..., -1] > 0.5).astype(chunk.dtype)
    return chunk


def request_from_raw(raw: dict) -> dict:
    image = pack_composite(raw["over_shoulder_left_camera"], raw["over_shoulder_right_camera"], raw["wrist_cam"])
    return {"image": image,
            "joint_position": np.asarray(raw["arm_joint_pos"], dtype=np.float64).reshape(7),
            "gripper_position": np.asarray(raw["gripper_pos"], dtype=np.float64).reshape(1)}


def _pack(arrays: dict, header: dict) -> bytes:
    buf = io.BytesIO()
    np.savez(buf, header=np.frombuffer(json.dumps(header).encode(), dtype=np.uint8), **arrays)
    return buf.getvalue()


def _unpack(data: bytes) -> tuple[dict, dict]:
    with np.load(io.BytesIO(data), allow_pickle=False) as npz:
        arrays = {k: npz[k] for k in npz.files if k != "header"}
        header = json.loads(npz["header"].tobytes().decode()) if "header" in npz.files else {}
    return arrays, header


class PolicyError(RuntimeError):
    """Transport/server error. Never retried; the attempt is quarantined as infrastructure-invalid."""


class HttpPolicy:
    def __init__(self, url: str, timeout_s: float = 900.0) -> None:
        self.url = url.rstrip("/")
        self.timeout_s = timeout_s

    def _post(self, path: str, body: bytes, ctype: str) -> bytes:
        req = urllib.request.Request(self.url + path, data=body, headers={"Content-Type": ctype}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                return resp.read()
        except urllib.error.HTTPError as error:
            raise PolicyError(f"HTTP {error.code}: {error.read()[:2000]!r}") from error
        except Exception as error:
            raise PolicyError(f"{type(error).__name__}: {error}") from error

    def info(self) -> dict:
        with urllib.request.urlopen(self.url + "/info", timeout=30) as resp:
            return json.loads(resp.read())

    def reset(self, seed: int, episode_id: str, attempt_id: str) -> dict:
        body = json.dumps({"seed": seed, "episode_id": episode_id, "attempt_id": attempt_id}).encode()
        return json.loads(self._post("/reset", body, "application/json"))

    def infer(self, request: dict, header: dict) -> tuple[np.ndarray, dict, float]:
        if hashlib.sha256(header["prompt"].encode()).hexdigest() != header["prompt_sha256"]:
            raise ValueError("prompt bytes differ from plan hash")
        start = time.perf_counter()
        data = self._post("/infer", _pack(request, header), "application/octet-stream")
        rtt = time.perf_counter() - start
        arrays, meta = _unpack(data)
        action = np.asarray(arrays["action"], dtype=np.float32)
        if action.shape != (CHUNK, 8) or not np.isfinite(action).all():
            raise PolicyError(f"bad action {action.shape}")
        return action, meta, rtt
