"""CPU-only v2 admission tests; kernel/source observations are synthetic."""
from dataclasses import replace
from datetime import datetime, timezone
import errno
import hashlib
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from experiments.workshops.spatial_grounding_v1 import producer, worker
from experiments.workshops.spatial_grounding_v1.contract import ContractError, load_release
from tests.test_sgw_contract import make_release
from tests.test_sgw_run_admission import bind_admission, record
from tests.test_sgw_worker import FakeAdapter, _rehash_binding


@pytest.fixture
def pod_lane(tmp_path, monkeypatch):
    release = load_release(make_release(tmp_path))
    source = Path(worker.__file__).resolve().parents[3]
    entry = Path(worker.__file__).resolve()
    entry_ref = {"path": str(entry), "sha256": hashlib.sha256(entry.read_bytes()).hexdigest()}
    binding = dict(release.binding, allow_operational_receipt_refresh=True, allow_parallel_existing_pod_lanes=True,
                   existing_pod_supervisor_entrypoint=entry_ref, source_root=str(source),
                   persistent_study_root=str(tmp_path), pvc_mount_path=str(tmp_path.parent),
                   model_gpu_counts={"N3": 4}, model_gpu_names={"N3": "NVIDIA A100-SXM4-40GB"})
    authorization = json.loads(Path(binding["operational_authorization_receipt"]["path"]).read_text())
    authorization["scope"]["persistent_study_root"] = binding["persistent_study_root"]
    binding["operational_authorization_receipt"] = record(tmp_path / "authorization-pod.json", authorization)
    budget = json.loads(Path(binding["resource_budget_receipt"]["path"]).read_text())
    budget["study_root"] = binding["persistent_study_root"]
    budget["pvc_mount_path"] = binding["pvc_mount_path"]
    binding["resource_budget_receipt"] = record(tmp_path / "budget-pod.json", budget)
    (release.root / "runtime_binding.json").write_text(json.dumps(binding))
    _rehash_binding(release)
    release = load_release(release.root)
    pod_uid = "00000000-0000-4000-8000-000000000001"
    gpus = [f"GPU-00000000-0000-4000-8000-{i:012d}" for i in range(10, 14)]
    monkeypatch.setenv("POD_NAME", "e")
    monkeypatch.setenv("POD_UID", pod_uid)
    monkeypatch.delenv("JOB_UID", raising=False)
    monkeypatch.delenv("JOB_NAME", raising=False)
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", gpus[0])
    old = json.loads(Path(binding["external_allocation_receipt"]["path"]).read_text())
    supervisor = {
        "schema": "sgw-01-existing-pod-supervisor-v1", "supervisor_id": "00000000-0000-4000-8000-000000000002",
        "pod_name": "e", "pod_uid": pod_uid, "pid": os.getpid() + 100000,
        "gpu_uuid": gpus[0],
        "process_start_identity": "12345", "source_root": str(source), "source_commit": binding["source_commit"],
        "entrypoint": entry_ref, "command": [sys.executable, "-m", "experiments.workshops.spatial_grounding_v1.worker"],
        "started_at_utc": old["startTime"], "deadline_seconds": old["activeDeadlineSeconds"],
        "deadline_utc": old["deadline_utc"],
    }
    observed_process = {
        "ppid": 1, "process_start_identity": supervisor["process_start_identity"],
        "started_at_unix": datetime.fromisoformat(supervisor["started_at_utc"]).timestamp(),
        "command": list(supervisor["command"]), "cwd": str(source),
    }
    actual_parent_pid = supervisor["pid"]
    monkeypatch.setattr(os, "getppid", lambda: actual_parent_pid)
    monkeypatch.setattr(worker, "_supervisor_process", lambda _pid: dict(observed_process))
    monkeypatch.setattr(producer, "_git_revision", lambda _: binding["source_commit"])

    def git_source(command, **kwargs):
        assert command[:4] == ["git", "-C", str(source), "show"]
        assert kwargs["check"] and kwargs["timeout"] == 10
        return SimpleNamespace(stdout=entry.read_bytes())

    monkeypatch.setattr(worker.subprocess, "run", git_source)
    pod = {"apiVersion": "v1", "kind": "Pod", "metadata": {"name": "e", "uid": pod_uid, "namespace": binding["namespace"]},
           "spec": {"containers": [{"name": "policy", "resources": {
               "requests": {"nvidia.com/gpu": "4"}, "limits": {"nvidia.com/gpu": "4"}}}]},
           "status": {"phase": "Running"}}
    idle = json.loads(Path(old["gpu_idle_probe_receipt"]["path"]).read_text())
    idle["expected_visible_gpu_count"] = 4
    idle["gpus"] = [{**idle["gpus"][0], "index": i, "uuid": gpu, "name": binding["model_gpu_names"]["N3"]}
                    for i, gpu in enumerate(gpus)]
    idle["selected_gpu"] = dict(idle["gpus"][0])
    allocation = {key: value for key, value in old.items() if key not in {"job_name", "job_uid", "startTime", "activeDeadlineSeconds", "deadline_utc"}}
    allocation.update(schema=worker.POD_ALLOCATION_SCHEMA, owner_kind="Pod", pod_name="e", pod_uid=pod_uid,
                      study_root=binding["persistent_study_root"], pvc_mount_path=binding["pvc_mount_path"],
                      allocated_gpu_count=4, allocated_gpu_uuids=gpus,
                      gpu_name=binding["model_gpu_names"]["N3"],
                      lane_gpu_count=1, selected_gpu_uuid=gpus[0], reservation_scope="whole_pod",
                      reservation_gpu_hours=4 * supervisor["deadline_seconds"] / 3600,
                      lane_gpu_hours=supervisor["deadline_seconds"] / 3600)
    admission = {
        "schema": worker.POD_ADMISSION_SCHEMA, "status": "approved", "release_id": release.release_id,
        "release_hashes": dict(release.hashes), "model": "N3", "family": "LAT", "stage": "P",
        "owner_kind": "Pod", "pod_name": "e", "pod_uid": pod_uid, "selected_gpu_uuid": gpus[0],
        "gpu_name": allocation["gpu_name"], "allocated_gpu_count": allocation["allocated_gpu_count"],
        "resource_owner": binding["resource_owner"], "operational_authorization_receipt": binding["operational_authorization_receipt"],
        "receipts": {"resource_budget_receipt": binding["resource_budget_receipt"]},
    }

    publication = 0

    def publish():
        nonlocal publication
        root = tmp_path / f"operation-{publication:03d}"
        publication += 1
        root.mkdir()
        allocation["supervisor_identity_receipt"] = record(root / "supervisor.json", supervisor)
        allocation["pod_snapshot"] = record(root / "pod.json", pod)
        allocation["gpu_idle_probe_receipt"] = record(root / "idle-pod.json", idle)
        admission["supervisor_identity_receipt"] = allocation["supervisor_identity_receipt"]
        admission["receipts"]["external_allocation_receipt"] = record(root / "allocation-pod.json", allocation)
        bind_admission(admission, root, monkeypatch)

    publish()
    return SimpleNamespace(release=release, allocation=allocation, admission=admission, pod=pod, idle=idle,
                           supervisor=supervisor, process=observed_process, publish=publish, gpus=gpus)


