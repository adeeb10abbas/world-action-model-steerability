"""Synthetic CPU-only r5 claims; no model, simulator or cluster processes."""

from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from experiments.workshops.spatial_grounding_v1 import block_scheduling as blocks
from experiments.workshops.spatial_grounding_v1 import study_lane as lane
from experiments.workshops.spatial_grounding_v1 import worker
from experiments.workshops.spatial_grounding_v1.contract import ContractError, load_release, sha256_file
from experiments.workshops.spatial_grounding_v1.recorder import AttemptRecorder, atomic_json, request_fleet_hold
from experiments.workshops.spatial_grounding_v1.release import _queue_rows, create_release
from tests.test_sgw_contract import make_release
from tests.test_sgw_worker import FakeAdapter


@pytest.fixture
def cohort(tmp_path, monkeypatch):
    from experiments.workshops.spatial_grounding_v1 import camera_configuration, mailbox_visibility, policy_observations
    monkeypatch.setattr(mailbox_visibility, "DirectoryRefresher", lambda: lambda _path: None)
    runtime = {
        "camera_configuration": {"revision": "synthetic-front-side", "sha256": "d" * 64},
        "policy_input_revision": "synthetic-packing",
    }
    monkeypatch.setattr(camera_configuration, "camera_configuration_identity",
                        lambda: dict(runtime["camera_configuration"]))
    monkeypatch.setattr(policy_observations, "policy_input_identity",
                        lambda: {"revision": runtime["policy_input_revision"]})
    old = load_release(make_release(tmp_path))
    root = tmp_path / "study-a40-v3"
    root.mkdir()
    protocol = tmp_path / "new-protocol.json"
    atomic_json(protocol, {**json.loads((blocks.SPEC / "protocol.json").read_text()),
                           "protocol_runtime": runtime,
                           "synthetic_revision": "r5 CPU test only; not launch authority"})
    reg_path = tmp_path / "registration.json"
    reg = {
        "schema": "sgw-01-block-scheduling-registration-v1", "status": "registered",
        "scheduling_mode": blocks.MODE, "release_revision": "r5", "allowed_models": ["N3"],
        "source_queue_sha256": blocks.QUEUE_SHA256, "stage_barrier": "per_model",
        "technical_invalid_threshold": 1, "action_cap": 450, "cohort_root": str(root),
        "protocol_sha256": sha256_file(protocol), "prompts_sha256": sha256_file(blocks.SPEC / "prompts.json"),
    }
    atomic_json(reg_path, reg)
    binding = {
        **old.binding, "scheduling_mode": blocks.MODE, "block_registration": lane.reference(reg_path),
        "protocol_runtime": runtime,
        "allowed_models": ["N3"], "hold_on_technical_invalid": True,
        "allow_parallel_existing_pod_lanes": True, "allow_operational_receipt_refresh": True,
        "persistent_study_root": str(root), "pvc_mount_path": str(tmp_path),
        "source_root": str(Path(worker.__file__).resolve().parents[3]),
        "model_gpu_names": {"N3": "NVIDIA A40"}, "model_code_commits": {"N3": "a" * 40},
        "checkpoint_hashes": {"N3": "b" * 64}, "cpu_memory_limits": {"cpu": 1},
        "policy_ports": {"N3": 8123}, "frame_time_mapping_hashes": {"N3": "c" * 64},
    }
    binding_path = tmp_path / "new-binding.json"
    atomic_json(binding_path, binding)
    fixtures = tmp_path / "new-fixtures.json"
    atomic_json(fixtures, {
        "status": "qualified",
        "layouts": {row["layout_id"]: {"fixture_sha256": "f" * 64}
                    for row in _queue_rows(blocks.SPEC / "planned_cells.csv")},
        "time_maps": {"N3": "c" * 64},
    })
    inputs = {key: lane.reference(path) for key, path in (
        ("protocol", protocol), ("prompts", blocks.SPEC / "prompts.json"),
        ("queue", blocks.SPEC / "planned_cells.csv"), ("fixtures", fixtures),
        ("binding", binding_path), ("allocation", Path(binding["external_allocation_receipt"]["path"])),
    )}
    plan = {
        "model": "N3", "cohort_root": str(root), "scheduling_mode": blocks.MODE,
        "allowed_models": ["N3"], "release_revision": "r5", "inputs": inputs,
        "lane_id": "n3-a", "partitions": [f"{f}-{s}" for s in lane.STAGES for f in lane.FAMILIES],
        "source_commit": binding["source_commit"], "source_root": binding["source_root"],
        "runtime_environment": {
            "SGW01_CAMERA_REVISION": runtime["camera_configuration"]["revision"],
            "SGW01_POLICY_INPUT_REVISION": runtime["policy_input_revision"],
        }, "policy_port": 8123, "model_interpreter": "/synthetic/python",
        "gpu_uuid": "GPU-00000000-0000-4000-8000-000000000001", "hold_on_technical_invalid": True,
        "gpu_name": "NVIDIA A40", "pod_gpu_count": 1,
    }

    def release(family="LAT", stage="P", **kwargs):
        output = lane.release_path(root, "N3", family, stage, "r5")
        return load_release(create_release(
            output=output, release_id=lane.partition_release_id(plan, family, stage),
            protocol=protocol, prompts=blocks.SPEC / "prompts.json",
            planned_queue=blocks.SPEC / "planned_cells.csv", fixtures=fixtures,
            runtime_binding=binding_path, resource_owner="ali", stage=stage, model="N3",
            family=family, **kwargs,
        ))

    monkeypatch.setattr(worker, "_supervisor_check", lambda *_: {})
    monkeypatch.setattr(worker, "_space_check", lambda *_a, **_k: None)
    monkeypatch.setattr(worker, "_budget_check", lambda *_a, **_k: None)
    monkeypatch.setattr(worker, "_allocation_check", lambda *_a, **_k: 10000)
    monkeypatch.setattr(worker, "STOP_REQUESTED", False)
    monkeypatch.setattr(lane, "stop_remote_lane", lambda *_: None)
    return SimpleNamespace(root=root, old=old, release=release, plan=plan, binding=binding,
                           reg=reg, reg_path=reg_path, binding_path=binding_path, protocol=protocol)


