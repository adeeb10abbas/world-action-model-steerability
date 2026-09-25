"""Real CPU subprocesses/filesystem/mailboxes; never invoke the native CLI."""
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

import numpy as np
import pytest

from experiments.workshops.spatial_grounding_v1 import remote_simulator_lane as lane
from experiments.workshops.spatial_grounding_v1.adapters import AdapterError
from experiments.workshops.spatial_grounding_v1.robolab_jointpos_environment import JointPositionBinding
from experiments.workshops.spatial_grounding_v1.simulator_mailbox import _read, _write


FAKE_CHILD = r'''
import argparse, json, os, signal, subprocess, sys, time
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from experiments.workshops.spatial_grounding_v1.simulator_mailbox import MailboxReceiver, _write
p=argparse.ArgumentParser()
p.add_argument("scenario")
for name in ("mailbox-root","identity","identity-sha256","deadline-seconds","release-cell-json","release-cell-sha256"):
    p.add_argument("--"+name, required=True)
p.add_argument("--renderer-gpu-index",type=int)
a=p.parse_args()
root=Path(a.mailbox_root)
identity=json.loads(Path(a.identity).read_text())
root.mkdir()
for name in ("requests","responses","faults"): (root/name).mkdir()
_write(root/"fake-process.json", {"pid":os.getpid(),"pgid":os.getpgrp(),"identity":identity})
if a.scenario == "early_exit": os._exit(0)
if a.scenario in ("hang","grandchild"):
    if a.scenario == "grandchild":
        child=subprocess.Popen([sys.executable,"-c","import time; time.sleep(60)"])
        _write(root/"fake-grandchild.json", {"pid":child.pid})
    while True: time.sleep(.02)
if a.scenario == "delayed_ready": time.sleep(.4)
class Environment:
    def __init__(self): self.index=0
    def snapshot(self): return {"sim_time":self.index/15,"action_step":self.index}
    def reset(self):
        self.index=0
        return SimpleNamespace(snapshot=self.snapshot(),receipt={
            "reset_id":"fake-reset","camera_id":"camera","camera_name":"camera",
            "fingerprint":"f"*64,"temporal_cache_reset":True})
    def step(self,action):
        assert np.asarray(action).shape==(8,)
        self.index+=1
        return {"safety_terminated":False}
    def render_viewport(self): return np.full((4,6,3),self.index+1,np.uint8)
    def policy_observation(self): return {"image":np.full((4,6,3),self.index+1,np.uint8)}
    def close(self): pass
r=MailboxReceiver(root=root,identity=identity,environment=Environment())
while not r.closed:
    for request in sorted((root/"requests").glob("*.json")):
        if int(request.name[:4])>r.last: r.serve_one(request)
    time.sleep(.01)
if a.scenario=="hidden_failure":
    _write(root/"receiver_failure.json",{"error":"synthetic hidden failure","identity":identity})
if a.scenario=="slow_exit": time.sleep(.4)
os._exit(0)
'''


