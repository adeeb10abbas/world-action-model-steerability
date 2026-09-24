"""Lazy, offline-only E3/F3 bindings to immutable official implementations.

See checkpoint_integrations.json for upstream identities and native invocation.
CPU contract coverage does not qualify either model for study execution.
"""

from __future__ import annotations

from dataclasses import replace
import hashlib
import importlib
import json
import os
from pathlib import Path
import threading
from typing import Any, Mapping

import numpy as np

from .adapters import AdapterError, EDGE_CONFIG, FLUX_CONFIG, _integer_seed
from .nano_backend import CosmosNanoBackend
from .producer import _git_revision, _proc_start_identity, composite_future_metadata


IDENTITIES = Path(__file__).with_name("checkpoint_integrations.json")
VIEW_KEYS = (
    "observation/wrist_image_left",
    "observation/exterior_image_1_left",
    "observation/exterior_image_2_left",
)


def _required_path(name: str) -> Path:
    value = os.environ.get(name, "").strip()
    if not value:
        raise AdapterError(f"{name} is required for the pinned checkpoint backend")
    return Path(value).expanduser().resolve()


def verify_files(root: Path, entries: list[Mapping[str, Any]]) -> None:
    """Verify local payloads against official immutable Git/LFS object identities."""
    for entry in entries:
        relative = Path(str(entry["path"]))
        if relative.is_absolute() or ".." in relative.parts:
            raise AdapterError("invalid checkpoint manifest path")
        path = root / relative
        size = entry["bytes"]
        if not path.is_file() or path.stat().st_size != size:
            raise AdapterError(f"checkpoint file missing or wrong size: {relative}")
        algorithm = "sha256" if "sha256" in entry else "git_blob"
        hasher = hashlib.sha256() if algorithm == "sha256" else hashlib.sha1()
        if algorithm == "git_blob":
            hasher.update(f"blob {size}\0".encode())
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                hasher.update(block)
        if hasher.hexdigest() != entry[algorithm]:
            raise AdapterError(f"checkpoint content hash mismatch: {relative}")


def verify_identity(model: str) -> tuple[Path, Path, Path | None]:
    config = {"E3": EDGE_CONFIG, "F3": FLUX_CONFIG}[model]
    source = _required_path(f"SGW01_{model}_SOURCE_ROOT")
    checkpoint = _required_path(f"SGW01_{model}_CHECKPOINT_PATH")
    if _git_revision(str(source)) != config["source_commit"]:
        raise AdapterError(f"{model} source commit is not pinned")
    manifest = json.loads(IDENTITIES.read_text())
    identity = manifest["checkpoints"][model]
    if identity["asset"] != config["asset"] or identity["revision"] != config["revision"]:
        raise AdapterError("checkpoint manifest differs from registered model")
    # The Cosmos loader gives a nested model/ or root consolidated file priority.
    if model == "E3" and ((checkpoint / "model").exists() or list(checkpoint.glob("*.safetensors"))):
        raise AdapterError("Edge checkpoint has an unregistered overriding model payload")
    verify_files(checkpoint, identity["files"])
    for key, value in manifest["sources"].items():
        if key.startswith("edge_" if model == "E3" else "flux_"):
            path = source / value["path"]
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != value["sha256"]:
                raise AdapterError(f"{model} official interface source hash mismatch: {path}")
    base = None
    if model == "F3":
        base = _required_path("SGW01_F3_BASE_PATH")
        identity = manifest["checkpoints"]["F3-base"]
        if identity["asset"] != config["base_asset"] or identity["revision"] != config["base_revision"]:
            raise AdapterError("FLUX base manifest differs from registered encoders")
        verify_files(base, identity["files"])
    return source, checkpoint, base


def _native_module(name: str, source: Path) -> Any:
    try:
        module = importlib.import_module(name)
        Path(module.__file__).resolve().relative_to(source)
    except (ImportError, AttributeError, TypeError, ValueError) as exc:
        raise AdapterError(f"official module is unavailable or outside pinned source: {name}") from exc
    return module


