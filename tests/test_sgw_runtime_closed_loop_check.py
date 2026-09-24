"""CPU contracts only: fake physics/models, real mailbox/HTTP/evidence paths."""
import csv
from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

import numpy as np
import pytest

from experiments.workshops.spatial_grounding_v1 import runtime_closed_loop_check as check
from experiments.workshops.spatial_grounding_v1 import native_runtime_check_receiver as receiver
from experiments.workshops.spatial_grounding_v1 import checkpoint_backends, producer
from experiments.workshops.spatial_grounding_v1 import robolab_jointpos_environment as jointpos
from experiments.workshops.spatial_grounding_v1.adapters import AdapterError
from experiments.workshops.spatial_grounding_v1.paper_engineering import record
from experiments.workshops.spatial_grounding_v1.policy_observations import CAMERAS
from experiments.workshops.spatial_grounding_v1.simulator_mailbox import _read, _write, _array, MailboxError
from test_sgw_jointpos_environment import candidate_json


def write(path, value):
    path.write_text(json.dumps(value))
    return record(path)


def specification(tmp_path, model="E3", **timeouts):
    candidate = tmp_path / "candidate.json"
    write(candidate, candidate_json())
    with Path("experiments/workshops/spatial_grounding_v1/spec/planned_cells.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    cell = next(row for row in rows if row["layout_id"] == "LAT-P01"
                and row["model"] == model and row["prompt_id"] == "LAT-D-POS")
    cell["fixture_sha256"] = "f" * 64
    queue = tmp_path / "bound-cells.jsonl"
    queue.write_text("".join(json.dumps(row) + "\n" for row in rows))
    native = {key: cell[key] for key in ("family", "layout_id", "fixture_sha256", "prompt_sha256")}
    native.update(candidate_path=str(candidate), candidate_file_sha256=record(candidate)["sha256"],
                  scene_seed=int(cell["environment_seed"]))
    binding = {
        "source_commit": "a" * 40, "source_root": str(tmp_path), "robolab_root": str(tmp_path),
        "assets_manifest": str(tmp_path / "assets.json"), "assets_manifest_sha256": "a" * 64,
        "camera_configuration": check.camera_configuration_identity(), "cells": {cell["cell_id"]: native},
    }
    binding_ref = write(tmp_path / "environment-binding.json", binding)
    prompts = record(Path("experiments/workshops/spatial_grounding_v1/spec/prompts.json"))
    handoff = {
        "source_commit": "a" * 40, "camera_configuration": check.camera_configuration_identity(),
        "status": "physical_qualified_runtime_pending", "runtime_qualified": False, "layout_count": 87, "cell_count": 1566,
        "files": {"environment-binding.json": binding_ref, "bound-cells.jsonl": record(queue)},
        "frozen_sources": {"prompts.json": prompts},
    }
    sample = check.example(model)
    value = sample["registration"]
    value.update(cell_id=cell["cell_id"], environment_binding=binding_ref,
                 materialization=write(tmp_path / "handoff.json", handoff), bound_cells=record(queue), prompts=prompts,
                 mailbox_root=str(tmp_path / "mailbox"), deadline_seconds=10,
                 mailbox_timeout_seconds=1, model_timeout_seconds=2)
    value.update(timeouts)
    launch = sample["launch_instruction"]
    launch["cell_id"] = cell["cell_id"]
    value["launch_instruction"] = write(tmp_path / "launch.json", launch)
    path = tmp_path / "registration.json"
    ref = write(path, value)
    identity = sample["identity"]
    identity.update(cell_id=cell["cell_id"], registration_sha256=ref["sha256"],
                    candidate_sha256=native["candidate_file_sha256"], binding_sha256=binding_ref["sha256"],
                    simulator_job_uid="actual-test-job", simulator_pod_uid="actual-test-pod")
    identity_path = tmp_path / "identity.json"
    identity_ref = write(identity_path, identity)
    return path, ref["sha256"], identity_path, identity_ref["sha256"]