@pytest.fixture
def setup(tmp_path, monkeypatch):
    source, cohort = tmp_path / "source", tmp_path / "cohort"
    source.mkdir()
    cohort.mkdir()
    candidate_path = tmp_path / "candidate.json"
    candidate = {
        "candidate_id": "LAT-SYNTHETIC", "family": "LAT", "seed": 1,
        "task_asset": "rubiks_cube_banana_bowl.usda", "asset_manifest_sha256": "a" * 64,
        "object_poses": {
            "rubiks_cube": {"position_m": [.3, 0, .08], "quaternion_wxyz": [1, 0, 0, 0]},
            "bowl": {"position_m": [.5, 0, .1], "quaternion_wxyz": [1, 0, 0, 0]},
        }, "metadata": {"scoring_center_offsets_root_local_m": {
            "rubiks_cube": [0, 0, .02], "bowl": [0, 0, 0],
        }},
    }
    _write(candidate_path, candidate)
    rows = [{"cell_id": f"N3-cell-{i}", "model": "N3", "status": "RELEASED", "release_id": "released-test",
             "family": "LAT", "layout_id": "LAT-P01", "fixture_sha256": "b" * 64,
             "prompt": f"static {i}", "prompt_sha256": hashlib.sha256(f"static {i}".encode()).hexdigest(),
             "environment_seed": "1"} for i in range(2)]
    records = {row["cell_id"]: {**row, "scene_seed": 1, "candidate_path": str(candidate_path),
                                "candidate_file_sha256": lane._digest(candidate_path)} for row in rows}
    binding_path = tmp_path / "binding.json"
    _write(binding_path, {"source_root": str(source), "source_commit": "c" * 40, "cells": records})
    binding = JointPositionBinding(source, source, tmp_path / "assets.json", "a" * 64, records)
    monkeypatch.setattr(JointPositionBinding, "load", classmethod(lambda cls: binding))
    monkeypatch.setattr(lane, "_code_root", lambda: source)
    monkeypatch.setattr(lane, "_git_revision", lambda _: "c" * 40)
    refreshes = []
    monkeypatch.setattr(lane, "DirectoryRefresher", lambda: lambda path: refreshes.append(path))
    identity = {
        "schema_version": lane.SCHEMA, "model": "N3", "source_root": str(source), "source_commit": "c" * 40,
        "cohort_root": str(cohort), "control_root": str(cohort / "lanes/N3"),
        "environment_binding": {"path": str(binding_path), "sha256": lane._digest(binding_path)},
        **{key: f"00000000-0000-4000-8000-{i:012d}" for i, key in enumerate(
            ("policy_job_uid", "policy_pod_uid", "simulator_job_uid", "simulator_pod_uid"), 1)},
    }
    path = tmp_path / "lane-identity.json"
    _write(path, identity)
    monkeypatch.setenv("SGW01_SIMULATOR_LANE_IDENTITY", str(path))
    monkeypatch.setenv("SGW01_SIMULATOR_LANE_IDENTITY_SHA256", lane._digest(path))
    monkeypatch.setenv("SGW01_ENV_BINDING", str(binding_path))
    monkeypatch.setenv("SGW01_ENV_BINDING_SHA256", lane._digest(binding_path))
    monkeypatch.setenv("JOB_UID", identity["policy_job_uid"])
    monkeypatch.setenv("POD_UID", identity["policy_pod_uid"])
    monkeypatch.setenv("MODEL", "N3")
    for name, value in (("startup", 4), ("rpc", .2), ("finish", 3), ("attempt", 5)):
        monkeypatch.setenv(f"SGW01_SIMULATOR_LANE_{name.upper()}_TIMEOUT_SECONDS", str(value))
    env = dict(os.environ)
    env.update(JOB_UID=identity["simulator_job_uid"], POD_UID=identity["simulator_pod_uid"],
               PYTHONPATH=str(Path(__file__).resolve().parents[1]), PYTHONDONTWRITEBYTECODE="1")
    script = tmp_path / "fake_child.py"
    script.write_text(FAKE_CHILD)
    return SimpleNamespace(source=source, cohort=cohort, rows=rows, identity=identity, path=path,
                           sha=lane._digest(path), env=env, script=script, refreshes=refreshes)


def attempt(setup, index=0, attempt_id=None):
    row = setup.rows[index]
    attempt_id = attempt_id or f"attempt-{index}"
    root = setup.cohort / "run/attempts" / row["cell_id"] / attempt_id
    root.mkdir(parents=True)
    _write(root / "intent.json", {"schema_version": "sgw-01-attempt-intent-v1", "cell": row,
                                 "cell_id": row["cell_id"], "attempt_id": attempt_id, "release_id": row["release_id"]})
    return root / "simulator"


def spawner(setup, scenario="fast", launches=None):
    launches = [] if launches is None else launches

    def spawn(command, **kwargs):
        assert command[:3] == [sys.executable, "-m", "experiments.workshops.spatial_grounding_v1.native_mailbox_receiver"]
        assert kwargs["start_new_session"] and kwargs["close_fds"]
        assert kwargs["env"]["POD_UID"] == setup.identity["simulator_pod_uid"]
        process = subprocess.Popen([sys.executable, str(setup.script), scenario, *command[3:]], **kwargs)
        launches.append((command, process))
        return process
    return spawn


def supervise_thread(setup, *, scenario="fast", seconds=8):
    errors, launches = [], []

    def run():
        try:
            lane.supervise(setup.path, setup.sha, seconds, metadata_refresh=lambda path: setup.refreshes.append(path),
                           popen=spawner(setup, scenario, launches), environ=setup.env, terminate_grace_seconds=.4)
        except BaseException as error:
            errors.append(error)
    thread = threading.Thread(target=run)
    thread.start()
    return thread, errors, launches


def stop(setup):
    path = Path(setup.identity["control_root"]) / "stop.json"
    _write(path, {"schema_version": lane.STOP_SCHEMA, "lane_identity_sha256": setup.sha, "model": setup.identity["model"]})


def wait_for(predicate, seconds=6):
    end = time.monotonic() + seconds
    while not predicate():
        assert time.monotonic() < end, "timed out waiting for fake CPU evidence"
        time.sleep(.02)


