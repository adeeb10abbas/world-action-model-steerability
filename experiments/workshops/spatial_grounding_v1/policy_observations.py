"""Camera/proprioception-only boundary shared by the two native policy clients."""

from __future__ import annotations

from functools import lru_cache
import hashlib
import os
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from .adapters import AdapterError


CAMERAS = ("wrist_cam", "over_shoulder_left_camera", "over_shoulder_right_camera")
RAW_INPUT_REVISION = "native-raw-three-view-v1"
OFFICIAL_INPUT_REVISION = "robolab-cosmos-client-pad-360x640-v1"
OFFICIAL_IMAGE_TOOLS_SHA256 = "d48b4bd7f44e79fe6db8a8e07c9161144fa250be686e1245014a8b47e6171977"


def policy_input_identity() -> dict[str, Any]:
    revision = os.environ.get("SGW01_POLICY_INPUT_REVISION", RAW_INPUT_REVISION)
    if revision == RAW_INPUT_REVISION:
        return {"revision": revision}
    if revision != OFFICIAL_INPUT_REVISION:
        raise AdapterError(f"Unregistered policy input revision: {revision}")
    return {
        "revision": revision, "height": 360, "width": 640,
        "helper_sha256": OFFICIAL_IMAGE_TOOLS_SHA256,
        "helper": "openpi_client.image_tools.resize_with_pad",
        "interpolation": "PIL bilinear", "server_composition_changed": False,
    }


@lru_cache(maxsize=1)
def _official_image_tools():
    try:
        from openpi_client import image_tools
    except ImportError as error:
        raise AdapterError("Official input revision requires pinned external openpi_client") from error
    path = Path(image_tools.__file__)
    if hashlib.sha256(path.read_bytes()).hexdigest() != OFFICIAL_IMAGE_TOOLS_SHA256:
        raise AdapterError("Official per-view resize helper differs from the registered source")
    return image_tools


def native_policy_observation(value: Mapping[str, Any]) -> dict[str, dict[str, np.ndarray]]:
    result: dict[str, dict[str, np.ndarray]] = {"image_obs": {}, "proprio_obs": {}}
    for group, names in (("image_obs", CAMERAS), ("proprio_obs", ("arm_joint_pos", "gripper_pos"))):
        fields = value.get(group)
        if not isinstance(fields, Mapping):
            raise AdapterError(f"native observation lacks {group}")
        for name in names:
            array = fields.get(name)
            if hasattr(array, "detach"):
                array = array.detach().cpu().numpy()
            array = np.asarray(array)
            if group == "image_obs":
                if (array.dtype != np.uint8 or array.ndim != 4 or array.shape[0] != 1
                        or array.shape[-1] != 3 or not np.ptp(array)):
                    raise AdapterError(f"{name} must be a nonblank one-environment uint8 RGB batch")
            elif (array.shape != (1, 7 if name == "arm_joint_pos" else 1)
                  or not np.issubdtype(array.dtype, np.floating) or not np.isfinite(array).all()):
                raise AdapterError(f"{name} has invalid native proprioception shape or values")
            result[group][name] = array.copy()
    return result


def nano_observation(value: Mapping[str, Any]) -> dict[str, Any]:
    """Apply the registered client packing; keep service composition unchanged."""
    native = native_policy_observation(value)
    cameras, proprio = native["image_obs"], native["proprio_obs"]
    identity = policy_input_identity()
    if identity["revision"] == OFFICIAL_INPUT_REVISION:
        tools = _official_image_tools()
        cameras = {name: tools.resize_with_pad(image, 360, 640)
                   for name, image in cameras.items()}
    return {
        "observation/wrist_image_left": cameras["wrist_cam"][0],
        "observation/exterior_image_1_left": cameras["over_shoulder_left_camera"][0],
        "observation/exterior_image_2_left": cameras["over_shoulder_right_camera"][0],
        "observation/joint_position": proprio["arm_joint_pos"][0],
        "observation/gripper_position": proprio["gripper_pos"][0],
    }


def dreamzero_observation(value: Mapping[str, Any]) -> Mapping[str, Any]:
    """Restore transported arrays to tensors before the unmodified official extractor."""
    native = native_policy_observation(value)
    import torch

    return {
        group: {name: torch.from_numpy(array) for name, array in fields.items()}
        for group, fields in native.items()
    }
