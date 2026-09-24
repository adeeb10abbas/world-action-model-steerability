"""Synthetic disk evidence only: no native/model, network, or lifecycle calls."""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

from tools import witness_runtime_check_exit as witness
from experiments.workshops.spatial_grounding_v1 import runtime_closed_loop_check as check
from experiments.workshops.spatial_grounding_v1 import native_runtime_check_receiver as receiver
from experiments.workshops.spatial_grounding_v1.paper_engineering import record
from experiments.workshops.spatial_grounding_v1.simulator_mailbox import _array, _encode_tree, _write


SIM_JOB = "52fc58f5-9c87-48a3-9ae6-0dd6c0f158d8"
SIM_POD = "91ff3894-b12a-4820-831f-2f906e976bce"
POLICY_JOB = "3029ea71-7fba-482c-bdbb-fabb65a6af2f"
POLICY_POD = "4b01b240-d8c8-4025-ac81-29f6957747be"
BASE = datetime(2026, 9, 24, 20, tzinfo=timezone.utc).timestamp()


def put(path, value):
    path.write_text(json.dumps(value))
    return record(path)


def jsonl(path, rows):
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))


def at(offset):
    return datetime.fromtimestamp(BASE + offset, timezone.utc).isoformat().replace("+00:00", "Z")


def pod(role, args, source):
    simulator = role == "simulator"
    uid, job = (SIM_POD, SIM_JOB) if simulator else (POLICY_POD, POLICY_JOB)
    output = args["registration_path"].parent / role
    env = {key: {"name": key, "value": str(value)} for key, value in {
        "OUT": output, "SOURCE": source, "MODEL": "N3", "REGISTRATION": args["registration_path"],
        "REGISTRATION_SHA256": args["registration_sha256"], "IDENTITY": args["identity_path"],
    }.items()}
    if simulator:
        binding_path = args["registration_path"].parent / "binding.json"
        for key, val in (("SGW01_ENV_BINDING", str(binding_path)), ("SGW01_ENV_BINDING_SHA256", record(binding_path)["sha256"])):
            env[key] = {"name": key, "value": val}
    for key, field in (("JOB_UID", "metadata.labels['batch.kubernetes.io/controller-uid']"), ("POD_UID", "metadata.uid")):
        env[key] = {"name": key, "valueFrom": {"fieldRef": {"fieldPath": field}}}
    module = "native_runtime_check_receiver" if simulator else "runtime_closed_loop_check"
    prefix = '"$PY"' if simulator else 'bash tools/cluster_policy_bootstrap.sh "$MODEL" "$PY"'
    command = (f'{prefix} -m experiments.workshops.spatial_grounding_v1.{module} '
               '--registration "$REGISTRATION" --registration-sha256 "$REGISTRATION_SHA256" '
               '--identity "$IDENTITY" --identity-sha256 "$IDENTITY_SHA256"')
    if not simulator:
        command += ' --output "$OUT/evidence"'
    script = "\n".join(['set -euo pipefail', 'cd "$SOURCE"', f'test "$(git rev-parse HEAD)" = {witness.SOURCE_COMMIT}',
                        'test -z "$(git status --porcelain)"',
                        'IDENTITY_SHA256=$(cat "${IDENTITY%.json}.sha256")', command, "sync"])
    container_id, image = "containerd://" + ("a" if simulator else "b") * 64, "registry/image@sha256:" + "c" * 64
    start, finish, exit_code, phase, reason = (0, 100, 0, "Succeeded", "Completed") if simulator else (1, 200, 1, "Failed", "Error")
    return {
        "apiVersion": "v1", "kind": "Pod",
        "metadata": {"uid": uid, "name": role + "-pod", "namespace": "synthetic", "creationTimestamp": at(start),
                     "labels": {"batch.kubernetes.io/controller-uid": job, "batch.kubernetes.io/job-name": role + "-job"},
                     "ownerReferences": [{"uid": job, "name": role + "-job", "kind": "Job",
                                          "apiVersion": "batch/v1", "controller": True}]},
        "spec": {"restartPolicy": "Never", "containers": [
            {"name": role, "image": image, "command": ["/bin/bash", "-ec"], "args": [script], "env": list(env.values())}]},
        "status": {"phase": phase, "startTime": at(start), "containerStatuses": [
            {"name": role, "imageID": image, "containerID": container_id, "restartCount": 0, "ready": False,
             "started": False, "lastState": {}, "state": {"terminated": {
                 "containerID": container_id, "exitCode": exit_code, "reason": reason,
                 "startedAt": at(start), "finishedAt": at(finish)}}}]},
    }


