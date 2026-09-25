"""Synthetic CPU recovery fixtures; no external source changes or resource use."""

from dataclasses import replace
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from experiments.workshops.spatial_grounding_v1 import operator_recovery as recovery
from experiments.workshops.spatial_grounding_v1 import study_lane as lane
from experiments.workshops.spatial_grounding_v1 import worker
from experiments.workshops.spatial_grounding_v1.block_scheduling import begin_once
from experiments.workshops.spatial_grounding_v1.contract import ContractError, load_release, sha256_file
from experiments.workshops.spatial_grounding_v1.recorder import AttemptRecorder, atomic_json, request_fleet_hold
from tests.test_sgw_block_scheduling import admit, cohort, execute
from tests.test_sgw_study_lifecycle import record_cell
from tests.test_sgw_worker import FakeAdapter


@pytest.fixture
def approved(cohort, monkeypatch):
    root = cohort.root
    old_environment = root / "old-environment.json"
    atomic_json(old_environment, {
        "source_root": cohort.binding["source_root"], "source_commit": cohort.binding["source_commit"],
        "cells": {"synthetic": {"scene": "unchanged"}}, "camera": cohort.binding["protocol_runtime"],
    })
    cohort.binding["environment_binding"] = lane.reference(old_environment)
    cohort.binding["existing_pod_supervisor_entrypoint"] = lane.reference(Path(lane.__file__).with_name("study_supervisor.py"))
    atomic_json(cohort.binding_path, cohort.binding)
    releases = [cohort.release(family) for family in lane.FAMILIES]
    records = []
    for release in releases:
        first = release.cells[0]
        record_cell(release, first, "technical_invalid" if first.family == "DIST" else "valid_model_failure")
        for area in ("block-claims", "block-executions"):
            begin_once(root, area, first.block_id, lane_id="old-lane", release_id=release.release_id)
        cells = []
        for cell in release.cells:
            pointer = root / "cells" / f"{cell.cell_id}.complete.json"
            attempts = list((root / "attempts" / cell.cell_id).glob("*/manifest.json"))
            cells.append({
                "cell_id": cell.cell_id, "attempts": [{"manifest": lane.reference(path)} for path in attempts],
                "completion": lane.reference(pointer) if pointer.exists() else None,
                "next_attempt": None if pointer.exists() else (2 if attempts else 1),
            })
        records.append({
            "path": str(release.root), "release_id": release.release_id, "hashes": dict(release.hashes),
            "blocks": [{"block_id": first.block_id, "cells": cells, "claims": {
                "dispatch": lane.reference(root / "block-claims" / f"{first.block_id}.json"),
                "execution": lane.reference(root / "block-executions" / f"{first.block_id}.json"),
            }}],
        })
    (root / "fleet-hold.json").rename(root / "preserved-hold.json")
    owners = []
    for index in range(12):
        directory = root / "old-supervisors" / str(index)
        atomic_json(directory / "start.json", {
            "source_commit": cohort.binding["source_commit"], "supervisor_id": f"synthetic-{index}",
            "pod_uid": f"synthetic-pod-{index}",
        })
        atomic_json(directory / "exit.json", {"returncode": 43, "owned_descendants_remaining": {}})
        owners.append({"start": lane.reference(directory / "start.json"), "exit": lane.reference(directory / "exit.json")})
    atomic_json(root / "approval.json", {"status": "approved", "test_only": True})
    atomic_json(root / "old-launch.json", {
        "source_commit": cohort.binding["source_commit"], "owners": [{"start": row["start"]} for row in owners],
    })
    new_source = {"root": cohort.binding["source_root"], "commit": "b" * 40}
    new_environment = root / "new-environment.json"
    atomic_json(new_environment, {
        **json.loads(old_environment.read_text()), "source_root": new_source["root"], "source_commit": new_source["commit"],
    })
    overlay = {
        "source_root": new_source["root"], "source_commit": new_source["commit"],
        "existing_pod_supervisor_entrypoint": cohort.binding["existing_pod_supervisor_entrypoint"],
        "environment_binding": lane.reference(new_environment),
    }
    value = {
        "schema": "sgw-01-operator-recovery-v1", "status": "approved", "recovery_id": "synthetic-r1",
        "allowed_models": ["N3"], "cohort_root": str(root),
        "old_source": {"root": cohort.binding["source_root"], "commit": cohort.binding["source_commit"]},
        "new_source": new_source, "source_diff_sha256": "synthetic",
        "owner_approval_reference": lane.reference(root / "approval.json"),
        "prior_hold": lane.reference(root / "preserved-hold.json"),
        "prior_launch": lane.reference(root / "old-launch.json"), "prior_owners": owners,
        "overlay": overlay, "releases": records,
    }
    path = root / "recovery.json"
    real_source_check = recovery._source_check
    monkeypatch.setattr(recovery, "_source_check", lambda _value: None)
    new_binding = {**cohort.binding, **overlay}
    binding_path = root / "recovery-binding.json"
    atomic_json(binding_path, new_binding)
    plan = {**cohort.plan, "source_commit": new_source["commit"],
            "inputs": {**cohort.plan["inputs"], "binding": lane.reference(binding_path)}}

    def publish():
        atomic_json(path, value)
        ref = lane.reference(path)
        plan["operator_recovery"] = ref
        monkeypatch.setenv("SGW01_OPERATOR_RECOVERY", str(path))
        monkeypatch.setenv("SGW01_OPERATOR_RECOVERY_SHA256", ref["sha256"])
        monkeypatch.setenv("SGW01_ENV_BINDING", overlay["environment_binding"]["path"])
        monkeypatch.setenv("SGW01_ENV_BINDING_SHA256", overlay["environment_binding"]["sha256"])
        return ref

    publish()
    return SimpleNamespace(value=value, path=path, releases=releases, publish=publish, plan=plan,
                           binding=new_binding, source_check=real_source_check)


