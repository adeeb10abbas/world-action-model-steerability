import json

import pytest

from experiments.workshops.spatial_grounding_v1 import gpu_idle_probe
from experiments.workshops.spatial_grounding_v1.gpu_idle_probe import select_idle


def gpu(index, used=100, utilization=0):
    return {"index": index, "uuid": f"gpu-{index}", "memory_used_mib": used,
            "memory_free_mib": 97000 - used, "utilization_percent": utilization}


def test_choose_only_idle_allocated_gpu():
    values = [gpu(0, 94000), gpu(1), gpu(2), gpu(3, utilization=100)]
    assert select_idle(values, {"gpu-1"}, 4)["uuid"] == "gpu-2"


def test_no_idle_gpu_blocks():
    with pytest.raises(RuntimeError, match="No allocated GPU"):
        select_idle([gpu(0, 94000)], set(), 1)


def test_allocation_mismatch_blocks():
    with pytest.raises(ValueError, match="count differs"):
        select_idle([gpu(0), gpu(1)], set(), 1)


@pytest.mark.parametrize("name", ["NVIDIA A100-SXM4-40GB", "Tesla V100-SXM2-32GB", "NVIDIA B200", None])
def test_idle_is_not_sufficient_when_qualified_hardware_is_bound(name):
    with pytest.raises(RuntimeError, match="qualified runtime hardware"):
        select_idle([{**gpu(0), "name": name}], set(), 1,
                    expected_name="NVIDIA A100-SXM4-80GB")


@pytest.mark.parametrize("name", ["NVIDIA A100-SXM4-80GB", "NVIDIA A40"])
def test_exact_policy_or_graphics_type_can_be_bound(name):
    value = {**gpu(0), "name": name}
    assert select_idle([value], set(), 1, expected_name=name) == value


def test_empty_expected_gpu_name_is_not_a_silent_opt_out():
    with pytest.raises(ValueError, match="non-empty"):
        select_idle([gpu(0)], set(), 1, expected_name="")


def test_cli_preserves_wrong_hardware_receipt_without_selecting_device(tmp_path, monkeypatch, capsys):
    output = tmp_path / "idle.json"
    values = iter(["0, GPU-test, NVIDIA A100-SXM4-40GB, 0, 40000, 0\n", ""])
    monkeypatch.setattr(gpu_idle_probe.subprocess, "check_output", lambda *_args, **_kwargs: next(values))
    monkeypatch.setattr("sys.argv", [
        "gpu_idle_probe", "--expected-count", "1", "--expected-name", "NVIDIA A100-SXM4-80GB",
        "--output", str(output),
    ])
    with pytest.raises(RuntimeError, match="qualified runtime hardware"):
        gpu_idle_probe.main()
    receipt = json.loads(output.read_text())
    assert receipt["status"] == "blocked"
    assert receipt["expected_gpu_name"] == "NVIDIA A100-SXM4-80GB"
    assert receipt["model_requests"] == 0
    assert "selected_gpu" not in receipt
    assert not capsys.readouterr().out