def test_registration_tool_prepares_exact_current_attempt_and_binds_real_uid_shape(tmp_path):
    from tools.register_runtime_closed_loop import prepare, bind_identity

    specification(tmp_path)
    handoff = _read(tmp_path / "handoff.json")
    handoff["source_root"] = str(tmp_path / "source")
    handoff["frozen_sources"].update({
        name: record(Path("experiments/workshops/spatial_grounding_v1/spec") / name)
        for name in ("protocol.json", "planned_cells.csv")
    })
    write(tmp_path / "handoff.json", handoff)
    authority = _read(Path("handoff/cluster-execution-20260924/launch-instruction.json"))
    authority["scope"]["persistent_cohort_parent"] = str(tmp_path)
    auth_path = tmp_path / "current-authority.json"
    write(auth_path, authority)
    ref = prepare(model="E3", materialized=tmp_path, output=tmp_path / "technical-only", authorization=auth_path)
    registered = check.load_registration(Path(ref["path"]), ref["sha256"])
    assert registered.cell["status"] == "PLANNED_NOT_RELEASED"
    assert registered.value["maximum_model_requests"] == 2
    assert registered.value["maximum_executed_actions"] == 64
    identity = tmp_path / "technical-only/identity.json"
    bound = bind_identity(
        registration=Path(ref["path"]), registration_sha256=ref["sha256"], identity=identity,
        simulator_job_uid="00000000-0000-4000-8000-000000000001",
        simulator_pod_uid="00000000-0000-4000-8000-000000000002",
    )
    assert check.load_identity(identity, bound["sha256"], registered)["simulator_pod_uid"].endswith("002")
    assert identity.with_suffix(".sha256").read_text().strip() == bound["sha256"]
    with pytest.raises(FileExistsError):
        bind_identity(
            registration=Path(ref["path"]), registration_sha256=ref["sha256"], identity=identity,
            simulator_job_uid="00000000-0000-4000-8000-000000000001",
            simulator_pod_uid="00000000-0000-4000-8000-000000000002",
        )


class FakeEnvironment:
    def __init__(self, *, safety_at=None, delay=0, wrong_time=False):
        self.resets = self.closed = self.index = 0
        self.actions = []
        self.safety_at, self.delay, self.wrong_time = safety_at, delay, wrong_time

    def reset(self):
        self.resets += 1
        self.index = 0
        return SimpleNamespace(snapshot=self.snapshot(), receipt={
            "reset_id": f"physical-reset-{self.resets}", "candidate_fingerprint": "synthetic-candidate",
        })

    def step(self, action):
        self.actions.append(np.array(action))
        self.index += 1
        if self.delay:
            time.sleep(self.delay)
        return {"safety_terminated": len(self.actions) == self.safety_at,
                "termination_reason": "synthetic-native-safety" if len(self.actions) == self.safety_at else None}

    def snapshot(self):
        return {"sim_time": self.index / (30 if self.wrong_time else 15), "action_step": self.index}

    def render_viewport(self):
        return np.full((4, 6, 3), self.index, np.uint8)

    def policy_observation(self):
        image = np.arange(4 * 6 * 3, dtype=np.uint8).reshape(1, 4, 6, 3)
        return {
            "image_obs": {name: image + self.index + i for i, name in enumerate(CAMERAS)},
            "proprio_obs": {"arm_joint_pos": np.full((1, 7), self.index, np.float32),
                           "gripper_pos": np.full((1, 1), .5, np.float32)},
        }

    def close(self):
        self.closed += 1


@dataclass
class NanoConfig:
    seed: int = 1140
    deterministic_seed: bool = True


class Latent:
    dtype = "float32"
    def detach(self): return self
    def float(self): return self
    def cpu(self): return self
    def numpy(self): return np.ones((1, 2, 3, 1, 1), np.float32)