def test_two_real_mailbox_attempts_sequential_attributed_and_finish_before_publication(setup):
    thread, errors, launches = supervise_thread(setup, scenario="slow_exit")
    originals = json.loads(json.dumps(setup.rows))
    roots = []
    try:
        for i in range(2):
            root = attempt(setup, i)
            roots.append(root)
            client = lane.create_environment(cell=SimpleNamespace(row=setup.rows[i]), evidence_root=root)
            assert client.reset().snapshot["action_step"] == 0
            client.step(np.arange(8, dtype=np.float32))
            assert client.snapshot()["action_step"] == 1
            started = time.monotonic()
            finished = client.finish_episode()
            assert time.monotonic() - started >= .3
            assert finished["status"] == "completed"
            # The parent can publish only now; a native close receipt alone
            # existed for .4 s while the real fake child was still running.
            _write(root.parent / "published.json", {"finish": finished})
            count = len(list((root / "mailbox/requests").glob("*.json")))
            client.close()
            assert client.finish_episode() == finished
            assert len(list((root / "mailbox/requests").glob("*.json"))) == count == 3
            with pytest.raises(AdapterError, match="finished"):
                client.reset()
            with pytest.raises(AdapterError, match="finished"):
                client.step(np.zeros(8))
            assert not (root / "lane/client-failure.json").exists()
            native = _read(root / "lane/identity.json")
            assert native["attempt_id"] == root.parent.name and native["cell_id"] == setup.rows[i]["cell_id"]
            assert native["simulator_pod_uid"] == setup.identity["simulator_pod_uid"]
            assert _read(root / "lane/cell.json")["candidate_sha256"] == native["candidate_sha256"]
            assert all(path.is_relative_to(root) for path in (root / "mailbox").rglob("*"))
            with pytest.raises(AdapterError, match="reuse"):
                lane.create_environment(cell=setup.rows[i], evidence_root=root)
        assert setup.rows == originals and len(launches) == 2
        first_exit = _read(roots[0] / "lane/child-exit.json")
        second_start = _read(roots[1] / "lane/child-start.json")
        assert first_exit["finished_at_unix_s"] <= second_start["started_at_unix_s"]
        assert any(path.name == "requests" for path in setup.refreshes)
        assert any(path.name == "responses" for path in setup.refreshes)
        # Empty queue is not a stop instruction.
        time.sleep(.15)
        assert thread.is_alive()
    finally:
        stop(setup)
        thread.join(8)
    assert not thread.is_alive() and not errors
    # Restart verifies/skips terminal descriptors and never respawns physics.
    lane.supervise(setup.path, setup.sha, 2, metadata_refresh=lambda _: None, environ=setup.env,
                   popen=lambda *a, **k: pytest.fail("completed descriptor respawned"))


def test_first_actual_reset_uses_startup_budget_without_a_probe(setup):
    thread, errors, launches = supervise_thread(setup, scenario="delayed_ready")
    try:
        root = attempt(setup)
        client = lane.create_environment(cell=setup.rows[0], evidence_root=root)
        client.reset()  # native construction takes longer than the .2 s RPC timeout
        assert client.command == 1
        client.finish_episode()
        assert client.command == 2
    finally:
        stop(setup)
        thread.join(8)
    assert not errors and len(launches) == 1


def test_process_group_probe_never_calls_permission_denied_absent(monkeypatch):
    def denied(pgid, signum):
        assert pgid == 123 and signum == 0
        raise PermissionError("synthetic kernel permission check")

    monkeypatch.setattr(lane.os, "killpg", denied)
    assert lane._group_exists(123) is True


@pytest.mark.parametrize("scenario", ["hidden_failure", "early_exit"])
def test_exit_zero_never_overrides_missing_or_contradictory_native_completion(setup, scenario):
    thread, errors, launches = supervise_thread(setup, scenario=scenario)
    root = attempt(setup)
    try:
        with pytest.raises(AdapterError):
            client = lane.create_environment(cell=setup.rows[0], evidence_root=root)
            client.reset()
            client.finish_episode()
    finally:
        thread.join(8)
    assert not thread.is_alive() and errors and len(launches) == 1
    assert _read(root / "lane/result.json")["status"] == "failed"
    assert _read(root / "lane/child-exit.json")["returncode"] == 0
    with pytest.raises(AdapterError):
        lane.supervise(setup.path, setup.sha, 2, metadata_refresh=lambda _: None, environ=setup.env,
                       popen=lambda *a, **k: pytest.fail("failed native descriptor retried"))


@pytest.mark.parametrize("scenario", ["hang", "grandchild"])
def test_deadline_drains_only_the_owned_python_group(setup, monkeypatch, scenario):
    monkeypatch.setenv("SGW01_SIMULATOR_LANE_ATTEMPT_TIMEOUT_SECONDS", ".8")
    unrelated = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(30)"], start_new_session=True)
    thread, errors, launches = supervise_thread(setup, scenario=scenario)
    root = attempt(setup)
    try:
        lane.create_environment(cell=setup.rows[0], evidence_root=root)
        thread.join(5)
        assert not thread.is_alive() and errors
        receipt = _read(root / "lane/child-exit.json")
        assert receipt["timed_out"] is True and receipt["group_drained"] is True
        assert launches[0][1].poll() is not None and unrelated.poll() is None
    finally:
        unrelated.terminate()
        unrelated.wait(timeout=3)
        thread.join(8)


