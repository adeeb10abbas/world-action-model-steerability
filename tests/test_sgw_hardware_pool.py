"""Prospective hardware-policy refresh; all devices/adapters are CPU fakes."""
import json
from pathlib import Path

import pytest

from experiments.workshops.spatial_grounding_v1 import worker
from experiments.workshops.spatial_grounding_v1.contract import ContractError, load_release
from tests.test_sgw_contract import make_release
from tests.test_sgw_existing_pod_admission import pod_lane, check
from tests.test_sgw_run_admission import record
from tests.test_sgw_worker import FakeAdapter, _rehash_binding, _replace_receipt

GPU40 = "NVIDIA A100-SXM4-40GB"
GPU80 = "NVIDIA A100-SXM4-80GB"


@pytest.fixture
def pool(pod_lane):
    release = pod_lane.release
    binding = {
        **release.binding,
        "node_gpu_type": "prospectively permitted A100-SXM4-40GB/A100-SXM4-80GB pool",
        "existing_pod_gpu_counts": {"N3": [1, 2, 4]},
        "existing_pod_gpu_names": {"N3": [GPU40, GPU80]},
    }
    runtime_hash = worker.runtime_identity_sha256(binding)
    budget = json.loads(Path(binding["resource_budget_receipt"]["path"]).read_text())
    budget["runtime_identity_sha256"] = runtime_hash
    binding["resource_budget_receipt"] = record(release.root.parent / "pool-budget.json", budget)
    pod_lane.allocation["runtime_identity_sha256"] = runtime_hash
    binding["external_allocation_receipt"] = record(release.root.parent / "pool-base-allocation.json", pod_lane.allocation)
    (release.root / "runtime_binding.json").write_text(json.dumps(binding))
    _rehash_binding(release)
    pod_lane.release = load_release(release.root)
    pod_lane.admission["release_hashes"] = dict(pod_lane.release.hashes)
    pod_lane.admission["receipts"]["resource_budget_receipt"] = binding["resource_budget_receipt"]
    pod_lane.publish()
    return pod_lane


def hardware(data, count, name):
    data.allocation.update(allocated_gpu_count=count, gpu_name=name,
                           allocated_gpu_uuids=data.gpus[:count], selected_gpu_uuid=data.gpus[0],
                           reservation_gpu_hours=count * data.supervisor["deadline_seconds"] / 3600)
    data.admission.update(allocated_gpu_count=count, gpu_name=name, selected_gpu_uuid=data.gpus[0])
    resources = data.pod["spec"]["containers"][0]["resources"]
    for key in ("requests", "limits"):
        resources[key]["nvidia.com/gpu"] = str(count)
    example = dict(data.idle["gpus"][0])
    data.idle["gpus"] = [{**example, "index": i, "uuid": gpu, "name": name} for i, gpu in enumerate(data.gpus[:count])]
    data.idle["selected_gpu"] = dict(data.idle["gpus"][0])
    data.idle["expected_visible_gpu_count"] = count
    data.supervisor["gpu_uuid"] = data.gpus[0]


@pytest.mark.parametrize("count,name", [(1, GPU80), (2, GPU80), (4, GPU40)])
def test_declared_pool_accepts_only_observed_actual_pod_size_and_type(pool, count, name):
    hardware(pool, count, name)
    pool.publish()
    assert check(pool) > 0
    assert pool.release.binding["model_gpu_counts"]["N3"] == 4
    assert pool.allocation["reservation_gpu_hours"] == count * pool.allocation["lane_gpu_hours"]


@pytest.mark.parametrize("field,value", [
    ("existing_pod_gpu_counts", {"N3": [1, 2, 8]}),
    ("existing_pod_gpu_counts", {"N3": [True, 2, 4]}),
    ("existing_pod_gpu_counts", {"N3": [1, 1, 4]}),
    ("existing_pod_gpu_counts", {"N3": [1, 2]}),
    ("existing_pod_gpu_counts", None),
    ("existing_pod_gpu_names", {"N3": []}),
    ("existing_pod_gpu_names", {"N3": ["*"]}),
    ("existing_pod_gpu_names", None),
])
def test_malformed_or_noncovering_hardware_policy_fails_closed(pool, field, value):
    binding = {**pool.release.binding, field: value}
    with pytest.raises(worker.ResourceBlocked):
        worker._pod_hardware_policy(binding, "N3")


@pytest.mark.parametrize("fault", ["unlisted-name", "unlisted-count", "snapshot-count", "inventory-count",
                                  "inventory-name", "admission-name", "admission-count"])
def test_actual_hardware_cannot_be_relabelled_to_fit_pool(pool, fault):
    hardware(pool, 2, GPU80)
    if fault == "unlisted-name":
        pool.allocation["gpu_name"] = pool.admission["gpu_name"] = "NVIDIA B200"
    elif fault == "unlisted-count":
        pool.allocation["allocated_gpu_count"] = pool.admission["allocated_gpu_count"] = 3
    elif fault == "snapshot-count":
        pool.pod["spec"]["containers"][0]["resources"]["limits"]["nvidia.com/gpu"] = "4"
    elif fault == "inventory-count":
        pool.idle["expected_visible_gpu_count"] = 4
    elif fault == "inventory-name":
        pool.idle["gpus"][1]["name"] = GPU40
    elif fault == "admission-name":
        pool.admission["gpu_name"] = GPU40
    else:
        pool.admission["allocated_gpu_count"] = 1
    pool.publish()
    with pytest.raises(worker.ResourceBlocked):
        check(pool)


