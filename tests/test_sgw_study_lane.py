"""CPU-only scheduling/ownership tests; no native model or cluster operations."""

from pathlib import Path

import pytest

from experiments.workshops.spatial_grounding_v1 import study_lane as lane
from experiments.workshops.spatial_grounding_v1 import study_supervisor as supervisor
from experiments.workshops.spatial_grounding_v1.contract import ContractError


def test_supervisor_distinguishes_sampled_and_kernel_memory_peaks(tmp_path):
    (tmp_path / "memory.current").write_text("2048\n")
    (tmp_path / "memory.max").write_text("34359738368\n")
    (tmp_path / "memory.events").write_text("oom 0\noom_kill 0\n")
    first = supervisor.sample_memory(root=tmp_path)
    assert first["sampled_peak_bytes"] == 2048
    assert first["kernel_peak_bytes"] is None
    assert first["limit_bytes"] == 32 * 1024**3
    (tmp_path / "memory.current").write_text("1024\n")
    (tmp_path / "memory.peak").write_text("4096\n")
    (tmp_path / "memory.events").write_text("oom 1\noom_kill 1\n")
    final = supervisor.sample_memory(first["sampled_peak_bytes"], tmp_path)
    assert final["sampled_peak_bytes"] == 2048
    assert final["kernel_peak_bytes"] == 4096
    assert final["events"]["oom_kill"] == 1


def test_dispatch_claim_is_exclusive_and_partition_scoped(tmp_path):
    with lane.dispatch_claim(tmp_path, "N3-LAT-P") as first:
        with lane.dispatch_claim(tmp_path, "N3-LAT-P") as duplicate:
            with lane.dispatch_claim(tmp_path, "N3-HEIGHT-P") as disjoint:
                assert first and not duplicate and disjoint
    with lane.dispatch_claim(tmp_path, "N3-LAT-P") as resumed:
        assert resumed


def test_reference_rejects_changed_input(tmp_path):
    path = tmp_path / "input.json"
    path.write_text('{"original":true}')
    ref = lane.reference(path)
    assert lane.read_reference(ref) == {"original": True}
    path.write_text('{"original":false}')
    with pytest.raises(ContractError, match="changed"):
        lane.read_reference(ref)


def test_stage_barrier_never_uses_outcome_success(monkeypatch, tmp_path):
    done = set()
    monkeypatch.setattr(lane, "read_partition_summary",
                        lambda root, model, family, stage: {"status": "complete"} if (model, family, stage) in done else None)
    assert lane.stage_ready(tmp_path, "P")
    assert not lane.stage_ready(tmp_path, "D")
    done.update((m, f, "P") for m in lane.MODELS for f in lane.FAMILIES)
    assert lane.stage_ready(tmp_path, "D")
    assert not lane.stage_ready(tmp_path, "C")
    done.update((m, f, "D") for m in lane.MODELS for f in lane.FAMILIES)
    assert lane.stage_ready(tmp_path, "C")


def test_controller_runs_whole_partitions_in_order_without_replay(monkeypatch, tmp_path):
    from experiments.workshops.spatial_grounding_v1 import mailbox_visibility

    monkeypatch.setattr(mailbox_visibility, "DirectoryRefresher", lambda: lambda path: None)
    completed = {("LAT", "P")}
    calls = []
    monkeypatch.setattr(lane, "read_partition_summary",
                        lambda root, model, family, stage: {} if (family, stage) in completed else None)
    monkeypatch.setattr(lane, "stage_ready", lambda *_: True)
    monkeypatch.setattr(lane, "stop_remote_lane", lambda *_: None)

    def execute(plan, family, stage):
        calls.append((family, stage))
        completed.add((family, stage))
        return 0

    monkeypatch.setattr(lane, "run_one", execute)
    plan = {"cohort_root": str(tmp_path), "lane_id": "n3-0", "model": "N3",
            "partitions": [f"{f}-{s}" for s in lane.STAGES for f in lane.FAMILIES]}
    assert lane.run(plan) == 0
    assert calls == [(f, s) for s in lane.STAGES for f in lane.FAMILIES if (f, s) != ("LAT", "P")]
    calls.clear()
    assert lane.run(plan) == 0
    assert calls == []