def bind(cohort, approved, release, monkeypatch):
    effective = recovery.effective_release(release)
    admission, _, root = admit(cohort, effective, release.cells[0].block_id, monkeypatch)
    admission["execution_identity"] = recovery.execution_identity(effective)
    atomic_json(root / "admission.json", admission)
    monkeypatch.setenv("SGW01_RUN_ADMISSION_SHA256", sha256_file(root / "admission.json"))
    monkeypatch.setenv("SGW01_OPERATOR_RECOVERY", str(approved.path))
    monkeypatch.setenv("SGW01_OPERATOR_RECOVERY_SHA256", sha256_file(approved.path))
    return effective, root


def test_all_three_partial_pilots_resume_without_rewriting_original_evidence(cohort, approved, monkeypatch):
    preserved = {path: path.read_bytes() for release in approved.releases for path in release.root.iterdir()}
    preserved.update({path: path.read_bytes() for area in ("block-claims", "block-executions", "cells")
                      for path in (cohort.root / area).iterdir()})
    preserved.update({path: path.read_bytes() for path in (cohort.root / "attempts").glob("*/*/manifest.json")})
    for release in approved.releases:
        bind(cohort, approved, release, monkeypatch)
        adapter = FakeAdapter()
        block = release.cells[0].block_id
        assert execute(release, block, adapter) == 0
        assert adapter.resets == (6 if release.cells[0].family == "DIST" else 5)
        for cell in release.cells:
            pointer = json.loads((cohort.root / "cells" / f"{cell.cell_id}.complete.json").read_text())
            manifest = json.loads(Path(pointer["manifest_path"]).read_text())
            assert manifest["release_hashes"] == dict(release.hashes)
            if cell.cell_id == recovery.RETRY_CELL:
                assert pointer["attempt_id"] == "attempt-002"
            if cell != release.cells[0] or cell.family == "DIST":
                identity = json.loads(Path(pointer["manifest_path"]).with_name("execution-identity.json").read_text())
                assert identity["source_commit"] == approved.value["new_source"]["commit"]
                assert "execution-identity.json" in manifest["artifacts"]
                assert json.loads(Path(pointer["manifest_path"]).with_name("run-admission.json").read_text())["execution_identity"] == identity
    assert all(path.read_bytes() == value for path, value in preserved.items())
    assert len(list((cohort.root / "cells").glob("*.json"))) == 18
    assert not (cohort.root / "fleet-hold.json").exists()