class FakeBackend:
    def __init__(self, model, *, fail_at=None, delay=0, status="decoded_unmapped"):
        self.model, self.fail_at, self.delay, self.status = model, fail_at, delay, status
        self.resolved_config = dict(check.CONFIGS[model])
        self.source_root = "/synthetic/source"
        self.checkpoint_path = "/synthetic/weights"
        self.base_path = "/synthetic/base"
        self.capture_future = False
        self.calls = []
        self.resets = 0
        self.service = SimpleNamespace(
            cfg=NanoConfig() if model == "N3" else {"synthetic": True},
            policy=SimpleNamespace(config={"synthetic": True}),
            model=SimpleNamespace(decode=lambda latent: np.ones((3, 4, 6, 3), np.uint8)),
        )

    def reset(self):
        self.resets += 1

    def predict(self, observation, prompt, seed):
        assert self.resets == (0 if self.model == "N3" else 1)
        assert len(observation) == 5
        self.calls.append({"prompt": prompt, "seed": seed,
                           "observed_index": observation["observation/joint_position"][0]})
        if self.fail_at == len(self.calls):
            raise AdapterError("synthetic model failure")
        if self.delay:
            time.sleep(self.delay)
        action = np.arange(256, dtype=np.float32).reshape(32, 8) / 1000 + len(self.calls) / 10
        result = {"action": action, "future_status": self.status}
        if self.status != "not_exposed":
            result["future_latent"] = Latent().numpy()
        if self.status == "decoded_unmapped":
            result["future"] = self.service.model.decode(Latent())
        if self.status == "decode_error":
            result["future_metadata"] = {"decode_error": "synthetic decode failure"}
        return result


def install(monkeypatch, spec, backend):
    path, sha, *_ = spec
    registration = check.load_registration(path, sha)
    binding = _read(registration.binding_path)
    native_binding = jointpos.JointPositionBinding(
        Path(binding["source_root"]), Path(binding["robolab_root"]), Path(binding["assets_manifest"]),
        binding["assets_manifest_sha256"], binding["cells"],
    )
    monkeypatch.setattr(jointpos.JointPositionBinding, "load", classmethod(lambda cls: native_binding))
    monkeypatch.setenv("SGW01_ENV_BINDING", str(registration.binding_path))
    monkeypatch.setenv("SGW01_ENV_BINDING_SHA256", registration.value["environment_binding"]["sha256"])
    monkeypatch.setenv("JOB_UID", "actual-test-job")
    monkeypatch.setenv("POD_UID", "actual-test-pod")
    monkeypatch.setattr(check, "_build_backend", lambda model: backend)
    attestations = []
    def attest(actual, *, expected_config):
        assert actual is backend and actual.resolved_config == expected_config
        attestations.append(actual)
        return {"model": backend.model, "config": backend.resolved_config, "test_only": True}
    monkeypatch.setattr(checkpoint_backends, "derive_attestation", attest)
    monkeypatch.setattr(producer, "derive_nano_attestation", attest)
    monkeypatch.setattr(check, "_runtime_record", lambda actual, model: {
        "resolved_config": actual.resolved_config, "synthetic_test_only": True,
    })
    return registration, native_binding, attestations


def start_receiver(spec, environment):
    errors, apps, refreshes = [], [], []
    class App:
        def close(self): apps.append("closed")
    def app_factory():
        apps.append("opened")
        return App()
    def target():
        try:
            receiver.run(*spec, metadata_refresh=lambda path: refreshes.append(path),
                         app_factory=app_factory, environment_factory=lambda **kwargs: environment)
        except BaseException as error:
            errors.append(error)
    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    return thread, errors, apps, refreshes


