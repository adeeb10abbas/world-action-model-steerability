"""Bounded E3/F3 diagnostics on the retained current LAT-P01 observation.

Run ``python -m experiments.workshops.spatial_grounding_v1.checkpoint_fixed_input
--model E3|F3 --registration CURRENT_N3_REGISTRATION --output NEW_DIRECTORY``.
The N3 registration supplies physical input only, not another model's qualification.
Use the checkpoint backend environment documented in checkpoint_integrations.json.
HTTP timeouts are finite; shutdown drains an in-flight native call rather than
retrying it. The coordinator must still impose its finite process/Job deadline.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, is_dataclass
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
import uuid

import numpy as np

from .adapters import EDGE_CONFIG, FLUX_CONFIG, _integer_seed
from . import nano_fixed_input as fixed
from .family_campaign_executor import _fsync_json
from .paper_engineering import bound_file, record
from .producer import NanoEvidenceProducer, make_nano_http_server
from .trace import read_trace_sidecar


CONFIGS = {"E3": EDGE_CONFIG, "F3": FLUX_CONFIG}
CAMERA = "over_shoulder_left_camera"
LIMITS = {
    "maximum_model_requests": 6, "behavioral_episodes": 0, "executed_actions": 0,
    "physical_reset_performed_in_this_job": False, "release_permitted": False,
    "physical_camera_time_alignment_qualified": False, "closed_loop_ready": False,
}


def load_input(path: Path, model: str) -> tuple[dict[str, Any], dict[str, dict[str, Any]], int]:
    if model not in CONFIGS:
        raise ValueError("fixed-input checkpoint diagnostics support only E3/F3")
    if json.loads(path.read_bytes()).get("schema_version") != fixed.CURRENT_SCHEMA:
        raise ValueError("only the current physical-input registration is accepted")
    registration = fixed.load_registration(path)
    rows = [json.loads(line) for line in bound_file(registration["bound_cells"]).read_text().splitlines() if line]
    selected = [row for row in rows if row["model"] == model and row["layout_id"] == "LAT-P01"]
    capture = json.loads(bound_file(registration["capture"]).read_bytes())
    binding = json.loads(bound_file(registration["environment_binding"]).read_bytes())
    prompt_rows = json.loads(bound_file(registration["prompts"]).read_bytes())["prompts"]
    prompts = {row["prompt_id"]: row for row in prompt_rows}
    if len(prompts) != len(prompt_rows):
        raise ValueError("duplicate frozen prompt identities")
    if (len(selected) != 6 or
            {(row["form"], int(row["physical_goal_sign"])) for row in selected}
            != {(form, goal) for form in ("D", "C", "I") for goal in (-1, 1)}):
        raise ValueError("target model must have its complete current LAT-P01 six-cell block")
    seeds = {_integer_seed(row["effective_policy_seed"], "effective_policy_seed") for row in selected}
    if len(seeds) != 1:
        raise ValueError("target model/layout has inconsistent frozen effective seeds")
    by_prompt = {}
    for row in selected:
        prompt = prompts[row["prompt_id"]]
        sign = "POS" if int(row["physical_goal_sign"]) == 1 else "NEG"
        if (
            row["status"] != "PLANNED_NOT_RELEASED" or row["family"] != "LAT" or row["stage"] != "P"
            or row["prompt_id"] != f"LAT-{row['form']}-{sign}"
            or hashlib.sha256(prompt["text"].encode()).hexdigest() != prompt["sha256"]
            or row["prompt"] != prompt["text"] or row["prompt_sha256"] != prompt["sha256"]
            or binding["cells"][row["cell_id"]]["candidate_file_sha256"] != capture["candidate_sha256"]
        ):
            raise ValueError("target model row differs from the current physical/prompt binding")
        by_prompt[row["prompt_id"]] = row
    return registration, by_prompt, seeds.pop()


def _build_backend(model: str) -> Any:
    from .checkpoint_backends import build_pinned_edge_backend, build_pinned_flux_backend

    return {"E3": build_pinned_edge_backend, "F3": build_pinned_flux_backend}[model]()


def _loaded_runtime(backend: Any, model: str) -> dict[str, Any]:
    cfg = backend.service.cfg if model == "E3" else backend.service.policy.config
    if is_dataclass(cfg):
        native_config = asdict(cfg)
    elif callable(getattr(cfg, "to_dict", None)):
        native_config = cfg.to_dict()
    elif isinstance(cfg, Mapping):
        native_config = dict(cfg)
    else:
        raise ValueError("loaded backend does not expose its actual native configuration")
    versions = {}
    for name in ("torch", "torchvision", "numpy", "transformers", "natten", "einops", "safetensors", "pydantic"):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = "not_installed"
    return {
        "model": model, "resolved_config": dict(backend.resolved_config), "native_config": native_config,
        "source_root": backend.source_root, "checkpoint_path": backend.checkpoint_path,
        "source_commit": CONFIGS[model]["source_commit"], "checkpoint_revision": CONFIGS[model]["revision"],
        "checkpoint_asset": CONFIGS[model]["asset"], "base_path": getattr(backend, "base_path", None),
        "base_revision": CONFIGS[model].get("base_revision"), "versions": versions,
        "python": platform.python_version(), "scope": "loaded runtime identity, not runtime qualification",
    }


def run(registration_path: Path, output: Path, *, model: str, request_timeout: float = 900) -> dict[str, Any]:
    if model not in CONFIGS or not math.isfinite(request_timeout) or request_timeout <= 0:
        raise ValueError("E3/F3 and a finite positive request timeout are required")
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    counts = {"http_prediction_attempts": 0, "model_requests_started": 0,
              "model_requests_completed": 0, "responses_validated": 0}
    server = thread = backend = original_predict = None
    original_capture = None
    failure = None
    saved_env = {name: os.environ.get(name) for name in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "SGW01_TRACE_SIDECAR")}
    results: list[dict[str, Any]] = []
    diagnostic_id = f"{model}-current-fixed-input-{uuid.uuid4().hex}"

    def progress() -> None:
        with (output / "progress.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({**LIMITS, **counts, "diagnostic_id": diagnostic_id,
                         "counter_semantics": "started/completed count backend.predict entry/return; validation is separate"},
                         sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())

    try:
        _fsync_json(output / "intent.json", {
            **LIMITS, "diagnostic_id": diagnostic_id, "model": model, "model_config": CONFIGS[model],
            "physical_input_registration": record(registration_path), "request_prompt_ids": fixed.ORDER,
            "n3_runtime_qualification_reused": False, "request_timeout_seconds": request_timeout,
            "reset_timeout_seconds": 30, "capture_schedule": [True] * 3 + ([False] * 3 if model == "F3" else [True] * 3),
        })
        progress()
        registration, cells, seed = load_input(registration_path, model)
        observation = fixed.current_observation(registration)
        inputs = output / "inputs"
        inputs.mkdir()
        input_records = {}
        for key, value in observation.items():
            path = inputs / (key.replace("/", "-") + ".npy")
            fixed.save_array(path, value)
            input_records[key] = {**record(path), "shape": list(value.shape), "dtype": str(value.dtype)}
        fingerprint = hashlib.sha256(json.dumps(input_records, sort_keys=True).encode()).hexdigest()
        _fsync_json(output / "input-manifest.json", {
            "inputs": input_records, "fingerprint": fingerprint, "capture": registration["capture"],
            "materialization": registration["materialization"], "bound_cells": registration["bound_cells"],
            "model": model, "layout_id": "LAT-P01", "sampling_seed": seed,
            "seed_source": "target model/layout effective_policy_seed from hash-bound cells",
            "physical_source_registration_sampling_seed": registration["sampling_seed"],
            "scope": "retained cameras/proprioception only; no object poses or scoring metadata sent to model",
        })
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        trace = output / "trace.jsonl"
        os.environ["SGW01_TRACE_SIDECAR"] = str(trace)
        backend = _build_backend(model)
        if model == "F3":
            original_capture = backend.capture_future
        owner = NanoEvidenceProducer(
            backend, trace_path=trace, future_dir=output / "futures",
            attestation_path=output / "server-attestation.json", expected_config=CONFIGS[model],
        )
        _fsync_json(output / "loaded-runtime.json", {
            **_loaded_runtime(backend, model), "identity_attestation": dict(owner.attestation),
        })
        original_predict = backend.predict
        request_root: Path | None = None

        def counted_predict(*args: Any, **kwargs: Any) -> Any:
            if counts["model_requests_started"] >= 6:
                raise ValueError("six-request diagnostic cap reached")
            counts["model_requests_started"] += 1
            progress()
            reply = original_predict(*args, **kwargs)
            counts["model_requests_completed"] += 1
            progress()
            # Preserve actual backend actions even if a later trace/HTTP validation fails.
            if request_root is not None and isinstance(reply, Mapping) and "action" in reply:
                fixed.save_array(request_root / "backend-actions.npy", np.asarray(reply["action"]))
            return reply

        backend.predict = counted_predict
        server = make_nano_http_server(owner, host="127.0.0.1", port=0)
        server.daemon_threads = False
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        thread.start()
        endpoint = f"http://127.0.0.1:{server.server_port}"
        _fsync_json(output / "endpoint.json", {"url": endpoint, "pid": os.getpid(), "loopback_only": True})
        actions = []
        for index, prompt_id in enumerate(fixed.ORDER):
            request_root = output / f"request-{index:02d}"
            request_root.mkdir()
            capture = model == "E3" or index < 3
            if model == "F3":
                backend.capture_future = capture
            cell = cells[prompt_id]
            request_id = f"{diagnostic_id}:request:{index}"
            _fsync_json(request_root / "intent.json", {
                **LIMITS, **counts, "request_id": request_id, "prompt_id": prompt_id,
                "registered_cell_id": cell["cell_id"], "sampling_seed": seed,
                "prompt": cell["prompt"], "prompt_sha256": cell["prompt_sha256"],
                "capture_future": capture, "input_manifest": record(output / "input-manifest.json"),
            })
            reset = fixed.post(endpoint + "/reset", {"camera_name": CAMERA}, timeout=30)
            _fsync_json(request_root / "reset.json", {
                **reset, "physical_reset": "retained_current_observation_not_new_simulator_reset",
                "backend_reset": "checkpoint-specific full cache/RNG reset",
            })
            if reset.get("status") != "reset":
                raise ValueError("owned checkpoint producer did not acknowledge full backend reset")
            packet = {
                "request_id": request_id, "request_index": 0, "registered_cell_id": cell["cell_id"],
                "reset_id": reset["reset_id"], "reset_fingerprint": fingerprint,
                "camera_id": CAMERA, "camera_name": CAMERA, "sampling_seed": seed,
                "prompt": cell["prompt"], "observation": observation,
            }
            counts["http_prediction_attempts"] += 1
            progress()
            started = time.monotonic()
            response = fixed.post(endpoint + "/predict", packet, timeout=request_timeout)
            _fsync_json(request_root / "response.json", response)
            action = np.asarray(response["action"], dtype=np.float32)
            fixed.save_array(request_root / "actions.npy", action)
            if response.get("request_id") != request_id or action.shape != (32, 8) or not np.isfinite(action).all():
                raise ValueError("native response identity or finite 32x8 action contract differs")
            checked = read_trace_sidecar(request=packet, response={"actions": action})
            rows = [json.loads(line) for line in trace.read_text().splitlines() if line]
            if len(rows) != index + 1 or rows[-1]["request_id"] != request_id:
                raise ValueError("native trace must contain exactly one row per diagnostic request")
            if (checked.get("model") != model or checked.get("effective_sampling_seed") != seed
                    or checked.get("prompt_sha256") != cell["prompt_sha256"]
                    or response.get("future_status") != checked["future_status"]):
                raise ValueError("native trace model/seed/prompt/future attribution differs")
            result = {
                "index": index, "request_id": request_id, "prompt_id": prompt_id,
                "registered_cell_id": cell["cell_id"], "sampling_seed": seed, "capture_future": capture,
                "seconds": time.monotonic() - started, "actions": record(request_root / "actions.npy"),
                "future_status": checked["future_status"], "trace": rows[-1], "executed_actions": 0,
            }
            _fsync_json(request_root / "result.json", result)
            results.append(result)
            actions.append(action)
            counts["responses_validated"] += 1
            progress()
        comparisons = fixed.compare_actions(actions)
        result = {
            **LIMITS, **counts, "diagnostic_id": diagnostic_id, "model": model, "sampling_seed": seed,
            "status": "six_current_fixed_input_requests_completed_not_a_study_release",
            "physical_input_registration": record(registration_path), "n3_runtime_qualification_reused": False,
            "comparisons": comparisons, "requests": results,
            "capture_parity": {
                "applicable": model == "F3",
                "capture_enabled_vs_disabled_equal": comparisons["between_groups_equal"] if model == "F3" else None,
                "max_absolute_action_difference": [
                    float(np.max(np.abs(actions[i].astype(float) - actions[i + 3]))) for i in range(3)
                ] if model == "F3" else None,
            },
            "forecast_scope": "same-request artifacts only; unavailable/decode_error preserved; physical camera/time mapping unqualified",
        }
        _fsync_json(output / "result.json", result)
        return result
    except BaseException:
        failure = traceback.format_exc()
        raise
    finally:
        if server is not None:
            if thread is not None and thread.is_alive():
                server.shutdown()
            server.server_close()
        if thread is not None:
            thread.join(timeout=5)
        if original_predict is not None:
            backend.predict = original_predict
        if backend is not None and model == "F3" and original_capture is not None:
            backend.capture_future = original_capture
        for name, value in saved_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        progress()
        _fsync_json(output / "shutdown.json", {"server_closed": True, "server_started": server is not None,
                    "serving_thread_alive": thread.is_alive() if thread is not None else False})
        if failure is not None:
            _fsync_json(output / "failure.json", {
                **LIMITS, **counts, "diagnostic_id": diagnostic_id, "model": model, "traceback": failure,
                "status": "technical_failure_preserve_partial_no_automatic_retry",
                "validated_requests": results, "in_flight_request_drained_before_final_counts": True,
            })


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--model", choices=tuple(CONFIGS), required=True)
    parser.add_argument("--registration", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--request-timeout", type=float, default=900)
    args = parser.parse_args()
    print(json.dumps(run(args.registration, args.output, model=args.model,
                         request_timeout=args.request_timeout), sort_keys=True))


if __name__ == "__main__":
    main()