def admit(cohort, release, block_id, monkeypatch, number=1, simulator_number=None):
    sim = simulator_number if simulator_number is not None else number + 100
    gpu = f"GPU-00000000-0000-4000-8000-{number:012d}"
    uid = f"00000000-0000-4000-9000-{number:012d}"
    root = cohort.root / "operations" / f"cpu-{number}"
    root.mkdir(parents=True, exist_ok=True)
    identity_path = root / "simulator.json"
    identity = {
        "schema_version": "sgw-01-simulator-lane-v3", "policy_owner_kind": "Pod", "simulator_owner_kind": "Pod",
        "model": "N3", "source_root": release.binding["source_root"],
        "source_commit": release.binding["source_commit"], "cohort_root": str(cohort.root),
        "control_root": str(cohort.root / "simulators" / f"cpu-{sim}"),
        "policy_pod_uid": uid, "policy_pod_name": f"policy-{number}",
        "simulator_pod_uid": f"00000000-0000-4000-9000-{sim:012d}",
        "simulator_gpu_uuid": f"GPU-00000000-0000-4000-8000-{sim:012d}",
    }
    atomic_json(identity_path, identity)
    ref = lane.reference(identity_path)
    runtime_environment = {
        **cohort.plan["runtime_environment"],
        "SGW01_SIMULATOR_LANE_IDENTITY": ref["path"], "SGW01_SIMULATOR_LANE_IDENTITY_SHA256": ref["sha256"],
    }
    plan = {**cohort.plan, "runtime_environment": runtime_environment, "gpu_uuid": gpu}
    for name, value in lane.worker_environment(plan, root).items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("POD_NAME", identity["policy_pod_name"])
    monkeypatch.setenv("POD_UID", uid)
    monkeypatch.delenv("JOB_UID", raising=False)
    monkeypatch.delenv("JOB_NAME", raising=False)
    atomic_json(root / "synthetic-receipt.json", {"test": "no observed resource evidence"})
    receipt = lane.reference(root / "synthetic-receipt.json")
    admission = {
        "schema": worker.POD_ADMISSION_SCHEMA, "status": "approved", "release_id": release.release_id,
        "release_hashes": dict(release.hashes), "model": "N3",
        "family": release.cells[0].family, "stage": release.cells[0].stage, "block_id": block_id,
        "owner_kind": "Pod", "pod_name": identity["policy_pod_name"], "pod_uid": uid,
        "selected_gpu_uuid": gpu, "gpu_name": "NVIDIA A40", "allocated_gpu_count": 1,
        "resource_owner": "ali", "operational_authorization_receipt": release.binding["operational_authorization_receipt"],
        "supervisor_identity_receipt": receipt, "operation_root": str(root), "simulator_lane_identity": ref,
        "receipts": {key: receipt for key in ("external_allocation_receipt", "resource_budget_receipt", "storage_budget_receipt")},
    }
    atomic_json(root / "admission.json", admission)
    monkeypatch.setenv("SGW01_RUN_ADMISSION", str(root / "admission.json"))
    monkeypatch.setenv("SGW01_RUN_ADMISSION_SHA256", sha256_file(root / "admission.json"))
    return admission, plan, root


