"""Synthetic CPU-only diagnostics: real loopback, fake checkpoint backends."""

import json
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace

import numpy as np
import pytest

from experiments.workshops.spatial_grounding_v1 import checkpoint_fixed_input as diagnostic
from experiments.workshops.spatial_grounding_v1 import checkpoint_backends
from experiments.workshops.spatial_grounding_v1.adapters import AdapterError
from experiments.workshops.spatial_grounding_v1.paper_engineering import record
from test_sgw_nano_fixed_input import current_registration


def write_json(path, value):
    path.write_text(json.dumps(value))
    return record(path)


def make_registration(tmp_path):
    value = current_registration(tmp_path)
    value["registration_id"] = "synthetic-current-N3-input"
    queue = Path(value["bound_cells"]["path"])
    rows = [json.loads(line) for line in queue.read_text().splitlines()]
    binding_path = Path(value["environment_binding"]["path"])
    binding = json.loads(binding_path.read_text())
    for row in rows:
        if row["layout_id"] == "LAT-P01" and row["model"] in ("E3", "F3"):
            row["effective_policy_seed"] = {"E3": "12345", "F3": "54321"}[row["model"]]
            binding["cells"][row["cell_id"]] = {"candidate_file_sha256": "b" * 64}
    queue.write_text("".join(json.dumps(row) + "\n" for row in rows))
    value["bound_cells"] = record(queue)
    value["environment_binding"] = write_json(binding_path, binding)
    materialization = Path(value["materialization"]["path"])
    handoff = json.loads(materialization.read_text())
    handoff["files"].update({"bound-cells.jsonl": value["bound_cells"],
                            "environment-binding.json": value["environment_binding"]})
    value["materialization"] = write_json(materialization, handoff)
    path = tmp_path / "registration.json"
    write_json(path, value)
    return path


class FakeBackend:
    def __init__(self, model, *, fail_at=None, future_status="decoded_unmapped", drift=False, delay=0):
        self.resolved_config = dict(diagnostic.CONFIGS[model])
        self.source_root = "/synthetic/source"
        self.checkpoint_path = "/synthetic/checkpoint"
        self.base_path = "/synthetic/base"
        cfg = {"test_only": True, "no_native_inference": True}
        self.service = SimpleNamespace(cfg=cfg, policy=SimpleNamespace(config=SimpleNamespace(to_dict=lambda: cfg)))
        self.model, self.fail_at, self.future_status, self.drift, self.delay = model, fail_at, future_status, drift, delay
        self.capture_future = False
        self.calls = []
        self.resets = 0
        self.reset_ready = False
        self.first_prompt = None
        self.evidence_root = None

    def reset(self):
        if self.evidence_root is not None:
            assert (self.evidence_root / f"request-{len(self.calls):02d}" / "intent.json").is_file()
        self.resets += 1
        self.reset_ready = True

    def predict(self, observation, prompt, seed):
        assert self.reset_ready
        self.reset_ready = False
        assert self.resets == len(self.calls) + 1
        assert set(observation) == {
            "observation/wrist_image_left", "observation/exterior_image_1_left",
            "observation/exterior_image_2_left", "observation/joint_position",
            "observation/gripper_position",
        }
        self.first_prompt = self.first_prompt or prompt
        capture = self.model == "E3" or self.capture_future
        self.calls.append({"prompt": prompt, "seed": seed, "capture": capture})
        if len(self.calls) == self.fail_at:
            raise AdapterError("synthetic native failure; no retry")
        if self.delay:
            time.sleep(self.delay)
        actions = np.arange(256, dtype=np.float32).reshape(32, 8) / 1000
        if prompt != self.first_prompt:
            actions += 0.5
        if self.drift and not capture:
            actions += 0.01
        result = {"action": actions, "future_status": self.future_status if capture else "not_exposed"}
        if capture and self.future_status != "not_exposed":
            result["future_latent"] = np.full((1, 2, 3, 1, 1), len(self.calls), np.float32)
            result["future_metadata"] = {"synthetic_request_number": len(self.calls)}
        if capture and self.future_status == "decoded_unmapped":
            result["future"] = np.full((5, 2, 2, 3), len(self.calls), np.uint8)
        if capture and self.future_status == "decode_error":
            result["future_metadata"]["decode_error"] = "synthetic decoder error"
        return result