@pytest.mark.parametrize("model", ["N3", "E3", "F3"])
def test_two_live_chunks_exact_prefix_frames_resets_and_same_request_trace(tmp_path, monkeypatch, model):
    spec = specification(tmp_path, model)
    backend, environment = FakeBackend(model), FakeEnvironment()
    registration, binding, attestations = install(monkeypatch, spec, backend)
    thread, errors, apps, refreshes = start_receiver(spec, environment)
    result = check.run(*spec, tmp_path / "output", metadata_refresh=lambda path: refreshes.append(path))
    thread.join(3)
    assert not thread.is_alive() and not errors
    assert apps == ["opened", "closed"] and environment.closed == 1 and len(attestations) == 1
    assert result["model_requests_started"] == result["model_requests_completed"] == result["responses_validated"] == 2
    assert result["executed_action_count"] == result["acknowledged_action_count"] == len(environment.actions) == 64
    assert result["physical_resets_completed"] == environment.resets == 2
    assert [call["observed_index"] for call in backend.calls] == [0, 32]
    assert {call["seed"] for call in backend.calls} == {registration.seed}
    assert {call["prompt"] for call in backend.calls} == {registration.cell["prompt"]}
    assert result["status"] == "technical_check_completed" and result["behavioral_episodes"] == 0
    assert not result["release_permitted"] and not result["study_ready"]
    assert result["future_physics_mapping"] == "unavailable" and backend.capture_future is False
    assert result["receiver_completion"]["schema"] == receiver.COMPLETION_SCHEMA
    assert result["receiver_completion"]["command_count"] == 67
    assert any(path.name == "requests" for path in refreshes)
    observations = [json.loads(line) for line in (tmp_path / "output/observations.jsonl").read_text().splitlines()]
    assert len(observations) == 66
    steps = [row for row in observations if "prefix_offset" in row]
    assert [row["global_action_index"] for row in steps] == list(range(64))
    for index, row in enumerate(steps):
        assert row["prefix_offset"] == index % 32
        assert row["sim_time"] == pytest.approx((index + 1) / 15)
        packet = _read(Path(row["response"]["path"]))
        viewport = np.load(registration.root / "responses" / packet["data"]["viewport"]["path"])
        assert viewport[0, 0, 0] == index + 1
        np.testing.assert_array_equal(np.array(row["action"]), environment.actions[index])
    for index in range(2):
        chunk = result["requests"][index]
        assert chunk["executed_prefix"] == 32
        np.testing.assert_array_equal(np.load(chunk["actions"]["path"]), environment.actions[index * 32:(index + 1) * 32])
        assert Path(chunk["trace"]["future_path"]).is_file()
        assert Path(chunk["trace"]["future_latent_path"]).is_file()
        assert chunk["trace"]["request_index"] == index
    if model == "N3":
        assert (tmp_path / "output/request-00/vision-latent.npy").is_file()
    with pytest.raises(AdapterError, match="released"):
        binding.cell(registration.cell)
    with pytest.raises(FileExistsError):
        check.run(*spec, tmp_path / "output", metadata_refresh=lambda _: None)
    with pytest.raises(FileExistsError):
        receiver.run(*spec, app_factory=lambda: pytest.fail("must not create another simulator"))
    from experiments.workshops.spatial_grounding_v1.native_mailbox_receiver import verify_receiver_completion
    with pytest.raises(AdapterError):
        verify_receiver_completion(registration.root, _read(spec[2]))


@pytest.mark.parametrize("safety_at", [5, 36])
def test_valid_safety_truncation_never_requests_or_executes_extra_prefix(tmp_path, monkeypatch, safety_at):
    spec = specification(tmp_path)
    backend, environment = FakeBackend("E3"), FakeEnvironment(safety_at=safety_at)
    install(monkeypatch, spec, backend)
    thread, errors, _, _ = start_receiver(spec, environment)
    result = check.run(*spec, tmp_path / "output", metadata_refresh=lambda _: None)
    thread.join(3)
    assert not errors and result["status"] == "technical_safety_terminated"
    assert result["executed_action_count"] == safety_at and len(backend.calls) == (1 if safety_at < 32 else 2)
    assert result["physical_resets_completed"] == 2 and result["safety_terminated"]


@pytest.mark.parametrize("status", ["not_exposed", "decode_error"])
def test_future_unavailability_is_not_a_fabricated_alignment_or_extra_sample(tmp_path, monkeypatch, status):
    spec = specification(tmp_path, "F3")
    backend = FakeBackend("F3", status=status)
    install(monkeypatch, spec, backend)
    thread, errors, _, _ = start_receiver(spec, FakeEnvironment(safety_at=1))
    result = check.run(*spec, tmp_path / "output", metadata_refresh=lambda _: None)
    thread.join(3)
    assert not errors and len(backend.calls) == 1
    assert result["requests"][0]["future_status"] == status
    assert result["future_physics_mapping"] == "unavailable"
    assert "future_path" not in result["requests"][0]["trace"]