def derive_attestation(backend: Any, *, expected_config: Mapping[str, Any]) -> dict[str, Any]:
    model = expected_config["model"]
    expected = {"E3": EDGE_CONFIG, "F3": FLUX_CONFIG}.get(model)
    if expected is None or dict(expected_config) != expected or backend.resolved_config != expected:
        raise AdapterError("loaded checkpoint backend config differs from registered identity")
    source, checkpoint, base = verify_identity(model)
    if str(source) != backend.source_root or str(checkpoint) != backend.checkpoint_path:
        raise AdapterError("loaded checkpoint paths differ from verified identity")
    if model == "F3" and str(base) != backend.base_path:
        raise AdapterError("loaded FLUX encoder paths differ from verified identity")
    return {
        "server_pid": os.getpid(),
        "server_start_time": _proc_start_identity(os.getpid()),
        "model": model,
        "config": dict(backend.resolved_config),
        "source_commit": expected["source_commit"],
        "checkpoint_revision": expected["revision"],
        "identity_manifest_sha256": hashlib.sha256(IDENTITIES.read_bytes()).hexdigest(),
        "identity_route": "clean_pinned_source_and_verified_checkpoint_file_manifest",
        "forecast_qualified": False,
    }


def _offline_only() -> None:
    if os.environ.get("HF_HUB_OFFLINE") != "1" or os.environ.get("TRANSFORMERS_OFFLINE") != "1":
        raise AdapterError("native checkpoint loading requires HF_HUB_OFFLINE=1 and TRANSFORMERS_OFFLINE=1")


class CosmosEdgeBackend(CosmosNanoBackend):
    def reset(self) -> None:
        with self._lock:
            if self.service.cfg.history_length != 1 or self.service._distributed_enabled():
                raise AdapterError("Edge reset requires the pinned stateless single-rank service")
            self.service.cfg = replace(self.service.cfg, seed=0, deterministic_seed=True)
            self.service._rng = np.random.default_rng(0)
            self.service._control_request_id = 0

    def predict(self, observation: Mapping[str, Any], prompt: str, sampling_seed: int) -> Mapping[str, Any]:
        _integer_seed(sampling_seed, "sampling_seed")
        result = dict(super().predict(observation, prompt, sampling_seed))
        return result


def build_pinned_edge_backend() -> CosmosEdgeBackend:
    _offline_only()
    source, checkpoint, _ = verify_identity("E3")
    output = _required_path("SGW01_E3_OUTPUT_DIR")
    native = _native_module("cosmos_framework.scripts.action_policy_server_robolab", source)
    args = native.RobolabServerArgs(
        checkpoint_path=str(checkpoint), hf_revision=EDGE_CONFIG["revision"],
        host="127.0.0.1", port=0, domain_name="droid_lerobot",
        decode_video=True, output_dir=output, sampler="unipc",
        seed=0, deterministic_seed=True, guidance=3.0,
        guidance_interval=(960, 1001), num_steps=4, shift=5.0,
        resolution="480", conditioning_fps=15.0, action_chunk_size=32,
        action_dim=8, history_length=1, image_height=540, image_width=640,
        action_space="joint_pos", use_state=True, format_prompt_as_json=True,
        cfg_parallel=False, allow_dcp_checkpoint=False,
    )
    service = native.RobolabPolicyService(args)
    cfg = service.cfg
    expected_fields = {
        "guidance": 3.0, "num_steps": 4, "shift": 5.0,
        "conditioning_fps": 15.0, "resolution": "480", "history_length": 1,
        "action_chunk_size": 32, "action_dim": 8, "image_height": 540,
        "image_width": 640, "action_space": "joint_pos", "use_state": True,
        "decode_video": True, "domain_name": "droid_lerobot",
    }
    if any(getattr(cfg, key, None) != value for key, value in expected_fields.items()):
        raise AdapterError("Edge resolved native interface differs from registered config")
    if (
        tuple(cfg.guidance_interval or ()) != (960, 1001)
        or getattr(service._transform, "prompt_json_formatter", None) is None
        or service.setup_args.sampler != "unipc"
        or service.model.config.precision != "bfloat16"
    ):
        raise AdapterError("Edge resolved guidance/prompt/sampler/precision differs")
    return CosmosEdgeBackend(
        service, resolved_config=EDGE_CONFIG, source_root=str(source), checkpoint_path=str(checkpoint)
    )