def execute(release, block, adapter=None):
    first = release.cells[0]
    return worker.run_partition(
        release, model=first.model, family=first.family, stage=first.stage, block_id=block,
        max_valid=6, max_attempts=3, worker_id=f"cpu-{block}", adapter=adapter or FakeAdapter(),
        scorer=lambda *_: {"status": "valid_model_failure"},
    )


def finish(release, block, operation):
    for cell in blocks.selected_cells(release, "N3", release.cells[0].family, release.cells[0].stage, block):
        recorder = AttemptRecorder(release, cell, "attempt-001")
        recorder.begin()
        for kind in ("actions", "states", "observations", "videos"):
            path = recorder.path / kind / "synthetic.txt"
            path.parent.mkdir()
            path.write_text("CPU fixture, not real episode evidence")
        recorder.complete({"status": "valid_model_failure", "executed_action_count": 450, "safety_terminated": False})
    summary = lane.verified_partition_summary(release.root, block)
    summary.update(block_id=block, operation=str(operation))
    atomic_json(release.root.parent / "block-completions" / f"{block}.json", summary)


def test_opt_in_requires_new_protocol_cohort_and_explicit_n3_gate(cohort):
    assert blocks.registration(cohort.old.binding) is None
    assert lane._block_registration(cohort.plan) == cohort.reg
    for changed in ({"allowed_models": ["N3", "E3"]}, {"allowed_models": []},
                    {"model": "E3"}, {"model": "F3"}, {"scheduling_mode": None},
                    {"release_revision": "r4"}):
        with pytest.raises(ContractError):
            lane._block_registration({**cohort.plan, **changed})
    for changed in ({"allowed_models": ["N3", "E3"]}, {"hold_on_technical_invalid": False},
                    {"persistent_study_root": str(cohort.root.parent / "study-a40-v2")},
                    {"allow_parallel_existing_pod_lanes": False}, {"block_registration": None}):
        with pytest.raises(ContractError):
            blocks.registration({**cohort.binding, **changed})
    with pytest.raises(ContractError, match="new protocol"):
        blocks.registration(cohort.binding, protocol_sha256=sha256_file(blocks.SPEC / "protocol.json"))
    cohort.reg_path.write_text("{}")
    with pytest.raises(ContractError, match="changed"):
        blocks.registration(cohort.binding)


def test_frozen_six_condition_selection_and_legacy_defaults(cohort):
    release = cohort.release(stage="D")
    groups = blocks.frozen_blocks(release.partition("N3", "LAT", "D"))
    assert len(groups) == 4 and len(release.cells) == 24
    block = next(iter(groups))
    selected = blocks.selected_cells(release, "N3", "LAT", "D", block)
    assert len(selected) == 6 and list(selected) == list(groups[block])
    assert len(blocks.selected_cells(cohort.old, "N3", "LAT", "P", None)) == 6
    for bad_id in (None, selected[0].cell_id, "LAT-P01-N3", "../LAT-D01-N3"):
        with pytest.raises(ContractError):
            blocks.selected_cells(release, "N3", "LAT", "D", bad_id)
    with pytest.raises(ContractError, match="registration"):
        blocks.selected_cells(cohort.old, "N3", "LAT", "P", "block-1")
    for field, value in (("form", "DUPLICATE"), ("physical_goal_sign", "0"), ("action_cap", "449"),
                         ("within_block_order", "1"), ("layout_id", "LAT-D99")):
        cell = selected[-1]
        bad = replace(cell, row={**cell.row, field: value})
        with pytest.raises(ContractError, match="frozen"):
            blocks.frozen_blocks((*selected[:-1], bad))
    with pytest.raises(ContractError, match="six"):
        blocks.frozen_blocks(selected[:-1])


