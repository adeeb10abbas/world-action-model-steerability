import hashlib
import json
from pathlib import Path

import pytest

from experiments.workshops.spatial_grounding_v1 import worker
from experiments.workshops.spatial_grounding_v1.contract import load_release
from tests.test_sgw_contract import make_release
from tests.test_sgw_worker import FakeAdapter, _rehash_binding


def record(path, value):
    path.write_text(json.dumps(value))
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def opted_release(tmp_path):
    release = load_release(make_release(tmp_path))
    binding = dict(release.binding, allow_operational_receipt_refresh=True)
    (release.root / "runtime_binding.json").write_text(json.dumps(binding))
    _rehash_binding(release)
    return load_release(release.root)


def admission(release, tmp_path, monkeypatch):
    monkeypatch.setenv("JOB_UID", "replacement-job")
    monkeypatch.setenv("POD_UID", "replacement-pod")
    old = json.loads(Path(release.binding["external_allocation_receipt"]["path"]).read_text())
    allocation = record(tmp_path / "replacement-allocation.json", {
        **old, "job_uid": "replacement-job", "pod_uid": "replacement-pod",
    })
    value = {
        "schema": "sgw-01-run-admission-v1", "status": "approved",
        "release_id": release.release_id, "release_hashes": dict(release.hashes),
        "model": "N3", "job_uid": "replacement-job", "pod_uid": "replacement-pod",
        "resource_owner": release.binding["resource_owner"],
        "operational_authorization_receipt": release.binding["operational_authorization_receipt"],
        "receipts": {
            "external_allocation_receipt": allocation,
            "resource_budget_receipt": release.binding["resource_budget_receipt"],
        },
    }
    bind_admission(value, tmp_path, monkeypatch)
    return value


def bind_admission(value, tmp_path, monkeypatch):
    ref = record(tmp_path / "admission.json", value)
    monkeypatch.setenv("SGW01_RUN_ADMISSION", ref["path"])
    monkeypatch.setenv("SGW01_RUN_ADMISSION_SHA256", ref["sha256"])


def test_replacement_job_resumes_remaining_cells_without_rewriting_release(tmp_path, monkeypatch):
    release = opted_release(tmp_path)
    original = worker._allocation_check
    calls = 0

    def stop_before_second_cell(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 4:
            raise worker.ResourceBlocked("synthetic interruption after one completed cell")
        return original(*args, **kwargs)

    monkeypatch.setattr(worker, "_allocation_check", stop_before_second_cell)
    first = FakeAdapter()
    run = dict(model="N3", family="LAT", stage="P", max_valid=6, max_attempts=3,
               scorer=lambda *_: {"status": "valid_model_failure"})
    assert worker.run_partition(release, worker_id="first", adapter=first, **run) == 44
    assert first.resets == 1
    scientific_bytes = {p.name: p.read_bytes() for p in release.root.iterdir()}
    monkeypatch.setattr(worker, "_allocation_check", original)
    monkeypatch.setenv("JOB_UID", "replacement-job")
    monkeypatch.setenv("POD_UID", "replacement-pod")
    with pytest.raises(worker.ResourceBlocked, match="Job UID"):
        original(release, model="N3", minimum_runtime_seconds=1)
    value = admission(release, tmp_path, monkeypatch)
    second = FakeAdapter()
    assert worker.run_partition(release, worker_id="replacement", adapter=second, **run) == 0
    assert second.resets == 5
    assert {p.name: p.read_bytes() for p in release.root.iterdir()} == scientific_bytes
    copied = release.root.parent / "attempts/cell-1/attempt-001/run-admission.json"
    assert json.loads(copied.read_text()) == value
    assert len(list((release.root.parent / "attempts/cell-0").iterdir())) == 1


@pytest.mark.parametrize("field,value", [
    ("release_id", "another-release"), ("release_hashes", {}),
    ("model", "E3"), ("model", []), ("pod_uid", "another-pod"),
    ("job_uid", "another-job"), ("resource_owner", "another-owner"),
    ("operational_authorization_receipt", {}),
])
def test_admission_cannot_change_scientific_or_resource_authority(tmp_path, monkeypatch, field, value):
    release = opted_release(tmp_path)
    receipt = admission(release, tmp_path, monkeypatch)
    receipt[field] = value
    bind_admission(receipt, tmp_path, monkeypatch)
    with pytest.raises(worker.ResourceBlocked, match="immutable release"):
        worker._allocation_check(release, model="N3", minimum_runtime_seconds=1)


@pytest.mark.parametrize("change", ["no-opt-in", "missing-budget", "scientific-override", "bad-hash", "stale-allocation"])
def test_admission_fails_closed_and_retains_allocation_guards(tmp_path, monkeypatch, change):
    release = load_release(make_release(tmp_path)) if change == "no-opt-in" else opted_release(tmp_path)
    receipt = admission(release, tmp_path, monkeypatch)
    if change == "missing-budget":
        del receipt["receipts"]["resource_budget_receipt"]
    elif change == "scientific-override":
        receipt["receipts"]["stage_authorizations"] = {}
    elif change == "stale-allocation":
        receipt["receipts"]["external_allocation_receipt"] = release.binding["external_allocation_receipt"]
    bind_admission(receipt, tmp_path, monkeypatch)
    if change == "bad-hash":
        monkeypatch.setenv("SGW01_RUN_ADMISSION_SHA256", "0" * 64)
    with pytest.raises(worker.ResourceBlocked):
        worker._allocation_check(release, model="N3", minimum_runtime_seconds=1)
