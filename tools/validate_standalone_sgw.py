"""Read-only SGW planning/import checks; no model, simulator, or network calls."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import importlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "experiments/workshops/spatial_grounding_v1/spec"
CORE_MODULES = (
    "contract", "scoring", "adapters", "recorder", "compile", "fixtures",
    "scene_design", "prospective_family_scene", "policy_observations",
    "producer", "nano_backend", "runtime", "worker",
    "simulator_mailbox", "native_worker_entrypoint",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_launch_instruction(status: dict, expected: dict, root: Path = ROOT) -> bool:
    authorized = status.get("learned_policy_launch_authorized")
    if authorized is False:
        return False
    require(authorized is True, "Launch authorization must be an explicit boolean")
    reference = status.get("learned_policy_authorization_receipt")
    require(isinstance(reference, dict) and isinstance(reference.get("path"), str),
            "Current launch instruction must have a hash-bound receipt")
    path = (root / reference["path"]).resolve()
    require(path.is_relative_to(root.resolve()) and path.is_file(),
            "Current launch instruction receipt is unavailable")
    require(hashlib.sha256(path.read_bytes()).hexdigest() == reference.get("sha256"),
            "Current launch instruction receipt hash differs")
    instruction = json.loads(path.read_text())
    constraints = instruction.get("constraints", {})
    require(instruction.get("schema_version") == "sgw-current-launch-instruction-v1"
            and instruction.get("status") == "approved"
            and instruction.get("authorization_source") == "current_user_instruction"
            and isinstance(instruction.get("owner_approval_reference"), dict)
            and instruction.get("source_queue_sha256") == expected["planned_cells.csv"]
            and instruction.get("source_protocol_sha256") == expected["protocol.json"]
            and instruction.get("scope", {}).get("models") == ["N3", "E3", "F3"]
            and instruction.get("scope", {}).get("maximum_registered_behavioral_episodes") == 1566
            and constraints.get("runtime_qualification_required") is True
            and constraints.get("existing_release_and_worker_gates_required") is True
            and constraints.get("fresh_idle_allocation_check_required") is True
            and constraints.get("new_paid_capacity_allowed") is False
            and constraints.get("preempt_or_stop_unowned_workloads_allowed") is False,
            "Current launch instruction does not cover this frozen, guarded study")
    return True


def validate(check_imports: bool = False) -> dict:
    expected = json.loads((SPEC / "registry_validation.json").read_text())["files"]
    for name, digest in expected.items():
        require(hashlib.sha256((SPEC / name).read_bytes()).hexdigest() == digest,
                f"Frozen registry hash differs: {name}")
    prompts = json.loads((SPEC / "prompts.json").read_text())["prompts"]
    protocol = json.loads((SPEC / "protocol.json").read_text())
    with (SPEC / "planned_cells.csv").open(newline="") as stream:
        cells = list(csv.DictReader(stream))
    require(len(prompts) == 18 and len({p["prompt_id"] for p in prompts}) == 18,
            "Expected 18 unique frozen prompts")
    require(len(cells) == 1566 and len({c["cell_id"] for c in cells}) == 1566,
            "Expected 1,566 unique planned cells")
    require(Counter(c["stage"] for c in cells) == {"P": 54, "D": 216, "C": 1296},
            "Frozen stage totals differ")
    require(set(c["status"] for c in cells) == {"PLANNED_NOT_RELEASED"},
            "Planning registry must not claim runtime release")
    lookup = {p["prompt_id"]: p for p in prompts}
    blocks: dict[str, list] = defaultdict(list)
    for cell in cells:
        prompt = lookup[cell["prompt_id"]]
        require(cell["prompt"] == prompt["text"] and cell["prompt_sha256"] == prompt["sha256"]
                == hashlib.sha256(cell["prompt"].encode()).hexdigest(),
                f"Prompt binding differs: {cell['cell_id']}")
        require(int(cell["action_cap"]) == 450, "Frozen action cap differs")
        blocks[cell["block_id"]].append(cell)
    require(len(blocks) == 261 and all(len(b) == 6 for b in blocks.values()),
            "Expected 261 six-cell blocks")
    require(protocol["episodes"]["total"] == 1566, "Protocol episode total differs")
    for block in blocks.values():
        require({int(c["within_block_order"]) for c in block} == set(range(1, 7)),
                "Matched block order differs")
        require({(c["form"], int(c["physical_goal_sign"])) for c in block}
                == {(f, sign) for f in ("D", "C", "I") for sign in (1, -1)},
                "Matched block conditions differ")
    status = json.loads((ROOT / "REPOSITORY_STATUS.json").read_text())
    authorized = validate_launch_instruction(status, expected)
    imported = []
    if check_imports:
        sys.path.insert(0, str(ROOT))
        for name in CORE_MODULES:
            module = importlib.import_module(f"experiments.workshops.spatial_grounding_v1.{name}")
            require(Path(module.__file__).resolve().is_relative_to(ROOT),
                    f"Imported {name} from outside this checkout")
            imported.append(name)
    return {
        "status": "portable_planning_checks_passed_not_runtime_release",
        "prompts": len(prompts), "planned_cells": len(cells), "matched_blocks": len(blocks),
        "stage_counts": dict(Counter(c["stage"] for c in cells)),
        "imported_modules": imported, "model_requests": 0, "simulator_trials": 0,
        "learned_policy_launch_authorized": authorized,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-imports", action="store_true")
    args = parser.parse_args()
    print(json.dumps(validate(args.check_imports), indent=2))