def test_client_rpc_failure_is_permanent_and_stops_native_without_retry(setup, monkeypatch):
    monkeypatch.setenv("SGW01_SIMULATOR_LANE_STARTUP_TIMEOUT_SECONDS", ".7")
    thread, errors, launches = supervise_thread(setup, scenario="hang")
    root = attempt(setup)
    try:
        client = lane.create_environment(cell=setup.rows[0], evidence_root=root)
        with pytest.raises(AdapterError):
            client.reset()
        with pytest.raises(AdapterError):
            client.finish_episode()
        with pytest.raises(AdapterError):
            client.close()
        assert len(list((root / "mailbox/requests").glob("*.json"))) == 1
    finally:
        thread.join(8)
    assert not thread.is_alive() and errors and len(launches) == 1
    assert (root / "lane/client-failure.json").exists()
    assert _read(root / "lane/result.json")["status"] == "failed"


def test_failed_finish_receipt_write_cannot_later_report_success(setup, monkeypatch):
    thread, errors, launches = supervise_thread(setup)
    root = attempt(setup)
    try:
        client = lane.create_environment(cell=setup.rows[0], evidence_root=root)
        client.reset()
        original_write = lane._write

        def fail_finish(path, value):
            if path.name == "client-finished.json":
                raise OSError("synthetic receipt storage failure")
            return original_write(path, value)

        monkeypatch.setattr(lane, "_write", fail_finish)
        with pytest.raises(OSError, match="storage failure"):
            client.finish_episode()
        with pytest.raises(AdapterError, match="cannot retry"):
            client.finish_episode()
        assert client.command == 2 and (root / "lane/client-failure.json").exists()
    finally:
        stop(setup)
        thread.join(8)
    assert not thread.is_alive() and len(launches) == 1
    assert not (root / "lane/client-finished.json").exists()


def publish_without_supervisor(setup, monkeypatch):
    monkeypatch.setenv("SGW01_SIMULATOR_LANE_STARTUP_TIMEOUT_SECONDS", ".1")
    root = attempt(setup)
    with pytest.raises(AdapterError, match="startup timed out"):
        lane.create_environment(cell=setup.rows[0], evidence_root=root)
    return root, next((Path(setup.identity["control_root"]) / "requests").glob("*.json"))


@pytest.mark.parametrize("orphan_kind", ["mailbox", "claim"])
def test_restart_blocks_orphan_without_spawning_or_signalling_old_pid(setup, monkeypatch, orphan_kind):
    root, descriptor = publish_without_supervisor(setup, monkeypatch)
    if orphan_kind == "mailbox":
        (root / "mailbox").mkdir()
    else:
        _write(Path(setup.identity["control_root"]) / "claims" / descriptor.name, {"pid": 1, "old": True})
    with pytest.raises(AdapterError, match="orphan"):
        lane.supervise(setup.path, setup.sha, 2, metadata_refresh=lambda _: None, environ=setup.env,
                       popen=lambda *a, **k: pytest.fail("orphan replayed"))
    assert _read(root / "lane/result.json")["status"] == "orphan_blocked_preserve_no_replay"


def test_duplicate_cell_attempt_cannot_republish_from_another_evidence_directory(setup, monkeypatch):
    root, descriptor = publish_without_supervisor(setup, monkeypatch)
    original_hash = lane._digest(descriptor)
    second = setup.cohort / "other/attempts" / root.parent.parent.name / root.parent.name / "simulator"
    second.parent.mkdir(parents=True)
    _write(second.parent / "intent.json", _read(root.parent / "intent.json"))
    with pytest.raises(FileExistsError):
        lane.create_environment(cell=setup.rows[0], evidence_root=second)
    assert lane._digest(descriptor) == original_hash
    assert not (second / "mailbox").exists() and not (root / "mailbox").exists()


def test_lane_flock_prevents_two_supervisors_and_stop_is_hash_bound(setup):
    thread, errors, launches = supervise_thread(setup)
    control = Path(setup.identity["control_root"])
    wait_for(lambda: bool(list((control / "runs").glob("*/start.json"))))
    try:
        with pytest.raises(AdapterError, match="in-flight"):
            lane.supervise(setup.path, setup.sha, 2, metadata_refresh=lambda _: None, environ=setup.env)
        _write(control / "stop.json", {"schema_version": lane.STOP_SCHEMA, "lane_identity_sha256": "0" * 64, "model": "N3"})
    finally:
        thread.join(8)
    assert not thread.is_alive() and errors and not launches