@pytest.mark.parametrize("fail_at,executed", [(1, 0), (2, 32)])
def test_model_failure_retains_partial_then_second_reset_without_retry(tmp_path, monkeypatch, fail_at, executed):
    spec = specification(tmp_path)
    backend, environment = FakeBackend("E3", fail_at=fail_at), FakeEnvironment()
    install(monkeypatch, spec, backend)
    thread, errors, _, _ = start_receiver(spec, environment)
    with pytest.raises(RuntimeError, match="partial evidence"):
        check.run(*spec, tmp_path / "output", metadata_refresh=lambda _: None)
    thread.join(3)
    failure = _read(tmp_path / "output/failure.json")
    assert not errors
    assert failure["model_requests_started"] == fail_at and failure["model_requests_completed"] == fail_at - 1
    assert len(backend.calls) == fail_at and failure["executed_action_count"] == executed
    assert failure["physical_resets_completed"] == 2 and len(environment.actions) == executed
    assert not (tmp_path / "output/result.json").exists()
    assert (tmp_path / f"output/request-{fail_at - 1:02d}/intent.json").is_file()


def test_http_timeout_drains_native_call_but_never_executes_late_actions(tmp_path, monkeypatch):
    spec = specification(tmp_path, model_timeout_seconds=.01)
    backend, environment = FakeBackend("E3", delay=.08), FakeEnvironment()
    install(monkeypatch, spec, backend)
    thread, errors, _, _ = start_receiver(spec, environment)
    with pytest.raises(RuntimeError):
        check.run(*spec, tmp_path / "output", metadata_refresh=lambda _: None)
    thread.join(3)
    failure = _read(tmp_path / "output/failure.json")
    assert not errors and failure["model_requests_started"] == failure["model_requests_completed"] == 1
    assert failure["responses_validated"] == failure["executed_action_count"] == 0
    assert (tmp_path / "output/request-00/backend-actions.npy").is_file()
    assert len((tmp_path / "output/trace.jsonl").read_text().splitlines()) == 1
    assert _read(tmp_path / "output/shutdown.json")["serving_thread_alive"] is False


def test_constructor_failure_closes_unstarted_receiver_without_fake_resets(tmp_path, monkeypatch):
    spec = specification(tmp_path)
    backend, environment = FakeBackend("E3"), FakeEnvironment()
    install(monkeypatch, spec, backend)
    def fail_build(model):
        raise AdapterError("synthetic constructor failure before any model request")
    monkeypatch.setattr(check, "_build_backend", fail_build)
    thread, errors, apps, _ = start_receiver(spec, environment)
    with pytest.raises(RuntimeError):
        check.run(*spec, tmp_path / "output", metadata_refresh=lambda _: None)
    thread.join(3)
    failure = _read(tmp_path / "output/failure.json")
    assert not errors and apps == ["opened", "closed"]
    assert environment.closed == 1 and environment.resets == 0
    assert failure["model_requests_started"] == failure["model_requests_completed"] == failure["executed_action_count"] == 0
    assert failure["receiver_completion"]["status"] == "aborted_before_physical_reset"
    assert not (tmp_path / "output/result.json").exists()


