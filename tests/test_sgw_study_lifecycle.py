"""CPU-only early-exit regression; all process/native observations are synthetic."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from experiments.workshops.spatial_grounding_v1 import block_scheduling as blocks
from experiments.workshops.spatial_grounding_v1 import study_lane as lane
from experiments.workshops.spatial_grounding_v1 import study_supervisor as supervisor
from experiments.workshops.spatial_grounding_v1.contract import ContractError
from experiments.workshops.spatial_grounding_v1.recorder import AttemptRecorder, atomic_json, request_fleet_hold
from tests.test_sgw_block_scheduling import admit, cohort, finish


def record_cell(release, cell, status="valid_model_failure"):
    recorder = AttemptRecorder(release, cell, "attempt-001")
    recorder.begin()
    if status == "partial":
        return recorder
    if status == "technical_invalid":
        recorder.complete({"status": status, "technical_cause": "synthetic transport failure"})
        return recorder
    for kind in ("actions", "states", "observations", "videos"):
        path = recorder.path / kind / "synthetic.txt"
        path.parent.mkdir()
        path.write_text("CPU test, not native evidence")
    recorder.complete({"status": status, "executed_action_count": 450, "safety_terminated": False})
    return recorder


@pytest.mark.parametrize("finished_cells", [0, 1, 5, 6])
def test_run_one_exit_zero_requires_all_six_immutable_pointers(cohort, monkeypatch, finished_cells):
    release = cohort.release()
    _, plan, root = admit(cohort, release, release.cells[0].block_id, monkeypatch)
    plan["partitions"] = ["LAT-P"]
    monkeypatch.setenv("SGW01_SUPERVISOR_RECEIPT", str(root / "synthetic-receipt.json"))
    monkeypatch.setattr(lane, "prepare_operation", lambda *_: dict(release.binding))
    calls = []

    def early_worker_exit(command, **_kwargs):
        assert command[3] == "experiments.workshops.spatial_grounding_v1.worker"
        calls.append(command)
        for cell in release.cells[:finished_cells]:
            record_cell(release, cell)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(lane.subprocess, "run", early_worker_exit)
    if finished_cells == 6:
        assert lane.run(plan) == 0
        assert lane.read_partition_summary(cohort.root, "N3", "LAT", "P") is not None
    else:
        with pytest.raises(ContractError, match="completion pointer"):
            lane.run(plan)
        assert (cohort.root / "fleet-hold.json").is_file()
        assert lane.read_partition_summary(cohort.root, "N3", "LAT", "P") is None
    pointers = list((cohort.root / "cells").glob("*.complete.json"))
    preserved = {path: path.read_bytes() for path in pointers}
    assert len(pointers) == finished_cells
    assert lane.run(plan) == (0 if finished_cells == 6 else 44)
    assert len(calls) == 1 and all(path.read_bytes() == value for path, value in preserved.items())


@pytest.fixture
def outer(cohort, monkeypatch):
    plan = {**cohort.plan, "partitions": ["LAT-P", "HEIGHT-P"],
            "pod_name": "synthetic-policy", "pod_uid": "synthetic-policy-uid"}
    control = cohort.root / "simulator-control"
    control.mkdir()
    identity = cohort.root / "synthetic-lane.json"
    atomic_json(identity, {
        "control_root": str(control), "simulator_pod_uid": plan["pod_uid"],
        "simulator_pod_name": plan["pod_name"], "simulator_gpu_uuid": plan["gpu_uuid"],
        "source_commit": plan["source_commit"], "source_root": plan["source_root"],
    })
    plan["runtime_environment"] = {
        **plan["runtime_environment"], "SGW01_SIMULATOR_LANE_IDENTITY": str(identity),
        "SGW01_SIMULATOR_LANE_IDENTITY_SHA256": lane.reference(identity)["sha256"],
    }
    plan["lane_identity_template"] = lane.reference(identity)
    plan_path = cohort.root / "synthetic-plan.json"
    atomic_json(plan_path, plan)
    root = cohort.root / "supervision"
    root.mkdir()
    args = SimpleNamespace(
        plan=plan_path, plan_sha256=lane.reference(plan_path)["sha256"], run_root=root,
        seconds=3600, role="policy", supervisor_id="synthetic-supervisor",
    )
    started = datetime.now(timezone.utc).timestamp()
    monkeypatch.setattr(supervisor.ctypes, "CDLL", lambda *_a, **_k: SimpleNamespace(prctl=lambda *_: 0))
    monkeypatch.setattr(supervisor.signal, "signal", lambda *_: None)
    monkeypatch.setattr(supervisor, "process_info", lambda pid: {
        "started_at_unix": started, "process_start_identity": str(pid), "command": ["synthetic-supervisor"],
    })
    monkeypatch.setattr(supervisor, "sample_memory", lambda *_a, **_k: {
        "sampled_peak_bytes": 1, "sampled_anon_plus_shmem_peak_bytes": 1,
    })
    monkeypatch.setattr(supervisor, "STOP", False)
    monkeypatch.setattr(supervisor, "descendants", lambda *_: {})
    shutdowns = []
    monkeypatch.setattr(supervisor, "stop_tree", lambda child: shutdowns.append(child.pid))
    monkeypatch.setattr(supervisor.subprocess, "run", lambda *_a, **_k: pytest.fail("unexpected probe/process"))
    children = []

    def launch(effect):
        def popen(command, **kwargs):
            assert kwargs["start_new_session"] is True
            assert command[1:3] == ["-m", "experiments.workshops.spatial_grounding_v1.study_lane"]
            child = SimpleNamespace(pid=10000 + len(children))
            children.append(child)
            child.returncode = effect()
            child.poll = lambda: child.returncode
            return child
        monkeypatch.setattr(supervisor.subprocess, "Popen", popen)

    def finish_unit(family, stage="P", block=None, owner=None):
        path = lane.release_path(cohort.root, "N3", family, stage, "r5")
        release = lane.load_release(path) if path.exists() else cohort.release(family, stage)
        block = block or release.cells[0].block_id
        blocks.begin_once(cohort.root, "block-claims", block, lane_id=owner or plan["lane_id"])
        operation = cohort.root / "operations" / block
        operation.mkdir(parents=True)
        finish(release, block, operation)
        lane.publish_block_partition(cohort.root, release, "N3", family, stage)
        return release

    return SimpleNamespace(plan=plan, args=args, root=root, children=children,
                           launch=launch, finish=finish_unit, control=control, shutdowns=shutdowns)


def test_supervisor_does_not_trust_zero_exit_or_lane_complete_status(cohort, outer):
    atomic_json(cohort.root / "lane-status" / f"{outer.plan['lane_id']}.json", {"status": "complete"})
    outer.launch(lambda: 0)
    assert supervisor.run_owned(outer.args, outer.plan) == 42
    assert len(outer.children) == 1
    result = json.loads((outer.root / "exit.json").read_text())
    assert result["child_returncode"] == 0
    assert result["status"] == "incomplete_preserve_no_automatic_retry"
    assert result["queue_completion"]["complete"] is False
    assert (cohort.root / "fleet-hold.json").is_file()


def test_supervisor_continues_only_untouched_blocks_across_verified_stage_boundaries(cohort, outer, monkeypatch):
    outer.plan["partitions"] = ["LAT-P", "HEIGHT-P", "DIST-P", "LAT-D"]
    dispatched = []

    def run_one(plan, family, stage, block):
        assert lane.stage_ready(cohort.root, stage, "N3")
        assert block not in dispatched
        dispatched.append(block)
        outer.finish(family, stage, block)
        raise SystemExit(0)  # The outer lane dies after publication, before the next unit.

    monkeypatch.setattr(lane, "run_one", run_one)

    def run_child():
        try:
            return lane.run(outer.plan)
        except SystemExit as exc:
            return exc.code

    outer.launch(run_child)
    assert supervisor.run_owned(outer.args, outer.plan) == 0
    assert len(outer.children) == len(dispatched) == 7
    assert dispatched[:3] == ["LAT-P01-N3", "HEIGHT-P01-N3", "DIST-P01-N3"]
    assert len(list((cohort.root / "cells").glob("*.complete.json"))) == 42
    assert all(len(list(path.iterdir())) == 1 for path in (cohort.root / "attempts").iterdir())
    result = json.loads((outer.root / "exit.json").read_text())
    assert result["status"] == "complete" and result["queue_completion"]["complete"]
    assert result["queue_completion"]["pending_units"] == []
    assert len(list(outer.root.glob("child*-exit.json"))) == 7
    assert len(list(outer.root.glob("child*-start.json"))) == 7
    assert json.loads((outer.root / "child-exit.json").read_text())["status"] == "continue_pending_blocks"
    assert not (cohort.root / "fleet-hold.json").exists()


@pytest.mark.parametrize("fault", ["partial", "technical_invalid", "no-progress", "empty-claim", "partial-block"])
def test_successful_exit_after_progress_never_retries_incomplete_attempts(cohort, outer, fault):
    def child():
        if len(outer.children) == 1:
            outer.finish("LAT")
        else:
            release = cohort.release("HEIGHT")
            if fault != "no-progress":
                blocks.begin_once(cohort.root, "block-claims", release.cells[0].block_id,
                                  lane_id=outer.plan["lane_id"])
                if fault not in {"empty-claim"}:
                    record_cell(release, release.cells[0],
                                "valid_model_failure" if fault == "partial-block" else fault)
        return 0

    outer.launch(child)
    assert supervisor.run_owned(outer.args, outer.plan) != 0
    assert len(outer.children) == 2
    result = json.loads((outer.root / "exit.json").read_text())
    assert result["status"] != "complete" and not result["queue_completion"]["complete"]
    assert (cohort.root / "fleet-hold.json").is_file()
    assert all(len(list(path.iterdir())) == 1 for path in (cohort.root / "attempts").iterdir())
    assert lane.read_partition_summary(cohort.root, "N3", "LAT", "P") is not None
    assert lane.read_partition_summary(cohort.root, "N3", "HEIGHT", "P") is None


def test_other_lane_progress_does_not_justify_restarting_no_progress_child(cohort, outer):
    outer.launch(lambda: outer.finish("LAT", owner="different-lane") and 0)
    assert supervisor.run_owned(outer.args, outer.plan) == 42
    assert len(outer.children) == 1


def test_prior_completed_own_blocks_do_not_count_as_new_progress(cohort, outer):
    outer.finish("LAT")
    outer.launch(lambda: 0)
    assert supervisor.run_owned(outer.args, outer.plan) == 42
    assert len(outer.children) == 1


@pytest.mark.parametrize("fault", ["hold", "stop", "deadline", "simulator-stopped", "nonzero", "leftovers"])
def test_progress_does_not_override_holds_stops_or_process_failures(cohort, outer, monkeypatch, fault):
    def child():
        outer.finish("LAT")
        if fault == "hold":
            request_fleet_hold(cohort.root, reason="synthetic user hold")
        elif fault == "stop":
            monkeypatch.setattr(supervisor, "STOP", True)
        elif fault == "deadline":
            class Expired(datetime):
                @classmethod
                def now(cls, tz=None):
                    return datetime.now(tz) + timedelta(hours=2)
            monkeypatch.setattr(supervisor, "datetime", Expired)
        elif fault == "simulator-stopped":
            atomic_json(outer.control / "stop.json", {"synthetic": True})
        elif fault == "leftovers":
            monkeypatch.setattr(supervisor, "descendants", lambda *_: {20000: "synthetic-child"})
        return 9 if fault == "nonzero" else 0

    outer.launch(child)
    assert supervisor.run_owned(outer.args, outer.plan) != 0
    assert len(outer.children) == 1
    assert json.loads((outer.root / "exit.json").read_text())["status"] != "complete"


@pytest.mark.parametrize("corrupt", ["pointer", "manifest", "result", "wrong-source"])
def test_supervisor_rejects_corrupt_or_wrong_release_completion(cohort, outer, corrupt):
    outer.plan["partitions"] = ["LAT-P"]

    def child():
        release = outer.finish("LAT")
        pointer = cohort.root / "cells" / f"{release.cells[0].cell_id}.complete.json"
        value = json.loads(pointer.read_text())
        path = {"pointer": pointer, "manifest": Path(value["manifest_path"]),
                "result": Path(value["result"]["path"])}.get(corrupt)
        if path is not None:
            path.write_text("{}")
        else:
            outer.plan["source_commit"] = "wrong"
        return 0

    outer.launch(child)
    with pytest.raises(ContractError):
        supervisor.run_owned(outer.args, outer.plan)
    assert not (outer.root / "exit.json").exists()
    assert (outer.root / "failure.json").is_file() and (cohort.root / "fleet-hold.json").is_file()
    assert json.loads((outer.root / "failure.json").read_text())["child_returncode"] == 0
    assert len(outer.children) == 1


def test_simulator_exit_zero_reports_listener_shutdown_not_queue_completion(outer, monkeypatch):
    outer.args.role = "simulator"
    monkeypatch.setattr(supervisor.subprocess, "run", lambda *_a, **_k: None)
    monkeypatch.setattr(supervisor.subprocess, "Popen",
                        lambda *_a, **_k: SimpleNamespace(pid=10000, returncode=0, poll=lambda: 0))
    monkeypatch.setattr(supervisor, "lane_completion_state", lambda *_: pytest.fail("simulator certified study queue"))
    assert supervisor.run_owned(outer.args, outer.plan) == 0
    result = json.loads((outer.root / "exit.json").read_text())
    assert result["status"] == "listener_stopped" and result["queue_completion"] is None