def install_backend(monkeypatch, backend):
    attestations = []
    servers = []
    def attest(actual, *, expected_config):
        assert actual is backend and expected_config == backend.resolved_config
        attestations.append(actual)
        return {"model": backend.model, "config": backend.resolved_config, "test_only": True}
    def build(model):
        assert model == backend.model
        return backend
    original_server = diagnostic.make_nano_http_server
    def server(*args, **kwargs):
        result = original_server(*args, **kwargs)
        servers.append(result)
        return result
    monkeypatch.setattr(diagnostic, "_build_backend", build)
    monkeypatch.setattr(checkpoint_backends, "derive_attestation", attest)
    monkeypatch.setattr(diagnostic, "make_nano_http_server", server)
    return attestations, servers


@pytest.mark.parametrize("model,seed", [("E3", 12345), ("F3", 54321)])
def test_six_current_input_requests_use_model_seed_full_resets_and_owned_trace(tmp_path, monkeypatch, model, seed):
    registration = make_registration(tmp_path)
    backend = FakeBackend(model)
    attestations, servers = install_backend(monkeypatch, backend)
    monkeypatch.setenv("HF_HUB_OFFLINE", "prior")
    monkeypatch.setenv("SGW01_TRACE_SIDECAR", "prior-sidecar")
    output = tmp_path / "run"
    backend.evidence_root = output
    result = diagnostic.run(registration, output, model=model, request_timeout=5)
    assert len(attestations) == len(servers) == 1
    assert result["model_requests_started"] == result["model_requests_completed"] == result["responses_validated"] == 6
    assert result["executed_actions"] == result["behavioral_episodes"] == 0
    assert not result["release_permitted"] and not result["closed_loop_ready"]
    assert not result["physical_camera_time_alignment_qualified"] and not result["n3_runtime_qualification_reused"]
    assert backend.resets == len(backend.calls) == 6
    assert {item["seed"] for item in backend.calls} == {seed}
    assert [item["capture"] for item in backend.calls] == ([True] * 6 if model == "E3" else [True] * 3 + [False] * 3)
    assert [item["prompt_id"] for item in result["requests"]] == diagnostic.fixed.ORDER
    assert result["comparisons"]["repeat_equal"] == [True, True]
    assert result["comparisons"]["opposite_prompt_distinct"] == [True, True]
    assert result["capture_parity"]["capture_enabled_vs_disabled_equal"] == ([True] * 3 if model == "F3" else None)
    rows = [json.loads(line) for line in (output / "trace.jsonl").read_text().splitlines()]
    assert len({row["request_id"] for row in rows}) == 6
    for index, row in enumerate(rows):
        assert row["request_id"].startswith(model + "-current-fixed-input-")
        assert row["request_index"] == 0
        assert row["effective_sampling_seed"] == seed
        assert (output / f"request-{index:02d}" / "intent.json").is_file()
        request = result["requests"][index]
        assert request["registered_cell_id"] == row["registered_cell_id"]
        np.testing.assert_array_equal(np.load(request["actions"]["path"]), np.load(output / f"request-{index:02d}" / "backend-actions.npy"))
        if backend.calls[index]["capture"]:
            assert np.load(row["future_path"]).flat[0] == index + 1
            assert np.load(row["future_latent_path"]).flat[0] == index + 1
        else:
            assert row["future_status"] == "not_exposed" and "future_path" not in row
    loaded = json.loads((output / "loaded-runtime.json").read_text())
    assert loaded["resolved_config"] == diagnostic.CONFIGS[model]
    assert loaded["source_commit"] == diagnostic.CONFIGS[model]["source_commit"]
    assert loaded["checkpoint_revision"] == diagnostic.CONFIGS[model]["revision"]
    assert "numpy" in loaded["versions"] and loaded["python"]
    shutdown = json.loads((output / "shutdown.json").read_text())
    assert shutdown == {"server_closed": True, "server_started": True, "serving_thread_alive": False}
    assert servers[0].server_address[0] == "127.0.0.1" and servers[0].socket.fileno() == -1
    assert backend.capture_future is False
    import os
    assert os.environ["HF_HUB_OFFLINE"] == "prior" and os.environ["SGW01_TRACE_SIDECAR"] == "prior-sidecar"
    original_result = (output / "result.json").read_bytes()
    with pytest.raises(FileExistsError):
        diagnostic.run(registration, output, model=model)
    assert (output / "result.json").read_bytes() == original_result and len(backend.calls) == 6


