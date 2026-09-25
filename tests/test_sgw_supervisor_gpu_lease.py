"""CPU lock tests; no cluster or physical GPU access."""
import fcntl

import pytest

from experiments.workshops.spatial_grounding_v1 import study_supervisor as supervisor


def test_block_supervisor_holds_cross_cohort_uuid_lock_for_entire_lifetime(tmp_path, monkeypatch):
    monkeypatch.setattr(supervisor, "PHYSICAL_GPU_LOCK_ROOT", tmp_path)
    plan = {"scheduling_mode": "six-cell-block-v1", "gpu_uuid": "GPU-test"}
    path = tmp_path / "gpu-GPU-test.lock"
    with supervisor.physical_gpu_lease(plan):
        inode = path.stat().st_ino
        with path.open("a+") as other:
            with pytest.raises(BlockingIOError):
                fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
    assert path.stat().st_ino == inode
    with path.open("a+") as other:
        fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)


def test_legacy_supervisor_lock_behavior_is_unchanged(tmp_path, monkeypatch):
    monkeypatch.setattr(supervisor, "PHYSICAL_GPU_LOCK_ROOT", tmp_path)
    with supervisor.physical_gpu_lease({"gpu_uuid": "GPU-test"}):
        assert list(tmp_path.iterdir()) == []
