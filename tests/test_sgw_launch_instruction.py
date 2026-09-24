import hashlib
import json
from pathlib import Path

import pytest

from tools.validate_standalone_sgw import validate_launch_instruction


RECEIPT = Path("handoff/cluster-execution-20260924/launch-instruction.json")
EXPECTED = json.loads(Path("experiments/workshops/spatial_grounding_v1/spec/registry_validation.json").read_text())["files"]


def test_preparation_permission_does_not_grant_launch():
    assert validate_launch_instruction({"learned_policy_launch_authorized": False}, EXPECTED) is False


def test_launch_requires_current_hash_bound_instruction(tmp_path):
    with pytest.raises(ValueError, match="hash-bound"):
        validate_launch_instruction({"learned_policy_launch_authorized": True}, EXPECTED, tmp_path)


@pytest.mark.parametrize("mutation", ["none", "changed_bytes", "old_queue", "historical", "weakened_gate"])
def test_current_instruction_is_not_runtime_qualification(tmp_path, mutation):
    value = json.loads(RECEIPT.read_text())
    if mutation == "old_queue":
        value["source_queue_sha256"] = "old"
    if mutation == "historical":
        value["authorization_source"] = "copied_historical_authorization"
    if mutation == "weakened_gate":
        value["constraints"]["runtime_qualification_required"] = False
    path = tmp_path / "instruction.json"
    path.write_text(json.dumps(value))
    status = {"learned_policy_launch_authorized": True, "learned_policy_authorization_receipt": {
        "path": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }}
    if mutation == "changed_bytes":
        path.write_text("{}")
    if mutation == "none":
        assert validate_launch_instruction(status, EXPECTED, tmp_path) is True
        assert value["runtime_qualification_claimed"] is False
        assert value["release_created"] is False
    else:
        with pytest.raises(ValueError, match="instruction"):
            validate_launch_instruction(status, EXPECTED, tmp_path)