def check(value, **kwargs):
    return worker._allocation_check(value.release, model="N3", minimum_runtime_seconds=1, **kwargs)


def test_persistent_root_separates_code_authorization_receipts_and_shared_gpu_lock(pod_lane):
    release = pod_lane.release
    root = release.root.parent
    assert release.binding["source_root"] == str(Path(worker.__file__).resolve().parents[3])
    assert release.binding["source_root"] != str(root)
    assert worker._study_root(release) == str(root)
    worker._authorization_check(release, model="N3")
    check(pod_lane)
    with worker.partition_lock(release, "N3", "LAT", "P"):
        locks = root / "locks" / "existing-pod-lanes"
        assert (locks / "partition-N3-LAT-P.lock").is_file()
        # An outer simulator owner using the documented common path must conflict.
        with (locks / f"gpu-{pod_lane.gpus[0]}.lock").open("a+") as stream:
            with pytest.raises(BlockingIOError):
                worker.fcntl.flock(stream.fileno(), worker.fcntl.LOCK_EX | worker.fcntl.LOCK_NB)


@pytest.mark.parametrize("fault", [
    "missing", "null", "relative", "wrong-parent", "at-mount", "outside-mount",
    "root-symlink", "mount-symlink", "noncanonical-root", "noncanonical-mount", "code-is-study",
])
def test_invalid_persistent_root_blocks_before_supervisor_or_model_construction(pod_lane, monkeypatch, fault):
    release = pod_lane.release
    root = release.root.parent
    binding = dict(release.binding)
    if fault == "missing":
        binding.pop("persistent_study_root")
    elif fault == "null":
        binding["persistent_study_root"] = None
    elif fault == "relative":
        binding["persistent_study_root"] = "study"
    elif fault == "wrong-parent":
        binding["persistent_study_root"] = str(root / "other-cohort")
    elif fault == "at-mount":
        binding["pvc_mount_path"] = str(root)
    elif fault == "outside-mount":
        binding["pvc_mount_path"] = str(root / "other-mount")
    elif fault in {"root-symlink", "mount-symlink"}:
        alias = root / "alias"
        alias.symlink_to(root if fault == "root-symlink" else root.parent, target_is_directory=True)
        binding["persistent_study_root" if fault == "root-symlink" else "pvc_mount_path"] = str(alias)
    elif fault == "noncanonical-root":
        binding["persistent_study_root"] += "/."
    elif fault == "noncanonical-mount":
        binding["pvc_mount_path"] += "/."
    else:
        binding["source_root"] = str(root)
    monkeypatch.setattr(worker, "_supervisor_check", lambda *_a, **_k: pytest.fail("invalid root reached supervisor"))
    monkeypatch.setattr(worker, "load_adapter", lambda *_a, **_k: pytest.fail("invalid root constructed a model"))
    with pytest.raises(worker.ResourceBlocked, match="persistent_study_root"):
        with worker.partition_lock(replace(release, binding=binding), "N3", "LAT", "P"):
            pytest.fail("invalid root acquired locks")
    assert not (root / "locks").exists()


