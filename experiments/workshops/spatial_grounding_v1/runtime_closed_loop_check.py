"""Two-request, 64-action technical check; never a behavioral release.

Print the complete registration/launch/identity template with ``--example N3``.
Both lanes require --registration, --registration-sha256, --identity and
--identity-sha256. This model lane additionally requires --output NEW_DIRECTORY.
Use the existing pinned backend environment and offline weights. Native model
output is assigned inside the new output directory. The simulator lane is
native_runtime_check_receiver.

The model is owned in-process behind the real attested loopback HTTP producer,
not the production subprocess owner. HTTP timeouts do not cancel native GPU
work: shutdown drains the call; the coordinator MUST impose a finite process/Job
deadline. No timed-out request or action is retried. Future/physics mapping is
unavailable even when all commands complete.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, replace
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import threading
import time
import traceback
from typing import Any, Mapping

import numpy as np

from .adapters import NANO_CONFIG, EDGE_CONFIG, FLUX_CONFIG, _integer_seed
from .camera_configuration import camera_configuration_identity
from . import nano_fixed_input as fixed
from .checkpoint_fixed_input import _loaded_runtime
from .family_campaign_executor import _fsync_json
from .paper_engineering import bound_file, record
from .policy_observations import nano_observation
from .producer import NanoEvidenceProducer, make_nano_http_server
from .simulator_mailbox import MailboxClient, MailboxError, _read, _digest
from .trace import read_trace_sidecar

SCHEMA = "sgw-01-runtime-closed-loop-check-v1"
SCOPE = "bounded_native_runtime_qualification"
CONFIGS = {"N3": NANO_CONFIG, "E3": EDGE_CONFIG, "F3": FLUX_CONFIG}
LIMITS = {
    "maximum_model_requests": 2, "actions_per_chunk": 32,
    "maximum_executed_actions": 64, "physical_resets": 2,
    "behavioral_episodes": 0, "release_permitted": False,
}
CAMERA = "over_shoulder_left_camera"
DISCLAIMER = {
    "attempt_scope": SCOPE, "behavioral_episodes": 0, "release_permitted": False,
    "future_physics_mapping": "unavailable",
    "physical_forecast_alignment_qualified": False, "study_ready": False,
}


@dataclass(frozen=True)
class Registration:
    path: Path
    sha256: str
    value: dict[str, Any]
    cell: dict[str, Any]
    binding_path: Path
    binding_record: dict[str, Any]

    @property
    def root(self) -> Path:
        return Path(self.value["mailbox_root"])

    @property
    def seed(self) -> int:
        return _integer_seed(self.cell["effective_policy_seed"], "effective_policy_seed")


def _hashed_json(path: Path, expected: str) -> dict[str, Any]:
    if (not isinstance(expected, str) or len(expected) != 64
            or any(c not in "0123456789abcdef" for c in expected)
            or _digest(path) != expected):
        raise ValueError("qualification JSON hash mismatch")
    value = _read(path)
    return value


def load_registration(path: Path, expected_sha256: str) -> Registration:
    value = _hashed_json(path, expected_sha256)
    keys = {
        "schema_version", "scope", "qualification_id", "attempt_id", "model", "model_config",
        "cell_id", "launch_instruction", "materialization", "environment_binding", "bound_cells",
        "prompts", "camera_configuration", "mailbox_root", "deadline_seconds",
        "mailbox_timeout_seconds", "model_timeout_seconds", *LIMITS,
    }
    model = value.get("model")
    if (set(value) != keys or value.get("schema_version") != SCHEMA or value.get("scope") != SCOPE
            or model not in CONFIGS
            or json.dumps(value.get("model_config"), sort_keys=True) != json.dumps(CONFIGS[model], sort_keys=True)
            or any(type(value.get(k)) is not type(v) or value[k] != v for k, v in LIMITS.items())
            or value.get("camera_configuration") != camera_configuration_identity()):
        raise ValueError("not the explicit bounded technical qualification registration")
    for key in ("qualification_id", "attempt_id", "cell_id", "mailbox_root"):
        if not isinstance(value[key], str) or not value[key]:
            raise ValueError(f"qualification requires {key}")
    if not Path(value["mailbox_root"]).is_absolute():
        raise ValueError("qualification mailbox must be an absolute, attempt-exclusive path")
    for key in ("deadline_seconds", "mailbox_timeout_seconds", "model_timeout_seconds"):
        number = value[key]
        if type(number) not in (int, float) or not math.isfinite(number) or not 0 < number <= 14400:
            raise ValueError("qualification requires finite bounded timeouts")
    if max(value["mailbox_timeout_seconds"], value["model_timeout_seconds"]) > value["deadline_seconds"]:
        raise ValueError("request timeout exceeds the lane wall deadline")
    launch = json.loads(bound_file(value["launch_instruction"]).read_bytes())
    for key in ("scope", "qualification_id", "attempt_id", "model", "cell_id", *LIMITS):
        if type(launch.get(key)) is not type(value[key]) or launch[key] != value[key]:
            raise ValueError("launch instruction does not authorize this exact technical attempt")
    if (launch.get("schema_version") != "sgw-01-runtime-check-launch-v1"
            or not isinstance(launch.get("instruction"), str) or not launch["instruction"].strip()):
        raise ValueError("explicit hash-bound launch instruction is required")
    handoff = json.loads(bound_file(value["materialization"]).read_bytes())
    binding_path = bound_file(value["environment_binding"])
    binding = json.loads(binding_path.read_bytes())
    rows = [json.loads(line) for line in bound_file(value["bound_cells"]).read_text().splitlines() if line]
    prompt_rows = json.loads(bound_file(value["prompts"]).read_bytes())["prompts"]
    if (handoff.get("status") != "physical_qualified_runtime_pending"
            or handoff.get("runtime_qualified") is not False
            or handoff.get("layout_count") != 87 or handoff.get("cell_count") != 1566
            or len(rows) != 1566 or len({row["cell_id"] for row in rows}) != 1566
            or any(item.get("camera_configuration") != value["camera_configuration"] for item in (handoff, binding))
            or binding.get("source_commit") != handoff.get("source_commit")
            or value["environment_binding"]["sha256"] != handoff["files"]["environment-binding.json"]["sha256"]
            or value["bound_cells"]["sha256"] != handoff["files"]["bound-cells.jsonl"]["sha256"]
            or value["prompts"]["sha256"] != handoff["frozen_sources"]["prompts.json"]["sha256"]
            or len(prompt_rows) != 18 or len({p["prompt_id"] for p in prompt_rows}) != 18):
        raise ValueError("qualification differs from current materialization/cameras/frozen inputs")
    selected = [row for row in rows if row["cell_id"] == value["cell_id"]]
    if len(selected) != 1:
        raise ValueError("qualification must select exactly one bound cell")
    cell = selected[0]
    prompt = next(row for row in prompt_rows if row["prompt_id"] == "LAT-D-POS")
    if (cell.get("model") != model or cell.get("layout_id") != "LAT-P01"
            or cell.get("family") != "LAT" or cell.get("stage") != "P" or cell.get("form") != "D"
            or cell.get("status") != "PLANNED_NOT_RELEASED" or int(cell["physical_goal_sign"]) != 1
            or cell.get("prompt_id") != "LAT-D-POS" or cell.get("prompt") != prompt["text"]
            or cell.get("prompt_sha256") != prompt["sha256"]
            or hashlib.sha256(prompt["text"].encode()).hexdigest() != prompt["sha256"]):
        raise ValueError("qualification must use the unchanged planned LAT-P01 direct-positive cell")
    seed = _integer_seed(cell["effective_policy_seed"], "effective_policy_seed")
    block = [row for row in rows if row["model"] == model and row["layout_id"] == "LAT-P01"]
    if len(block) != 6 or any(_integer_seed(row["effective_policy_seed"], "effective_policy_seed") != seed for row in block):
        raise ValueError("qualification differs from frozen model/layout seed")
    native = binding["cells"][cell["cell_id"]]
    for key in ("family", "layout_id", "fixture_sha256", "prompt_sha256"):
        if not native.get(key) or native[key] != cell.get(key):
            raise ValueError(f"qualification native binding differs for {key}")
    if (type(native.get("scene_seed")) is not int
            or native["scene_seed"] != _integer_seed(cell["environment_seed"], "environment_seed")
            or _digest(Path(native["candidate_path"])) != native["candidate_file_sha256"]):
        raise ValueError("qualification candidate/physical seed hash differs")
    for item in native.get("native_scene_files", []):
        if _digest(Path(item["path"])) != item["sha256"]:
            raise ValueError("qualification native scene file hash differs")
    return Registration(path.resolve(), expected_sha256, value, cell, binding_path, native)


def load_identity(path: Path, expected: str, registration: Registration) -> dict[str, str]:
    identity = _hashed_json(path, expected)
    required = {"scope", "qualification_id", "attempt_id", "registration_sha256", "cell_id",
                "candidate_sha256", "binding_sha256", "channel_nonce", "simulator_job_uid", "simulator_pod_uid"}
    if set(identity) != required or any(not isinstance(v, str) or not v for v in identity.values()):
        raise ValueError("technical identity must be complete and must not contain a release_id")
    expected_fields = {
        **{k: registration.value[k] for k in ("scope", "qualification_id", "attempt_id", "cell_id")},
        "registration_sha256": registration.sha256,
        "candidate_sha256": registration.binding_record["candidate_file_sha256"],
        "binding_sha256": registration.value["environment_binding"]["sha256"],
    }
    if any(identity[k] != v for k, v in expected_fields.items()):
        raise ValueError("technical identity differs from bound registration/candidate")
    return identity


def append_progress(path: Path, value: Mapping[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"recorded_at_unix_s": time.time(), **value}, sort_keys=True, allow_nan=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def remaining(deadline: float, maximum: float) -> float:
    left = deadline - time.monotonic()
    if left <= 0:
        raise TimeoutError("technical check wall deadline elapsed; no retry")
    return min(left, maximum)


def _build_backend(model: str) -> Any:
    if model == "N3":
        from .nano_backend import build_pinned_nano_backend
        return build_pinned_nano_backend()
    from .checkpoint_fixed_input import _build_backend as build_checkpoint
    return build_checkpoint(model)


def _runtime_record(backend: Any, model: str) -> dict[str, Any]:
    if model != "N3":
        return _loaded_runtime(backend, model)
    return {
        "model": model, "resolved_config": dict(backend.resolved_config),
        "native_config": asdict(backend.service.cfg), "source_root": backend.source_root,
        "checkpoint_path": backend.checkpoint_path, "source_commit": NANO_CONFIG["source_commit"],
        "checkpoint_revision": NANO_CONFIG["revision"], "checkpoint_asset": NANO_CONFIG["asset"],
        "python": platform.python_version(),
        "versions": {name: importlib.metadata.version(name) for name in ("numpy", "torch", "transformers")},
    }


def run(
    registration_path: Path, registration_sha256: str, identity_path: Path, identity_sha256: str,
    output: Path, *, metadata_refresh: Any = None,
) -> dict[str, Any]:
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    counts = {"model_requests_started": 0, "model_requests_completed": 0, "responses_validated": 0,
              "acknowledged_action_count": 0, "physical_resets_started": 0, "physical_resets_completed": 0}
    server = thread = backend = original_predict = original_decode = client = None
    original_capture = None
    registration = identity = completion = None
    deadline = None
    failure = None
    safety = False
    request_root: Path | None = None
    resets: list[dict[str, Any]] = []
    chunks: list[dict[str, Any]] = []
    saved_env = {name: os.environ.get(name) for name in (
        "HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "SGW01_TRACE_SIDECAR", "SGW01_NANO_OUTPUT_DIR", "SGW01_E3_OUTPUT_DIR",
    )}

    def progress() -> None:
        append_progress(output / "progress.jsonl", {**DISCLAIMER, **counts})

    def capture(operation: str, **extra: Any) -> dict[str, Any]:
        path = client.root / "responses" / f"{client.command:04d}-{operation}.json"
        snapshot = client.snapshot()
        stamp = snapshot.get("sim_time")
        if type(stamp) not in (int, float) or not math.isfinite(stamp):
            raise ValueError("native response lacks finite measured simulation time")
        item = {"command_id": client.command, "response": record(path),
                "snapshot": snapshot, "sim_time": stamp, **extra}
        append_progress(output / "observations.jsonl", item)
        return item

    def physical_reset(label: str) -> Any:
        client.timeout_s = remaining(deadline, registration.value["mailbox_timeout_seconds"])
        counts["physical_resets_started"] += 1
        progress()
        reset = client.reset()
        counts["physical_resets_completed"] += 1
        item = capture("reset", label=label, receipt=dict(reset.receipt))
        resets.append(item)
        progress()
        return reset

    try:
        _fsync_json(output / "intent.json", {
            **DISCLAIMER, **LIMITS, "registration": record(registration_path),
            "expected_registration_sha256": registration_sha256,
            "identity": record(identity_path), "expected_identity_sha256": identity_sha256,
            "ownership": "in-process pinned backend + attested owned loopback HTTP; not subprocess owner",
            "counter_semantics": "model started/completed = backend.predict entry/return; validation is separate",
        })
        progress()
        registration = load_registration(registration_path, registration_sha256)
        deadline = time.monotonic() + registration.value["deadline_seconds"]
        identity = load_identity(identity_path, identity_sha256, registration)
        if metadata_refresh is None:
            from .mailbox_visibility import DirectoryRefresher
            metadata_refresh = DirectoryRefresher()
        # No model allocation before the actual simulator has attested its identity.
        ready_path = registration.root / "receiver_ready.json"
        while not ready_path.is_file():
            remaining(deadline, 1)
            metadata_refresh(registration.root.parent)
            if registration.root.is_dir():
                metadata_refresh(registration.root)
                if (registration.root / "receiver_failure.json").is_file():
                    raise MailboxError("native technical receiver failed before readiness")
            time.sleep(.05)
        ready = _read(ready_path)
        if ready.get("identity") != identity or ready.get("attempt_scope") != SCOPE:
            raise ValueError("actual receiver readiness identity differs")
        _fsync_json(output / "receiver-ready.json", {"record": record(ready_path), "receipt": ready})
        client = MailboxClient(root=registration.root, identity=identity,
                               timeout_s=registration.value["mailbox_timeout_seconds"], metadata_refresh=metadata_refresh)
        model = registration.value["model"]
        os.environ["HF_HUB_OFFLINE"] = os.environ["TRANSFORMERS_OFFLINE"] = "1"
        trace = output / "trace.jsonl"
        os.environ["SGW01_TRACE_SIDECAR"] = str(trace)
        if model in ("N3", "E3"):
            native_output = output / "native-model"
            native_output.mkdir()
            os.environ[{"N3": "SGW01_NANO_OUTPUT_DIR", "E3": "SGW01_E3_OUTPUT_DIR"}[model]] = str(native_output)
        backend = _build_backend(model)
        if model == "F3":
            original_capture = backend.capture_future
            backend.capture_future = True
        owner = NanoEvidenceProducer(backend, trace_path=trace, future_dir=output / "futures",
                                     attestation_path=output / "server-attestation.json", expected_config=CONFIGS[model])
        _fsync_json(output / "loaded-runtime.json", {**_runtime_record(backend, model), "identity_attestation": owner.attestation})
        original_predict = backend.predict

        def counted_predict(*args: Any, **kwargs: Any) -> Any:
            remaining(deadline, 1)
            if counts["model_requests_started"] >= 2:
                raise ValueError("technical check model request cap reached")
            counts["model_requests_started"] += 1
            progress()
            reply = original_predict(*args, **kwargs)
            counts["model_requests_completed"] += 1
            progress()
            if isinstance(reply, Mapping) and "action" in reply:
                fixed.save_array(request_root / "backend-actions.npy", np.asarray(reply["action"]))
            return reply

        backend.predict = counted_predict
        if model == "N3":
            # The pinned service has no temporal cache at history_length=1.
            # Reinitialize request RNG/seed, then use the producer's full identity reset.
            if backend.resolved_config.get("history_length") != 1:
                raise ValueError("N3 technical reset requires the pinned stateless history=1")
            backend.service.cfg = replace(backend.service.cfg, seed=registration.seed, deterministic_seed=True)
            backend.service._rng = np.random.default_rng(registration.seed)
            original_decode = backend.service.model.decode

            def retain_decode(latent: Any, *args: Any, **kwargs: Any) -> Any:
                if str(latent.dtype) not in ("torch.float16", "torch.float32", "torch.bfloat16", "float32"):
                    raise ValueError("unsupported native latent dtype for lossless float32 retention")
                fixed.save_array(request_root / "vision-latent.npy", latent.detach().float().cpu().numpy())
                _fsync_json(request_root / "vision-latent.json", {
                    **record(request_root / "vision-latent.npy"), "native_dtype": str(latent.dtype),
                    "retention": "same-request native latent represented losslessly as float32",
                })
                return original_decode(latent, *args, **kwargs)

            backend.service.model.decode = retain_decode
        server = make_nano_http_server(owner, host="127.0.0.1", port=0)
        server.daemon_threads = False
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .05}, daemon=True)
        thread.start()
        endpoint = f"http://127.0.0.1:{server.server_port}"
        _fsync_json(output / "endpoint.json", {"url": endpoint, "pid": os.getpid(), "loopback_only": True})
        reset_packet = fixed.post(endpoint + "/reset", {"camera_name": CAMERA}, timeout=remaining(deadline, 30))
        if reset_packet.get("status") != "reset":
            raise ValueError("owned producer reset not acknowledged")
        _fsync_json(output / "backend-reset.json", {
            **reset_packet, "semantics": "N3 stateless history=1 and reinitialized deterministic RNG"
            if model == "N3" else "official backend RNG/text/history/queue reset through producer",
        })
        initial = physical_reset("before")
        reset_id = initial.receipt["reset_id"]
        fingerprint = initial.receipt["candidate_fingerprint"]
        for index in range(2):
            remaining(deadline, 1)
            request_root = output / f"request-{index:02d}"
            request_root.mkdir()
            observation = nano_observation(client.policy_observation())
            request_id = f"{registration.value['attempt_id']}:request:{index}"
            _fsync_json(request_root / "intent.json", {
                **DISCLAIMER, **counts, "request_id": request_id, "request_index": index,
                "registered_cell_id": registration.cell["cell_id"], "sampling_seed": registration.seed,
                "prompt": registration.cell["prompt"], "prompt_sha256": registration.cell["prompt_sha256"],
                "input_response": record(client.root / "responses" /
                                         f"{client.command:04d}-{'reset' if index == 0 else 'step'}.json"),
                "input_sim_time": client.snapshot()["sim_time"], "requested_prefix": 32,
            })
            input_records = {}
            for key, array in observation.items():
                array_path = request_root / (key.replace("/", "-") + ".npy")
                fixed.save_array(array_path, array)
                input_records[key] = {**record(array_path), "shape": list(array.shape), "dtype": str(array.dtype)}
            _fsync_json(request_root / "input-manifest.json", {
                "inputs": input_records, "camera_configuration": registration.value["camera_configuration"],
                "scope": "actual native camera/proprioception input only; no scoring metadata",
            })
            packet = {
                "request_id": request_id, "request_index": index, "registered_cell_id": registration.cell["cell_id"],
                "reset_id": reset_id, "reset_fingerprint": fingerprint, "camera_id": CAMERA, "camera_name": CAMERA,
                "sampling_seed": registration.seed, "prompt": registration.cell["prompt"], "observation": observation,
            }
            response = fixed.post(endpoint + "/predict", packet,
                                  timeout=remaining(deadline, registration.value["model_timeout_seconds"]))
            _fsync_json(request_root / "response.json", response)
            actions = np.asarray(response["action"], dtype=np.float32)
            fixed.save_array(request_root / "actions.npy", actions)
            if response.get("request_id") != request_id or actions.shape != (32, 8) or not np.isfinite(actions).all():
                raise ValueError("actual policy response is not the finite matched 32x8 absolute-action contract")
            checked = read_trace_sidecar(request=packet, response={"actions": actions})
            trace_rows = [json.loads(line) for line in trace.read_text().splitlines() if line]
            if (len(trace_rows) != index + 1 or trace_rows[-1]["request_id"] != request_id
                    or checked.get("sampling_seed") != registration.seed
                    or (model != "N3" and (checked.get("model") != model
                                          or checked.get("effective_sampling_seed") != registration.seed))
                    or checked.get("prompt_sha256") != registration.cell["prompt_sha256"]):
                raise ValueError("same-request native trace attribution differs")
            counts["responses_validated"] += 1
            progress()
            chunk = {"request_id": request_id, "actions": record(request_root / "actions.npy"),
                     "trace": trace_rows[-1], "future_status": checked["future_status"], "executed_prefix": 0}
            for offset, action in enumerate(actions):
                if counts["acknowledged_action_count"] >= 64:
                    raise ValueError("technical check absolute-action cap reached")
                before = client.snapshot()["sim_time"]
                client.timeout_s = remaining(deadline, registration.value["mailbox_timeout_seconds"])
                _fsync_json(request_root / f"action-{offset:02d}-intent.json", {
                    "request_id": request_id, "prefix_offset": offset, "action": action.tolist(),
                    "global_action_index": counts["acknowledged_action_count"], "before_sim_time": before,
                    "expected_mailbox_command_id": client.command + 1,
                })
                step = client.step(action)
                counts["acknowledged_action_count"] += 1
                chunk["executed_prefix"] += 1
                item = capture("step", request_id=request_id, prefix_offset=offset,
                               global_action_index=counts["acknowledged_action_count"] - 1,
                               action=action.tolist(), before_sim_time=before, step_result=step)
                if not math.isclose(item["sim_time"] - before, 1 / 15, rel_tol=0, abs_tol=1e-6):
                    raise ValueError("measured action/frame time differs from one native 15Hz physics step")
                progress()
                if step.get("safety_terminated"):
                    safety = True
                    break
            _fsync_json(request_root / "result.json", chunk)
            chunks.append(chunk)
            if safety:
                break
    except BaseException:
        failure = traceback.format_exc()
    finally:
        # This is the second physical reset, not a retry. A timed-out mailbox
        # is permanently closed, so no speculative recovery command is sent.
        if client is not None and not client._closed:
            try:
                if counts["physical_resets_completed"] == 1 and counts["physical_resets_started"] == 1:
                    physical_reset("after")
                if counts["physical_resets_completed"] == 2 or (failure and counts["physical_resets_started"] == 0):
                    client.timeout_s = remaining(deadline, registration.value["mailbox_timeout_seconds"])
                    client.close()
                    from .native_runtime_check_receiver import verify_completion
                    completion = verify_completion(registration.root, identity, metadata_refresh,
                                                   deadline, counts["acknowledged_action_count"],
                                                   expected_resets=counts["physical_resets_completed"])
            except BaseException:
                failure = (failure or "") + "\nCleanup:\n" + traceback.format_exc()
        if server is not None:
            if thread is not None and thread.is_alive():
                server.shutdown()
            server.server_close()
        if thread is not None:
            thread.join(timeout=5)
        if original_predict is not None:
            backend.predict = original_predict
        if original_decode is not None:
            backend.service.model.decode = original_decode
        if original_capture is not None:
            backend.capture_future = original_capture
        for name, previous in saved_env.items():
            if previous is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = previous
        progress()
        _fsync_json(output / "shutdown.json", {"server_started": server is not None, "server_closed": True,
                    "serving_thread_alive": bool(thread and thread.is_alive()), "native_call_drained": True})
    if failure is None and completion is None:
        failure = "no complete technical receiver receipt"
    result = {
        **DISCLAIMER, **counts, "status": "technical_failure_preserve_partial_no_retry" if failure else
        ("technical_safety_terminated" if safety else "technical_check_completed"),
        "executed_action_count": completion["executed_action_count"] if completion else None,
        "execution_count_semantics": "receiver-confirmed" if completion else
        "unavailable final count; acknowledged prefix retained; inspect receiver partial evidence",
        "safety_terminated": safety, "requests": chunks, "resets": resets, "receiver_completion": completion,
        "model_config": registration.value["model_config"] if registration else None,
        "sampling_seed": registration.seed if registration else None,
    }
    if failure:
        _fsync_json(output / "failure.json", {**result, "traceback": failure})
        raise RuntimeError(f"technical check failed; partial evidence retained at {output}")
    _fsync_json(output / "result.json", result)
    return result


def example(model: str) -> dict[str, Any]:
    ref = lambda name: {"path": f"/ABSOLUTE/{name}", "bytes": 0, "sha256": "<actual-file-sha256>"}
    value = {
        "schema_version": SCHEMA, "scope": SCOPE, "qualification_id": "runtime-check-unique",
        "attempt_id": f"{model}-LAT-P01-attempt-unique", "model": model, "model_config": CONFIGS[model],
        "cell_id": "<exact-bound-LAT-P01-LAT-D-POS-cell-id>",
        **{key: ref(name) for key, name in {
            "launch_instruction": "launch-instruction.json", "materialization": "materialization/handoff.json",
            "environment_binding": "materialization/environment-binding.json",
            "bound_cells": "materialization/bound-cells.jsonl", "prompts": "source/spec/prompts.json",
        }.items()},
        "camera_configuration": camera_configuration_identity(), "mailbox_root": "/ABSOLUTE/new-attempt-mailbox",
        "deadline_seconds": 1800, "mailbox_timeout_seconds": 120, "model_timeout_seconds": 900, **LIMITS,
    }
    launch = {k: value[k] for k in ("scope", "qualification_id", "attempt_id", "model", "cell_id", *LIMITS)}
    launch.update(schema_version="sgw-01-runtime-check-launch-v1", instruction="<actual new user launch instruction>")
    identity = {k: value[k] for k in ("scope", "qualification_id", "attempt_id", "cell_id")}
    identity.update(registration_sha256="<actual-registration-file-sha256>",
                    candidate_sha256="<bound-candidate-file-sha256>", binding_sha256="<bound-binding-file-sha256>",
                    channel_nonce="<unique-nonce>", simulator_job_uid="<actual-DownwardAPI-JOB_UID>",
                    simulator_pod_uid="<actual-DownwardAPI-POD_UID>")
    return {"registration": value, "launch_instruction": launch, "identity": identity}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--example", choices=tuple(CONFIGS))
    parser.add_argument("--registration", type=Path)
    parser.add_argument("--registration-sha256")
    parser.add_argument("--identity", type=Path)
    parser.add_argument("--identity-sha256")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.example:
        print(json.dumps(example(args.example), indent=2))
        return
    if any(getattr(args, key) is None for key in ("registration", "registration_sha256", "identity", "identity_sha256", "output")):
        parser.error("both hash-bound inputs and an exclusive output directory are required")
    print(json.dumps(run(args.registration, args.registration_sha256, args.identity, args.identity_sha256, args.output)))


if __name__ == "__main__":
    main()