@pytest.mark.parametrize("future_status", ["not_exposed", "decode_error"])
def test_missing_future_and_action_parity_mismatch_are_preserved_not_erased(tmp_path, monkeypatch, future_status):
    registration = make_registration(tmp_path)
    backend = FakeBackend("F3", future_status=future_status, drift=True)
    install_backend(monkeypatch, backend)
    result = diagnostic.run(registration, tmp_path / "run", model="F3")
    assert result["responses_validated"] == 6
    assert result["capture_parity"]["capture_enabled_vs_disabled_equal"] == [False] * 3
    assert all(value > 0 for value in result["capture_parity"]["max_absolute_action_difference"])
    assert [item["future_status"] for item in result["requests"]] == [future_status] * 3 + ["not_exposed"] * 3
    for item in result["requests"][:3]:
        assert "future_path" not in item["trace"]
        if future_status == "decode_error":
            assert "future_latent_path" in item["trace"]
            assert item["trace"]["future_metadata"]["decode_error"] == "synthetic decoder error"
    assert not result["physical_camera_time_alignment_qualified"]


def test_first_technical_failure_stops_with_honest_partial_counts(tmp_path, monkeypatch):
    registration = make_registration(tmp_path)
    backend = FakeBackend("F3", fail_at=2)
    _, servers = install_backend(monkeypatch, backend)
    output = tmp_path / "run"
    with pytest.raises(Exception, match="400"):
        diagnostic.run(registration, output, model="F3")
    failure = json.loads((output / "failure.json").read_text())
    assert failure["http_prediction_attempts"] == failure["model_requests_started"] == 2
    assert failure["model_requests_completed"] == failure["responses_validated"] == 1
    assert len(backend.calls) == backend.resets == 2 and backend.capture_future is False
    assert (output / "request-00" / "result.json").is_file()
    assert (output / "request-01" / "intent.json").is_file()
    assert not (output / "request-02").exists() and not (output / "result.json").exists()
    assert servers[0].socket.fileno() == -1


def test_timeout_drains_once_without_retries_and_preserves_late_native_evidence(tmp_path, monkeypatch):
    registration = make_registration(tmp_path)
    backend = FakeBackend("F3", delay=0.1)
    install_backend(monkeypatch, backend)
    output = tmp_path / "run"
    with pytest.raises(TimeoutError):
        diagnostic.run(registration, output, model="F3", request_timeout=0.01)
    failure = json.loads((output / "failure.json").read_text())
    assert failure["http_prediction_attempts"] == failure["model_requests_started"] == failure["model_requests_completed"] == 1
    assert failure["responses_validated"] == 0
    assert len(backend.calls) == 1 and (output / "request-00" / "backend-actions.npy").is_file()
    assert len((output / "trace.jsonl").read_text().splitlines()) == 1
    assert not (output / "request-01").exists()


def test_trace_hash_failure_retains_raw_response_and_actual_backend_actions(tmp_path, monkeypatch):
    registration = make_registration(tmp_path)
    backend = FakeBackend("E3")
    install_backend(monkeypatch, backend)
    real_post = diagnostic.fixed.post
    def corrupt(url, packet, **kwargs):
        result = real_post(url, packet, **kwargs)
        if url.endswith("/predict"):
            result["action"][0][0] += 1
        return result
    monkeypatch.setattr(diagnostic.fixed, "post", corrupt)
    output = tmp_path / "run"
    with pytest.raises(AdapterError, match="action hash"):
        diagnostic.run(registration, output, model="E3")
    failure = json.loads((output / "failure.json").read_text())
    assert failure["model_requests_started"] == failure["model_requests_completed"] == 1
    assert failure["responses_validated"] == 0
    assert (output / "request-00" / "response.json").is_file()
    assert np.load(output / "request-00" / "backend-actions.npy")[0, 0] == 0
    assert np.load(output / "request-00" / "actions.npy")[0, 0] == 1


