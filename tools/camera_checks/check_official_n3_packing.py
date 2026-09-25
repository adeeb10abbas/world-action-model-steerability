"""One offline three-view packing gate; never construct a policy or client."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np

from experiments.workshops.spatial_grounding_v1.policy_observations import (
    CAMERAS, OFFICIAL_INPUT_REVISION, _official_image_tools, nano_observation,
    policy_input_identity,
)
from experiments.workshops.spatial_grounding_v1.camera_configuration import (
    camera_configuration_identity, verify_captured_camera_configuration,
)
from experiments.workshops.spatial_grounding_v1.runtime import (
    D1_ROBOLAB_CLIENT_COMMIT, _verify_git_checkout,
)

NANO_COMMIT = "411d25b2e35bc441126f48c44a4b93e1c0564274"
NANO_HELPER_SHA256 = "024a6d19048a6ac732ca0b23e741b5da6d38424223783b944bf539b2b6bd9a24"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--nano-root", type=Path, required=True)
    parser.add_argument("--robolab-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    import torch
    import torch.nn.functional as functional
    from PIL import Image

    identity = policy_input_identity()
    if identity["revision"] != OFFICIAL_INPUT_REVISION:
        raise ValueError("Packing gate requires the registered official input revision")
    _verify_git_checkout(args.nano_root, NANO_COMMIT, "Nano helpers")
    _verify_git_checkout(args.robolab_root, D1_ROBOLAB_CLIENT_COMMIT, "RoboLab client", exclude_assets=True)
    capture = json.loads((args.capture / "receipt.json").read_text())
    verify_captured_camera_configuration(capture)
    source = args.nano_root / "cosmos_framework/scripts/action_policy_server_robolab.py"
    data = source.read_bytes()
    if hashlib.sha256(data).hexdigest() != NANO_HELPER_SHA256:
        raise ValueError("Nano composition helper source differs")
    names = {"_ensure_rgb_uint8_image", "_resize_rgb_uint8", "_compose_roboarena_views",
             "_extract_observation_image"}
    nodes = [n for n in ast.parse(data).body if isinstance(n, ast.FunctionDef) and n.name in names]
    if len(nodes) != len(names):
        raise ValueError("Pinned Nano helper function set differs")
    ns = {"np": np, "torch": torch, "F": functional, "Any": Any}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), "exec"), ns)

    official_path = args.robolab_root / "policies/cosmos3/client.py"
    official = ast.parse(official_path.read_text())
    cls = next(n for n in official.body if isinstance(n, ast.ClassDef) and n.name == "Cosmos3Client")
    constants = {n.targets[0].id: ast.literal_eval(n.value) for n in cls.body
                 if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)}
    if (constants["IMAGE_H"], constants["IMAGE_W"]) != (360, 640):
        raise ValueError("Pinned official client input dimensions differ")
    methods = [n for n in cls.body if isinstance(n, ast.FunctionDef)
               and n.name in {"_extract_observation", "_pack_request"}]
    if len(methods) != 2:
        raise ValueError("Pinned official client packing methods differ")
    official_ns = {"np": np, "torch": torch, "F": functional, "image_tools": _official_image_tools()}
    exec(compile(ast.Module(body=methods, type_ignores=[]), str(official_path), "exec"), official_ns)
    client = SimpleNamespace(_image_h=360, _image_w=640)
    with np.load(args.capture / "reset-1/observation.npz", allow_pickle=False) as arrays:
        raw = {
            "image_obs": {name: arrays[name] for name in CAMERAS},
            "proprio_obs": {name: arrays[name] for name in ("arm_joint_pos", "gripper_pos")},
        }
    args.output.mkdir(parents=True, exist_ok=False)
    rows = []
    for label, observation in (("native-reset", raw), ("synthetic-corners", _corners(raw))):
        tensors = {group: {key: torch.from_numpy(value) for key, value in fields.items()}
                   for group, fields in observation.items()}
        extracted = official_ns["_extract_observation"](client, tensors)
        reference = official_ns["_pack_request"](client, extracted, "image-only packing gate")
        prepared = nano_observation(observation)
        for key, field in (
            ("observation/wrist_image_left", "wrist_image"),
            ("observation/exterior_image_1_left", "left_image"),
            ("observation/exterior_image_2_left", "right_image"),
            ("observation/joint_position", "joint_position"),
            ("observation/gripper_position", "gripper_position"),
        ):
            np.testing.assert_array_equal(prepared[key], extracted[field])
        wire = json.loads(json.dumps(prepared, default=lambda value: value.tolist()))
        composite = ns["_extract_observation_image"](wire)
        np.testing.assert_array_equal(composite, reference["observation/image"])
        assert composite.shape == (540, 640, 3) and composite.dtype == np.uint8
        Image.fromarray(composite).save(args.output / f"{label}-service-input.png")
        rows.append({"input": label, "per_view_shape": [360, 640, 3],
                     "composite_shape": list(composite.shape),
                     "official_extraction_pixel_equal": True, "official_composition_pixel_equal": True,
                     "composite_rgb_sha256": hashlib.sha256(composite.tobytes()).hexdigest()})
    receipt = {
        "schema": "sgw-official-n3-packing-gate-v1", "status": "passed",
        "policy_input": identity, "camera_configuration": camera_configuration_identity(),
        "capture": str(args.capture), "native_reset_inputs": 1, "synthetic_inputs": 1,
        "model_requests": 0, "model_runtime_qualification": False,
        "nano_source_sha256": NANO_HELPER_SHA256,
        "official_client_sha256": hashlib.sha256(official_path.read_bytes()).hexdigest(),
        "capture_declared_configuration": capture["camera_configuration"],
        "view_order": ["wrist top", "stock left bottom left", "stock right bottom right"],
        "retained_capture_extrinsics_intrinsics_verified": True,
        "scope": "Official per-view resize and existing service compose exactly match the pinned official client. No model, learned transforms, or forecasts executed.",
        "checks": rows,
    }
    (args.output / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, sort_keys=True))


def _corners(raw):
    images = {}
    for index, name in enumerate(CAMERAS):
        image = np.full_like(raw["image_obs"][name], 30 + index * 60)
        for y, x, color in (
            (slice(0, 128), slice(0, 128), (255, 0, 0)),
            (slice(0, 128), slice(-128, None), (0, 255, 0)),
            (slice(-128, None), slice(0, 128), (0, 0, 255)),
            (slice(-128, None), slice(-128, None), (255, 255, 0)),
        ):
            image[:, y, x] = color
        images[name] = image
    return {"image_obs": images, "proprio_obs": raw["proprio_obs"]}


if __name__ == "__main__":
    main()
