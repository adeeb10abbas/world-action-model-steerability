"""Shared constants and helpers for RQA-20261006 (pure Python + numpy)."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC_DIR = REPO_ROOT / "docs/robolab-vqa-20261006"
REPORT_DIR = REPO_ROOT / "reports/robolab-vqa-20261006"

STUDY_ID = "RQA-20261006"
PROTOCOL_VERSION = "1.0"
IMPLEMENTATION_VERSION = "rqa-impl-1"
ORDER_SEED = 6106
BOOTSTRAP_REPLICATES = 10_000
BOOTSTRAP_SEED = 6106
CONTROL_HZ = 15
TICK_S = 1.0 / CONTROL_HZ

SCENES = ("S1", "S3", "S4", "S5")
MAIN_POOL_SCENES = ("S1", "S3", "S4")
HORIZON_S = {"S1": 30, "S3": 40, "S4": 40, "S5": 20}
HORIZON_TICKS = {s: HORIZON_S[s] * CONTROL_HZ for s in SCENES}
LEGACY_FORM_MAP = {"D": "DIR", "S": "TF", "I": "RF"}
DISPLAY_TO_LEGACY = {v: k for k, v in LEGACY_FORM_MAP.items()}
MODELS = ("N3", "E3", "F3")

# Native camera order used by every policy input (wrist on top, then left, right exterior).
VIEW_KEYS = ("wrist_cam", "over_shoulder_left_camera", "over_shoulder_right_camera")
VIEW_SHORT = {"wrist_cam": "wrist", "over_shoulder_left_camera": "left", "over_shoulder_right_camera": "right"}
# Composite policy input (540x640): wrist 360x640 on top, then left | right at 180x320 each.
COMPOSITE_SLICES = {
    "wrist_cam": (slice(0, 360), slice(0, 640)),
    "over_shoulder_left_camera": (slice(360, 540), slice(0, 320)),
    "over_shoulder_right_camera": (slice(360, 540), slice(320, 640)),
}

RELATION_VOCABULARY = ("left_of", "right_of", "in_front_of", "behind", "on_top_supported", "stacked_on", "unknown")
YES_NO_UNKNOWN = ("yes", "no", "unknown")

DEFAULT_SOURCE_ROOT = Path("/data/users/ali/rws-20260926")
DEFAULT_WORK_ROOT = Path("/data/users/ali/rqa-20261006")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path: Path | str, block: int = 1 << 22) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(block), b""):
            digest.update(chunk)
    return digest.hexdigest()


def array_sha256(array) -> str:
    """Identical to the RWS worker/state receipts: sha256(dtype.str + shape + raw bytes)."""
    import numpy as np

    a = np.ascontiguousarray(array)
    return hashlib.sha256(f"{a.dtype.str}{a.shape}".encode() + a.tobytes()).hexdigest()


def raw_rgb_sha256(array) -> str:
    """Per-frame stream hash used by recording.LosslessStream: sha256 of raw uint8 bytes."""
    import numpy as np

    return hashlib.sha256(np.ascontiguousarray(array, dtype=np.uint8).tobytes()).hexdigest()


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return sha256_bytes(canonical_json(value))


def order_key(query_id: str) -> str:
    return sha256_text(f"{ORDER_SEED}|{query_id}")


def write_json_atomic(path: Path | str, value: Any, indent: int | None = 2) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with open(tmp, "w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=indent, sort_keys=True, ensure_ascii=False, default=str)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    tmp.replace(path)


def append_jsonl(path: Path | str, record: dict) -> None:
    """Append one JSON line and fsync (one writer per file)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, sort_keys=True, ensure_ascii=False, default=str) + "\n"
    with open(path, "a", encoding="utf-8") as stream:
        stream.write(line)
        stream.flush()
        os.fsync(stream.fileno())


def read_jsonl(path: Path | str) -> list[dict]:
    path = Path(path)
    if not path.exists():
        return []
    out = []
    with open(path, encoding="utf-8") as stream:
        for line in stream:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def write_jsonl(path: Path | str, rows: Iterable[dict]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with open(tmp, "w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, sort_keys=True, ensure_ascii=False, default=str) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    tmp.replace(path)


def load_json(path: Path | str) -> Any:
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)


def load_catalog(spec_dir: Path = SPEC_DIR) -> dict:
    return load_json(Path(spec_dir) / "question_catalog.json")


def load_frame_selection(spec_dir: Path = SPEC_DIR) -> dict:
    return load_json(Path(spec_dir) / "frame_selection.json")


def load_protocol(spec_dir: Path = SPEC_DIR) -> dict:
    return load_json(Path(spec_dir) / "protocol.json")


def goals_by_scene(catalog: dict) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {s: [] for s in SCENES}
    for goal in catalog["goals"]:
        out[goal["scene_id"]].append(goal)
    return out


def instructions_by_scene(catalog: dict) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {s: [] for s in SCENES}
    for item in catalog["original_instructions"]:
        out[item["scene"]].append(item)
    return out


def physical_start_ids(frame_selection: dict) -> list[str]:
    return [row["physical_start_id"] for row in frame_selection["initial"]]


def scene_of_start(start_id: str) -> str:
    return start_id.split("-")[0]


def utc_now() -> str:
    import datetime as _dt

    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