@pytest.mark.parametrize("fault", [
    "extra-attempt", "nonterminal", "request", "wrong-next", "changed-claim", "changed-manifest",
    "unlisted-owner", "live-owner", "scientific-overlay", "changed-environment", "wrong-release-hashes",
])
def test_recovery_refuses_unapproved_or_mutated_state(cohort, approved, fault):
    release = approved.releases[-1]
    block = release.cells[0].block_id
    record = approved.value["releases"][-1]["blocks"][0]
    first = record["cells"][0]
    directory = cohort.root / "attempts" / first["cell_id"] / "attempt-001"
    if fault == "extra-attempt":
        directory.with_name("attempt-002").mkdir()
    elif fault == "nonterminal":
        path = directory / "manifest.json"
        manifest = json.loads(path.read_text())
        atomic_json(path, {**manifest, "complete": False})
        first["attempts"][0]["manifest"] = lane.reference(path)
    elif fault == "request":
        (directory / "request_index.jsonl").write_text('{"request_id":"already-requested"}\n')
    elif fault == "wrong-next":
        first["next_attempt"] = 3
    elif fault == "changed-claim":
        Path(record["claims"]["dispatch"]["path"]).write_text("{}")
    elif fault == "changed-manifest":
        (directory / "manifest.json").write_text("{}")
    elif fault == "unlisted-owner":
        approved.value["prior_owners"].pop()
    elif fault == "live-owner":
        owner = approved.value["prior_owners"][0]
        path = Path(owner["exit"]["path"])
        atomic_json(path, {"returncode": 0, "owned_descendants_remaining": {"123": "owned"}})
        owner["exit"] = lane.reference(path)
    elif fault == "scientific-overlay":
        approved.value["overlay"]["checkpoint_hashes"] = {"N3": "different"}
    elif fault == "changed-environment":
        path = Path(approved.value["overlay"]["environment_binding"]["path"])
        env = json.loads(path.read_text())
        atomic_json(path, {**env, "cells": {}})
        approved.value["overlay"]["environment_binding"] = lane.reference(path)
    else:
        approved.value["releases"][-1]["hashes"]["protocol.json"] = "different"
    approved.publish()
    with pytest.raises(ContractError):
        effective = recovery.effective_release(release)
        recovery.validate_block_start(effective, block)


def test_only_dist_can_retry_and_completed_cells_cannot_replay(cohort, approved):
    first = approved.value["releases"][0]["blocks"][0]["cells"][0]
    first["next_attempt"] = 2
    approved.publish()
    release = recovery.effective_release(approved.releases[0])
    with pytest.raises(ContractError, match="completed cells"):
        recovery.validate_block_start(release, release.cells[0].block_id)


def test_recovery_claims_are_append_only_exclusive_and_new_faults_hold(cohort, approved, monkeypatch):
    release, _ = bind(cohort, approved, approved.releases[-1], monkeypatch)
    block = release.cells[0].block_id
    recovery.begin_recovery(release, block, "dispatch", lane_id="new")
    with pytest.raises(ContractError, match="no automatic replay"):
        recovery.begin_recovery(release, block, "dispatch", lane_id="duplicate")
    assert (cohort.root / "fleet-hold.json").exists()
    adapter = FakeAdapter()
    assert execute(release, block, adapter) == 44 and adapter.resets == 0
    assert not (cohort.root / recovery.claim_area(release, "execution")).exists()