@pytest.mark.parametrize("model", ["E3", "F3"])
def test_release_generation_rejects_unapproved_models_before_writing(cohort, model):
    inputs = cohort.plan["inputs"]
    path = cohort.root / f"rejected-{model}"
    with pytest.raises(ContractError, match="N3-only"):
        create_release(
            output=path, release_id=f"forbidden-{model}", protocol=Path(inputs["protocol"]["path"]),
            prompts=Path(inputs["prompts"]["path"]), planned_queue=Path(inputs["queue"]["path"]),
            fixtures=Path(inputs["fixtures"]["path"]), runtime_binding=cohort.binding_path,
            resource_owner="ali", stage="P", model=model, family="LAT",
        )
    assert not path.exists()


def test_worker_locks_allow_same_partition_different_blocks_but_exclude_duplicates(cohort, monkeypatch):
    release = cohort.release(stage="D")
    a, b, *_ = blocks.frozen_blocks(release.cells)
    admit(cohort, release, a, monkeypatch)
    with worker.partition_lock(release, "N3", "LAT", "D", a):
        with monkeypatch.context() as other:
            admit(cohort, release, b, other, number=2)
            with worker.partition_lock(release, "N3", "LAT", "D", b):
                pass
            admit(cohort, release, a, other, number=2)
            with pytest.raises(worker.ResourceBlocked, match="block-"):
                with worker.partition_lock(release, "N3", "LAT", "D", a):
                    pytest.fail("duplicate block acquired")
        with monkeypatch.context() as other:
            admit(cohort, release, b, other, number=2, simulator_number=101)
            with pytest.raises(worker.ResourceBlocked, match="simulator-pair"):
                with worker.partition_lock(release, "N3", "LAT", "D", b):
                    pytest.fail("shared simulator admitted")
        admit(cohort, release, b, monkeypatch)
        with pytest.raises(worker.ResourceBlocked, match="gpu-"):
            with worker.partition_lock(release, "N3", "LAT", "D", b):
                pytest.fail("shared policy GPU admitted")
    locks = cohort.root / "locks" / "existing-pod-lanes"
    assert not list(locks.glob("partition-*")) and not (cohort.root / "locks" / "N3.lock").exists()


def test_block_admission_cannot_substitute_block_or_mutable_paths(cohort, monkeypatch):
    release = cohort.release(stage="D")
    a, b, *_ = blocks.frozen_blocks(release.cells)
    admission, _, root = admit(cohort, release, a, monkeypatch)
    with pytest.raises(worker.ResourceBlocked, match="block_id"):
        worker._run_admission(release, model="N3", family="LAT", stage="D", block_id=b)
    monkeypatch.setenv("SGW01_RUNTIME_RECEIPT", str(root.parent / "shared.json"))
    with pytest.raises(worker.ResourceBlocked, match="private"):
        worker._run_admission(release)
    monkeypatch.setenv("SGW01_RUNTIME_RECEIPT", str(root / "runtime" / "launch.json"))
    worker._run_admission(release)
    monkeypatch.delenv("SGW01_RUN_ADMISSION")
    monkeypatch.delenv("SGW01_RUN_ADMISSION_SHA256")
    with pytest.raises(worker.ResourceBlocked, match="exact"):
        worker._run_admission(release)


def test_barrier_is_per_model_with_all_prior_stages_and_not_success(cohort, monkeypatch):
    done = set()
    monkeypatch.setattr(lane, "read_partition_summary",
                        lambda _r, m, f, s: {"status": "complete", "outcome": "valid_model_failure"}
                        if (m, f, s) in done else None)
    assert lane.stage_ready(cohort.root, "P", "N3")
    for family in lane.FAMILIES[:2]:
        done.add(("N3", family, "P"))
    assert not lane.stage_ready(cohort.root, "D", "N3")
    done.add(("N3", "DIST", "P"))
    assert lane.stage_ready(cohort.root, "D", "N3")
    assert not lane.stage_ready(cohort.root, "D")  # legacy all-model barrier
    assert not lane.stage_ready(cohort.root, "C", "N3")
    done.update(("N3", family, "D") for family in lane.FAMILIES)
    assert lane.stage_ready(cohort.root, "C", "N3")
    done.remove(("N3", "LAT", "P"))
    assert not lane.stage_ready(cohort.root, "C", "N3")


