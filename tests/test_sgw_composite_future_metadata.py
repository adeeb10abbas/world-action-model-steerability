"""Prospective composite labels only; all predictions here are CPU fakes."""

from dataclasses import dataclass
import hashlib
import json
from types import SimpleNamespace

import numpy as np
import pytest

from experiments.workshops.spatial_grounding_v1 import adapters, checkpoint_backends, nano_backend, producer
from experiments.workshops.spatial_grounding_v1.trace import read_trace_sidecar


CONFIGS = (adapters.NANO_CONFIG, adapters.EDGE_CONFIG, adapters.FLUX_CONFIG)
CAMERAS = ("wrist_cam", "over_shoulder_left_camera", "over_shoulder_right_camera")


@pytest.mark.parametrize("config", CONFIGS, ids=lambda config: config["model"])
def test_composite_regions_distinguish_input_canvas_actual_output_and_unqualified_alignment(config):
    height = 544 if config["model"] == "F3" else 528
    future = np.broadcast_to(np.uint8(17), (33, height, 640, 3))
    metadata = producer.composite_future_metadata(config, future)
    assert metadata["camera_layout"] == "wrist_above_left_right_composite"
    assert metadata["input_content_hw"] == [540, 640]
    assert metadata["input_padded_canvas_hw"] == [544, 736]
    assert metadata["decoded_output_hw"] == [height, 640]
    assert metadata["decoded_output_shape"] == list(future.shape)
    assert metadata["region_bounds_convention"] == "half_open_y0_x0_y1_x1"
    assert metadata["decoded_to_input_content"] == "top_left_no_rescale"
    assert metadata["decoded_layout_status"] == "source_defined_unqualified"
    assert metadata["physical_time_alignment"] == metadata["camera_alignment"] == "unqualified"
    assert "conditioning_frame_included" not in metadata
    assert "conditioning_fps" not in metadata
    regions = metadata["camera_regions"]
    assert [region["camera_name"] for region in regions] == list(CAMERAS)
    assert [region["view"] for region in regions] == ["wrist", "left", "right"]
    assert [region["input_content_bounds_yxyx"] for region in regions] == [
        [0, 0, 360, 640], [360, 0, 540, 320], [360, 320, 540, 640],
    ]
    assert [region["decoded_bounds_yxyx"] for region in regions] == [
        [0, 0, 360, 640], [360, 0, min(540, height), 320], [360, 320, min(540, height), 640],
    ]
    assert metadata["non_camera_regions"] == (
        [{"kind": "reflection_padding", "decoded_bounds_yxyx": [540, 0, 544, 640]}]
        if config["model"] == "F3" else []
    )
    provenance = metadata["layout_provenance"]
    assert provenance["model"] == config["model"]
    assert provenance["source_commit"] == config["source_commit"]
    assert provenance["checkpoint_revision"] == config["revision"]
    assert all(f"/blob/{config['source_commit']}/" in url and "#L" in url for url in provenance["source_urls"])
    assert json.loads(json.dumps(metadata)) == metadata
    regions[0]["decoded_bounds_yxyx"][0] = 99
    assert producer.composite_future_metadata(config, future)["camera_regions"][0]["decoded_bounds_yxyx"][0] == 0


@pytest.mark.parametrize("config", CONFIGS, ids=lambda config: config["model"])
@pytest.mark.parametrize("shape", [None, (33, 2, 2, 3), (33, 544, 736, 3), (33, 528, 640, 4), (0, 528, 640, 3)])
def test_absent_or_unexpected_decode_never_invents_actual_regions(config, shape):
    future = None if shape is None else np.broadcast_to(np.uint8(1), shape)
    metadata = producer.composite_future_metadata(config, future)
    assert metadata["decoded_output_shape"] == (None if shape is None else list(shape))
    expected_hw = list(shape[1:3]) if shape and shape[-1] == 3 and all(shape) else None
    assert metadata["decoded_output_hw"] == expected_hw
    assert metadata["decoded_layout_status"] == (
        "unavailable_no_decoded_output" if shape is None else "unavailable_unexpected_decoded_shape"
    )
    assert all(region["decoded_bounds_yxyx"] is None for region in metadata["camera_regions"])
    assert metadata["decoded_to_input_content"] is None
    assert metadata["non_camera_regions"] == []
    assert metadata["physical_time_alignment"] == metadata["camera_alignment"] == "unqualified"


