"""CPU-only checks for exact queue partitioning and inert Job export."""
import copy
import json

import pytest

from tools.prepare_cluster_handoff import ENTRYPOINT, disabled_job, prepare_partitions, write_handoff


def test_partition_export_keeps_every_frozen_cell_and_matched_block_once():
    value = prepare_partitions()
    assert value["stage_cell_counts"] == {"P": 36, "D": 144, "C": 864}
    assert value["partition_count"] == 18
    cells = [c for p in value["partitions"] for b in p["blocks"] for c in b["cells"]]
    assert len(cells) == len({c["cell_id"] for c in cells}) == 1044
    for partition in value["partitions"]:
        assert partition["episode_count"] == {"P": 6, "D": 24, "C": 144}[partition["stage"]]
        for block in partition["blocks"]:
            assert len(block["cells"]) == 6
            assert [int(c["within_block_order"]) for c in block["cells"]] == list(range(1, 7))
            assert len({c["environment_seed"] for c in block["cells"]}) == 1
    assert not value["learned_policy_launch_authorized"]
    assert value["release_namespace_policy"]["new_release_namespace_required"]
    assert not value["release_namespace_policy"]["reuse_other_cohort_completion_pointers"]
    assert not value["release_namespace_policy"]["release_created"]


def example_job():
    # Test-only concrete values. No example Job is written into the handoff.
    return {"apiVersion": "batch/v1", "kind": "Job", "metadata": {"name": "test-only", "namespace": "test-only"},
            "spec": {"activeDeadlineSeconds": 3600, "template": {"spec": {"restartPolicy": "Never",
            "containers": [{"name": "worker", "image": "registry.invalid/test@sha256:" + "a" * 64,
                            "workingDir": "/source", "command": ["/env/bin/python", "-m", ENTRYPOINT],
                            "args": ["--release", "/data/release", "--model", "N3", "--family", "LAT", "--stage", "P",
                                     "--max-valid-episodes", "6", "--max-cell-attempts", "3"],
                            "volumeMounts": [{"name": "study", "mountPath": "/data"}],
                            "resources": {"limits": {"nvidia.com/gpu": 1}}}],
            "volumes": [{"name": "study", "persistentVolumeClaim": {"claimName": "test-only"}}]}}}}


def test_job_export_cannot_create_pods_and_does_not_invent_resources():
    original = example_job()
    before = copy.deepcopy(original)
    result, identity = disabled_job(original, prepare_partitions())
    assert original == before
    assert identity == "N3-LAT-P"
    assert result["spec"]["suspend"] is True
    assert result["spec"]["parallelism"] == 0
    assert result["spec"]["template"] == before["spec"]["template"]


@pytest.mark.parametrize("case", ["legacy", "partial_block", "placeholder", "missing_pvc", "missing_deadline"])
def test_job_export_refuses_incompatible_or_incomplete_runtime(case):
    job = example_job()
    worker = job["spec"]["template"]["spec"]["containers"][0]
    if case == "legacy":
        worker["command"][-1] = "experiments.workshops.spatial_grounding_v1.worker"
    elif case == "partial_block":
        worker["args"][worker["args"].index("--max-valid-episodes") + 1] = "1"
    elif case == "placeholder":
        worker["image"] = "${IMAGE}"
    elif case == "missing_pvc":
        job["spec"]["template"]["spec"]["volumes"] = []
    else:
        del job["spec"]["activeDeadlineSeconds"]
    with pytest.raises(ValueError):
        disabled_job(job, prepare_partitions())


def test_default_export_has_no_job_or_launch_command_and_preserves_existing_output(tmp_path):
    target = tmp_path / "handoff"
    summary = write_handoff(target)
    assert not summary["suspended_job_generated"]
    assert {p.name for p in target.iterdir()} == {"partitions.json", "preparation.json"}
    assert json.loads((target / "partitions.json").read_text())["status"] == "PLANNING_ONLY_NO_LAUNCH_AUTHORIZED"
    with pytest.raises(FileExistsError):
        write_handoff(target)