def test_direct_worker_cannot_bypass_stage_or_allowed_model_gate(cohort, monkeypatch):
    release = cohort.release(stage="D")
    block = next(iter(blocks.frozen_blocks(release.cells)))
    monkeypatch.setattr(worker, "load_adapter", lambda *_: pytest.fail("constructed model"))
    with pytest.raises(ContractError, match="stage barrier"):
        execute(release, block)
    with pytest.raises(ContractError, match="N3-only"):
        worker.run_partition(release, model="E3", family="LAT", stage="D", block_id=block,
                             max_valid=6, max_attempts=3, worker_id="bad-model")


def test_one_block_worker_completes_only_six_cells_and_retains_full_release(cohort, monkeypatch):
    release = cohort.release(stage="D")
    block = next(iter(blocks.frozen_blocks(release.cells)))
    monkeypatch.setattr(lane, "stage_ready", lambda *_: True)
    admit(cohort, release, block, monkeypatch)
    before = {p.name: p.read_bytes() for p in release.root.iterdir()}
    adapter = FakeAdapter()
    assert execute(release, block, adapter) == 0 and adapter.resets == 6
    assert len(list((cohort.root / "cells").glob("*.json"))) == 6
    assert {p.name: p.read_bytes() for p in release.root.iterdir()} == before
    assert len(release.partition("N3", "LAT", "D")) == 24
    assert execute(release, block, adapter) == 0 and adapter.resets == 6
    with pytest.raises(ContractError, match="limits"):
        worker.run_partition(release, model="N3", family="LAT", stage="D", block_id=block,
                             max_valid=24, max_attempts=3, worker_id="too-many")


def test_first_technical_invalid_holds_without_second_attempt(cohort, monkeypatch):
    release = cohort.release()
    block = release.cells[0].block_id
    admit(cohort, release, block, monkeypatch)

    class Broken(FakeAdapter):
        def run_episode(self, *_):
            return {"status": "technical_invalid", "technical_cause": "synthetic transport fault"}

    broken = Broken()
    assert execute(release, block, broken) == 44
    assert broken.resets == 1 and (cohort.root / "fleet-hold.json").is_file()
    manifests = list((cohort.root / "attempts").glob("*/*/manifest.json"))
    assert len(manifests) == 1
    preserved = manifests[0].read_bytes()
    assert execute(release, block, broken) == 44 and broken.resets == 1
    assert manifests[0].read_bytes() == preserved


@pytest.mark.parametrize("prior", ["dispatch", "execution", "partial"])
def test_crash_claims_and_partial_blocks_never_automatically_replay(cohort, monkeypatch, prior):
    release = cohort.release()
    block = release.cells[0].block_id
    admit(cohort, release, block, monkeypatch)
    adapter = FakeAdapter()
    if prior == "dispatch":
        marker = blocks.begin_once(cohort.root, "block-claims", block, lane_id="crashed")
        preserved = marker.read_bytes()
        with pytest.raises(ContractError, match="no automatic replay"):
            lane.run_one(cohort.plan, "LAT", "P", block)
        assert marker.read_bytes() == preserved
    else:
        if prior == "execution":
            blocks.begin_once(cohort.root, "block-executions", block, worker_id="crashed")
        else:
            AttemptRecorder(release, release.cells[0], "attempt-001").begin()
        with pytest.raises(ContractError, match="no automatic replay"):
            execute(release, block, adapter)
    assert adapter.resets == 0 and (cohort.root / "fleet-hold.json").exists()


