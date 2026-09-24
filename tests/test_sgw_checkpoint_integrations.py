"""CPU-only E3/F3 contracts; no downloaded checkpoint/model instantiation."""

import ast
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from experiments.workshops.spatial_grounding_v1 import adapters, checkpoint_backends as backends
from experiments.workshops.spatial_grounding_v1 import producer, runtime
from experiments.workshops.spatial_grounding_v1.policy_observations import nano_observation


@pytest.mark.parametrize("model", ["E3", "F3"])
def test_model_config_dispatch_prefix_and_cap(model):
    actions = np.arange(32 * 8, dtype=np.float32).reshape(32, 8)
    actions[:, -1] = np.linspace(0, 1, 32)

    def transport(request):
        return {**request, "actions": actions}

    adapter = adapters.make_adapter(model, cell_id="cell", prompt="unaltered", transport=transport, sampling_seed=8300)
    adapter.reset(reset_fn=lambda: {"fingerprint": "a" * 64}, reset_id="reset", camera_id="camera")
    adapter.executed_steps = 448
    predicted = adapter.predict({}, "unaltered", action_step_start=448)
    assert predicted.returned_horizon == 32
    assert predicted.executed_horizon == 2
    np.testing.assert_array_equal(predicted.executable_actions, actions[:2])
    assert predicted.raw_request["model"] == model
    assert predicted.raw_request["sampling_seed"] == 8300
    adapter.commit_executed(2)
    with pytest.raises(adapters.AdapterError, match="450-action"):
        adapter.predict({}, "unaltered", action_step_start=450)
    with pytest.raises(adapters.AdapterError, match="exact SGW-01"):
        runtime.create_runtime(model=model, config=adapters.NANO_CONFIG)


def test_checkpoint_hashes_validate_lfs_and_git_blobs(tmp_path):
    payload = b"official small fixture\n"
    (tmp_path / "fixture").write_bytes(payload)
    git_hash = hashlib.sha1(f"blob {len(payload)}\0".encode() + payload).hexdigest()
    for algorithm, digest in (("git_blob", git_hash), ("sha256", hashlib.sha256(payload).hexdigest())):
        entry = {"path": "fixture", "bytes": len(payload), algorithm: digest}
        backends.verify_files(tmp_path, [entry])
        with pytest.raises(adapters.AdapterError, match="hash mismatch"):
            backends.verify_files(tmp_path, [{**entry, algorithm: "0" * len(digest)}])
        with pytest.raises(adapters.AdapterError, match="wrong size"):
            backends.verify_files(tmp_path, [{**entry, "bytes": len(payload) + 1}])


@pytest.mark.parametrize("model", ["E3", "F3"])
def test_identity_rejected_before_native_import(model, monkeypatch):
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    monkeypatch.setenv(f"SGW01_{model}_SOURCE_ROOT", "/nonexistent-source")
    monkeypatch.setenv(f"SGW01_{model}_CHECKPOINT_PATH", "/nonexistent-checkpoint")
    monkeypatch.setattr(backends, "_git_revision", lambda _: "wrong")
    monkeypatch.setattr(backends, "_native_module", lambda *_: pytest.fail("native import attempted"))
    factory = backends.build_pinned_edge_backend if model == "E3" else backends.build_pinned_flux_backend
    with pytest.raises(adapters.AdapterError, match="source commit"):
        factory()


def test_registered_slots_pass_without_unit_or_gripper_changes():
    images = {name: np.full((1, 4, 8, 3), value, dtype=np.uint8) for name, value in (
        ("wrist_cam", 20), ("over_shoulder_left_camera", 80), ("over_shoulder_right_camera", 140)
    )}
    for image in images.values():
        image[:, 0, 0] += 1
    raw = {"image_obs": images, "proprio_obs": {
        "arm_joint_pos": np.array([[0.1, -0.2, 0.3, -0.4, 0.5, -0.6, 0.7]], np.float32),
        "gripper_pos": np.array([[0.75]], np.float32),
    }}
    obs = nano_observation(raw)
    for key, expected in zip(backends.VIEW_KEYS, images.values()):
        np.testing.assert_array_equal(obs[key], expected[0])
    np.testing.assert_array_equal(obs["observation/joint_position"], raw["proprio_obs"]["arm_joint_pos"][0])
    assert obs["observation/gripper_position"][0] == 0.75