def test_recovery_invalid_attempt002_stops_without_attempt003(cohort, approved, monkeypatch):
    release = approved.releases[-1]
    bind(cohort, approved, release, monkeypatch)

    class Broken(FakeAdapter):
        def run_episode(self, *_):
            return {"status": "technical_invalid", "technical_cause": "new synthetic fault"}

    assert execute(release, release.cells[0].block_id, Broken()) == 44
    assert (cohort.root / "fleet-hold.json").exists()
    attempts = cohort.root / "attempts" / recovery.RETRY_CELL
    assert sorted(path.name for path in attempts.iterdir()) == ["attempt-001", "attempt-002"]


@pytest.mark.parametrize("fault", [None, "policy-code", "diff-hash", "dirty", "wrong-head"])
def test_actual_source_check_restricts_diff_and_exact_clean_pin(approved, monkeypatch, fault):
    value = approved.value
    patch = b"synthetic infrastructure diff"
    value["source_diff_sha256"] = hashlib.sha256(patch).hexdigest()
    if fault == "diff-hash":
        value["source_diff_sha256"] = "0" * 64

    def git(command, **_kwargs):
        args = command[3:]
        if args == ["rev-parse", "HEAD"]:
            return (("a" * 40 if fault == "wrong-head" else value["new_source"]["commit"]) + "\n").encode()
        if args == ["status", "--porcelain"]:
            return b" M worker.py" if fault == "dirty" else b""
        if "--name-only" in args:
            return (recovery.BASE + ("policy_observations.py" if fault == "policy-code" else "remote_simulator_lane.py") + "\n").encode()
        assert args[:4] == ["diff", "--no-ext-diff", "--no-textconv", "--binary"]
        return patch

    monkeypatch.setattr(recovery.subprocess, "check_output", git)
    if fault is None:
        approved.source_check(value)
    else:
        with pytest.raises(ContractError):
            approved.source_check(value)


def test_run_one_bridges_pin_and_preserves_release_hashes(cohort, approved, monkeypatch):
    original = approved.releases[-1]
    effective, root = bind(cohort, approved, original, monkeypatch)
    plan = {**approved.plan, "partitions": ["DIST-P"], "runtime_environment": {
        **approved.plan["runtime_environment"],
        "SGW01_SIMULATOR_LANE_IDENTITY": str(root / "simulator.json"),
        "SGW01_SIMULATOR_LANE_IDENTITY_SHA256": sha256_file(root / "simulator.json"),
    }}
    monkeypatch.setenv("SGW01_SUPERVISOR_RECEIPT", str(root / "synthetic-receipt.json"))
    monkeypatch.setattr(lane, "prepare_operation", lambda *_: dict(approved.binding))

    def cpu_worker(command, **kwargs):
        assert command[3] == "experiments.workshops.spatial_grounding_v1.worker"
        with monkeypatch.context() as env:
            for key, value in kwargs["env"].items():
                env.setenv(key, value)
            assert execute(original, original.cells[0].block_id) == 0
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(lane.subprocess, "run", cpu_worker)
    assert lane.run(plan) == 0
    assert dict(load_release(original.root).hashes) == dict(original.hashes)
    summary = lane.read_partition_summary(cohort.root, "N3", "DIST", "P")
    assert summary["execution_identity"] == recovery.execution_identity(effective)
    assert lane.lane_completion_state(plan)["complete"]


def test_parallel_recovery_accepts_other_blocks_approved_inflight_attempt(cohort, approved):
    first = recovery.effective_release(approved.releases[0])
    block = first.cells[0].block_id
    recovery.begin_recovery(first, block, "dispatch", lane_id="first")
    recovery.begin_recovery(first, block, "execution", worker_id="first")
    AttemptRecorder(first, first.cells[1], "attempt-001").begin()
    second = recovery.effective_release(approved.releases[-1])
    recovery.begin_recovery(second, second.cells[0].block_id, "dispatch", lane_id="second")
    recovery.begin_recovery(second, second.cells[0].block_id, "execution", worker_id="second")
    with pytest.raises(ContractError, match="unapproved, partial, or extra"):
        recovery.begin_recovery(first, block, "execution", worker_id="replay")