def test_partition_accounting_waits_for_all_blocks_and_budget_uses_n3_p18(cohort):
    release = cohort.release(stage="D")
    operation = cohort.root / "operations" / "synthetic"
    operation.mkdir(parents=True)
    ids = list(blocks.frozen_blocks(release.cells))
    for block in ids[:-1]:
        finish(release, block, operation)
    lane.publish_block_partition(cohort.root, release, "N3", "LAT", "D")
    assert lane.read_partition_summary(cohort.root, "N3", "LAT", "D") is None
    finish(release, ids[-1], operation)
    lane.publish_block_partition(cohort.root, release, "N3", "LAT", "D")
    summary = lane.read_partition_summary(cohort.root, "N3", "LAT", "D")
    assert len(summary["episodes"]) == 24 and len(summary["blocks"]) == 4
    for family in lane.FAMILIES:
        pilot = cohort.release(family)
        finish(pilot, pilot.cells[0].block_id, operation)
        lane.publish_block_partition(cohort.root, pilot, "N3", family, "P")
    measured = lane.measured_pilots(cohort.root, "N3")
    assert len(measured["episodes"]) == 18 and measured["pilot_p95_episode_bytes"] > 0
    with pytest.raises(ContractError, match="all required"):
        lane.measured_pilots(cohort.root)


def test_six_lanes_can_only_claim_three_pilot_blocks(cohort):
    ids = [block for family in lane.FAMILIES for block in lane.planned_blocks(cohort.plan, family, "P")]
    assert len(ids) == 3
    from contextlib import ExitStack
    with ExitStack() as stack:
        assert all(stack.enter_context(lane.dispatch_claim(cohort.root, block)) for block in ids)
        assert not any(stack.enter_context(lane.dispatch_claim(cohort.root, block)) for block in ids)


def test_scheduler_hold_precedes_claim_and_e3_plan_never_runs(cohort, monkeypatch):
    request_fleet_hold(cohort.root, reason="synthetic user hold")
    before = (cohort.root / "fleet-hold.json").read_bytes()
    monkeypatch.setattr(lane, "run_one", lambda *_: pytest.fail("held or excluded model dispatched"))
    assert lane.run(cohort.plan) == 44
    assert not (cohort.root / "block-claims").exists()
    assert (cohort.root / "fleet-hold.json").read_bytes() == before
    with pytest.raises(ContractError, match="N3-only"):
        lane.run({**cohort.plan, "model": "E3"})


def test_run_one_reuses_immutable_partition_with_distinct_operation_admissions(cohort, monkeypatch):
    release = cohort.release(stage="D")
    ids = list(blocks.frozen_blocks(release.cells))
    original = {p.name: p.read_bytes() for p in release.root.iterdir()}
    monkeypatch.setattr(lane, "stage_ready", lambda *_: True)
    operations = []

    def prepare(_plan, _family, _stage, root):
        binding = {**cohort.binding, "storage_budget_receipt": cohort.binding["resource_budget_receipt"]}
        atomic_json(root / "binding.json", binding)
        return binding

    def cpu_worker(command, **kwargs):
        assert command[3] == "experiments.workshops.spatial_grounding_v1.worker"
        block = command[command.index("--block-id") + 1]
        assert command[command.index("--max-valid-episodes") + 1] == "6"
        assert command[command.index("--max-cell-attempts") + 1] == "3"
        operations.append(kwargs["env"]["SGW01_RUNTIME_RECEIPT"])
        with monkeypatch.context() as env:
            for key, value in kwargs["env"].items():
                env.setenv(key, value)
            assert execute(release, block) == 0
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(lane, "prepare_operation", prepare)
    monkeypatch.setattr(lane.subprocess, "run", cpu_worker)
    for index, block in enumerate(ids):
        _, plan, admission_root = admit(cohort, release, block, monkeypatch, number=index + 1)
        monkeypatch.setenv("SGW01_SUPERVISOR_RECEIPT", str(admission_root / "synthetic-receipt.json"))
        assert lane.run_one(plan, "LAT", "D", block) == 0
        assert {p.name: p.read_bytes() for p in release.root.iterdir()} == original
    assert len(operations) == len(set(operations)) == 4
    assert len(lane.read_partition_summary(cohort.root, "N3", "LAT", "D")["episodes"]) == 24
    assert len(list((cohort.root / "block-claims").glob("*.json"))) == 4


