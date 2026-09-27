"""Lossless executed-stream recording (libx264rgb qp0 via ffmpeg pipe) with per-frame raw hashes."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np

FFMPEG = "/data/users/ali/vla_wam/envs/robolab-v2-isaac50/lib/python3.11/site-packages/imageio_ffmpeg/binaries/ffmpeg-linux-x86_64-v7.0.2"
FPS = 15


class LosslessStream:
    def __init__(self, path: Path, height: int, width: int, fps: int = FPS) -> None:
        self.path, self.shape = Path(path), (height, width, 3)
        self.hashes: list[str] = []
        self.proc = subprocess.Popen(
            [FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
             "-s", f"{width}x{height}", "-r", str(fps), "-i", "-", "-c:v", "libx264rgb", "-qp", "0",
             "-preset", "ultrafast", str(self.path)], stdin=subprocess.PIPE, stderr=subprocess.PIPE)

    def write(self, frame: np.ndarray) -> None:
        frame = np.ascontiguousarray(frame, dtype=np.uint8)
        if frame.shape != self.shape:
            raise ValueError(f"{self.path.name}: frame {frame.shape} != {self.shape}")
        self.hashes.append(hashlib.sha256(frame.tobytes()).hexdigest())
        self.proc.stdin.write(frame.tobytes())

    def close(self) -> dict:
        self.proc.stdin.close()
        err = self.proc.stderr.read().decode(errors="replace")
        code = self.proc.wait()
        if code != 0:
            raise RuntimeError(f"ffmpeg failed for {self.path}: {err[-500:]}")
        return {"uri": str(self.path), "codec": "libx264rgb qp0 (lossless rgb24)", "fps": FPS,
                "frames": len(self.hashes), "height": self.shape[0], "width": self.shape[1],
                "frame_sha256": self.hashes, "bytes": self.path.stat().st_size}


def decode_frames(path: Path, height: int, width: int) -> np.ndarray:
    raw = subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-i", str(path), "-f", "rawvideo",
                          "-pix_fmt", "rgb24", "-"], check=True, capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.uint8).reshape(-1, height, width, 3)


def verify_stream(receipt: dict) -> bool:
    frames = decode_frames(Path(receipt["uri"]), receipt["height"], receipt["width"])
    if len(frames) != receipt["frames"]:
        return False
    return all(hashlib.sha256(f.tobytes()).hexdigest() == h for f, h in zip(frames, receipt["frame_sha256"]))


def write_json_atomic(path: Path, value: dict) -> None:
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True, default=str))
    tmp.replace(path)
