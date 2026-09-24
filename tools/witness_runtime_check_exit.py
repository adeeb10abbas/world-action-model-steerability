"""Read-only external witness for the 8ac4858 missing-receiver-shutdown case.

Run with ``python -m tools.witness_runtime_check_exit --help``. This neither
repairs the original failure nor writes a receiver-authored shutdown marker.
Missing or contradictory evidence fails closed, with no output or retries.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sys
from typing import Any
from uuid import UUID

import numpy as np

from experiments.workshops.spatial_grounding_v1 import native_runtime_check_receiver as receiver
from experiments.workshops.spatial_grounding_v1 import runtime_closed_loop_check as check
from experiments.workshops.spatial_grounding_v1.producer import _git_revision
from experiments.workshops.spatial_grounding_v1.simulator_mailbox import _digest, _load_array


SOURCE_COMMIT = "8ac48581eec62143dbd8be7d4cd77cce6de10887"
COUNTS = {"model_requests_started": 2, "model_requests_completed": 2, "responses_validated": 2,
          "acknowledged_action_count": 64, "physical_resets_started": 2, "physical_resets_completed": 2}
LIFECYCLE_FILES = (
    "receiver_shutdown.json", "receiver_child_shutdown.json", "receiver_process_exit.json",
    "receiver_cleanup_started.json", "receiver_supervisor_failure.json", "receiver_failure.json",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def fields(value: dict, expected: dict, label: str) -> None:
    require(all(type(value.get(k)) is type(v) and value[k] == v for k, v in expected.items()), label)


def number(value: Any) -> float:
    require(type(value) in (int, float) and math.isfinite(value), "nonfinite/non-numeric evidence time")
    return float(value)


def timestamp(value: str) -> float:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(parsed.tzinfo is not None, "Pod timestamp lacks timezone")
    return parsed.timestamp()


class Evidence:
    """Hash the files actually checked, then detect changes before publication."""
    def __init__(self) -> None:
        self.records: dict[str, dict] = {}

    def file(self, path: Path) -> dict:
        path = path.resolve(strict=True)
        item = {"path": str(path), "sha256": _digest(path), "bytes": path.stat().st_size}
        require(str(path) not in self.records or self.records[str(path)] == item, "evidence changed during verification")
        self.records[str(path)] = item
        return item

    def json(self, path: Path) -> dict:
        self.file(path)
        value = json.loads(path.read_bytes())
        require(isinstance(value, dict), f"JSON object required: {path}")
        return value

    def lines(self, path: Path) -> list[dict]:
        self.file(path)
        rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        require(bool(rows) and all(isinstance(row, dict) for row in rows), f"JSONL objects required: {path}")
        return rows

    def bound(self, item: dict, expected: Path) -> dict:
        require(Path(item["path"]).resolve() == expected.resolve(), "artifact path differs from original attempt")
        actual = self.file(expected)
        require(item.get("sha256") == actual["sha256"] and
                ("bytes" not in item or item["bytes"] == actual["bytes"]), f"artifact hash/size differs: {expected}")
        return actual

    def array(self, root: Path, item: dict) -> np.ndarray:
        path = (root / item["path"]).resolve()
        require(path.is_relative_to(root.resolve()), "array escaped original evidence directory")
        self.bound({**item, "path": str(path)}, path)
        value = _load_array(root, item)
        require(value.dtype != object and np.isfinite(value).all(), "nonfinite evidence array")
        return value

    def tree(self, root: Path, value: dict) -> Any:
        if set(value) == {"array"}:
            return self.array(root, value["array"])
        require(set(value) == {"mapping"} and bool(value["mapping"]), "invalid observation tree")
        return {key: self.tree(root, item) for key, item in value["mapping"].items()}

    def stable_digest(self) -> dict:
        for path, expected in list(self.records.items()):
            require(self.file(Path(path)) == expected, "evidence changed before witness publication")
        pairs = sorted((path, item["sha256"]) for path, item in self.records.items())
        encoded = json.dumps(pairs, separators=(",", ":"), ensure_ascii=True).encode()
        return {"files": len(pairs), "sha256": hashlib.sha256(encoded).hexdigest(),
                "encoding": "SHA256 of compact JSON sorted [absolute_path, file_sha256] pairs"}


def terminal_pod(pod: dict, *, role: str, pod_uid: str, job_uid: str, registration: check.Registration,
                 identity_path: Path, identity_sha256: str, evidence: Path, source: Path) -> dict:
    require(str(UUID(pod_uid)) == pod_uid and str(UUID(job_uid)) == job_uid, "canonical expected UIDs required")
    meta, spec, status = pod["metadata"], pod["spec"], pod["status"]
    owners = meta.get("ownerReferences", [])
    require(pod.get("apiVersion") == "v1" and pod.get("kind") == "Pod" and meta.get("uid") == pod_uid
            and len(owners) == 1, "terminal Pod/owner identity differs")
    owner = owners[0]
    fields(owner, {"uid": job_uid, "kind": "Job", "apiVersion": "batch/v1", "controller": True}, "Job owner differs")
    require(bool(meta.get("name")) and bool(meta.get("namespace")) and bool(owner.get("name")), "missing Pod/Job name")
    labels = meta.get("labels", {})
    require(labels.get("batch.kubernetes.io/controller-uid") == job_uid
            and labels.get("batch.kubernetes.io/job-name") == owner["name"], "Pod Job labels differ")
    require(spec.get("restartPolicy") == "Never" and len(spec.get("containers", [])) == 1
            and len(status.get("containerStatuses", [])) == 1
            and not any(spec.get(k) for k in ("initContainers", "ephemeralContainers"))
            and not any(status.get(k) for k in ("initContainerStatuses", "ephemeralContainerStatuses")),
            "unexpected/restarted/additional Pod containers")
    container, state = spec["containers"][0], status["containerStatuses"][0]
    require(container.get("name") == state.get("name") == role, "container role identity differs")
    fields(state, {"restartCount": 0, "ready": False, "started": False, "lastState": {}}, "container restart/state differs")
    require(set(state.get("state", {})) == {"terminated"}, "container is not exclusively terminal")
    terminal = state["state"]["terminated"]
    code, phase, reason = (0, "Succeeded", "Completed") if role == "simulator" else (1, "Failed", "Error")
    fields(terminal, {"exitCode": code, "reason": reason}, "terminal exit contradicts the lifecycle case")
    require(status.get("phase") == phase and terminal.get("signal", 0) == 0, "Pod phase/signal differs")
    require(re.fullmatch(r"[^ ]+@sha256:[0-9a-f]{64}", container.get("image", "")) is not None
            and state.get("imageID", "").removeprefix("docker-pullable://") == container["image"],
            "container image digest identity differs")
    container_id = state.get("containerID", "")
    require(re.fullmatch(r"[a-z]+://[0-9a-f]{64}", container_id) is not None
            and terminal.get("containerID") == container_id, "terminated container identity differs")
    created, started = timestamp(meta["creationTimestamp"]), timestamp(terminal["startedAt"])
    finished = timestamp(terminal["finishedAt"])
    require(created <= timestamp(status["startTime"]) <= started <= finished, "inconsistent Pod lifecycle times")
    entries = container.get("env", [])
    env = {item["name"]: item for item in entries}
    require(len(env) == len(entries), "duplicate Pod environment bindings")
    expected = {
        "OUT": str(registration.root.parent if role == "simulator" else evidence.parent),
        "SOURCE": str(source), "MODEL": registration.value["model"], "REGISTRATION": str(registration.path),
        "REGISTRATION_SHA256": registration.sha256, "IDENTITY": str(identity_path),
    }
    if role == "simulator":
        expected.update(SGW01_ENV_BINDING=str(registration.binding_path),
                        SGW01_ENV_BINDING_SHA256=registration.value["environment_binding"]["sha256"])
    for key, value in expected.items():
        require(env.get(key) == {"name": key, "value": value}, f"Pod {key} does not bind original evidence")
    if "IDENTITY_SHA256" in env:
        require(env["IDENTITY_SHA256"].get("value") == identity_sha256, "Pod identity hash contradicts sidecar")
    for key, field in (("JOB_UID", "metadata.labels['batch.kubernetes.io/controller-uid']"), ("POD_UID", "metadata.uid")):
        require(env.get(key, {}).get("valueFrom", {}).get("fieldRef", {}).get("fieldPath") == field,
                "Pod lacks exact Downward API identity binding")
    require(container.get("command") == ["/bin/bash", "-ec"] and len(container.get("args", [])) == 1,
            "unrecognized legacy entrypoint")
    lines = container["args"][0].splitlines()
    module = "native_runtime_check_receiver" if role == "simulator" else "runtime_closed_loop_check"
    prefix = '"$PY"' if role == "simulator" else 'bash tools/cluster_policy_bootstrap.sh "$MODEL" "$PY"'
    invocation = (f'{prefix} -m experiments.workshops.spatial_grounding_v1.{module} '
                  '--registration "$REGISTRATION" --registration-sha256 "$REGISTRATION_SHA256" '
                  '--identity "$IDENTITY" --identity-sha256 "$IDENTITY_SHA256"')
    if role == "policy":
        invocation += ' --output "$OUT/evidence"'
    require(lines[0] == "set -euo pipefail" and lines[-2:] == [invocation, "sync"],
            "legacy shell must preserve the native process exit status")
    for line in ('cd "$SOURCE"', f'test "$(git rev-parse HEAD)" = {SOURCE_COMMIT}',
                 'test -z "$(git status --porcelain)"', 'IDENTITY_SHA256=$(cat "${IDENTITY%.json}.sha256")', invocation):
        require(lines.count(line) == 1, "legacy command/source/hash binding is absent or ambiguous")
    return {"pod_uid": pod_uid, "job_uid": job_uid, "pod_name": meta["name"], "job_name": owner["name"],
            "namespace": meta["namespace"], "container_name": role, "container_id": container_id,
            "image_id": state["imageID"], "phase": phase, "exit_code": code, "restart_count": 0,
            "started_at": terminal["startedAt"], "finished_at": terminal["finishedAt"]}


def interrupted_cleanup(trace: Any, source: Path) -> None:
    require(isinstance(trace, str), "policy failure lacks traceback")
    text = trace.strip()
    require(text.startswith("Cleanup:\nTraceback (most recent call last):\n")
            and text.endswith("\nKeyboardInterrupt") and text.count("Cleanup:") == 1
            and text.count("Traceback (most recent call last):") == 1,
            "failure is not solely an interrupted cleanup wait")
    frames = re.findall(r'^  File "([^"]+)", line (\d+), in ([^\n]+)$', text, flags=re.MULTILINE)
    expected = [("runtime_closed_loop_check.py", "run"), ("native_runtime_check_receiver.py", "verify_completion")]
    require(len(frames) == 2, "cleanup traceback has additional/earlier failing frames")
    for (filename, line, function), (name, expected_function) in zip(frames, expected):
        require(Path(filename) == source / "experiments/workshops/spatial_grounding_v1" / name
                and function == expected_function and int(line) > 0, "cleanup traceback is not the original wait")
    lines = [line for line in text.splitlines() if not re.fullmatch(r"[\t ~^]+", line)]
    require(lines[-2].strip() == "time.sleep(.01)"
            and all(line.startswith(("  File ", "    ")) for line in lines[2:-1])
            and text.count("KeyboardInterrupt") == 1, "interrupt was not solely in the completion-marker wait")


def policy_progress(rows: list[dict], start: float, finish: float) -> None:
    counts = {key: 0 for key in COUNTS}
    expected = [dict(counts)]
    changes = ["physical_resets_started", "physical_resets_completed"]
    for _ in range(2):
        changes += ["model_requests_started", "model_requests_completed", "responses_validated"]
        changes += ["acknowledged_action_count"] * 32
    changes += ["physical_resets_started", "physical_resets_completed"]
    for key in changes:
        counts[key] += 1
        expected.append(dict(counts))
    expected.append(dict(counts))
    require(len(rows) == len(expected), "policy progress has missing/extra transitions")
    previous = start
    for row, state in zip(rows, expected):
        fields(row, {**check.DISCLAIMER, **state}, "policy counters/disclaimer differ")
        current = number(row.get("recorded_at_unix_s"))
        require(previous <= current <= finish + 1, "policy progress falls outside terminal lifetime/order")
        previous = current


def physics_progress(rows: list[dict], simulator: dict) -> None:
    events = ["physical_reset_started", "physical_reset_returned"]
    events += ["action_step_started", "action_step_returned"] * 64
    events += ["physical_reset_started", "physical_reset_returned"]
    require(len(rows) == len(events), "receiver physics progress is incomplete")
    state = {"physical_resets_started": 0, "physical_resets_completed": 0,
             "action_steps_started": 0, "returned_action_count": 0}
    keys = dict(zip(("physical_reset_started", "physical_reset_returned", "action_step_started", "action_step_returned"),
                    state))
    previous, finish = timestamp(simulator["started_at"]), timestamp(simulator["finished_at"])
    for row, event in zip(rows, events):
        state[keys[event]] += 1
        executed = state["returned_action_count"] if state["action_steps_started"] == state["returned_action_count"] else None
        fields(row, {**check.DISCLAIMER, **state, "executed_action_count": executed,
                     "safety_terminated": False, "event": event}, "receiver physics transition contradicts completion")
        current = number(row.get("recorded_at_unix_s"))
        require(previous <= current <= finish + 1, "receiver progress falls outside terminal lifetime/order")
        previous = current


def mailbox_data(files: Evidence, registration: check.Registration, identity: dict, evidence: Path,
                 observations: list[dict], simulator: dict, policy: dict) -> list[dict]:
    root = registration.root
    names = ["0001-reset.json", *[f"{i:04d}-step.json" for i in range(2, 66)], "0066-reset.json", "0067-close.json"]
    for directory in ("requests", "responses"):
        require(sorted(p.name for p in (root / directory).glob("*.json")) == names, "mailbox has missing/extra commands")
    require(sorted(p.name for p in (root / "requests").glob("*.action.npy")) ==
            [f"{i:04d}-step.action.npy" for i in range(2, 66)], "mailbox has missing/extra action arrays")
    require(len(observations) == 66, "exactly two resets and 64 observations are required")
    begin = max(timestamp(simulator["started_at"]), timestamp(policy["started_at"]))
    finish = timestamp(simulator["finished_at"])
    decoded = []
    previous_wall = begin
    for command, name in enumerate(names, 1):
        operation = name[5:-5]
        request = files.json(root / "requests" / name)
        fields(request, {"schema": "sgw-01-simulator-mailbox-v1", "operation": operation, "command_id": command,
                         "identity": identity, "channel_nonce": identity["channel_nonce"]}, "mailbox request identity differs")
        packet = files.json(root / "responses" / name)
        fields(packet, {"command_id": command, "identity": identity, "status": "ok"}, "mailbox response identity differs")
        if operation != "step":
            require(request.get("payload") == {}, "reset/close contains an action")
        if operation == "close":
            continue
        row, data = observations[command - 1], packet["data"]
        fields(row, {"command_id": command, "snapshot": data["snapshot"]}, "observation/response identity differs")
        files.bound(row["response"], root / "responses" / name)
        wall = number(row.get("recorded_at_unix_s"))
        require(previous_wall <= wall <= finish + 1, "observation falls outside simulator lifetime/order")
        previous_wall = wall
        snap = data["snapshot"]
        index = command - 1 if operation == "step" else 0
        fields(snap, {"action_step": index}, "snapshot action index differs")
        stamp = number(row.get("sim_time"))
        require(all(math.isclose(number(v), stamp, rel_tol=0, abs_tol=1e-6)
                    for v in (snap.get("sim_time"), snap.get("sim_time_s"),
                              snap.get("raw_snapshot", {}).get("simulated_time_s"), index / 15)),
                "recorded frame/action time differs from 15Hz")
        require(snap["raw_snapshot"].get("termination_reason") is None, "native safety termination is present")
        viewport = files.array(root / "responses", data["viewport"])
        require(viewport.ndim == 3 and viewport.shape[-1] == 3 and viewport.dtype == np.uint8, "viewport is not retained RGB")
        native = files.tree(root / "responses", data["policy_observation"])
        model_input = check.nano_observation(native)
        if operation == "reset":
            fields(row, {"label": "before" if command == 1 else "after",
                         "receipt": data["reset"]["receipt"]}, "reset receipt differs")
            require(data["reset"]["snapshot"] == snap and data["step_result"] is None, "reset data differs")
            receipt = row["receipt"]
            require(receipt.get("native_action_mode") == "joint_position" and bool(receipt.get("candidate_fingerprint"))
                    and bool(receipt.get("reset_id")) and bool(receipt.get("actor_root_reset_errors")), "native reset evidence absent")
            for error in receipt["actor_root_reset_errors"].values():
                require(0 <= number(error["position_error_m"]) <= .003
                        and 0 <= number(error["angle_error_degrees"]) <= 2, "recorded reset exceeds existing guards")
        else:
            offset, chunk = (command - 2) % 32, (command - 2) // 32
            request_id = f"{registration.value['attempt_id']}:request:{chunk}"
            fields(row, {"request_id": request_id, "prefix_offset": offset, "global_action_index": command - 2,
                         "step_result": {"safety_terminated": False, "termination_reason": None}},
                   "action observation/request/prefix/safety differs")
            require(data["reset"] is None and data["step_result"] == row["step_result"], "step response differs")
            fields(data["step_result"], {"safety_terminated": False, "termination_reason": None}, "step safety state differs")
            before = number(row.get("before_sim_time"))
            require(math.isclose(before, number(observations[command - 2]["sim_time"]), rel_tol=0, abs_tol=1e-6)
                    and math.isclose(stamp - before, 1 / 15, rel_tol=0, abs_tol=1e-6), "measured step delta differs")
            require(set(request["payload"]) == {"action"}, "step action payload differs")
            action = files.array(root / "requests", request["payload"]["action"])
            require(request["payload"]["action"]["path"] == f"{command:04d}-step.action.npy"
                    and action.shape == (8,) and action.dtype == np.float32
                    and np.array_equal(action, np.asarray(row["action"], dtype=np.float32)), "executed action bytes differ")
        decoded.append(model_input if command in (1, 33) else {})
    require(observations[0]["receipt"]["reset_id"] != observations[-1]["receipt"]["reset_id"]
            and observations[0]["receipt"]["candidate_fingerprint"] == observations[-1]["receipt"]["candidate_fingerprint"],
            "two distinct resets of the same bound candidate are required")
    return decoded


def policy_requests(files: Evidence, registration: check.Registration, evidence: Path, failure: dict,
                    observations: list[dict], native_inputs: list[dict]) -> list[dict]:
    require(sorted(p.name for p in evidence.glob("request-*")) == ["request-00", "request-01"]
            and len(list(evidence.glob("request-*/actions.npy"))) == 2, "exactly two returned chunks are required")
    traces = files.lines(evidence / "trace.jsonl")
    require(len(traces) == len(failure["requests"]) == 2, "request/trace count differs")
    summaries = []
    for index in range(2):
        directory = evidence / f"request-{index:02d}"
        request_id = f"{registration.value['attempt_id']}:request:{index}"
        intent = files.json(directory / "intent.json")
        input_row = observations[index * 32]
        fields(intent, {**check.DISCLAIMER, "request_id": request_id, "request_index": index,
                        "registered_cell_id": registration.cell["cell_id"], "sampling_seed": registration.seed,
                        "prompt": registration.cell["prompt"], "prompt_sha256": registration.cell["prompt_sha256"],
                        "requested_prefix": 32}, "model request intent differs")
        files.bound(intent["input_response"], Path(input_row["response"]["path"]))
        require(intent.get("input_sim_time") == input_row["sim_time"], "model input timestamp differs")
        manifest = files.json(directory / "input-manifest.json")
        require(manifest.get("camera_configuration") == registration.value["camera_configuration"]
                and set(manifest["inputs"]) == set(native_inputs[index * 32]), "model input camera/key binding differs")
        for key, expected in native_inputs[index * 32].items():
            item = manifest["inputs"][key]
            files.bound(item, directory / (key.replace("/", "-") + ".npy"))
            require(np.array_equal(files.array(directory, item), expected), "saved model input differs from native observation")
        response = files.json(directory / "response.json")
        chunk = files.json(directory / "result.json")
        require(chunk == failure["requests"][index] and chunk.get("request_id") == request_id
                and chunk.get("executed_prefix") == 32, "original request result is incomplete or contradictory")
        files.bound(chunk["actions"], directory / "actions.npy")
        actions = np.load(directory / "actions.npy", allow_pickle=False)
        files.file(directory / "backend-actions.npy")
        require(actions.shape == (32, 8) and actions.dtype == np.float32 and np.isfinite(actions).all()
                and np.array_equal(actions, np.load(directory / "backend-actions.npy", allow_pickle=False))
                and np.array_equal(actions, np.asarray(response["action"], dtype=np.float32))
                and response.get("request_id") == request_id, "returned/backend/HTTP action artifacts differ")
        trace = traces[index]
        fields(trace, {"request_id": request_id, "request_index": index, "registered_cell_id": registration.cell["cell_id"],
                       "sampling_seed": registration.seed, "prompt_sha256": registration.cell["prompt_sha256"],
                       "reset_id": observations[0]["receipt"]["reset_id"],
                       "reset_fingerprint": observations[0]["receipt"]["candidate_fingerprint"],
                       "camera_id": check.CAMERA, "camera_name": check.CAMERA, "actions_shape": [32, 8],
                       "actions_sha256": hashlib.sha256(actions.tobytes()).hexdigest()}, "native trace attribution differs")
        require(chunk["trace"] == trace and chunk["future_status"] == trace["future_status"] == response["future_status"],
                "request future/trace classification differs")
        require(trace["future_status"] in {"exposed_and_retained", "decoded_unmapped", "not_exposed", "decode_error"},
                "original future availability is unclassified")
        if trace["future_status"] in {"exposed_and_retained", "decoded_unmapped"}:
            require(bool(trace.get("future_path")) and bool(trace.get("future_sha256")), "retained future is missing")
        require(number(input_row["recorded_at_unix_s"]) <= number(trace["created_at"])
                <= number(observations[index * 32 + 1]["recorded_at_unix_s"]), "native trace time is outside its request")
        for key in ("future", "future_latent"):
            if trace.get(f"{key}_path"):
                path = Path(trace[f"{key}_path"])
                require(path.resolve().is_relative_to(evidence.resolve()), "retained future escaped original evidence")
                files.bound({"path": str(path), "sha256": trace[f"{key}_sha256"]}, path)
        if registration.value["model"] == "N3":
            latent = files.json(directory / "vision-latent.json")
            files.bound(latent, directory / "vision-latent.npy")
        for offset, action in enumerate(actions):
            row = observations[index * 32 + offset + 1]
            require(np.array_equal(action, np.asarray(row["action"], dtype=np.float32)), "executed prefix differs from original actions")
            action_intent = files.json(directory / f"action-{offset:02d}-intent.json")
            require(action_intent == {
                "request_id": request_id, "prefix_offset": offset, "action": row["action"],
                "global_action_index": index * 32 + offset, "before_sim_time": row["before_sim_time"],
                "expected_mailbox_command_id": row["command_id"],
            }, "action intent/observation identity differs")
        require(len(list(directory.glob("action-*-intent.json"))) == 32, "extra/missing action intents")
        summaries.append({name: files.file(directory / name) for name in (
            "intent.json", "input-manifest.json", "response.json", "result.json", "actions.npy", "backend-actions.npy")})
    return summaries


def witness(*, registration_path: Path, registration_sha256: str, identity_path: Path, identity_sha256: str,
            policy_evidence: Path, terminal_pods: Path, policy_job_uid: str, policy_pod_uid: str, output: Path) -> dict:
    files = Evidence()
    registration_path, identity_path, policy_evidence, output = (
        p.resolve() for p in (registration_path, identity_path, policy_evidence, output))
    require(not any(output.is_relative_to(p) for p in
                    (registration_path.parent, identity_path.parent, policy_evidence.parent)),
            "external witness output must be outside the entire original attempt")
    if output.exists():
        raise FileExistsError(output)
    registration = check.load_registration(registration_path, registration_sha256)
    identity = check.load_identity(identity_path, identity_sha256, registration)
    attempt = registration_path.parent
    require(registration.root == attempt / "simulator/mailbox" and policy_evidence == attempt / "policy/evidence"
            and identity_path == attempt / "identity.json", "unexpected original attempt directory binding")
    files.bound({"path": str(registration_path), "sha256": registration_sha256}, registration_path)
    files.bound({"path": str(identity_path), "sha256": identity_sha256}, identity_path)
    files.file(identity_path.with_suffix(".sha256"))
    require(identity_path.with_suffix(".sha256").read_text().strip() == identity_sha256, "original identity sidecar differs")
    for key in ("launch_instruction", "materialization", "environment_binding", "bound_cells", "prompts"):
        files.bound(registration.value[key], Path(registration.value[key]["path"]))
    native = registration.binding_record
    files.bound({"path": native["candidate_path"], "sha256": native["candidate_file_sha256"]},
                Path(native["candidate_path"]))
    for item in native.get("native_scene_files", []):
        files.bound(item, Path(item["path"]))
    binding = files.json(registration.binding_path)
    source = Path(binding["source_root"]).resolve()
    require(binding.get("source_commit") == SOURCE_COMMIT and _git_revision(str(source)) == SOURCE_COMMIT,
            "original clean SGW source does not match 8ac4858")
    pods = files.json(terminal_pods)
    require(pods.get("apiVersion") == "v1" and pods.get("kind") in ("List", "PodList")
            and len(pods.get("items", [])) == 2, "exact raw two-Pod terminal snapshot required")
    by_uid = {pod["metadata"]["uid"]: pod for pod in pods["items"]}
    require(set(by_uid) == {identity["simulator_pod_uid"], policy_pod_uid}, "raw snapshot Pod identities differ")
    require(policy_job_uid != identity["simulator_job_uid"], "policy and simulator must be distinct Jobs")
    simulator = terminal_pod(by_uid[identity["simulator_pod_uid"]], role="simulator",
                             pod_uid=identity["simulator_pod_uid"], job_uid=identity["simulator_job_uid"],
                             registration=registration, identity_path=identity_path, identity_sha256=identity_sha256,
                             evidence=policy_evidence, source=source)
    policy = terminal_pod(by_uid[policy_pod_uid], role="policy", pod_uid=policy_pod_uid, job_uid=policy_job_uid,
                         registration=registration, identity_path=identity_path, identity_sha256=identity_sha256,
                         evidence=policy_evidence, source=source)
    require(simulator["namespace"] == policy["namespace"]
            and timestamp(policy["started_at"]) <= timestamp(simulator["finished_at"]) < timestamp(policy["finished_at"]),
            "policy interruption does not follow simulator termination")
    root = registration.root
    require(not any((root / name).exists() for name in LIFECYCLE_FILES)
            and (root / "faults").is_dir() and not any((root / "faults").iterdir()),
            "receiver failure/fault/lifecycle evidence contradicts the legacy missing-marker case")
    completion = receiver.verify_data_completion(root, identity, 64, expected_resets=2)
    fields(completion, {**check.DISCLAIMER, "returned_action_count": 64, "safety_terminated": False}, "receiver data is not complete/safe")
    ready = files.json(root / "receiver_ready.json")
    fields(ready, {**check.DISCLAIMER, "identity": identity, "registration_sha256": registration_sha256,
                   "binding": binding, "app_launcher_count": 1, "executed_action_count": 0,
                   "physical_resets_completed": 0, "metadata_transport": "DirectoryRefresher STATX_FORCE_SYNC"},
           "original receiver readiness binding differs")
    require(type(ready.get("pid")) is int and ready["pid"] > 0, "receiver PID unavailable")
    require(not (policy_evidence / "result.json").exists()
            and not list(policy_evidence.glob("request-*/failure.json")), "policy has contradictory success/earlier failure")
    failure = files.json(policy_evidence / "failure.json")
    fields(failure, {**check.DISCLAIMER, **COUNTS, "status": "technical_failure_preserve_partial_no_retry",
                     "executed_action_count": None, "receiver_completion": None, "safety_terminated": False,
                     "execution_count_semantics":
                     "unavailable final count; acknowledged prefix retained; inspect receiver partial evidence",
                     "sampling_seed": registration.seed}, "original policy failure/counts are not the cleanup-only case")
    require(failure.get("model_config") == registration.value["model_config"], "policy model config differs")
    interrupted_cleanup(failure.get("traceback"), source)
    progress = files.lines(policy_evidence / "progress.jsonl")
    policy_progress(progress, timestamp(policy["started_at"]), timestamp(policy["finished_at"]))
    require(number(progress[-1]["recorded_at_unix_s"]) >= timestamp(simulator["finished_at"]),
            "policy cleanup preceded observed simulator termination")
    observations = files.lines(policy_evidence / "observations.jsonl")
    native_inputs = mailbox_data(files, registration, identity, policy_evidence, observations, simulator, policy)
    require(failure.get("resets") == [{k: v for k, v in observations[i].items() if k != "recorded_at_unix_s"}
                                     for i in (0, 65)], "policy reset summaries differ from retained observations")
    requests = policy_requests(files, registration, policy_evidence, failure, observations, native_inputs)
    intent = files.json(policy_evidence / "intent.json")
    fields(intent, {**check.DISCLAIMER, **check.LIMITS, "expected_registration_sha256": registration_sha256,
                    "expected_identity_sha256": identity_sha256}, "policy launch intent differs")
    files.bound(intent["registration"], registration_path)
    files.bound(intent["identity"], identity_path)
    ready_copy = files.json(policy_evidence / "receiver-ready.json")
    files.bound(ready_copy["record"], root / "receiver_ready.json")
    require(ready_copy.get("receipt") == ready, "policy receiver-ready copy differs")
    shutdown = files.json(policy_evidence / "shutdown.json")
    fields(shutdown, {"server_started": True, "server_closed": True, "serving_thread_alive": False,
                      "native_call_drained": True}, "policy endpoint did not shut down cleanly after interruption")
    endpoint = files.json(policy_evidence / "endpoint.json")
    attest = files.json(policy_evidence / "server-attestation.json")
    loaded = files.json(policy_evidence / "loaded-runtime.json")
    config = registration.value["model_config"]
    require(type(endpoint.get("pid")) is int and endpoint["pid"] > 0 and endpoint.get("loopback_only") is True
            and re.fullmatch(r"http://127\.0\.0\.1:[0-9]+", endpoint.get("url", "")) is not None
            and 0 < int(endpoint["url"].rsplit(":", 1)[1]) < 65536
            and attest.get("server_pid") == endpoint["pid"]
            and isinstance(attest.get("server_start_time"), str) and attest["server_start_time"].isdecimal()
            and attest.get("model") == registration.value["model"] and attest.get("config") == config
            and attest.get("source_commit") == config["source_commit"] and attest.get("checkpoint_revision") == config["revision"]
            and attest.get("identity_route") == "clean_pinned_source_and_verified_checkpoint_file_manifest"
            and loaded.get("resolved_config") == config and loaded.get("identity_attestation") == attest
            and loaded.get("source_commit") == config["source_commit"] and loaded.get("checkpoint_revision") == config["revision"],
            "owned endpoint/loaded model attestation differs")
    backend_reset = files.json(policy_evidence / "backend-reset.json")
    require(backend_reset.get("status") == "reset" and backend_reset.get("camera_name") == check.CAMERA
            and bool(backend_reset.get("reset_id")), "owned backend reset evidence absent")
    require(all(chunk["trace"].get("wrapper_reset_id") == backend_reset.get("wrapper_reset_id") == backend_reset["reset_id"]
                for chunk in failure["requests"])
            and len({chunk["trace"].get("wrapper_request_id") for chunk in failure["requests"]}) == 2,
            "owned request/reset identity is inconsistent")
    receiver_progress = files.lines(root / "physics-progress.jsonl")
    physics_progress(receiver_progress, simulator)
    fields(receiver_progress[-1], {k: completion[k] for k in (
        "physical_resets_started", "physical_resets_completed", "action_steps_started",
        "returned_action_count", "executed_action_count", "safety_terminated")}, "receiver final physics counters differ")
    originals = {name: files.file(path) for name, path in {
        "registration": registration_path, "identity": identity_path, "terminal_pods": terminal_pods,
        "receiver_complete": root / "receiver_complete.json", "receiver_close_response": root / "responses/0067-close.json",
        "policy_failure": policy_evidence / "failure.json", "policy_progress": policy_evidence / "progress.jsonl",
        "policy_observations": policy_evidence / "observations.jsonl", "policy_trace": policy_evidence / "trace.jsonl",
        "receiver_physics_progress": root / "physics-progress.jsonl",
        "witness_implementation": Path(__file__),
    }.items()}
    manifest = files.stable_digest()
    require(not any((root / name).exists() for name in LIFECYCLE_FILES), "receiver lifecycle evidence appeared during verification")
    receiver.verify_data_completion(root, identity, 64, expected_resets=2)
    result = {
        "schema": "sgw-01-external-runtime-exit-witness-v1", "scope": "external_observation_not_receiver_authored",
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(), "source_commit": SOURCE_COMMIT,
        "attempt_id": registration.value["attempt_id"], "model": registration.value["model"],
        "data_plane_contract_verified": True, "simulator_process_termination_observed": True,
        "app_close_return_observed": False, "receiver_authored_shutdown_marker": "unavailable",
        "original_policy_status": failure["status"], "original_policy_executed_action_count": None,
        "policy_handoff_failure": "preserved_cleanup_verify_completion_wait_KeyboardInterrupt",
        "interrupt_origin": "coordinator_reported; not independently established by Pod JSON or traceback",
        "requests_consumed": 2, "receiver_executed_actions_verified": 64, "physical_resets_verified": 2,
        "command_count": 67, "recorded_step_dt_s": 1 / 15, "behavioral_episodes": 0,
        "release_permitted": False, "study_ready": False, "physical_forecast_alignment_qualified": False,
        "future_physics_mapping": "unavailable", "simulator": simulator, "policy": policy,
        "receiver_native_pid": ready["pid"], "policy_endpoint_pid": endpoint["pid"],
        "originals": originals, "requests": requests, "verified_artifacts": manifest,
        "limitations": [
            "External retained-Pod observation, not a receiver/supervisor-authored shutdown receipt.",
            "No observation that app.close returned; original failed cleanup handoff remains a failure.",
            "Recorded 15Hz action/observation correspondence is not camera exposure or forecast alignment.",
            "No replay, model call, behavioral release, or change to original evidence/future classification.",
        ],
    }
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, sort_keys=True, separators=(",", ":"), allow_nan=False)
        stream.write("\n")
        stream.flush()
        import os
        os.fsync(stream.fileno())
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("registration", "identity", "policy-evidence", "terminal-pods", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    for name in ("registration-sha256", "identity-sha256", "policy-job-uid", "policy-pod-uid"):
        parser.add_argument(f"--{name}", required=True)
    args = vars(parser.parse_args())
    args["registration_path"], args["identity_path"] = args.pop("registration"), args.pop("identity")
    try:
        result = witness(**args)
    except Exception as exc:
        print(json.dumps({"status": "unavailable", "error": f"{type(exc).__name__}: {exc}",
                          "study_ready": False, "release_permitted": False}), file=sys.stderr)
        raise SystemExit(2)
    print(json.dumps({"status": "external_observation_written", "output": str(args["output"].resolve()),
                      "sha256": _digest(args["output"]), "requests_consumed": result["requests_consumed"]}))


if __name__ == "__main__":
    main()