@pytest.mark.parametrize("change", ["planned", "model", "prompt", "candidate", "unsafe", "intent", "outside"])
def test_factory_rejects_stale_unreleased_or_unbound_cells_before_descriptor(setup, change):
    root = attempt(setup)
    row = dict(setup.rows[0])
    if change == "planned": row["status"] = "PLANNED_NOT_RELEASED"
    elif change == "model": row["model"] = "E3"
    elif change == "prompt": row["prompt"] = "changed"
    elif change == "candidate": row["candidate_sha256"] = "f" * 64
    elif change == "unsafe": row["cell_id"] = "../outside"
    elif change == "intent":
        value = _read(root.parent / "intent.json")
        value["release_id"] = "different"
        (root.parent / "intent.json").write_text(json.dumps(value))
    elif change == "outside": root = setup.source / "simulator"
    with pytest.raises((AdapterError, KeyError)):
        lane.create_environment(cell=row, evidence_root=root)
    assert not list(Path(setup.identity["control_root"]).glob("requests/*.json"))


@pytest.mark.parametrize("change", ["hash", "job", "pod", "binding", "source", "model"])
def test_lane_authority_rejects_identity_and_environment_drift(setup, monkeypatch, change):
    sha = setup.sha
    if change == "hash": sha = "0" * 64
    elif change == "job": monkeypatch.setenv("JOB_UID", setup.identity["simulator_job_uid"])
    elif change == "pod": monkeypatch.setenv("POD_UID", setup.identity["simulator_pod_uid"])
    elif change == "binding": monkeypatch.setenv("SGW01_ENV_BINDING_SHA256", "0" * 64)
    elif change == "source": monkeypatch.setattr(lane, "_git_revision", lambda _: "f" * 40)
    elif change == "model": monkeypatch.setenv("MODEL", "F3")
    with pytest.raises(AdapterError):
        lane.load_lane(setup.path, sha, "policy")


@pytest.mark.parametrize("model", ["E3", "F3"])
def test_other_active_models_keep_separate_lane_and_released_cell_identity(setup, monkeypatch, model):
    from dataclasses import replace
    old = JointPositionBinding.load()
    rows, records = [], {}
    for original in setup.rows:
        row = {**original, "cell_id": original["cell_id"].replace("N3", model), "model": model}
        rows.append(row)
        records[row["cell_id"]] = {**old.cells[original["cell_id"]], **row}
    binding = replace(old, cells=records)
    monkeypatch.setattr(JointPositionBinding, "load", classmethod(lambda cls: binding))
    setup.rows = rows
    binding_path = Path(setup.identity["environment_binding"]["path"])
    binding_path.write_text(json.dumps({"source_root": str(setup.source), "source_commit": "c" * 40, "cells": records}))
    setup.identity.update(model=model, control_root=str(setup.cohort / "lanes" / model),
                          environment_binding={"path": str(binding_path), "sha256": lane._digest(binding_path)})
    setup.path.write_text(json.dumps(setup.identity))
    setup.sha = lane._digest(setup.path)
    for key, value in (("MODEL", model), ("SGW01_ENV_BINDING_SHA256", lane._digest(binding_path)),
                       ("SGW01_SIMULATOR_LANE_IDENTITY_SHA256", setup.sha)):
        monkeypatch.setenv(key, value)
        setup.env[key] = value
    thread, errors, launches = supervise_thread(setup)
    try:
        root = attempt(setup)
        client = lane.create_environment(cell=setup.rows[0], evidence_root=root)
        client.reset()
        assert client.finish_episode()["status"] == "completed"
        assert _read(root / "lane/cell.json")["model"] == model
    finally:
        stop(setup)
        thread.join(8)
    assert not errors and len(launches) == 1


def test_descriptor_hash_and_receiver_cell_are_checked_before_spawn(setup, monkeypatch):
    root, descriptor = publish_without_supervisor(setup, monkeypatch)
    value = _read(root / "lane/cell.json")
    value["status"] = "PLANNED_NOT_RELEASED"
    (root / "lane/cell.json").write_text(json.dumps(value))
    with pytest.raises(AdapterError, match="hash"):
        lane.supervise(setup.path, setup.sha, 2, metadata_refresh=lambda _: None, environ=setup.env,
                       popen=lambda *a, **k: pytest.fail("drifted cell started"))


def bare_policy_identity(setup, monkeypatch):
    setup.identity.update(schema_version=lane.POD_SCHEMA, policy_owner_kind="Pod", policy_pod_name="e")
    setup.identity.pop("policy_job_uid")
    setup.path.write_text(json.dumps(setup.identity))
    setup.sha = lane._digest(setup.path)
    monkeypatch.setenv("SGW01_SIMULATOR_LANE_IDENTITY_SHA256", setup.sha)
    monkeypatch.setenv("POD_NAME", "e")
    monkeypatch.delenv("JOB_UID", raising=False)
    monkeypatch.delenv("JOB_NAME", raising=False)