def test_without_prospective_pool_exact_bare_hardware_stays_exact(pod_lane):
    hardware(pod_lane, 1, GPU80)
    pod_lane.publish()
    with pytest.raises(worker.ResourceBlocked, match="immutable declared"):
        check(pod_lane)


@pytest.mark.parametrize("count", [1, 2])
def test_exact_bare_policy_can_prospectively_bind_one_or_two_gpus(pod_lane, count):
    release = pod_lane.release
    binding = {**release.binding, "model_gpu_counts": {"N3": count}, "model_gpu_names": {"N3": GPU80}}
    (release.root / "runtime_binding.json").write_text(json.dumps(binding))
    _rehash_binding(release)
    pod_lane.release = load_release(release.root)
    pod_lane.admission["release_hashes"] = dict(pod_lane.release.hashes)
    hardware(pod_lane, count, GPU80)
    pod_lane.publish()
    assert check(pod_lane) > 0


def test_legacy_job_count_remains_exact_even_with_pool_metadata(tmp_path, monkeypatch):
    monkeypatch.delenv("SGW01_RUN_ADMISSION", raising=False)
    monkeypatch.delenv("SGW01_RUN_ADMISSION_SHA256", raising=False)
    release = load_release(make_release(tmp_path))
    binding = {**release.binding, "existing_pod_gpu_counts": {"N3": [1, 2, 4]},
               "existing_pod_gpu_names": {"N3": [GPU40, GPU80]}}
    (release.root / "runtime_binding.json").write_text(json.dumps(binding))
    _rehash_binding(release)
    release = load_release(release.root)
    allocation = json.loads(Path(release.binding["external_allocation_receipt"]["path"]).read_text())
    allocation["allocated_gpu_count"] = 2
    release = _replace_receipt(release, "external_allocation_receipt", allocation)
    with pytest.raises(worker.ResourceBlocked, match="exact GPU allocation"):
        worker._allocation_check(release, model="N3", minimum_runtime_seconds=1)


def test_occupied_unselected_80gb_sibling_is_allowed_but_selected_is_not(pool):
    hardware(pool, 2, GPU80)
    sibling = pool.idle["gpus"][1]
    sibling.update(memory_used_mib=70000, memory_free_mib=1000, utilization_percent=100)
    pool.idle["compute_occupied_uuids"] = [sibling["uuid"]]
    pool.publish()
    assert check(pool) > 0
    pool.idle["compute_occupied_uuids"].append(pool.idle["gpus"][0]["uuid"])
    pool.publish()
    with pytest.raises(worker.ResourceBlocked, match="idle/declared"):
        check(pool)


@pytest.mark.parametrize("count", [1, 2])
def test_coordinator_80gb_refresh_preserves_release_and_first_40gb_oom_attempt(pool, monkeypatch, count):
    release = pool.release
    original_release = {path.name: path.read_bytes() for path in release.root.iterdir() if path.is_file()}

    class OOM(FakeAdapter):
        def run_episode(self, *_args):
            raise RuntimeError("CUDA out of memory")

    run = dict(model="N3", family="LAT", stage="P", max_valid=6, max_attempts=3)
    first = OOM()
    with pytest.raises(ContractError, match="without replay"):
        worker.run_partition(release, **run, worker_id="40gb-fit", adapter=first)
    assert first.resets == 1
    root = release.root.parent / "attempts/cell-0/attempt-001"
    original_attempt = {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}
    original_admission = json.loads((root / "run-admission.json").read_text())
    assert original_admission["gpu_name"] == GPU40 and original_admission["allocated_gpu_count"] == 4
    old_reference = original_admission["receipts"]["external_allocation_receipt"]
    old_allocation_bytes = Path(old_reference["path"]).read_bytes()

    # A distinct coordinator-issued operation/owner, never an automatic retry.
    pool.gpus = [f"GPU-00000000-0000-4000-8000-{i:012d}" for i in range(30, 34)]
    hardware(pool, count, GPU80)
    pod_uid = "00000000-0000-4000-8000-000000000080"
    pool.pod["metadata"].update(name="fallback80", uid=pod_uid)
    pool.allocation.update(pod_name="fallback80", pod_uid=pod_uid)
    pool.admission.update(pod_name="fallback80", pod_uid=pod_uid)
    pool.supervisor.update(pod_name="fallback80", pod_uid=pod_uid,
                           supervisor_id="00000000-0000-4000-8000-000000000081")
    monkeypatch.setenv("POD_NAME", "fallback80")
    monkeypatch.setenv("POD_UID", pod_uid)
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", pool.gpus[0])
    pool.publish()
    second = FakeAdapter()
    assert worker.run_partition(release, **run, worker_id="80gb-admission", adapter=second,
                                scorer=lambda *_: {"status": "valid_model_failure"}) == 0
    assert second.resets == 6
    assert original_release == {path.name: path.read_bytes() for path in release.root.iterdir() if path.is_file()}
    assert original_attempt == {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}
    assert Path(old_reference["path"]).read_bytes() == old_allocation_bytes
    old_allocation = worker._receipt(old_reference, "retained original allocation")
    assert old_allocation["gpu_name"] == GPU40 and old_allocation["allocated_gpu_count"] == 4
    current = json.loads((release.root.parent / "attempts/cell-0/attempt-002/run-admission.json").read_text())
    assert current["gpu_name"] == GPU80 and current["allocated_gpu_count"] == count