@pytest.mark.parametrize("target", ["authorization", "allocation", "budget"])
def test_operational_identity_cannot_substitute_code_root_for_study_root(pod_lane, target):
    release = pod_lane.release
    if target == "authorization":
        reference = release.binding["operational_authorization_receipt"]
        value = json.loads(Path(reference["path"]).read_text())
        value["scope"]["persistent_study_root"] = release.binding["source_root"]
        binding = dict(release.binding, operational_authorization_receipt=record(
            release.root.parent / "wrong-root-authorization.json", value))
        with pytest.raises(worker.ResourceBlocked, match="operational authorization"):
            worker._authorization_check(replace(release, binding=binding), model="N3")
    else:
        value = (dict(pod_lane.allocation) if target == "allocation" else
                 json.loads(Path(release.binding["resource_budget_receipt"]["path"]).read_text()))
        value["study_root"] = release.binding["source_root"]
        with pytest.raises(worker.ResourceBlocked, match="study root"):
            worker._receipt_identity(release, value, target)


def test_lock_directory_symlink_cannot_redirect_writes_outside_persistent_root(pod_lane):
    root = pod_lane.release.root.parent
    destination = root / "not-the-lock-directory"
    destination.mkdir()
    (root / "locks").symlink_to(destination, target_is_directory=True)
    with pytest.raises(worker.ResourceBlocked, match="lock directory"):
        with worker.partition_lock(pod_lane.release, "N3", "LAT", "P"):
            pytest.fail("redirected lane lock admitted")
    assert list(destination.iterdir()) == []


@pytest.mark.parametrize("opt_in", [None, False])
def test_legacy_study_identity_ignores_persistent_root_without_explicit_opt_in(tmp_path, opt_in):
    release = load_release(make_release(tmp_path))
    binding = dict(release.binding, persistent_study_root="ignored-relative-path")
    if opt_in is False:
        binding["allow_parallel_existing_pod_lanes"] = False
    release = replace(release, binding=binding)
    assert worker._study_root(release) == binding["source_root"]
    worker._authorization_check(release, model="N3")
    worker._receipt_identity(release, json.loads(Path(binding["external_allocation_receipt"]["path"]).read_text()), "legacy")
    with worker.partition_lock(release, "N3", "LAT", "P"):
        assert (release.root.parent / "locks" / "N3.lock").is_file()
        assert not (release.root.parent / "locks" / "existing-pod-lanes").exists()