def test_trace_hash_corruption_preserves_raw_outputs_without_executing(tmp_path, monkeypatch):
    spec = specification(tmp_path)
    backend, environment = FakeBackend("E3"), FakeEnvironment()
    install(monkeypatch, spec, backend)
    real_post = check.fixed.post
    def corrupt(url, payload, **kwargs):
        reply = real_post(url, payload, **kwargs)
        if url.endswith("/predict"):
            reply["action"][0][0] += 1
        return reply
    monkeypatch.setattr(check.fixed, "post", corrupt)
    thread, errors, _, _ = start_receiver(spec, environment)
    with pytest.raises(RuntimeError):
        check.run(*spec, tmp_path / "output", metadata_refresh=lambda _: None)
    thread.join(3)
    failure = _read(tmp_path / "output/failure.json")
    assert not errors and len(backend.calls) == 1 and not environment.actions
    assert failure["model_requests_completed"] == 1 and failure["responses_validated"] == 0
    assert failure["physical_resets_completed"] == 2 and "action hash differs" in failure["traceback"]
    assert (tmp_path / "output/request-00/backend-actions.npy").exists()
    assert (tmp_path / "output/request-00/response.json").exists()


def test_mailbox_timeout_does_not_replay_or_invent_final_execution_count(tmp_path, monkeypatch):
    spec = specification(tmp_path, deadline_seconds=2, mailbox_timeout_seconds=.3, model_timeout_seconds=.5)
    backend, environment = FakeBackend("E3"), FakeEnvironment(delay=.6)
    install(monkeypatch, spec, backend)
    thread, _, _, _ = start_receiver(spec, environment)
    with pytest.raises(RuntimeError):
        check.run(*spec, tmp_path / "output", metadata_refresh=lambda _: None)
    thread.join(3)
    failure = _read(tmp_path / "output/failure.json")
    assert failure["executed_action_count"] is None and failure["acknowledged_action_count"] == 0
    assert environment.resets == 1 and len(environment.actions) == 1
    assert len(list((tmp_path / "mailbox/requests").glob("*.json"))) == 2
    assert _read(tmp_path / "mailbox/receiver_failure.json")["counts"]["executed_action_count"] == 1


@pytest.mark.parametrize("field,value", [
    ("maximum_model_requests", 3), ("physical_resets", 3), ("maximum_executed_actions", 65),
    ("release_permitted", True), ("behavioral_episodes", 1), ("model", "D1"),
    ("model_config", check.NANO_CONFIG), ("camera_configuration", {"revision": "old"}),
    ("deadline_seconds", float("inf")), ("model_timeout_seconds", True), ("runtime_factory", "fake:factory"),
])
def test_registration_rejects_expanded_or_unbound_authority(tmp_path, field, value):
    path, _, _, _ = specification(tmp_path)
    spec = _read(path)
    spec[field] = value
    changed = write(path, spec)
    with pytest.raises((ValueError, KeyError)):
        check.load_registration(path, changed["sha256"])


@pytest.mark.parametrize("target", ["launch", "candidate", "cell_status", "cell_seed"])
def test_launch_candidate_and_frozen_cell_changes_fail_closed(tmp_path, target):
    path, sha, _, _ = specification(tmp_path)
    spec = _read(path)
    if target == "launch":
        Path(spec["launch_instruction"]["path"]).write_text("{}")
    elif target == "candidate":
        (tmp_path / "candidate.json").write_text("{}")
    else:
        queue = Path(spec["bound_cells"]["path"])
        rows = [json.loads(line) for line in queue.read_text().splitlines()]
        selected = next(row for row in rows if row["cell_id"] == spec["cell_id"])
        selected["status" if target == "cell_status" else "effective_policy_seed"] = "RELEASED" if target == "cell_status" else "1140"
        queue.write_text("".join(json.dumps(row) + "\n" for row in rows))
        spec["bound_cells"] = record(queue)
        handoff = _read(Path(spec["materialization"]["path"]))
        handoff["files"]["bound-cells.jsonl"] = spec["bound_cells"]
        spec["materialization"] = write(Path(spec["materialization"]["path"]), handoff)
        sha = write(path, spec)["sha256"]
    with pytest.raises(ValueError):
        check.load_registration(path, sha)