@pytest.fixture
def case(tmp_path, monkeypatch):
    attempt, source = tmp_path / "original-attempt", tmp_path / "original-source"
    evidence, root = attempt / "policy/evidence", attempt / "simulator/mailbox"
    for path in (evidence, root / "requests", root / "responses", root / "faults", source):
        path.mkdir(parents=True)
    config, camera = dict(check.CONFIGS["N3"]), check.camera_configuration_identity()
    binding_path = attempt / "binding.json"
    binding = {"source_commit": witness.SOURCE_COMMIT, "source_root": str(source)}
    binding_ref = put(binding_path, binding)
    candidate_ref = put(attempt / "candidate.json", {"synthetic": True})
    cell = {"cell_id": "synthetic-cell", "effective_policy_seed": 8300, "prompt": "fixed positive",
            "prompt_sha256": witness.hashlib.sha256(b"fixed positive").hexdigest()}
    value = {
        "scope": check.SCOPE, "qualification_id": "synthetic-qualification", "attempt_id": "synthetic-attempt",
        "cell_id": cell["cell_id"], "model": "N3", "model_config": config, "camera_configuration": camera,
        "mailbox_root": str(root), "environment_binding": binding_ref,
    }
    for key in ("launch_instruction", "materialization", "bound_cells", "prompts"):
        value[key] = put(attempt / f"{key}.json", {"synthetic": True})
    registration_path = attempt / "registration.json"
    reg_ref = put(registration_path, value)
    registration = check.Registration(registration_path, reg_ref["sha256"], value, cell, binding_path,
                                      {"candidate_file_sha256": candidate_ref["sha256"], "candidate_path": candidate_ref["path"]})
    # Frozen scene/materialization loading and git identity have independent CPU
    # coverage. Every witness, identity, receipt, array and Pod check is real here.
    monkeypatch.setattr(check, "load_registration", lambda path, sha: registration)
    monkeypatch.setattr(witness, "_git_revision", lambda path: witness.SOURCE_COMMIT)
    identity = {
        **{key: value[key] for key in ("scope", "qualification_id", "attempt_id", "cell_id")},
        "registration_sha256": reg_ref["sha256"], "candidate_sha256": candidate_ref["sha256"],
        "binding_sha256": binding_ref["sha256"], "channel_nonce": "synthetic-nonce",
        "simulator_job_uid": SIM_JOB, "simulator_pod_uid": SIM_POD,
    }
    identity_path = attempt / "identity.json"
    id_ref = put(identity_path, identity)
    identity_path.with_suffix(".sha256").write_text(id_ref["sha256"] + "\n")
    args = dict(registration_path=registration_path, registration_sha256=reg_ref["sha256"],
                identity_path=identity_path, identity_sha256=id_ref["sha256"], policy_evidence=evidence,
                terminal_pods=tmp_path / "pods.json", policy_job_uid=POLICY_JOB, policy_pod_uid=POLICY_POD,
                output=tmp_path / "external-witness.json")
    put(args["terminal_pods"], {"apiVersion": "v1", "kind": "List",
                               "items": [pod("simulator", args, source), pod("policy", args, source)]})
    ready = {**check.DISCLAIMER, "identity": identity, "registration_sha256": reg_ref["sha256"], "binding": binding,
             "app_launcher_count": 1, "executed_action_count": 0, "physical_resets_completed": 0,
             "metadata_transport": "DirectoryRefresher STATX_FORCE_SYNC", "pid": 98}
    put(root / "receiver_ready.json", ready)
    put(evidence / "receiver-ready.json", {"record": record(root / "receiver_ready.json"), "receipt": ready})
    actions = [np.arange(256, dtype=np.float32).reshape(32, 8) / 1000 + i for i in range(2)]
    observations, native_inputs = [], []
    for command in range(1, 68):
        operation = "reset" if command in (1, 66) else "close" if command == 67 else "step"
        name = f"{command:04d}-{operation}"
        payload = {}
        if operation == "step":
            action = actions[(command - 2) // 32][(command - 2) % 32]
            payload = {"action": _array(root / "requests" / f"{name}.action.npy", action)}
        _write(root / "requests" / f"{name}.json", {
            "schema": "sgw-01-simulator-mailbox-v1", "operation": operation, "command_id": command,
            "identity": identity, "channel_nonce": identity["channel_nonce"], "payload": payload,
        })
        packet = {"command_id": command, "identity": identity, "status": "ok"}
        if operation == "close":
            put(root / "responses" / f"{name}.json", {**packet, "data": {"reset": None, "step_result": None}})
            continue
        index = command - 1 if operation == "step" else 0
        snapshot = {"action_step": index, "sim_time": index / 15, "sim_time_s": index / 15,
                    "raw_snapshot": {"simulated_time_s": index / 15, "termination_reason": None}}
        native = {"image_obs": {key: np.arange(72, dtype=np.uint8).reshape(1, 4, 6, 3) + index + i
                                for i, key in enumerate(("wrist_cam", check.CAMERA, "over_shoulder_right_camera"))},
                  "proprio_obs": {"arm_joint_pos": np.full((1, 7), index, np.float32),
                                  "gripper_pos": np.full((1, 1), .5, np.float32)}}
        receipt = {"reset_id": f"reset-{command}", "candidate_fingerprint": "synthetic-candidate",
                   "native_action_mode": "joint_position",
                   "actor_root_reset_errors": {"cube": {"position_error_m": 0.0, "angle_error_degrees": 0.0}}}
        step = {"safety_terminated": False, "termination_reason": None} if operation == "step" else None
        packet["data"] = {
            "snapshot": snapshot, "reset": {"snapshot": snapshot, "receipt": receipt} if operation == "reset" else None,
            "step_result": step, "viewport": _array(root / "responses" / f"{name}.viewport.npy", np.zeros((4, 6, 3), np.uint8)),
            "policy_observation": _encode_tree(root / "responses", name + ".policy", native),
        }
        response_ref = put(root / "responses" / f"{name}.json", packet)
        row = {"recorded_at_unix_s": BASE + 10 + command / 2, "command_id": command,
               "response": response_ref, "snapshot": snapshot, "sim_time": index / 15}
        if operation == "reset":
            row.update(label="before" if command == 1 else "after", receipt=receipt)
        else:
            row.update(request_id=f"synthetic-attempt:request:{(command - 2) // 32}", prefix_offset=(command - 2) % 32,
                       global_action_index=command - 2, action=action.tolist(), before_sim_time=(index - 1) / 15,
                       step_result=step)
        observations.append(row)
        native_inputs.append(check.nano_observation(native))
    jsonl(evidence / "observations.jsonl", observations)
    completion = {**check.DISCLAIMER, "schema": receiver.COMPLETION_SCHEMA, "identity": identity,
                  "status": "closed_with_two_resets", "physical_resets_started": 2, "physical_resets_completed": 2,
                  "action_steps_started": 64, "returned_action_count": 64, "executed_action_count": 64,
                  "safety_terminated": False, "command_count": 67, "close_command_id": 67,
                  "close_response_sha256": record(root / "responses/0067-close.json")["sha256"]}
    put(root / "receiver_complete.json", completion)
    counters = {key: 0 for key in witness.COUNTS}
    progress = [{**check.DISCLAIMER, **counters, "recorded_at_unix_s": BASE + 2}]
    changes = ["physical_resets_started", "physical_resets_completed"]
    for _ in range(2):
        changes += ["model_requests_started", "model_requests_completed", "responses_validated"] + ["acknowledged_action_count"] * 32
    changes += ["physical_resets_started", "physical_resets_completed"]
    for key in changes:
        counters[key] += 1
        progress.append({**check.DISCLAIMER, **counters, "recorded_at_unix_s": BASE + 2 + len(progress) / 2})
    progress.append({**check.DISCLAIMER, **counters, "recorded_at_unix_s": BASE + 199.8})
    jsonl(evidence / "progress.jsonl", progress)
    physics, counts = [], {"physical_resets_started": 0, "physical_resets_completed": 0,
                           "action_steps_started": 0, "returned_action_count": 0}
    events = ["physical_reset_started", "physical_reset_returned"] + ["action_step_started", "action_step_returned"] * 64
    events += ["physical_reset_started", "physical_reset_returned"]
    keys = dict(zip(("physical_reset_started", "physical_reset_returned", "action_step_started", "action_step_returned"), counts))
    for event in events:
        counts[keys[event]] += 1
        physics.append({**check.DISCLAIMER, **counts, "event": event, "safety_terminated": False,
                        "executed_action_count": counts["returned_action_count"]
                        if counts["action_steps_started"] == counts["returned_action_count"] else None,
                        "recorded_at_unix_s": BASE + 5 + len(physics) / 4})
    jsonl(root / "physics-progress.jsonl", physics)
    chunks, traces = [], []
    for index in range(2):
        directory = evidence / f"request-{index:02d}"
        directory.mkdir()
        request_id = f"synthetic-attempt:request:{index}"
        put(directory / "intent.json", {**check.DISCLAIMER, "request_id": request_id, "request_index": index,
            "registered_cell_id": cell["cell_id"], "sampling_seed": 8300, "prompt": cell["prompt"],
            "prompt_sha256": cell["prompt_sha256"], "requested_prefix": 32,
            "input_response": observations[index * 32]["response"], "input_sim_time": index * 32 / 15})
        inputs = {}
        for key, array in native_inputs[index * 32].items():
            name = key.replace("/", "-") + ".npy"
            meta = _array(directory / name, array)
            inputs[key] = {**meta, **record(directory / name)}
        put(directory / "input-manifest.json", {"inputs": inputs, "camera_configuration": camera})
        _array(directory / "actions.npy", actions[index])
        _array(directory / "backend-actions.npy", actions[index])
        _array(directory / "vision-latent.npy", np.ones((1, 2, 3), np.float32))
        put(directory / "vision-latent.json", record(directory / "vision-latent.npy"))
        future_ref = _array(directory / "future.npy", np.ones((33, 2, 2, 3), np.uint8))
        trace = {"request_id": request_id, "request_index": index, "registered_cell_id": cell["cell_id"],
                 "sampling_seed": 8300, "prompt_sha256": cell["prompt_sha256"], "reset_id": "reset-1",
                 "reset_fingerprint": "synthetic-candidate", "camera_id": check.CAMERA, "camera_name": check.CAMERA,
                 "actions_shape": [32, 8], "actions_sha256": witness.hashlib.sha256(actions[index].tobytes()).hexdigest(),
                 "future_status": "decoded_unmapped", "future_path": str(directory / "future.npy"),
                 "future_sha256": future_ref["sha256"], "created_at": observations[index * 32]["recorded_at_unix_s"] + .1,
                 "wrapper_request_id": f"wrapper-{index}", "wrapper_reset_id": "backend-reset"}
        chunk = {"request_id": request_id, "actions": record(directory / "actions.npy"), "trace": trace,
                 "future_status": trace["future_status"], "executed_prefix": 32}
        put(directory / "result.json", chunk)
        put(directory / "response.json", {"request_id": request_id, "action": actions[index].tolist(),
                                         "future_status": trace["future_status"]})
        for offset in range(32):
            row = observations[index * 32 + offset + 1]
            put(directory / f"action-{offset:02d}-intent.json", {
                "request_id": request_id, "prefix_offset": offset, "action": row["action"],
                "global_action_index": index * 32 + offset, "before_sim_time": row["before_sim_time"],
                "expected_mailbox_command_id": row["command_id"]})
        chunks.append(chunk)
        traces.append(trace)
    jsonl(evidence / "trace.jsonl", traces)
    trace = (f'\nCleanup:\nTraceback (most recent call last):\n'
             f'  File "{source}/experiments/workshops/spatial_grounding_v1/runtime_closed_loop_check.py", line 450, in run\n'
             '    completion = verify_completion(registration.root, identity, metadata_refresh,\n'
             f'  File "{source}/experiments/workshops/spatial_grounding_v1/native_runtime_check_receiver.py", line 173, in verify_completion\n'
             '    time.sleep(.01)\nKeyboardInterrupt\n')
    failure = {**check.DISCLAIMER, **witness.COUNTS, "status": "technical_failure_preserve_partial_no_retry",
               "executed_action_count": None, "receiver_completion": None, "safety_terminated": False,
               "execution_count_semantics": "unavailable final count; acknowledged prefix retained; inspect receiver partial evidence",
               "model_config": config, "sampling_seed": 8300, "requests": chunks,
               "resets": [{key: val for key, val in observations[i].items() if key != "recorded_at_unix_s"} for i in (0, 65)],
               "traceback": trace}
    put(evidence / "failure.json", failure)
    put(evidence / "intent.json", {**check.DISCLAIMER, **check.LIMITS, "registration": reg_ref, "identity": id_ref,
                                   "expected_registration_sha256": reg_ref["sha256"], "expected_identity_sha256": id_ref["sha256"]})
    put(evidence / "shutdown.json", {"server_started": True, "server_closed": True,
                                     "serving_thread_alive": False, "native_call_drained": True})
    put(evidence / "endpoint.json", {"pid": 26, "url": "http://127.0.0.1:1025", "loopback_only": True})
    attestation = {"server_pid": 26, "server_start_time": "12345", "model": "N3", "config": config,
                   "source_commit": config["source_commit"], "checkpoint_revision": config["revision"],
                   "identity_route": "clean_pinned_source_and_verified_checkpoint_file_manifest"}
    put(evidence / "server-attestation.json", attestation)
    put(evidence / "loaded-runtime.json", {"resolved_config": config, "identity_attestation": attestation,
                                          "source_commit": config["source_commit"], "checkpoint_revision": config["revision"]})
    put(evidence / "backend-reset.json", {"status": "reset", "camera_name": check.CAMERA,
                                         "reset_id": "backend-reset", "wrapper_reset_id": "backend-reset"})
    return args


def amend(path, change):
    value = json.loads(path.read_text())
    change(value)
    put(path, value)


def fingerprint(root):
    return {str(path.relative_to(root)): (path.stat().st_mtime_ns, record(path)["sha256"])
            for path in root.rglob("*") if path.is_file()}


def test_external_witness_preserves_entire_failed_attempt_and_never_claims_release(case):
    original = fingerprint(case["registration_path"].parent)
    result = witness.witness(**case)
    assert result == json.loads(case["output"].read_text())
    assert result["data_plane_contract_verified"] and result["simulator_process_termination_observed"]
    assert result["requests_consumed"] == 2 and result["receiver_executed_actions_verified"] == 64
    assert result["command_count"] == 67 and result["physical_resets_verified"] == 2
    assert result["policy"]["exit_code"] == 1 and result["simulator"]["exit_code"] == 0
    assert result["policy_endpoint_pid"] == 26 and result["receiver_native_pid"] == 98
    assert result["original_policy_status"] == "technical_failure_preserve_partial_no_retry"
    assert result["original_policy_executed_action_count"] is None
    assert not result["app_close_return_observed"] and result["receiver_authored_shutdown_marker"] == "unavailable"
    assert not result["study_ready"] and not result["release_permitted"] and result["behavioral_episodes"] == 0
    assert not result["physical_forecast_alignment_qualified"] and result["future_physics_mapping"] == "unavailable"
    assert result["verified_artifacts"]["files"] > 500
    assert len(case["output"].read_bytes()) < 16000
    assert fingerprint(case["registration_path"].parent) == original
    with pytest.raises(FileExistsError):
        witness.witness(**case)
    assert fingerprint(case["registration_path"].parent) == original


def test_python_313_traceback_caret_annotations_do_not_hide_the_same_wait(case):
    amend(case["policy_evidence"] / "failure.json", lambda value: value.update(
        traceback=value["traceback"].replace("    time.sleep(.01)\n", "    time.sleep(.01)\n    ~~~~~~~~~~^^^^^\n")))
    assert witness.witness(**case)["policy_handoff_failure"].endswith("KeyboardInterrupt")


@pytest.mark.parametrize("target", [
    "simulator/mailbox/receiver_complete.json", "simulator/mailbox/responses/0067-close.json",
    "simulator/mailbox/responses/0042-step.json", "simulator/mailbox/responses/0033-step.policy.000000.npy",
    "policy/evidence/request-01/actions.npy", "policy/evidence/request-00/backend-actions.npy",
    "policy/evidence/request-00/action-31-intent.json", "policy/evidence/observations.jsonl",
    "policy/evidence/progress.jsonl", "policy/evidence/shutdown.json",
])
def test_simulator_exit_zero_cannot_replace_missing_data(case, target):
    (case["registration_path"].parent / target).unlink()
    with pytest.raises((ValueError, OSError)):
        witness.witness(**case)
    assert not case["output"].exists()


@pytest.mark.parametrize("filename", witness.LIFECYCLE_FILES)
def test_receiver_lifecycle_or_failure_markers_are_not_rewritten_or_ignored(case, filename):
    root = case["registration_path"].parent / "simulator/mailbox"
    put(root / filename, {"identity": "contradiction"})
    with pytest.raises(ValueError, match="lifecycle"):
        witness.witness(**case)
    assert not case["output"].exists()


@pytest.mark.parametrize("field,value", [
    ("executed_action_count", 63), ("returned_action_count", 63), ("physical_resets_completed", 1),
    ("safety_terminated", True), ("close_response_sha256", "0" * 64), ("release_permitted", True),
])
def test_exit_zero_does_not_override_contradictory_receiver_completion(case, field, value):
    amend(case["registration_path"].parent / "simulator/mailbox/receiver_complete.json",
          lambda receipt: receipt.update({field: value}))
    with pytest.raises(ValueError):
        witness.witness(**case)
    assert not case["output"].exists()


@pytest.mark.parametrize("mutation", [
    "owner", "uid", "restart", "container", "image", "time", "phase", "exit", "out",
    "source", "model", "registration", "identity", "hash", "script", "extra-container",
])
def test_terminal_policy_identity_source_and_exit_must_all_match(case, mutation):
    def change(raw):
        item = raw["items"][1]
        status = item["status"]["containerStatuses"][0]
        container = item["spec"]["containers"][0]
        if mutation == "owner": item["metadata"]["ownerReferences"][0]["uid"] = SIM_JOB
        elif mutation == "uid": item["metadata"]["uid"] = SIM_POD
        elif mutation == "restart": status["restartCount"] = 1
        elif mutation == "container": status["state"]["terminated"]["containerID"] = "containerd://" + "e" * 64
        elif mutation == "image": status["imageID"] = "registry/image@sha256:" + "e" * 64
        elif mutation == "time": status["state"]["terminated"]["finishedAt"] = at(50)
        elif mutation == "phase": item["status"]["phase"] = "Succeeded"
        elif mutation == "exit": status["state"]["terminated"]["exitCode"] = 0
        elif mutation == "script": container["args"][0] = container["args"][0].replace(witness.SOURCE_COMMIT, "f" * 40)
        elif mutation == "extra-container": item["spec"]["containers"].append(dict(container))
        else:
            key = {"out": "OUT", "source": "SOURCE", "model": "MODEL", "registration": "REGISTRATION",
                   "identity": "IDENTITY", "hash": "REGISTRATION_SHA256"}[mutation]
            next(env for env in container["env"] if env["name"] == key)["value"] = "different"
    amend(case["terminal_pods"], change)
    with pytest.raises(ValueError):
        witness.witness(**case)
    assert not case["output"].exists()


@pytest.mark.parametrize("mutation", [
    "earlier-failure", "timeout", "wrong-frame", "extra-frame", "safety", "count", "prefix", "reset",
])
def test_policy_failure_must_be_only_the_complete_cleanup_wait(case, mutation):
    def change(value):
        if mutation == "earlier-failure": value["traceback"] = "ValueError: original failure\n" + value["traceback"]
        elif mutation == "timeout": value["traceback"] = value["traceback"].replace("KeyboardInterrupt", "TimeoutError: timed out")
        elif mutation == "wrong-frame": value["traceback"] = value["traceback"].replace("in verify_completion", "in predict")
        elif mutation == "extra-frame": value["traceback"] = value["traceback"].replace("    time.sleep(.01)", '  File "other.py", line 1, in bad\n    time.sleep(.01)')
        elif mutation == "safety": value["safety_terminated"] = True
        elif mutation == "count": value["model_requests_completed"] = 1
        elif mutation == "prefix": value["requests"][0]["executed_prefix"] = 31
        elif mutation == "reset": value["resets"][1]["receipt"]["reset_id"] = "reset-1"
    amend(case["policy_evidence"] / "failure.json", change)
    with pytest.raises(ValueError):
        witness.witness(**case)
    assert not case["output"].exists()


@pytest.mark.parametrize("mutation", ["delta", "order", "action", "response-hash", "request-id", "camera-bytes"])
def test_complete_counts_do_not_replace_observation_action_time_identity(case, mutation):
    path = case["policy_evidence"] / "observations.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    if mutation == "delta": rows[4]["before_sim_time"] += .001
    elif mutation == "order": rows[4], rows[5] = rows[5], rows[4]
    elif mutation == "action": rows[4]["action"][0] += .01
    elif mutation == "response-hash": rows[4]["response"]["sha256"] = "0" * 64
    elif mutation == "request-id": rows[4]["request_id"] = "wrong"
    elif mutation == "camera-bytes":
        root = case["registration_path"].parent / "simulator/mailbox/responses"
        (root / "0042-step.policy.000000.npy").write_bytes(b"corrupted")
    jsonl(path, rows)
    with pytest.raises(ValueError):
        witness.witness(**case)
    assert not case["output"].exists()


@pytest.mark.parametrize("filename,key", [
    ("progress.jsonl", "model_requests_started"), ("progress.jsonl", "acknowledged_action_count"),
    ("../..//simulator/mailbox/physics-progress.jsonl", "action_steps_started"),
])
def test_intermediate_counter_contradictions_are_rejected(case, filename, key):
    path = case["policy_evidence"] / filename
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    rows[8][key] = 99
    jsonl(path, rows)
    with pytest.raises(ValueError):
        witness.witness(**case)
    assert not case["output"].exists()


def test_hash_source_fault_and_output_scope_fail_closed(case, monkeypatch):
    bad = {**case, "registration_sha256": "0" * 64}
    with pytest.raises(ValueError):
        witness.witness(**bad)
    with pytest.raises(ValueError):
        witness.witness(**{**case, "identity_sha256": "0" * 64})
    with pytest.raises(ValueError, match="outside"):
        witness.witness(**{**case, "output": case["registration_path"].parent / "receiver_shutdown.json"})
    monkeypatch.setattr(witness, "_git_revision", lambda _: "f" * 40)
    with pytest.raises(ValueError, match="source"):
        witness.witness(**case)
    monkeypatch.setattr(witness, "_git_revision", lambda _: witness.SOURCE_COMMIT)
    put(case["registration_path"].parent / "simulator/mailbox/faults/0040-step.json", {"error": "real failure"})
    with pytest.raises(ValueError, match="failure/fault"):
        witness.witness(**case)
    assert not case["output"].exists()


def test_cli_has_no_native_factory_and_missing_evidence_reports_unavailable(case):
    process = subprocess.run([
        sys.executable, "-m", "tools.witness_runtime_check_exit", "--registration", str(case["registration_path"]),
        "--registration-sha256", "0" * 64, "--identity", str(case["identity_path"]),
        "--identity-sha256", case["identity_sha256"], "--policy-evidence", str(case["policy_evidence"]),
        "--terminal-pods", str(case["terminal_pods"]), "--policy-job-uid", POLICY_JOB,
        "--policy-pod-uid", POLICY_POD, "--output", str(case["output"]),
    ], text=True, capture_output=True, timeout=30)
    assert process.returncode == 2
    assert json.loads(process.stderr)["status"] == "unavailable"
    assert "torch" not in process.stderr
    assert not case["output"].exists()
