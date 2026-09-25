"""Opt-in r5 block claims; immutable releases remain whole family partitions.

The coordinator supplies a hash-bound ``block_registration`` in the binding.
It must register scheduling_mode, allowed_models, cohort_root, release_revision,
protocol_sha256, prompts_sha256, source_queue_sha256, stage_barrier and
technical_invalid_threshold with the values checked below. Plans repeat the
mode and allowed_models. The new protocol and binding also share protocol_runtime:
camera_configuration is the revision/SHA-256 identity, policy_input_revision is
the registered input revision string. This supplies no launch/qualification authority.
"""

from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Any, Mapping

from .contract import Cell, ContractError, Release, canonical_bytes, load_json, partition_blocks, sha256_file
from .recorder import _fsync_directory, request_fleet_hold, utc_now

MODE = "six-cell-block-v1"
QUEUE_SHA256 = "07a2bd6c1893e7662db0c12c01843c20d743bfeb4cb1b506f238a37ae19e068a"
SPEC = Path(__file__).parent / "spec"


def protocol_runtime(binding: Mapping[str, Any]) -> Mapping[str, Any]:
    value = binding.get("protocol_runtime")
    if not isinstance(value, Mapping) or set(value) != {"camera_configuration", "policy_input_revision"}:
        raise ContractError("block mode requires explicit protocol_runtime camera/input identities")
    camera = value["camera_configuration"]
    if (not isinstance(camera, Mapping) or set(camera) != {"revision", "sha256"}
            or not isinstance(camera["revision"], str) or not camera["revision"].strip()
            or not isinstance(camera["sha256"], str) or len(camera["sha256"]) != 64
            or any(c not in "0123456789abcdef" for c in camera["sha256"])
            or not isinstance(value["policy_input_revision"], str) or not value["policy_input_revision"].strip()):
        raise ContractError("protocol_runtime requires a hashed camera identity and explicit input revision")
    return value


def registration(binding: Mapping[str, Any], *, model: str | None = None,
                 cohort: Path | None = None, protocol_sha256: str | None = None,
                 prompts_sha256: str | None = None) -> dict[str, Any] | None:
    if "scheduling_mode" not in binding:
        if "block_registration" in binding:
            raise ContractError("block registration requires explicit scheduling_mode")
        return None
    if binding["scheduling_mode"] != MODE:
        raise ContractError("unknown scheduling_mode")
    protocol_runtime(binding)
    ref = binding.get("block_registration")
    if not isinstance(ref, Mapping) or not isinstance(ref.get("path"), str):
        raise ContractError("block mode requires a hash-bound prospective registration")
    path = Path(ref["path"])
    if not path.is_absolute() or not path.is_file() or sha256_file(path) != ref.get("sha256"):
        raise ContractError("block registration is absent or changed")
    value = load_json(path, "block registration")
    expected = {
        "schema": "sgw-01-block-scheduling-registration-v1", "status": "registered",
        "scheduling_mode": MODE, "release_revision": "r5", "allowed_models": ["N3"],
        "source_queue_sha256": QUEUE_SHA256, "stage_barrier": "per_model",
        "technical_invalid_threshold": 1, "action_cap": 450,
    }
    if any(value.get(key) != item for key, item in expected.items()):
        raise ContractError("block registration must explicitly register r5, N3-only and N=1")
    if (binding.get("allowed_models") != ["N3"] or (model is not None and model != "N3")
            or binding.get("allow_parallel_existing_pod_lanes") is not True
            or binding.get("allow_operational_receipt_refresh") is not True
            or binding.get("hold_on_technical_invalid") is not True):
        raise ContractError("block mode requires N3-only, parallel Pod admission and first-fault hold")
    root = Path(str(value.get("cohort_root", "")))
    if (not root.is_absolute() or str(root) != value.get("cohort_root") or root != root.resolve()
            or root.name != "study-a40-v3" or str(root) != binding.get("persistent_study_root")
            or (cohort is not None and root != cohort.resolve())):
        raise ContractError("block mode requires its separately registered study-a40-v3 cohort")
    protocol_hash = value.get("protocol_sha256")
    if (not isinstance(protocol_hash, str) or len(protocol_hash) != 64
            or any(c not in "0123456789abcdef" for c in protocol_hash)
            or protocol_hash == sha256_file(SPEC / "protocol.json")
            or (protocol_sha256 is not None and protocol_hash != protocol_sha256)
            or value.get("prompts_sha256") != sha256_file(SPEC / "prompts.json")
            or (prompts_sha256 is not None and value["prompts_sha256"] != prompts_sha256)):
        raise ContractError("block registration requires a new protocol and unchanged frozen prompts")
    return value


def frozen_blocks(cells: tuple[Cell, ...]) -> dict[str, tuple[Cell, ...]]:
    """Validate every condition against the unchanged queue, not just its count."""
    path = SPEC / "planned_cells.csv"
    if sha256_file(path) != QUEUE_SHA256:
        raise ContractError("frozen planned queue changed")
    with path.open(newline="", encoding="utf-8") as stream:
        frozen = {row["cell_id"]: row for row in csv.DictReader(stream)}
    ignored = {"status", "fixture_sha256", "runtime_sha256", "time_map_sha256"}
    for cell in cells:
        row = frozen.get(cell.cell_id)
        if row is None or any(str(cell.row.get(key)) != value for key, value in row.items() if key not in ignored):
            raise ContractError("block condition differs from the frozen planned queue")
    blocks = partition_blocks(cells)
    for block in blocks.values():
        if (len({cell.cell_id for cell in block}) != 6
                or {int(cell.row["within_block_order"]) for cell in block} != set(range(1, 7))
                or {(cell.row["form"], int(cell.row["physical_goal_sign"])) for cell in block}
                != {(form, sign) for form in ("D", "C", "I") for sign in (-1, 1)}
                or len({cell.row["layout_id"] for cell in block}) != 1):
            raise ContractError("block requires six unique frozen layout conditions")
    return blocks


def selected_cells(release: Release, model: str, family: str, stage: str,
                   block_id: str | None) -> tuple[Cell, ...]:
    registered = registration(release.binding, model=model, cohort=release.root.parent,
                              protocol_sha256=release.hashes["protocol.json"],
                              prompts_sha256=release.hashes["prompts.json"])
    cells = release.partition(model, family, stage)
    if registered is None:
        if block_id is not None:
            raise ContractError("block selection requires prospective registration")
        return cells
    blocks = frozen_blocks(cells)
    if block_id not in blocks:
        raise ContractError("registered block mode requires one exact whole block_id")
    return blocks[block_id]


def begin_once(root: Path, area: str, block_id: str, **details: Any) -> Path:
    """A process lock expiring is not permission to replay a crashed claim."""
    path = root / area / f"{block_id}.json"
    if path.parent != path.parent.resolve():
        raise ContractError("block claim directory must remain canonical")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(canonical_bytes({
                "schema": "sgw-01-block-claim-v1", "block_id": block_id,
                "started_at_utc": utc_now(), **details,
            }))
            stream.flush()
            os.fsync(stream.fileno())
        _fsync_directory(path.parent)
    except FileExistsError as exc:
        request_fleet_hold(root, block_id=block_id, reason=f"existing {area}; no automatic replay")
        raise ContractError("previous block claim preserved; no automatic replay") from exc
    return path