def test_linux_supervisor_identity_reads_start_ticks_argv_and_ancestry(tmp_path):
    proc = tmp_path / "proc"
    root = proc / "321"
    root.mkdir(parents=True)
    fields = ["S", "42", *(["0"] * 17), "12345"]
    (root / "stat").write_text("321 (python worker) " + " ".join(fields))
    (proc / "stat").write_text("btime 1000\n")
    (root / "cmdline").write_bytes(b"python\0-m\0checked.supervisor\0")
    (root / "cwd").symlink_to(tmp_path, target_is_directory=True)
    result = worker._supervisor_process(321, proc)
    assert result["ppid"] == 42 and result["process_start_identity"] == "12345"
    assert result["command"] == ["python", "-m", "checked.supervisor"]
    assert result["started_at_unix"] == 1000 + 12345 / os.sysconf("SC_CLK_TCK")


def test_four_allocated_one_lane_keeps_whole_pod_accounting(pod_lane):
    assert check(pod_lane) > 0
    assert pod_lane.allocation["allocated_gpu_count"] == 4 and pod_lane.allocation["lane_gpu_count"] == 1
    assert pod_lane.allocation["reservation_gpu_hours"] == 4 * pod_lane.allocation["lane_gpu_hours"]
    assert "JOB_UID" not in os.environ
    assert worker.runtime_identity_sha256(pod_lane.release.binding) == worker._runtime_identity_sha256(pod_lane.release)