def test_explicit_qualification_path_cannot_weaken_default_release_guard(tmp_path, monkeypatch):
    spec = specification(tmp_path)
    registration, binding, _ = install(monkeypatch, spec, FakeBackend("E3"))
    original = dict(registration.cell)
    bound, candidate = binding.qualification_cell(registration_path=spec[0], registration_sha256=spec[1])
    assert bound == registration.binding_record and candidate.family == "LAT" and registration.cell == original
    with pytest.raises(AdapterError, match="released"):
        jointpos.create_environment(cell=registration.cell, evidence_root=tmp_path / "production")
    calls = []
    monkeypatch.setattr(jointpos, "_create_bound_environment", lambda *args: calls.append(args))
    jointpos.create_qualification_environment(registration_path=spec[0], registration_sha256=spec[1],
                                             evidence_root=tmp_path / "qualified")
    assert len(calls) == 1 and calls[0][0] == binding and calls[0][1] == original
    assert calls[0][1]["status"] == "PLANNED_NOT_RELEASED"
    monkeypatch.setenv("SGW01_ENV_BINDING_SHA256", "0" * 64)
    with pytest.raises(AdapterError, match="actual environment binding"):
        binding.qualification_cell(registration_path=spec[0], registration_sha256=spec[1])


@pytest.mark.parametrize("field", ["simulator_job_uid", "simulator_pod_uid", "candidate_sha256", "registration_sha256", "release_id"])
def test_identity_rejection_precedes_app_launcher(tmp_path, monkeypatch, field):
    spec = specification(tmp_path)
    install(monkeypatch, spec, FakeBackend("E3"))
    identity = _read(spec[2])
    identity[field] = "wrong"
    changed = write(spec[2], identity)
    with pytest.raises(RuntimeError):
        receiver.run(spec[0], spec[1], spec[2], changed["sha256"],
                     app_factory=lambda: pytest.fail("identity must be checked before AppLauncher"))
    assert (tmp_path / "mailbox/receiver_failure.json").exists()
    assert not (tmp_path / "mailbox/receiver_ready.json").exists()


def test_new_modules_import_without_native_models(tmp_path):
    result = subprocess.run([sys.executable, "-c",
        "import sys; from experiments.workshops.spatial_grounding_v1 import runtime_closed_loop_check, native_runtime_check_receiver; "
        "assert not {'torch','isaaclab','robolab','cosmos_framework','flux_action'} & set(sys.modules)"],
        capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_receiver_enforces_prefix_limit_reset_order_and_preserves_bad_time_frames(tmp_path):
    root = tmp_path / "channel"
    root.mkdir()
    for name in ("requests", "responses", "faults"):
        (root / name).mkdir()
    environment = FakeEnvironment()
    bounded = receiver.BoundedEnvironment(environment, root, time.monotonic() + 5)
    with pytest.raises(MailboxError):
        bounded.step(np.zeros(8))
    bounded.reset()
    for _ in range(64):
        bounded.step(np.zeros(8))
        bounded.check_action_time()
    with pytest.raises(MailboxError):
        bounded.step(np.zeros(8))
    bounded.reset()
    with pytest.raises(MailboxError):
        bounded.reset()
    with pytest.raises(MailboxError):
        bounded.step(np.zeros(8))
    assert len(environment.actions) == 64 and environment.resets == 2

    wrong = FakeEnvironment(wrong_time=True)
    bounded = receiver.BoundedEnvironment(wrong, root, time.monotonic() + 5)
    bounded.reset()
    identity = {"channel_nonce": "synthetic-only"}
    instance = receiver.TechnicalMailboxReceiver(root=root, identity=identity, environment=bounded)
    action_ref = _array(root / "requests/action.npy", np.zeros(8, np.float32))
    command = root / "requests/0001-step.json"
    _write(command, {"schema": "sgw-01-simulator-mailbox-v1", "operation": "step", "command_id": 1,
                     "identity": identity, "channel_nonce": identity["channel_nonce"], "payload": {"action": action_ref}})
    with pytest.raises(MailboxError, match="15Hz"):
        instance.serve_one(command)
    assert (root / "responses/0001-step.json").exists()
    assert (root / "responses/0001-step.viewport.npy").exists()
    assert (root / "faults/0001-step.json").exists() and len(wrong.actions) == 1