def test_bare_policy_pod_keeps_actual_job_simulator_and_native_identity_unchanged(setup, monkeypatch):
    bare_policy_identity(setup, monkeypatch)
    thread, errors, launches = supervise_thread(setup)
    try:
        root = attempt(setup)
        client = lane.create_environment(cell=setup.rows[0], evidence_root=root)
        client.reset()
        assert client.finish_episode()["status"] == "completed"
        native = _read(root / "lane/identity.json")
        assert native["simulator_job_uid"] == setup.identity["simulator_job_uid"]
        assert "policy_job_uid" not in native and "job_uid" not in setup.identity
        assert client.command == 2
    finally:
        stop(setup)
        thread.join(8)
    assert not errors and len(launches) == 1


@pytest.mark.parametrize("fault", ["job", "kind", "name", "missing-pod", "env-job"])
def test_bare_pod_lane_rejects_forged_or_missing_owner(setup, monkeypatch, fault):
    bare_policy_identity(setup, monkeypatch)
    if fault == "job": setup.identity["policy_job_uid"] = "00000000-0000-4000-8000-000000000009"
    elif fault == "kind": setup.identity["policy_owner_kind"] = "Job"
    elif fault == "name": setup.identity["policy_pod_name"] = "f"
    elif fault == "missing-pod": setup.identity.pop("policy_pod_uid")
    else: monkeypatch.setenv("JOB_UID", "invented-job")
    setup.path.write_text(json.dumps(setup.identity))
    with pytest.raises(AdapterError):
        lane.load_lane(setup.path, lane._digest(setup.path), "policy")


def bare_simulator_identity(setup, monkeypatch, seconds=20):
    from experiments.workshops.spatial_grounding_v1 import worker
    bare_policy_identity(setup, monkeypatch)
    setup.identity.update(schema_version=lane.POD_SIMULATOR_SCHEMA, simulator_owner_kind="Pod",
                          simulator_pod_name="a40e", simulator_gpu_uuid="GPU-00000000-0000-4000-8000-000000000100",
                          simulator_renderer_gpu_index=0, simulator_multi_gpu=False)
    setup.identity.pop("simulator_job_uid")
    entrypoint = setup.source / "supervisor.py"
    entrypoint.write_text("# Synthetic CPU supervisor metadata\n")
    setup.identity["simulator_supervisor_entrypoint"] = {"path": str(entrypoint), "sha256": lane._digest(entrypoint)}
    start = datetime.now(timezone.utc)
    supervisor = {
        "schema": "sgw-01-existing-pod-supervisor-v1", "role": "simulator",
        "command": [sys.executable, "-m", "experiments.workshops.spatial_grounding_v1.study_supervisor", "run"],
        "pod_name": "a40e", "pod_uid": setup.identity["simulator_pod_uid"],
        "gpu_uuid": setup.identity["simulator_gpu_uuid"], "source_root": str(setup.source), "source_commit": "c" * 40,
        "entrypoint": setup.identity["simulator_supervisor_entrypoint"], "started_at_utc": start.isoformat(),
        "deadline_seconds": seconds, "deadline_utc": (start + timedelta(seconds=seconds)).isoformat(),
    }
    start_path = setup.source / "supervisor-start.json"
    _write(start_path, supervisor)
    setup.identity["simulator_supervisor_identity_receipt"] = {"path": str(start_path), "sha256": lane._digest(start_path)}
    setup.path.write_text(json.dumps(setup.identity))
    setup.sha = lane._digest(setup.path)
    setup.env.pop("JOB_UID")
    setup.env.pop("JOB_NAME", None)
    setup.env.update(POD_NAME="a40e", CUDA_VISIBLE_DEVICES=setup.identity["simulator_gpu_uuid"])
    monkeypatch.setenv("SGW01_SIMULATOR_LANE_IDENTITY_SHA256", setup.sha)

    def verified(reference, *, source_commit, entrypoint, environ):
        record = _read(Path(reference["path"]))
        assert environ["POD_UID"] == record["pod_uid"] and environ["POD_NAME"] == record["pod_name"]
        if environ["CUDA_VISIBLE_DEVICES"] != record["gpu_uuid"]:
            raise lane.AdapterError("synthetic observed GPU differs")
        assert source_commit == record["source_commit"] and entrypoint == record["entrypoint"]
        return record

    monkeypatch.setattr(worker, "verify_existing_pod_supervisor", verified)
    return start_path, supervisor