def test_public_runtime_hash_retains_original_encoding_and_excluded_fields():
    binding = {
        "worker_image_digest": "image@sha256:" + "a" * 64, "source_commit": "b" * 40,
        "simulator_commit": "c" * 40, "model_code_commits": {"F3": "f" * 40, "N3": "d" * 40},
        "checkpoint_hashes": {"N3": "e" * 64}, "node_gpu_type": "NVIDIA A100",
        "resource_budget_receipt": {"path": "/unused/receipt"}, "allow_parallel_existing_pod_lanes": True,
    }
    original = {key: binding[key] for key in (
        "worker_image_digest", "source_commit", "simulator_commit", "model_code_commits",
        "checkpoint_hashes", "node_gpu_type",
    )}
    expected = hashlib.sha256(json.dumps(original, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert worker.runtime_identity_sha256(binding) == expected
    assert worker.runtime_identity_sha256(dict(reversed(list(binding.items())))) == expected


@pytest.mark.parametrize("fault", ["job_uid", "job_name", "pod_uid", "pod_name", "owner_kind", "uuid", "cuda"])
def test_forged_or_missing_owner_and_selected_uuid_are_rejected(pod_lane, monkeypatch, fault):
    if fault in {"job_uid", "job_name"}:
        pod_lane.admission[fault] = "fabricated-job"
    elif fault in {"pod_uid", "pod_name", "owner_kind"}:
        pod_lane.admission.pop(fault)
    elif fault == "uuid":
        pod_lane.allocation["selected_gpu_uuid"] = pod_lane.gpus[1]
    else:
        monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0")
    pod_lane.publish()
    with pytest.raises(worker.ResourceBlocked):
        check(pod_lane)


@pytest.mark.parametrize("fault", ["job-owner", "wrong-pod", "wrong-gpus", "fractional-gpus", "lane-count", "undercharge", "approval"])
def test_snapshot_and_accounting_cannot_be_substituted(pod_lane, fault):
    if fault == "job-owner":
        pod_lane.pod["metadata"]["ownerReferences"] = [{"kind": "Job", "uid": "invented"}]
    elif fault == "wrong-pod":
        pod_lane.pod["metadata"]["uid"] = "00000000-0000-4000-8000-000000000099"
    elif fault in {"wrong-gpus", "fractional-gpus"}:
        for key in ("requests", "limits"):
            pod_lane.pod["spec"]["containers"][0]["resources"][key]["nvidia.com/gpu"] = 1 if fault == "wrong-gpus" else 4.2
    elif fault == "lane-count":
        pod_lane.allocation["lane_gpu_count"] = 4
    elif fault == "undercharge":
        pod_lane.allocation["reservation_gpu_hours"] = pod_lane.allocation["lane_gpu_hours"]
    else:
        pod_lane.allocation.pop("owner_approval_reference")
    pod_lane.publish()
    with pytest.raises(worker.ResourceBlocked):
        check(pod_lane)


@pytest.mark.parametrize("selected_busy", [False, True])
def test_only_selected_gpu_must_be_idle_while_all_four_are_retained(pod_lane, selected_busy):
    index = 0 if selected_busy else 1
    gpu = pod_lane.idle["gpus"][index]
    gpu.update(memory_used_mib=30000, memory_free_mib=1000, utilization_percent=90)
    pod_lane.idle["compute_occupied_uuids"] = [gpu["uuid"]]
    pod_lane.idle["selected_gpu"] = dict(pod_lane.idle["gpus"][0])
    pod_lane.publish()
    if selected_busy:
        with pytest.raises(worker.ResourceBlocked, match="idle/declared"):
            check(pod_lane)
    else:
        assert check(pod_lane) > 0


@pytest.mark.parametrize("fault", ["start", "deadline", "pid", "command", "entrypoint", "source", "current-pid", "gpu"])
def test_finite_supervisor_must_match_actual_ancestor_and_checked_in_source(pod_lane, fault):
    if fault == "start": pod_lane.supervisor["process_start_identity"] = "different"
    elif fault == "deadline": pod_lane.supervisor["deadline_seconds"] = 1
    elif fault == "pid": pod_lane.supervisor["pid"] += 1
    elif fault == "command": pod_lane.supervisor["command"] = ["python", "-c", "pass"]
    elif fault == "entrypoint": pod_lane.supervisor["entrypoint"] = {"path": "unbound.py", "sha256": "a" * 64}
    elif fault == "source": pod_lane.supervisor["source_commit"] = "f" * 40
    elif fault == "gpu": pod_lane.supervisor["gpu_uuid"] = pod_lane.gpus[1]
    else: pod_lane.supervisor["pid"] = os.getpid()
    pod_lane.publish()
    with pytest.raises(worker.ResourceBlocked):
        check(pod_lane)


@pytest.mark.parametrize("file_entrypoint", [False, True])
def test_actual_unbuffered_checked_in_supervisor_command_is_supported(pod_lane, file_entrypoint):
    entry = Path(pod_lane.supervisor["entrypoint"]["path"])
    target = ([str(entry.relative_to(pod_lane.supervisor["source_root"]))] if file_entrypoint
              else ["-m", "experiments.workshops.spatial_grounding_v1.worker"])
    command = [sys.executable, "-u", "-B", *target]
    pod_lane.supervisor["command"] = command
    pod_lane.process["command"] = command
    pod_lane.publish()
    assert check(pod_lane) > 0


def test_parallel_mode_requires_explicit_binding_and_admission(pod_lane, monkeypatch):
    not_opted = replace(pod_lane.release, binding={**pod_lane.release.binding, "allow_parallel_existing_pod_lanes": False})
    with pytest.raises(worker.ResourceBlocked):
        worker._run_admission(not_opted)
    monkeypatch.delenv("SGW01_RUN_ADMISSION")
    monkeypatch.delenv("SGW01_RUN_ADMISSION_SHA256")
    with pytest.raises(worker.ResourceBlocked):
        with worker.partition_lock(pod_lane.release, "N3", "LAT", "P"):
            pytest.fail("unadmitted lane acquired locks")


def test_partition_duplicate_and_same_gpu_are_blocked_but_disjoint_model_lanes_are_allowed(pod_lane, monkeypatch):
    # Lock identity tests use already-checked admission objects; actual fcntl.
    current = dict(pod_lane.admission)
    monkeypatch.setattr(worker, "_run_admission", lambda *_a, **_k: dict(current))
    with worker.partition_lock(pod_lane.release, "N3", "LAT", "P"):
        with pytest.raises(worker.ResourceBlocked, match="gpu-"):
            with worker.partition_lock(pod_lane.release, "N3", "HEIGHT", "P"):
                pytest.fail("same physical GPU admitted twice")
        current["selected_gpu_uuid"] = pod_lane.gpus[1]
        with pytest.raises(worker.ResourceBlocked, match="partition-"):
            with worker.partition_lock(pod_lane.release, "N3", "LAT", "P"):
                pytest.fail("same partition admitted twice")
        with worker.partition_lock(pod_lane.release, "N3", "HEIGHT", "P"):
            pass
    # Failed second-lock acquisition must release its first GPU lock.
    with worker.partition_lock(pod_lane.release, "N3", "LAT", "P"):
        pass


def test_initial_idle_gate_precedes_factory_and_is_not_reprobed_per_cell(pod_lane, monkeypatch):
    calls = []
    original = worker._allocation_check
    monkeypatch.setattr(worker, "_allocation_check",
                        lambda *a, **k: (calls.append(k.get("verify_idle_probe", True)), original(*a, **k))[1])
    class ClosingAdapter(FakeAdapter):
        def close(self):
            with pytest.raises(worker.ResourceBlocked, match="lane lock held"):
                with worker.partition_lock(pod_lane.release, "N3", "LAT", "P"):
                    pytest.fail("GPU released before owned adapter cleanup")

    adapter = ClosingAdapter()

    def factory(_):
        assert calls == [True]
        return adapter

    monkeypatch.setattr(worker, "load_adapter", factory)
    assert worker.run_partition(pod_lane.release, model="N3", family="LAT", stage="P", max_valid=6,
                                max_attempts=3, worker_id="pod", scorer=lambda *_: {"status": "valid_model_failure"}) == 0
    assert adapter.resets == 6 and sum(calls) == 1
    monkeypatch.setattr(worker, "_run_admission", lambda *_a, **_k: pytest.fail("completed resume re-admitted"))
    assert worker.run_partition(pod_lane.release, model="N3", family="LAT", stage="P", max_valid=6,
                                max_attempts=3, worker_id="done") == 0


def test_busy_selected_device_blocks_before_any_model_construction(pod_lane, monkeypatch):
    pod_lane.idle["compute_occupied_uuids"] = [pod_lane.gpus[0]]
    pod_lane.publish()
    monkeypatch.setattr(worker, "load_adapter", lambda _: pytest.fail("occupied lane constructed a model"))
    assert worker.run_partition(pod_lane.release, model="N3", family="LAT", stage="P", max_valid=6,
                                max_attempts=3, worker_id="occupied") == worker.EXIT_STORAGE_BUDGET_BLOCKED
    assert not (pod_lane.release.root.parent / "attempts").exists()


@pytest.mark.parametrize("where", ["startup", "request", "os-error", "returned"])
def test_memory_exhaustion_aborts_without_automatic_replay_or_model_failure(tmp_path, monkeypatch, where):
    release = load_release(make_release(tmp_path))

    class OOM(FakeAdapter):
        def run_episode(self, *_args):
            if where == "returned":
                return {"status": "technical_invalid", "technical_cause": "CUDA OOM"}
            if where == "os-error":
                raise OSError(errno.ENOMEM, "cannot allocate memory")
            raise RuntimeError("CUDA out of memory")

    adapter = OOM()
    if where == "startup":
        monkeypatch.setattr(worker, "load_adapter", lambda _: (_ for _ in ()).throw(RuntimeError("CUDA out of memory")))
    with pytest.raises(ContractError, match="without replay"):
        worker.run_partition(release, model="N3", family="LAT", stage="P", max_valid=6, max_attempts=3,
                             worker_id="oom", adapter=None if where == "startup" else adapter)
    assert adapter.resets == (0 if where == "startup" else 1)
    assert not list((release.root.parent / "cells").glob("*.complete.json"))
    attempts = list((release.root.parent / "attempts").glob("*/*"))
    assert len(attempts) == (0 if where == "startup" else 1)
    if attempts:
        result = json.loads((attempts[0] / "result.json").read_text())
        assert result["status"] == "technical_invalid"
    else:
        status = json.loads((release.root.parent / "status/oom.json").read_text())
        assert status["state"] == "technical_invalid" and status["phase"] == "model_construction"