def test_scheduler_progresses_n3_p18_d72_c432_and_reuses_no_completed_blocks(cohort, monkeypatch):
    completed = set()
    calls = []
    real_read = lane.read_partition_summary

    def read(root, model, family, stage, block_id=None):
        if block_id is not None:
            return {"status": "complete"} if block_id in completed else None
        ids = lane.planned_blocks(cohort.plan, family, stage)
        return {"status": "complete"} if all(block in completed for block in ids) else None

    def complete(plan, family, stage, block):
        assert lane.stage_ready(cohort.root, stage, "N3")
        assert block not in completed
        completed.add(block)
        calls.append((family, stage, block))
        return 0

    monkeypatch.setattr(lane, "read_partition_summary", read)
    monkeypatch.setattr(lane, "run_one", complete)
    assert lane.run(cohort.plan) == 0
    assert [stage for _, stage, _ in calls] == ["P"] * 3 + ["D"] * 12 + ["C"] * 72
    assert len(completed) == 87 and len(calls) * 6 == 522
    assert lane.run(cohort.plan) == 0 and len(calls) == 87
    monkeypatch.setattr(lane, "read_partition_summary", real_read)


def test_completed_block_publication_recovery_never_starts_worker(cohort, monkeypatch):
    release = cohort.release()
    operation = cohort.root / "operations" / "synthetic"
    operation.mkdir(parents=True)
    block = release.cells[0].block_id
    finish(release, block, operation)
    blocks.begin_once(cohort.root, "block-claims", block, lane_id="crashed-after-completion")
    monkeypatch.setattr(lane, "run_one", lambda *_: pytest.fail("publication recovery replayed a block"))
    plan = {**cohort.plan, "partitions": ["LAT-P"]}
    assert lane.read_partition_summary(cohort.root, "N3", "LAT", "P") is None
    assert lane.run(plan) == 0
    assert len(lane.read_partition_summary(cohort.root, "N3", "LAT", "P")["episodes"]) == 6


@pytest.mark.parametrize("field", ["camera-revision", "camera-sha256", "input-revision"])
def test_runtime_identity_drift_blocks_before_claim_or_model_construction(cohort, monkeypatch, field):
    from experiments.workshops.spatial_grounding_v1 import camera_configuration, policy_observations

    release = cohort.release()
    if field.startswith("camera"):
        key = "revision" if field == "camera-revision" else "sha256"
        camera = {**release.binding["protocol_runtime"]["camera_configuration"], key: "different"}
        monkeypatch.setattr(camera_configuration, "camera_configuration_identity", lambda: camera)
    else:
        monkeypatch.setattr(policy_observations, "policy_input_identity", lambda: {"revision": "different"})
    monkeypatch.setattr(worker, "partition_lock", lambda *_: pytest.fail("drift reached claim"))
    monkeypatch.setattr(worker, "load_adapter", lambda *_: pytest.fail("drift constructed model"))
    with pytest.raises(worker.ResourceBlocked, match="immutable protocol_runtime"):
        execute(release, release.cells[0].block_id)
    assert not (cohort.root / "block-executions").exists()


@pytest.mark.parametrize("variable", ["SGW01_CAMERA_REVISION", "SGW01_POLICY_INPUT_REVISION"])
def test_block_plan_cannot_fall_back_to_legacy_runtime_defaults(cohort, variable):
    environment = dict(cohort.plan["runtime_environment"])
    environment.pop(variable)
    with pytest.raises(ContractError, match="explicitly propagate"):
        lane._block_registration({**cohort.plan, "runtime_environment": environment})


def test_release_rejects_protocol_binding_camera_input_disagreement(cohort):
    release = cohort.release()
    binding = dict(release.binding)
    binding["protocol_runtime"] = {**binding["protocol_runtime"], "policy_input_revision": "different"}
    atomic_json(release.root / "runtime_binding.json", binding)
    hashes = dict(release.hashes)
    hashes["runtime_binding.json"] = sha256_file(release.root / "runtime_binding.json")
    atomic_json(release.root / "hashes.json", hashes)
    with pytest.raises(ContractError, match="protocol_runtime differs"):
        load_release(release.root)


def test_legacy_worker_does_not_require_new_runtime_identity_declarations(cohort, monkeypatch):
    monkeypatch.setattr(worker, "_protocol_runtime_check", lambda *_: pytest.fail("legacy defaults changed"))
    assert worker.run_partition(
        cohort.old, model="N3", family="LAT", stage="P", max_valid=6, max_attempts=3,
        worker_id="legacy-cpu", adapter=FakeAdapter(), scorer=lambda *_: {"status": "valid_model_failure"},
    ) == 0