@pytest.mark.parametrize("different_policy_python", [False, True])
def test_both_bare_pods_exchange_native_v2_identity_and_verified_outer_exit(setup, monkeypatch, different_policy_python):
    bare_simulator_identity(setup, monkeypatch)
    thread, errors, launches = supervise_thread(setup)
    try:
        root = attempt(setup)
        client = lane.create_environment(cell=setup.rows[0], evidence_root=root)
        client.reset()
        client.step(np.zeros(8, dtype=np.float32))
        with monkeypatch.context() as policy_context:
            if different_policy_python:
                policy_context.setattr(lane.sys, "executable", "/different-policy-environment/bin/python")
            assert client.finish_episode()["status"] == "completed"
        identity = _read(root / "lane/identity.json")
        assert identity["identity_schema"] == lane.POD_IDENTITY_SCHEMA
        assert identity["simulator_owner_kind"] == "Pod" and "simulator_job_uid" not in identity
        assert identity["simulator_pod_uid"] == setup.identity["simulator_pod_uid"]
        assert launches[0][0][-2:] == ["--renderer-gpu-index", "0"]
        assert client.command == 3
    finally:
        stop(setup)
        thread.join(8)
    assert not errors and len(launches) == 1


@pytest.mark.parametrize("fault", ["job", "missing-pod", "gpu", "supervisor-hash", "role", "expired"])
def test_bare_simulator_lane_rejects_unbound_ownership_and_supervisor(setup, monkeypatch, fault):
    start_path, supervisor = bare_simulator_identity(setup, monkeypatch)
    if fault == "job": setup.identity["simulator_job_uid"] = setup.identity["simulator_pod_uid"]
    elif fault == "missing-pod": setup.identity.pop("simulator_pod_uid")
    elif fault == "gpu": setup.env["CUDA_VISIBLE_DEVICES"] = "0"
    elif fault == "supervisor-hash": setup.identity["simulator_supervisor_identity_receipt"]["sha256"] = "0" * 64
    elif fault in {"role", "expired"}:
        if fault == "role": supervisor["role"] = "policy"
        else: supervisor["deadline_utc"] = "2000-01-01T00:00:00Z"
        start_path.write_text(json.dumps(supervisor))
        setup.identity["simulator_supervisor_identity_receipt"]["sha256"] = lane._digest(start_path)
    setup.path.write_text(json.dumps(setup.identity))
    with pytest.raises(lane.AdapterError):
        lane.load_lane(setup.path, lane._digest(setup.path), "simulator", setup.env)


def test_simulator_lane_cannot_outlive_bare_pod_supervisor(setup, monkeypatch):
    bare_simulator_identity(setup, monkeypatch, seconds=2)
    thread, errors, launches = supervise_thread(setup, scenario="hang", seconds=8)
    root = attempt(setup)
    lane.create_environment(cell=setup.rows[0], evidence_root=root)
    thread.join(6)
    assert not thread.is_alive() and errors and len(launches) == 1
    start = _read(root / "lane/child-start.json")
    exit_record = _read(root / "lane/child-exit.json")
    assert start["deadline_seconds"] <= 2 and exit_record["timed_out"] is True
    assert exit_record["group_drained"] is True


def test_distinct_control_directories_cannot_claim_the_same_simulator_gpu(setup, monkeypatch):
    bare_simulator_identity(setup, monkeypatch)
    thread, errors, launches = supervise_thread(setup)
    control = Path(setup.identity["control_root"])
    wait_for(lambda: bool(list((control / "runs").glob("*/start.json"))))
    try:
        other = {**setup.identity, "control_root": str(setup.cohort / "lanes/another")}
        path = setup.source / "other-lane.json"
        _write(path, other)
        with pytest.raises(AdapterError, match="in-flight"):
            lane.supervise(path, lane._digest(path), 3, metadata_refresh=lambda _: None, environ=setup.env,
                           popen=lambda *_a, **_k: pytest.fail("duplicate simulator GPU launched"))
    finally:
        stop(setup)
        thread.join(8)
    assert not errors and not launches


def test_disjoint_simulator_gpus_in_distinct_pods_can_hold_independent_renderers(setup, monkeypatch):
    _start_path, supervisor = bare_simulator_identity(setup, monkeypatch)
    first, errors, launches = supervise_thread(setup)
    other = {**setup.identity, "control_root": str(setup.cohort / "lanes/other-gpu"),
             "simulator_gpu_uuid": "GPU-00000000-0000-4000-8000-000000000101",
             "simulator_pod_uid": "00000000-0000-4000-8000-000000000104", "simulator_pod_name": "a40f"}
    receipt_path = setup.source / "other-supervisor.json"
    _write(receipt_path, {**supervisor, "gpu_uuid": other["simulator_gpu_uuid"],
                          "pod_uid": other["simulator_pod_uid"], "pod_name": other["simulator_pod_name"]})
    other["simulator_supervisor_identity_receipt"] = {"path": str(receipt_path), "sha256": lane._digest(receipt_path)}
    path = setup.source / "other-lane.json"
    _write(path, other)
    other_sha = lane._digest(path)
    other_env = {**setup.env, "CUDA_VISIBLE_DEVICES": other["simulator_gpu_uuid"],
                 "POD_UID": other["simulator_pod_uid"], "POD_NAME": other["simulator_pod_name"]}
    second_errors = []

    def run_second():
        try:
            lane.supervise(path, other_sha, 8, metadata_refresh=lambda _: None, environ=other_env,
                           popen=lambda *_a, **_k: pytest.fail("empty lane launched native work"))
        except BaseException as exc:
            second_errors.append(exc)

    second = threading.Thread(target=run_second)
    second.start()
    try:
        for control in (Path(setup.identity["control_root"]), Path(other["control_root"])):
            wait_for(lambda: bool(list((control / "runs").glob("*/start.json"))))
        assert first.is_alive() and second.is_alive()
    finally:
        stop(setup)
        _write(Path(other["control_root"]) / "stop.json",
               {"schema_version": lane.STOP_SCHEMA, "model": "N3", "lane_identity_sha256": other_sha})
        first.join(8)
        second.join(8)
    assert not errors and not second_errors and not launches