def test_native_attestation_stays_active_and_failure_starts_no_requests(tmp_path, monkeypatch):
    registration = make_registration(tmp_path)
    backend = FakeBackend("E3")
    install_backend(monkeypatch, backend)
    def fail(*_args, **_kwargs):
        raise AdapterError("synthetic source/checkpoint identity mismatch")
    monkeypatch.setattr(checkpoint_backends, "derive_attestation", fail)
    output = tmp_path / "run"
    with pytest.raises(AdapterError, match="identity mismatch"):
        diagnostic.run(registration, output, model="E3")
    failure = json.loads((output / "failure.json").read_text())
    assert failure["model_requests_started"] == failure["model_requests_completed"] == 0
    assert not backend.calls and not backend.resets


def test_obsolete_registration_never_reaches_historical_gate(tmp_path, monkeypatch):
    path = tmp_path / "old.json"
    write_json(path, {"schema_version": diagnostic.fixed.SCHEMA})
    monkeypatch.setattr(diagnostic.fixed, "load_registration", lambda _: pytest.fail("legacy loader entered"))
    monkeypatch.setattr(diagnostic, "_build_backend", lambda _: pytest.fail("model construction attempted"))
    with pytest.raises(ValueError, match="only the current"):
        diagnostic.run(path, tmp_path / "run", model="E3")
    failure = json.loads((tmp_path / "run" / "failure.json").read_text())
    assert failure["model_requests_started"] == 0


@pytest.mark.parametrize("change", ["candidate", "mixed_seed", "wrong_prompt", "released"])
def test_target_model_must_match_current_model_specific_binding(tmp_path, change):
    path = make_registration(tmp_path)
    value = json.loads(path.read_text())
    queue = Path(value["bound_cells"]["path"])
    rows = [json.loads(line) for line in queue.read_text().splitlines()]
    target = next(row for row in rows if row["model"] == "E3" and row["layout_id"] == "LAT-P01")
    if change == "candidate":
        binding_path = Path(value["environment_binding"]["path"])
        binding = json.loads(binding_path.read_text())
        binding["cells"][target["cell_id"]]["candidate_file_sha256"] = "c" * 64
        value["environment_binding"] = write_json(binding_path, binding)
    else:
        target[{"mixed_seed": "effective_policy_seed", "wrong_prompt": "prompt", "released": "status"}[change]] = {
            "mixed_seed": "12", "wrong_prompt": "rewritten", "released": "RELEASED",
        }[change]
        queue.write_text("".join(json.dumps(row) + "\n" for row in rows))
        value["bound_cells"] = record(queue)
    materialization = Path(value["materialization"]["path"])
    handoff = json.loads(materialization.read_text())
    handoff["files"].update({"bound-cells.jsonl": value["bound_cells"], "environment-binding.json": value["environment_binding"]})
    value["materialization"] = write_json(materialization, handoff)
    write_json(path, value)
    with pytest.raises(ValueError, match="target model"):
        diagnostic.load_input(path, "E3")


def test_changed_input_hash_is_rejected_before_backend_construction(tmp_path, monkeypatch):
    path = make_registration(tmp_path)
    value = json.loads(path.read_text())
    Path(value["observation"]["path"]).write_bytes(b"changed")
    monkeypatch.setattr(diagnostic, "_build_backend", lambda _: pytest.fail("model construction attempted"))
    with pytest.raises(ValueError, match="bytes differ"):
        diagnostic.run(path, tmp_path / "run", model="F3")


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan")])
def test_timeout_must_be_finite_positive(tmp_path, timeout):
    with pytest.raises(ValueError, match="finite positive"):
        diagnostic.run(tmp_path / "unused", tmp_path / "run", model="E3", request_timeout=timeout)
    assert not (tmp_path / "run").exists()


def test_module_and_help_import_no_model_libraries():
    code = """
import importlib.abc, runpy, sys
class Guard(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, *args):
        if fullname.split('.')[0] in {'torch', 'cosmos_framework', 'flux_action'}:
            raise RuntimeError('model import at CLI/module boundary: ' + fullname)
sys.meta_path.insert(0, Guard())
sys.argv = ['checkpoint_fixed_input', '--help']
runpy.run_module('experiments.workshops.spatial_grounding_v1.checkpoint_fixed_input', run_name='__main__')
"""
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert "--registration" in result.stdout and "--request-timeout" in result.stdout