def flux_observation(observation: Mapping[str, Any], native: Any) -> dict[str, Any]:
    """Adapt full registered images with the official FLUX pure image helpers."""
    def image_array(value: Any) -> np.ndarray:
        image = np.asarray(value)
        # JSON transports lose the ndarray dtype, but must not change pixel values.
        if image.dtype != np.uint8 and image.dtype.kind in "iu" and image.size and image.min() >= 0 and image.max() <= 255:
            image = image.astype(np.uint8)
        if image.dtype != np.uint8 or image.ndim != 3 or image.shape[-1] != 3:
            raise AdapterError("FLUX native cameras must be HWC uint8 RGB")
        return image

    result = dict(observation)
    if all(key in observation for key in VIEW_KEYS):
        images = [image_array(observation[key]) for key in VIEW_KEYS]
        image = native.compose_views(*images)
        if image.shape[:2] != native.COMPOSITE_HW:
            image = native._resize_uint8(image, native.COMPOSITE_HW)
        result = {key: value for key, value in result.items() if key not in VIEW_KEYS}
        result["observation/image"] = image
    image = image_array(result.get("observation/image"))
    if image.shape != (540, 640, 3):
        raise AdapterError("FLUX requires the official 540x640 uint8 composite")
    result["observation/image"] = image
    return result


class FluxBackend:
    def __init__(self, service: Any, *, native: Any, positional: Any, source: Path,
                 checkpoint: Path, base: Path, resolved_config: Mapping[str, Any]) -> None:
        self.service, self.native, self.positional = service, native, positional
        self.source_root, self.checkpoint_path, self.base_path = str(source), str(checkpoint), str(base)
        self.resolved_config = dict(resolved_config)
        self._lock = threading.Lock()
        capture = os.environ.get("SGW01_F3_CAPTURE_FUTURE", "1")
        if capture not in {"0", "1"}:
            raise AdapterError("SGW01_F3_CAPTURE_FUTURE must be 0 or 1")
        self.capture_future = capture == "1"

    def reset(self) -> None:
        with self._lock:
            self.service.policy.reset()
            self.service.queries = 0
            policy = self.service.policy
            if policy._ctx_cache or policy._prepared_text_cache or policy._action_queue or policy._last_command is not None:
                raise AdapterError("official FLUX reset failed to clear text/command state")

    def predict(self, observation: Mapping[str, Any], prompt: str, sampling_seed: int) -> Mapping[str, Any]:
        _integer_seed(sampling_seed, "sampling_seed")
        import torch

        obs = flux_observation(observation, self.native)
        obs["prompt"] = prompt
        with self._lock, torch.inference_mode():
            policy = self.service.policy
            captured: list[tuple[Any, Any]] = []
            original = policy._sample_prepared

            def capture(**kwargs: Any) -> Any:
                out = original(**kwargs)
                # Observe only this request's completed native solve; return the
                # exact same object so the official action postprocessing is unchanged.
                captured.append((out["x_video"].detach().clone(), {
                    key: kwargs["fixed"][key].detach().clone()
                    for key in ("x_video_ids", "x_video_cond", "x_video_cond_ids")
                }))
                return out

            if self.capture_future:
                policy._sample_prepared = capture
            try:
                result = dict(self.service.infer(obs, seed=sampling_seed))
            finally:
                if self.capture_future:
                    policy._sample_prepared = original
            actions = np.asarray(result.get("action"), dtype=np.float32)
            if actions.shape != (32, 8) or not np.isfinite(actions).all():
                raise AdapterError("official FLUX returned invalid absolute actions")
            result["action"] = actions
            if not self.capture_future:
                result["future_status"] = "not_exposed"
                result["future_metadata"] = composite_future_metadata(self.resolved_config)
                return result
            if len(captured) != 1:
                raise AdapterError("FLUX did not expose exactly one same-request joint sample")
            video, fixed = captured[0]
            cond = self.positional.scatter_ids(fixed["x_video_cond"], fixed["x_video_cond_ids"])[0]
            predicted = self.positional.scatter_ids(video, fixed["x_video_ids"])[0]
            latents = torch.cat((cond.float(), predicted.float()), dim=2)
            result["future_latent"] = latents.cpu().numpy()
            result["future_metadata"] = {
                **composite_future_metadata(self.resolved_config),
                "sampling_calls": 1, "source": "same_request_official_sample_prepared",
                "latent_layout": "B,C,T,H,W", "canvas_hw": [544, 736],
                "canvas_hw_semantics": "input_padded_canvas_hw",
                "camera_order": ["wrist", "left", "right"],
                "conditioning_frame_included": True, "conditioning_fps": 15,
                "physical_time_alignment": "unqualified", "camera_alignment": "unqualified",
                "sampling_seed": sampling_seed,
            }
            try:
                decoded = policy.video_vae.decode(latents.to(device=video.device, dtype=torch.bfloat16))
                if decoded.ndim != 5 or tuple(decoded.shape[:2]) != (1, 3) or not torch.isfinite(decoded).all():
                    raise AdapterError("FLUX decoder did not return finite BCTHW RGB")
                result["future"] = (
                    ((decoded[0].clamp(-1, 1) + 1) * 127.5).to(torch.uint8)
                    .permute(1, 2, 3, 0).cpu().numpy()
                )
                result["future_metadata"].update(composite_future_metadata(self.resolved_config, result["future"]))
                result["future_status"] = "decoded_unmapped"
            except Exception as exc:
                # A decoder failure cannot erase the already valid behavior response.
                result["future_status"] = "decode_error"
                result["future_metadata"]["decode_error"] = f"{type(exc).__name__}: {exc}"
            return result