def test_retired_model_gets_no_invented_composite_layout():
    with pytest.raises(adapters.AdapterError, match="registered N3/E3/F3"):
        producer.composite_future_metadata(adapters.DREAMZERO_CONFIG)


@pytest.mark.parametrize("config,backend_type", [
    (adapters.NANO_CONFIG, nano_backend.CosmosNanoBackend),
    (adapters.EDGE_CONFIG, checkpoint_backends.CosmosEdgeBackend),
], ids=["N3", "E3"])
def test_cosmos_metadata_keeps_one_native_call_seed_actions_and_future_bytes(config, backend_type):
    @dataclass(frozen=True)
    class Config:
        seed: int = 0
        deterministic_seed: bool = False

    actions = np.arange(256, dtype=np.float32).reshape(32, 8)
    future = np.broadcast_to(np.uint8(29), (33, 528, 640, 3))
    calls = []
    service = SimpleNamespace(cfg=Config())

    def infer(obs):
        calls.append((obs, service.cfg))
        return {"action": actions, "video": future}

    service.infer = infer
    backend = backend_type(service, resolved_config=config, source_root="/source", checkpoint_path="/checkpoint")
    result = backend.predict({"observation/image": "unchanged"}, "unchanged prompt", 8300)
    assert len(calls) == 1
    assert calls[0][0] == {"observation/image": "unchanged", "prompt": "unchanged prompt"}
    assert calls[0][1] == Config(seed=8300, deterministic_seed=True)
    assert result["action"] is actions
    assert result["future"] is future
    assert result["future_status"] == "decoded_unmapped"
    assert result["future_metadata"]["decoded_output_hw"] == [528, 640]
    service.infer = lambda _: {"action": actions}
    absent = backend.predict({}, "unchanged prompt", 8300)
    assert absent["action"] is actions
    assert absent["future_status"] == "not_exposed"
    assert absent["future_metadata"]["decoded_output_shape"] is None


@pytest.mark.parametrize("config", CONFIGS, ids=lambda config: config["model"])
def test_producer_and_trace_retain_composite_metadata_separate_from_reset_camera(config, tmp_path, monkeypatch):
    height = 544 if config["model"] == "F3" else 528
    future = np.broadcast_to(np.uint8(37), (1, height, 640, 3))
    actions = np.arange(256, dtype=np.float32).reshape(32, 8)
    metadata = {**producer.composite_future_metadata(config, future), "existing_backend_key": "preserved"}
    backend = SimpleNamespace(
        reset=lambda: None,
        predict=lambda *_: {"action": actions, "future": future,
                            "future_status": "decoded_unmapped", "future_metadata": metadata},
    )
    for module, name in ((producer, "derive_nano_attestation"), (checkpoint_backends, "derive_attestation")):
        monkeypatch.setattr(module, name, lambda *_, **__: {"model": config["model"]})
    trace_path = tmp_path / "trace.jsonl"
    monkeypatch.setenv("SGW01_TRACE_SIDECAR", str(trace_path))
    owner = producer.NanoEvidenceProducer(
        backend, trace_path=trace_path, future_dir=tmp_path / "futures",
        attestation_path=tmp_path / "attestation.json", expected_config=config,
    )
    owner.reset({"camera_name": CAMERAS[1]})
    request = {
        "request_id": "cell:request:0", "request_index": 0, "registered_cell_id": "cell",
        "reset_id": "physical-reset", "reset_fingerprint": "a" * 64,
        "camera_id": CAMERAS[1], "camera_name": CAMERAS[1],
        "prompt": "static positive", "sampling_seed": 8300, "observation": {},
    }
    response = owner.predict(request)
    raw = json.loads(trace_path.read_text())
    checked = read_trace_sidecar(request=request, response={"actions": response["action"]})
    assert raw["camera_name"] == raw["camera_id"] == CAMERAS[1]
    assert raw["camera_attribution_scope"] == "physical_reset_primary_camera_not_future_layout"
    assert response["camera_attribution_scope"] == raw["camera_attribution_scope"]
    assert raw["future_metadata"] == response["future_metadata"] == checked["future_metadata"] == metadata
    assert raw["future_shape"] == metadata["decoded_output_shape"]
    assert raw["future_status"] == "decoded_unmapped"
    assert raw["actions_sha256"] == hashlib.sha256(actions.tobytes()).hexdigest()
    np.testing.assert_array_equal(response["action"], actions)
    np.testing.assert_array_equal(checked["future"], future)