@pytest.mark.parametrize("stage", ["D", "C"])
def test_prospective_new_pin_releases_do_not_inherit_partial_retry_permissions(cohort, approved, stage):
    atomic_json(cohort.binding_path, approved.binding)
    release = cohort.release(stage=stage)
    effective = recovery.effective_release(release)
    assert effective is release
    assert "operator_recovery" not in effective.binding
    assert recovery.block_record(effective, effective.cells[0].block_id) is None


def test_unlisted_old_pin_release_is_not_recovered(cohort, approved):
    release = cohort.release(stage="D")
    with pytest.raises(ContractError, match="old release is not enumerated"):
        recovery.effective_release(release)


@pytest.mark.parametrize("fault", ["missing-release", "missing-cell", "other-block-nonterminal", "active-hold"])
def test_recovery_validates_global_inventory_before_any_block(cohort, approved, fault):
    if fault == "missing-release":
        approved.value["releases"].pop(0)
    elif fault == "missing-cell":
        approved.value["releases"][0]["blocks"][0]["cells"].pop()
    elif fault == "other-block-nonterminal":
        cell = approved.value["releases"][0]["blocks"][0]["cells"][0]
        path = Path(cell["attempts"][0]["manifest"]["path"])
        atomic_json(path, {**json.loads(path.read_text()), "complete": False})
        cell["attempts"][0]["manifest"] = lane.reference(path)
    else:
        request_fleet_hold(cohort.root, reason="new active hold must not authorize recovery")
        approved.value["prior_hold"] = lane.reference(cohort.root / "fleet-hold.json")
    approved.publish()
    with pytest.raises(ContractError):
        recovery.effective_release(approved.releases[-1])


@pytest.mark.parametrize("fault", [None, "wrong-owner", "unverified-pid", "live-child"])
def test_explicit_drain_receipt_requires_identity_and_verified_exit(cohort, approved, fault):
    owner = approved.value["prior_owners"][0]
    start = json.loads(Path(owner["start"]["path"]).read_text())
    drained = {
        "schema": "sgw-01-owner-drain-v1", "supervisor_id": start["supervisor_id"],
        "pod_uid": start["pod_uid"], "pid_exit_verified": True,
        "returncode": 1, "owned_descendants_remaining": {},
    }
    if fault == "wrong-owner":
        drained["supervisor_id"] = "different"
    elif fault == "unverified-pid":
        drained["pid_exit_verified"] = False
    elif fault == "live-child":
        drained["owned_descendants_remaining"] = {"123": "still-owned"}
    path = cohort.root / "explicit-drain.json"
    atomic_json(path, drained)
    owner["exit"] = lane.reference(path)
    approved.publish()
    if fault is None:
        recovery.effective_release(approved.releases[0])
    else:
        with pytest.raises(ContractError):
            recovery.effective_release(approved.releases[0])


def test_preflight_cli_does_not_clear_hold_or_create_claims(cohort, approved, monkeypatch, capsys):
    request_fleet_hold(cohort.root, reason="operator must clear separately after preflight")
    hold = (cohort.root / "fleet-hold.json").read_bytes()
    monkeypatch.setattr("sys.argv", [
        "operator_recovery", "--receipt", str(approved.path), "--sha256", sha256_file(approved.path),
    ])
    recovery.main()
    value = json.loads(capsys.readouterr().out)
    assert value["status"] == "validated_only_no_launch"
    assert set(value["blocks"]) == {"LAT-P01-N3", "HEIGHT-P01-N3", "DIST-P01-N3"}
    assert (cohort.root / "fleet-hold.json").read_bytes() == hold
    assert not (cohort.root / "operator-recoveries").exists()