def build_pinned_flux_backend() -> FluxBackend:
    _offline_only()
    source, checkpoint, base = verify_identity("F3")
    assert base is not None
    native = _native_module("flux_action.serving.robolab", source)
    policy_module = _native_module("flux_action.policy", source)
    vae_module = _native_module("flux_action.models.video_vae", source)
    text_module = _native_module("flux_action.models.text_encoder", source)
    positional = _native_module("flux_action.models.positional", source)
    # Inject only hash-verified local encoders; never resolve a mutable Hub name.
    policy = policy_module.FluxActionPolicy.from_pretrained(
        str(checkpoint), device="cpu",
        video_vae=vae_module.load_video_vae(str(base / "video_vae.safetensors"), compile_model=False),
        text_encoder=text_module.load_text_encoder(str(base / "text_encoder"), compile_model=False),
    )
    native.prepare_serving_policy(policy, device="cuda", dtype="keep", settings=None,
                                  compile_dit=False, offload_text_encoder=False, warmup=0)
    cfg = policy.config
    fields = {
        "precision": "torch_dtype", "quantization": "quantization", "sampler": "sampler",
        "denoising_steps": "num_inference_steps", "guidance": "guidance_scale",
        "action_guidance": "guidance_scale_action", "shift": "sampler_shift",
        "conditioning_fps": "fps", "camera_keys": "camera_keys", "canvas_hw": "canvas_hw",
        "action_scale": "action_scale", "action_parameterization": "action_parameterization",
        "gripper_flip_dims": "gripper_flip_dims", "single_frame_encode": "single_frame_encode",
        "returned_action_horizon": "chunk_size", "executed_action_horizon": "n_action_steps",
        "history_length": "n_obs_steps",
    }
    actual = dict(FLUX_CONFIG)
    for label, field in fields.items():
        value = getattr(cfg, field, None)
        actual[label] = list(value) if isinstance(value, tuple) else value
    if (
        actual != FLUX_CONFIG or cfg.action_dim != 8 or cfg.camera_layout != "droid"
        or cfg.action_modality != "action_prediction_droid"
        or cfg.action_normalization is not None or cfg.state_normalization is not None
        or cfg.compile_model or not policy._inference_prepared
        or policy.serving_setup != {"prepared": True, "compile_dit": False, "offload_text_encoder": False}
    ):
        raise AdapterError("FLUX resolved native config differs from registered root BF16 settings")
    return FluxBackend(
        native.RoboLabPolicy(policy, seed_base=0), native=native, positional=positional,
        source=source, checkpoint=checkpoint, base=base, resolved_config=actual,
    )