def test_controller_stops_on_first_failure_without_retry(monkeypatch, tmp_path):
    from experiments.workshops.spatial_grounding_v1 import mailbox_visibility

    monkeypatch.setattr(mailbox_visibility, "DirectoryRefresher", lambda: lambda path: None)
    monkeypatch.setattr(lane, "read_partition_summary", lambda *_: None)
    monkeypatch.setattr(lane, "stage_ready", lambda *_: True)
    calls = []
    monkeypatch.setattr(lane, "run_one", lambda p, f, s: calls.append((f, s)) or 42)
    plan = {"cohort_root": str(tmp_path), "lane_id": "n3-0", "model": "N3",
            "partitions": ["LAT-P", "HEIGHT-P"]}
    assert lane.run(plan) == 42
    assert calls == [("LAT", "P")]


def _proc_stat(root: Path, pid: int, ppid: int, start: int, state="S"):
    path = root / str(pid)
    path.mkdir()
    fields = [state, str(ppid)] + ["0"] * 17 + [str(start)] + ["0"] * 4
    (path / "stat").write_text(f"{pid} (command with spaces) " + " ".join(fields))


def test_descendants_excludes_siblings_and_zombies(tmp_path):
    _proc_stat(tmp_path, 10, 1, 100)
    _proc_stat(tmp_path, 11, 10, 110)
    _proc_stat(tmp_path, 12, 11, 120)
    _proc_stat(tmp_path, 13, 1, 130)
    _proc_stat(tmp_path, 14, 10, 140, "Z")
    assert supervisor.descendants(10, tmp_path) == {11: "110", 12: "120"}


def test_signal_owned_rejects_pid_reuse(monkeypatch):
    calls = []
    monkeypatch.setattr(supervisor, "process_info", lambda pid: {"process_start_identity": "new"})
    monkeypatch.setattr(supervisor.os, "kill", lambda pid, sig: calls.append((pid, sig)))
    supervisor.signal_owned({22: "old"}, 15)
    assert calls == []
    supervisor.signal_owned({22: "new"}, 15)
    assert calls == [(22, 15)]


def test_simulator_gpu_lease_is_shared_and_policy_does_not_double_lock(tmp_path):
    plan = {"cohort_root": str(tmp_path), "gpu_uuid": "GPU-test"}
    with supervisor.simulator_gpu_lease(plan, "simulator"):
        with pytest.raises(BlockingIOError):
            with supervisor.simulator_gpu_lease(plan, "simulator"):
                raise AssertionError("duplicate simulator acquired the physical GPU")
        with supervisor.simulator_gpu_lease(plan, "policy"):
            pass


def test_finished_lane_only_stops_its_pinned_simulator(tmp_path):
    import json

    control = tmp_path / "control"
    control.mkdir()
    identity = tmp_path / "identity.json"
    identity.write_text(json.dumps({"model": "N3", "control_root": str(control)}))
    ref = lane.reference(identity)
    plan = {"model": "N3", "runtime_environment": {
        "SGW01_SIMULATOR_LANE_IDENTITY": str(identity),
        "SGW01_SIMULATOR_LANE_IDENTITY_SHA256": ref["sha256"],
    }}
    lane.stop_remote_lane(plan)
    lane.stop_remote_lane(plan)
    assert json.loads((control / "stop.json").read_text())["model"] == "N3"
    with pytest.raises(ContractError, match="another model"):
        lane.stop_remote_lane({**plan, "model": "F3"})


@pytest.mark.parametrize("model", ["N3", "E3", "F3"])
def test_worker_environment_forces_real_pinned_factories(model, tmp_path):
    import json

    plan = {
        "model": model, "source_root": "/source", "model_interpreter": "/pinned/bin/python",
        "policy_port": 8123, "gpu_uuid": "GPU-real",
        "runtime_environment": {"SGW01_RUNTIME_FACTORY": "fake:factory", "SGW01_SERVER_ARGV": '["fake"]'},
    }
    result = lane.worker_environment(plan, tmp_path)
    assert result["SGW01_RUNTIME_FACTORY"].endswith(".runtime:create_runtime")
    assert result["SGW01_ENV_FACTORY"].endswith(".remote_simulator_lane:create_environment")
    assert result["CUDA_VISIBLE_DEVICES"] == "GPU-real"
    command = json.loads(result["SGW01_SERVER_ARGV"])
    assert command[:2] == ["/pinned/bin/python", "-m"]
    assert ("nano_wrapper_entrypoint" in command[-1]) if model == "N3" else (command[-1] == model)