def test_distinct_cuda_uuids_cannot_share_unqualified_renderer_zero_in_one_pod(setup, monkeypatch):
    _start_path, supervisor = bare_simulator_identity(setup, monkeypatch)
    first, errors, launches = supervise_thread(setup)
    control = Path(setup.identity["control_root"])
    wait_for(lambda: bool(list((control / "runs").glob("*/start.json"))))
    other = {**setup.identity, "control_root": str(setup.cohort / "lanes/other-renderer"),
             "simulator_gpu_uuid": "GPU-00000000-0000-4000-8000-000000000101"}
    receipt_path = setup.source / "other-supervisor.json"
    _write(receipt_path, {**supervisor, "gpu_uuid": other["simulator_gpu_uuid"]})
    other["simulator_supervisor_identity_receipt"] = {"path": str(receipt_path), "sha256": lane._digest(receipt_path)}
    path = setup.source / "other-lane.json"
    _write(path, other)
    try:
        with pytest.raises(AdapterError, match="renderer-"):
            lane.supervise(path, lane._digest(path), 8, metadata_refresh=lambda _: None,
                           environ={**setup.env, "CUDA_VISIBLE_DEVICES": other["simulator_gpu_uuid"]},
                           popen=lambda *_a, **_k: pytest.fail("second unqualified renderer launched"))
    finally:
        stop(setup)
        first.join(8)
    assert not errors and not launches


def test_supervisor_sigterm_drains_its_exact_child_and_preserves_exit_receipts(setup):
    # A separate CPU-only supervisor process exercises the real CLI signal
    # handler; its Popen seam always substitutes the fake Python mailbox.
    driver = setup.script.with_name("fake_supervisor.py")
    driver.write_text(r'''
import json, os, subprocess, sys
from pathlib import Path
from types import SimpleNamespace
from experiments.workshops.spatial_grounding_v1 import remote_simulator_lane as m
identity=json.loads(Path(sys.argv[1]).read_text())
fake_script=sys.argv[3]
binding=json.loads(Path(identity["environment_binding"]["path"]).read_text())
m._code_root=lambda:Path(identity["source_root"])
m._git_revision=lambda _:identity["source_commit"]
def cell(row):
    m._require(row["status"]=="RELEASED","not released")
    return binding["cells"][row["cell_id"]],None
m.JointPositionBinding.load=classmethod(lambda cls:SimpleNamespace(source_root=Path(identity["source_root"]),cells=binding["cells"],cell=cell))
real=m.supervise
def spawn(command,**kwargs):
    assert command[2]=="experiments.workshops.spatial_grounding_v1.native_mailbox_receiver"
    return subprocess.Popen([sys.executable,fake_script,"hang",*command[3:]],**kwargs)
m.supervise=lambda path,sha,seconds:real(path,sha,seconds,metadata_refresh=lambda _:None,popen=spawn,terminate_grace_seconds=.4)
sys.argv=[sys.argv[0],"--lane-identity",sys.argv[1],"--lane-identity-sha256",sys.argv[2],"--deadline-seconds","10"]
m.main()
''')
    process = subprocess.Popen([sys.executable, str(driver), str(setup.path), setup.sha, str(setup.script)],
                               env=setup.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    root = attempt(setup)
    try:
        client = lane.create_environment(cell=setup.rows[0], evidence_root=root)
        started = _read(root / "lane/child-start.json")
        os.kill(process.pid, signal.SIGTERM)
        process.communicate(timeout=6)
        assert process.returncode != 0
        exited = _read(root / "lane/child-exit.json")
        assert exited["pid"] == started["pid"] and exited["interrupted"] is True and exited["group_drained"] is True
        assert _read(root / "lane/result.json")["status"] == "failed"
        assert client.command == 0
    finally:
        if process.poll() is None:
            process.terminate()
            process.communicate(timeout=6)