def _source_functions(filename, names, namespace, *, class_name=None):
    identity = json.loads(backends.IDENTITIES.read_text())["sources"][filename]
    path = os.environ.get("SGW01_OFFICIAL_SOURCE_AUDIT")
    if path:
        source_path = Path(path) / filename
    else:
        root = os.environ.get("SGW01_E3_SOURCE_ROOT" if filename.startswith("edge") else "SGW01_F3_SOURCE_ROOT")
        if not root:
            pytest.skip("set SGW01_OFFICIAL_SOURCE_AUDIT or E3/F3 source roots for official pure helpers")
        source_path = Path(root) / identity["path"]
    source = source_path.read_bytes()
    assert hashlib.sha256(source).hexdigest() == identity["sha256"]
    tree = ast.parse(source)
    nodes = tree.body if class_name is None else next(
        node.body for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name
    )
    functions = [node for node in nodes if isinstance(node, ast.FunctionDef) and node.name in names]
    assert len(functions) == len(names)
    for node in functions:
        node.decorator_list = []
    module = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), *functions], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), filename, "exec"), namespace)
    return namespace


def test_official_camera_order_resize_and_flux_reflect_padding():
    torch = pytest.importorskip("torch")
    namespace = {"np": np, "torch": torch, "F": torch.nn.functional}
    edge = _source_functions("edge_server.py", [
        "_ensure_rgb_uint8_image", "_resize_rgb_uint8", "_compose_roboarena_views", "_extract_observation_image",
    ], dict(namespace))
    flux = _source_functions("flux_robolab.py", [
        "_rgb_uint8", "_resize_uint8", "compose_views", "observation_image", "observation_state",
    ], {**namespace, "COMPOSITE_HW": (540, 640), "IMAGE_KEY": "observation/image", "VIEW_KEYS": backends.VIEW_KEYS})
    y, x = np.indices((720, 1280))
    images = [np.stack(((x + i * 23) % 256, (y + i * 51) % 256, (x // 5 + y // 7 + i * 63) % 256), -1).astype(np.uint8) for i in range(3)]
    observation = dict(zip(backends.VIEW_KEYS, images))
    expected = edge["_resize_rgb_uint8"](edge["_extract_observation_image"](observation), (540, 640))
    actual = backends.flux_observation(observation, SimpleNamespace(**flux))
    np.testing.assert_array_equal(actual["observation/image"], expected)
    json_obs = json.loads(json.dumps(observation, default=lambda v: v.tolist()))
    np.testing.assert_array_equal(backends.flux_observation(json_obs, SimpleNamespace(**flux))["observation/image"], expected)
    # At the leading pixel, the wrist averages a 2x2 cell once. Exteriors
    # undergo two bilinear/truncating halves; neither operation rounds.
    for (row, col), color in zip(((0, 0), (360, 0), (360, 320)), ([0, 0, 0], [24, 52, 63], [47, 103, 126])):
        assert expected[row, col].tolist() == color
    padding = _source_functions("flux_packing.py", ["pad_composite"], {
        **namespace, "CANVAS_HW": (544, 736), "COMPOSITE_HW": (540, 640),
    })["pad_composite"]
    tensor = torch.from_numpy(expected).permute(2, 0, 1).float().div(255)[None]
    canvas = padding(tensor)
    assert tuple(canvas.shape) == (3, 1, 544, 736)
    torch.testing.assert_close(canvas[:, 0, :540, :640], tensor[0] * 2 - 1)
    torch.testing.assert_close(canvas[:, 0, 540, 640], canvas[:, 0, 538, 638])
    invalid = {**observation, backends.VIEW_KEYS[0]: images[0].astype(float) / 255}
    with pytest.raises(adapters.AdapterError, match="uint8"):
        backends.flux_observation(invalid, SimpleNamespace(**flux))


def test_official_edge_state_trim_gripper_and_flux_flip():
    torch = pytest.importorskip("torch")
    namespace = {"np": np, "torch": torch}
    edge = _source_functions("edge_server.py", ["_format_outputs"], {
        **namespace, "time": SimpleNamespace(monotonic=lambda: 1.0), "os": os,
    }, class_name="RobolabPolicyService")
    server = SimpleNamespace(cfg=SimpleNamespace(action_dim=8, history_length=1, action_space="joint_pos", decode_video=False))
    source = torch.arange(33 * 8, dtype=torch.float32).reshape(33, 8)
    source[:, -1] = torch.linspace(0, 1, 33)
    expected = source[1:].numpy().copy()
    expected[:, -1] = 1 - expected[:, -1]
    result = edge["_format_outputs"](server, {}, {"action": [source.clone()]}, start_time=0)
    np.testing.assert_array_equal(result["action"], expected)
    flip = _source_functions("flux_policy.py", ["_flip"], namespace, class_name="FluxActionPolicy")["_flip"]
    policy = SimpleNamespace(config=SimpleNamespace(gripper_flip_dims=[-1]))
    tensor = torch.tensor([[0.1, -0.2, 0.3, -0.4, 0.5, -0.6, 0.7, 0.75]])
    once = flip(policy, tensor)
    torch.testing.assert_close(once[:, :7], tensor[:, :7])
    assert once[0, -1] == 0.25
    torch.testing.assert_close(flip(policy, once), tensor)


def test_official_flux_video_token_roundtrip_and_action_time_horizon():
    torch = pytest.importorskip("torch")
    einops = pytest.importorskip("einops")
    namespace = {"torch": torch, "rearrange": einops.rearrange}
    positional = _source_functions("flux_positional.py", ["prc_vid", "_compress_time", "scatter_ids"], namespace)
    latents = torch.arange(96 * 9 * 2 * 3, dtype=torch.float32).reshape(96, 9, 2, 3)
    condition, condition_ids = positional["prc_vid"](latents[:, :1], torch.tensor([0]))
    prediction, prediction_ids = positional["prc_vid"](latents[:, 1:], torch.arange(1, 9) * 26)
    decoded_condition = positional["scatter_ids"](condition[None], condition_ids[None])[0]
    decoded_prediction = positional["scatter_ids"](prediction[None], prediction_ids[None])[0]
    torch.testing.assert_close(torch.cat((decoded_condition, decoded_prediction), dim=2), latents[None])
    packing = _source_functions("flux_packing.py", ["default_action_times"], {
        "torch": torch, "repeat": einops.repeat, "CHUNK": 32, "FPS": 15.0,
    })
    times = packing["default_action_times"](1)
    assert tuple(times.shape) == (1, 32)
    torch.testing.assert_close(times, (torch.arange(32).float()[None] + 1) / 15)


def test_edge_factory_uses_explicit_official_defaults(monkeypatch):
    captured = {}
    @dataclass(frozen=True)
    class Config:
        seed: int = 0
        deterministic_seed: bool = True
        guidance: float = 3.0
        guidance_interval: tuple = (960, 1001)
        num_steps: int = 4
        shift: float = 5.0
        conditioning_fps: float = 15.0
        resolution: str = "480"
        history_length: int = 1
        action_chunk_size: int = 32
        action_dim: int = 8
        image_height: int = 540
        image_width: int = 640
        action_space: str = "joint_pos"
        use_state: bool = True
        decode_video: bool = True
        domain_name: str = "droid_lerobot"
    service = SimpleNamespace(
        cfg=Config(), _transform=SimpleNamespace(prompt_json_formatter=object()),
        setup_args=SimpleNamespace(sampler="unipc"), model=SimpleNamespace(config=SimpleNamespace(precision="bfloat16")),
        _distributed_enabled=lambda: False,
    )
    def infer(obs):
        captured["request"] = obs
        return {"action": np.zeros((32, 8), np.float32)}
    service.infer = infer
    def args(**kwargs):
        captured["args"] = kwargs
        return kwargs
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    monkeypatch.setenv("SGW01_E3_OUTPUT_DIR", str(Path.cwd() / "not-created-output"))
    monkeypatch.setattr(backends, "verify_identity", lambda _: (Path("/source"), Path("/checkpoint"), None))
    monkeypatch.setattr(backends, "_native_module", lambda *_: SimpleNamespace(RobolabServerArgs=args, RobolabPolicyService=lambda _: service))
    backend = backends.build_pinned_edge_backend()
    assert captured["args"]["format_prompt_as_json"] is True
    assert captured["args"]["guidance_interval"] == (960, 1001)
    backend.predict({}, "exact original prompt", 8300)
    assert captured["request"]["prompt"] == "exact original prompt"
    assert service.cfg.seed == 8300
    backend.reset()
    assert service.cfg.seed == 0
    assert service._control_request_id == 0
    service._transform.prompt_json_formatter = None
    with pytest.raises(adapters.AdapterError, match="guidance/prompt"):
        backends.build_pinned_edge_backend()


def _flux_fixture():
    torch = pytest.importorskip("torch")
    class Policy:
        def __init__(self):
            self.calls = 0
            self.video_vae = SimpleNamespace(decode=lambda x: torch.zeros((1, 3, 5, 2, 2)))
            self.reset()
        def reset(self):
            self._ctx_cache, self._prepared_text_cache = {}, {}
            self._action_queue, self._last_command = [], None
        def _sample_prepared(self, **kwargs):
            self.calls += 1
            return {"x_video": torch.ones((1, 1, 1)), "actions": torch.arange(256).reshape(32, 8).float()}
    policy = Policy()
    class Service:
        queries = 0
        def infer(self, obs, *, seed):
            self.queries += 1
            self.last_obs, self.seed = obs, seed
            result = policy._sample_prepared(fixed={
                "x_video_ids": torch.ones((1, 1, 4)),
                "x_video_cond": torch.zeros((1, 1, 1)), "x_video_cond_ids": torch.zeros((1, 1, 4)),
            })
            return {"action": result["actions"].numpy()}
    service = Service()
    service.policy = policy
    backend = backends.FluxBackend(
        service, native=SimpleNamespace(), positional=SimpleNamespace(scatter_ids=lambda x, _: [x.reshape(1, 1, 1, 1, 1)]),
        source=Path("/source"), checkpoint=Path("/checkpoint"), base=Path("/base"), resolved_config=adapters.FLUX_CONFIG,
    )
    return backend, {"observation/image": np.zeros((540, 640, 3), np.uint8)}


def test_flux_same_request_capture_is_passive_and_reset_clears_caches():
    backend, obs = _flux_fixture()
    result = backend.predict(obs, "literal instruction", 8300)
    policy = backend.service.policy
    assert policy.calls == 1
    assert backend.service.seed == 8300
    assert backend.service.last_obs["prompt"] == "literal instruction"
    assert result["future_status"] == "decoded_unmapped"
    assert result["future_metadata"]["sampling_calls"] == 1
    metadata = result["future_metadata"]
    assert metadata["source"] == "same_request_official_sample_prepared"
    assert metadata["conditioning_frame_included"] is True
    assert metadata["conditioning_fps"] == 15
    assert metadata["sampling_seed"] == 8300
    assert metadata["camera_order"] == ["wrist", "left", "right"]
    assert metadata["canvas_hw"] == metadata["input_padded_canvas_hw"] == [544, 736]
    assert metadata["canvas_hw_semantics"] == "input_padded_canvas_hw"
    assert metadata["decoded_output_shape"] == [5, 2, 2, 3]
    assert metadata["decoded_output_hw"] == [2, 2]
    assert metadata["decoded_layout_status"] == "unavailable_unexpected_decoded_shape"
    assert all(region["decoded_bounds_yxyx"] is None for region in metadata["camera_regions"])
    assert result["future_latent"].shape == (1, 1, 2, 1, 1)
    backend.capture_future = False
    disabled = backend.predict(obs, "literal instruction", 8300)
    assert policy.calls == 2
    np.testing.assert_array_equal(result["action"], disabled["action"])
    assert disabled["future_status"] == "not_exposed"
    assert disabled["future_metadata"]["decoded_output_shape"] is None
    assert disabled["future_metadata"]["decoded_layout_status"] == "unavailable_no_decoded_output"
    assert "future" not in disabled and "future_latent" not in disabled
    policy._ctx_cache["old"] = 1
    policy._prepared_text_cache["old"] = 1
    policy._action_queue.append(1)
    policy._last_command = "old"
    backend.reset()
    assert not policy._ctx_cache and not policy._prepared_text_cache and not policy._action_queue
    assert backend.service.queries == 0 and policy._last_command is None


def test_flux_decoder_failure_keeps_actions_and_same_sample_latents():
    backend, obs = _flux_fixture()
    def fail(_):
        raise RuntimeError("synthetic decode failure")
    backend.service.policy.video_vae.decode = fail
    result = backend.predict(obs, "unaltered", 0)
    assert result["action"].shape == (32, 8)
    assert result["future_status"] == "decode_error"
    assert "synthetic decode failure" in result["future_metadata"]["decode_error"]
    assert result["future_metadata"]["decoded_output_hw"] is None
    assert result["future_metadata"]["decoded_layout_status"] == "unavailable_no_decoded_output"
    assert result["future_metadata"]["camera_alignment"] == "unqualified"
    assert "future_latent" in result and "future" not in result
    assert backend.service.policy.calls == 1


def test_flux_labels_actual_decoded_canvas_without_resizing_or_changing_capture_parity():
    torch = pytest.importorskip("torch")
    backend, obs = _flux_fixture()
    calls = []

    def decode(latents):
        calls.append(latents.clone())
        return torch.zeros((1, 3, 1, 544, 640))

    backend.service.policy.video_vae.decode = decode
    result = backend.predict(obs, "unaltered", 0)
    metadata = result["future_metadata"]
    assert result["future"].shape == (1, 544, 640, 3)
    assert np.all(result["future"] == 127)
    assert metadata["decoded_output_shape"] == [1, 544, 640, 3]
    assert metadata["decoded_output_hw"] != metadata["canvas_hw"]
    assert [region["decoded_bounds_yxyx"] for region in metadata["camera_regions"]] == [
        [0, 0, 360, 640], [360, 0, 540, 320], [360, 320, 540, 640],
    ]
    assert metadata["non_camera_regions"] == [
        {"kind": "reflection_padding", "decoded_bounds_yxyx": [540, 0, 544, 640]}
    ]
    assert metadata["physical_time_alignment"] == metadata["camera_alignment"] == "unqualified"
    backend.capture_future = False
    disabled = backend.predict(obs, "unaltered", 0)
    assert len(calls) == 1 and backend.service.policy.calls == 2
    np.testing.assert_array_equal(result["action"], disabled["action"])


def test_flux_factory_uses_root_bf16_local_encoders_and_no_warmup(monkeypatch):
    captured = {}
    fields = dict(
        torch_dtype="bfloat16", quantization=None, sampler="cosmos_unipc",
        num_inference_steps=4, guidance_scale=4.0, guidance_scale_action=1.0,
        sampler_shift=5.0, fps=15.0, camera_keys=("images.wrist", "images.left", "images.right"),
        canvas_hw=(544, 736), action_scale=2.0, action_parameterization="absolute",
        gripper_flip_dims=(-1,), single_frame_encode=True, chunk_size=32,
        n_action_steps=32, n_obs_steps=1, action_dim=8, camera_layout="droid",
        action_modality="action_prediction_droid", action_normalization=None,
        state_normalization=None, compile_model=False,
    )
    policy = SimpleNamespace(config=SimpleNamespace(**fields), _inference_prepared=True,
                             serving_setup={"prepared": True, "compile_dit": False, "offload_text_encoder": False})
    def load(checkpoint, **kwargs):
        captured["checkpoint"], captured["load"] = checkpoint, kwargs
        return policy
    def prepare(received, **kwargs):
        assert received is policy
        captured["prepare"] = kwargs
        return received
    native = SimpleNamespace(prepare_serving_policy=prepare, RoboLabPolicy=lambda p, **_: SimpleNamespace(policy=p))
    modules = {
        "flux_action.serving.robolab": native,
        "flux_action.policy": SimpleNamespace(FluxActionPolicy=SimpleNamespace(from_pretrained=load)),
        "flux_action.models.video_vae": SimpleNamespace(load_video_vae=lambda path, **_: ("vae", path)),
        "flux_action.models.text_encoder": SimpleNamespace(load_text_encoder=lambda path, **_: ("text", path)),
        "flux_action.models.positional": SimpleNamespace(),
    }
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    monkeypatch.setattr(backends, "verify_identity", lambda _: (Path("/source"), Path("/root-bf16"), Path("/base")))
    monkeypatch.setattr(backends, "_native_module", lambda name, _: modules[name])
    backend = backends.build_pinned_flux_backend()
    assert backend.resolved_config == adapters.FLUX_CONFIG
    assert captured["checkpoint"] == "/root-bf16"
    assert captured["load"] == dict(device="cpu", video_vae=("vae", "/base/video_vae.safetensors"),
                                   text_encoder=("text", "/base/text_encoder"))
    assert captured["prepare"] == dict(device="cuda", dtype="keep", settings=None, compile_dit=False,
                                      offload_text_encoder=False, warmup=0)
    policy.config.guidance_scale = 3.0
    with pytest.raises(adapters.AdapterError, match="root BF16"):
        backends.build_pinned_flux_backend()


@pytest.mark.parametrize("model", ["E3", "F3"])
def test_owned_producer_reset_trace_and_unmapped_future(model, tmp_path, monkeypatch):
    from experiments.workshops.spatial_grounding_v1.trace import read_trace_sidecar
    config = adapters.MODEL_ADAPTERS[model].config
    class Backend:
        resets = 0
        def reset(self):
            self.resets += 1
        def predict(self, observation, prompt, seed):
            return {"action": np.zeros((32, 8), np.float32), "future": np.ones((2, 2, 2, 3), np.uint8),
                    "future_status": "decoded_unmapped", "future_latent": np.ones((1, 1, 2, 1, 1), np.float32)}
    backend = Backend()
    monkeypatch.setattr(backends, "derive_attestation", lambda *_args, **_kwargs: {"model": model})
    trace = tmp_path / "trace.jsonl"
    monkeypatch.setenv("SGW01_TRACE_SIDECAR", str(trace))
    owner = producer.NanoEvidenceProducer(
        backend, trace_path=trace, future_dir=tmp_path / "future",
        attestation_path=tmp_path / "attest.json", expected_config=config,
    )
    owner.reset({"camera_name": "camera"})
    assert backend.resets == 1
    packet = dict(prompt="literal", observation={}, sampling_seed=8300, request_index=0,
                  request_id="request", registered_cell_id="cell", reset_id="physical-reset",
                  reset_fingerprint="a" * 64, camera_name="camera", camera_id="camera")
    response = owner.predict(packet)
    loaded = read_trace_sidecar(request=packet, response={"actions": response["action"]})
    assert loaded["model"] == model
    assert loaded["effective_sampling_seed"] == 8300
    assert loaded["future_status"] == "decoded_unmapped"
    assert loaded["future"].dtype == np.uint8
    assert loaded["future_latent"].shape == (1, 1, 2, 1, 1)
    with pytest.raises(adapters.AdapterError, match="stale"):
        owner.predict(packet)
