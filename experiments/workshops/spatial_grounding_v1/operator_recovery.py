"""Explicit, single-use infrastructure recovery of immutable r5 pilot releases.

No hold is cleared and no old evidence is rewritten. The coordinator archives
the old hold after drain, supplies a hashed approval/launch/owner-exit inventory,
and pins an infrastructure-only source diff before enabling this path.
"""

from __future__ import annotations

from dataclasses import replace
import hashlib
import os
from pathlib import Path
import re
import subprocess
from typing import Any, Mapping

from .block_scheduling import begin_once, registration, selected_cells
from .contract import ContractError, Release, load_json, load_release, sha256_file, verify_completion_pointer

BASE = "experiments/workshops/spatial_grounding_v1/"
SOURCE_ALLOWLIST = {
    BASE + name for name in (
        "remote_simulator_lane.py", "study_lane.py", "study_supervisor.py",
        "worker.py", "block_scheduling.py", "operator_recovery.py",
    )
} | {
    "tests/" + name for name in (
        "test_sgw_remote_simulator_lane.py", "test_sgw_study_lifecycle.py",
        "test_sgw_study_lane.py", "test_sgw_block_scheduling.py",
        "test_sgw_worker.py", "test_sgw_operator_recovery.py",
    )
}
OVERLAY_FIELDS = {"source_root", "source_commit", "existing_pod_supervisor_entrypoint", "environment_binding"}
RETRY_CELL = "DIST-P01-N3-I-POS"
INTERNAL_FIELDS = {"operator_recovery", "operator_recovery_id"}


def read_reference(ref: Any) -> dict[str, Any]:
    if not isinstance(ref, Mapping) or not isinstance(ref.get("path"), str):
        raise ContractError("recovery requires an absolute hash-bound reference")
    path = Path(ref["path"])
    if not path.is_absolute() or path != path.resolve() or not path.is_file() or sha256_file(path) != ref.get("sha256"):
        raise ContractError("operator recovery reference is absent or changed")
    return load_json(path, "operator recovery reference")


def environment_reference() -> dict[str, str] | None:
    path, digest = os.environ.get("SGW01_OPERATOR_RECOVERY"), os.environ.get("SGW01_OPERATOR_RECOVERY_SHA256")
    if path is None and digest is None:
        return None
    if not path or not digest:
        raise ContractError("operator recovery environment requires both path and SHA-256")
    return {"path": path, "sha256": digest}


def _source_check(value: Mapping[str, Any]) -> None:
    old, new = value["old_source"], value["new_source"]
    root = Path(new["root"])
    if (root != Path(__file__).resolve().parents[3] or root != root.resolve() or not Path(old["root"]).is_absolute()
            or any(re.fullmatch("[0-9a-f]{40}", source.get("commit", "")) is None for source in (old, new))
            or old["commit"] == new["commit"]):
        raise ContractError("recovery requires distinct pinned old/new executable sources")
    def git(*args):
        return subprocess.check_output(["git", "-C", str(root), *args], timeout=30)
    if (git("rev-parse", "HEAD").decode().strip() != new["commit"]
            or git("status", "--porcelain")):
        raise ContractError("recovery source must be the actual clean pinned checkout")
    files = set(git("diff", "--name-only", old["commit"], new["commit"], "--").decode().splitlines())
    diff = git("diff", "--no-ext-diff", "--no-textconv", "--binary", old["commit"], new["commit"], "--")
    if (not files or not files.issubset(SOURCE_ALLOWLIST)
            or hashlib.sha256(diff).hexdigest() != value.get("source_diff_sha256")):
        raise ContractError("recovery source diff is not the hash-bound infrastructure-only allowlist")


def load_recovery(ref: Mapping[str, Any]) -> dict[str, Any]:
    value = read_reference(ref)
    if (value.get("schema") != "sgw-01-operator-recovery-v1" or value.get("status") != "approved"
            or value.get("allowed_models") != ["N3"]
            or re.fullmatch("[a-zA-Z0-9-]{1,64}", value.get("recovery_id", "")) is None):
        raise ContractError("invalid explicit N3 operator recovery approval")
    root = Path(str(value.get("cohort_root", "")))
    if not root.is_absolute() or root != root.resolve() or root.name != "study-a40-v3":
        raise ContractError("operator recovery cohort differs from r5")
    if read_reference(value.get("owner_approval_reference")).get("status") != "approved":
        raise ContractError("operator recovery lacks current hash-bound owner approval")
    hold = read_reference(value.get("prior_hold"))
    if (hold.get("schema_version") != "sgw-01-fleet-hold-v1"
            or not Path(value["prior_hold"]["path"]).is_relative_to(root)
            or Path(value["prior_hold"]["path"]) == root / "fleet-hold.json"):
        raise ContractError("recovery requires the archived original hold, never suppression of an active hold")
    launch = read_reference(value.get("prior_launch"))
    if launch.get("source_commit") != value["old_source"]["commit"]:
        raise ContractError("prior launch source differs")
    expected = {(row["start"]["path"], row["start"]["sha256"]) for row in launch["owners"]}
    owners = value.get("prior_owners", [])
    actual = {(row["start"]["path"], row["start"]["sha256"]) for row in owners}
    if not expected or actual != expected or len(actual) != len(owners):
        raise ContractError("recovery must enumerate every prior launch owner exactly once")
    for row in owners:
        start, exit_record = read_reference(row["start"]), read_reference(row["exit"])
        if (start.get("source_commit") != value["old_source"]["commit"]
                or not Path(row["start"]["path"]).is_relative_to(root)
                or exit_record.get("owned_descendants_remaining") != {}
                or type(exit_record.get("returncode")) is not int):
            raise ContractError("prior owner is not verifiably terminal and drained")
        standard = Path(row["exit"]["path"]) == Path(row["start"]["path"]).with_name("exit.json")
        if not standard and (
                exit_record.get("schema") != "sgw-01-owner-drain-v1"
                or exit_record.get("supervisor_id") != start.get("supervisor_id")
                or exit_record.get("pod_uid") != start.get("pod_uid")
                or exit_record.get("pid_exit_verified") is not True):
            raise ContractError("nonstandard owner exit requires an explicit identity-bound drain receipt")
    _source_check(value)
    overlay = value.get("overlay")
    if (not isinstance(overlay, Mapping) or set(overlay) != OVERLAY_FIELDS
            or overlay["source_root"] != value["new_source"]["root"]
            or overlay["source_commit"] != value["new_source"]["commit"]):
        raise ContractError("recovery overlay can change only source/supervisor/environment identities")
    entry = overlay["existing_pod_supervisor_entrypoint"]
    if (not isinstance(entry, Mapping)
            or entry.get("path") != str(Path(value["new_source"]["root"]) / BASE / "study_supervisor.py")
            or sha256_file(Path(entry["path"])) != entry.get("sha256")):
        raise ContractError("recovery supervisor entrypoint differs from the new source")
    releases = value.get("releases")
    if (not isinstance(releases, list) or not releases
            or len({row["release_id"] for row in releases}) != len(releases)):
        raise ContractError("recovery must enumerate unique immutable pilot releases")
    prior_paths = {str(path) for path in root.glob("release-r5-N3-*-P")}
    if {row["path"] for row in releases} != prior_paths:
        raise ContractError("recovery must cover every existing r5 pilot release")
    for record in releases:
        original = load_release(Path(record["path"]))
        if (dict(original.hashes) != record["hashes"] or original.release_id != record["release_id"]
                or original.binding["source_commit"] != value["old_source"]["commit"]
                or {(cell.model, cell.stage) for cell in original.cells} != {("N3", "P")}
                or len(record["blocks"]) != 1
                or record["blocks"][0]["block_id"] != original.cells[0].block_id
                or len(record["blocks"][0]["cells"]) != 6
                or {row["cell_id"] for row in record["blocks"][0]["cells"]} != {cell.cell_id for cell in original.cells}):
            raise ContractError("retained pilot release identity changed")
        for block in record["blocks"]:
            execution_path = root / f"operator-recoveries/{value['recovery_id']}/execution/{block['block_id']}.json"
            execution = load_json(execution_path, "recovery execution") if execution_path.exists() else None
            active = execution is not None and execution.get("operator_recovery") == {
                "path": ref["path"], "sha256": ref["sha256"],
            }
            for cell in block["cells"]:
                directory = root / "attempts" / cell["cell_id"]
                expected = {f"attempt-{i:03d}" for i in range(1, len(cell["attempts"]) + 1)}
                allowed = expected | ({f"attempt-{cell['next_attempt']:03d}"}
                                      if active and type(cell["next_attempt"]) is int else set())
                actual = {p.name for p in directory.iterdir()} if directory.exists() else set()
                if not expected.issubset(actual) or not actual.issubset(allowed):
                    raise ContractError("prior attempt inventory is incomplete or contains an unapproved attempt")
                for attempt in cell["attempts"]:
                    manifest = read_reference(attempt["manifest"])
                    if (manifest.get("complete") is not True or manifest.get("release_hashes") != record["hashes"]
                            or manifest.get("cell_id") != cell["cell_id"]
                            or manifest.get("result", {}).get("status") not in {
                                "valid_success", "valid_model_failure", "censored", "technical_invalid"}):
                        raise ContractError("all retained prior attempts must be terminal and enumerated")
                if cell["completion"] is not None:
                    read_reference(cell["completion"])
    return value


def effective_release(release: Release, ref: Mapping[str, Any] | None = None) -> Release:
    ref = ref if ref is not None else environment_reference()
    if ref is None:
        return release
    ref = {"path": ref["path"], "sha256": ref["sha256"]}
    value = load_recovery(ref)
    if release.root.parent != Path(value["cohort_root"]):
        raise ContractError("operator recovery cannot cross cohorts")
    record = next((row for row in value["releases"] if row["release_id"] == release.release_id), None)
    if record is None:
        if release.binding["source_commit"] != value["new_source"]["commit"]:
            raise ContractError("old release is not enumerated in operator recovery")
        return release
    original = load_release(release.root)
    if (record["path"] != str(original.root) or record["hashes"] != dict(original.hashes)
            or original.binding["source_root"] != value["old_source"]["root"]
            or original.binding["source_commit"] != value["old_source"]["commit"]
            or {(cell.model, cell.stage) for cell in original.cells} != {("N3", "P")}):
        raise ContractError("operator recovery must retain the exact old N3 pilot release")
    registration(original.binding, model="N3", cohort=original.root.parent,
                 protocol_sha256=original.hashes["protocol.json"], prompts_sha256=original.hashes["prompts.json"])
    if (len(record["blocks"]) != len({cell.block_id for cell in original.cells})
            or {row["block_id"] for row in record["blocks"]} != {cell.block_id for cell in original.cells}):
        raise ContractError("recovery must enumerate the exact released blocks")
    old_environment = read_reference(original.binding.get("environment_binding"))
    new_environment = read_reference(value["overlay"]["environment_binding"])
    if (new_environment.get("source_root") != value["new_source"]["root"]
            or new_environment.get("source_commit") != value["new_source"]["commit"]
            or {k: v for k, v in old_environment.items() if k not in {"source_root", "source_commit"}}
            != {k: v for k, v in new_environment.items() if k not in {"source_root", "source_commit"}}):
        raise ContractError("recovery environment changed scientific or asset bindings")
    return replace(original, binding={
        **original.binding, **value["overlay"], "operator_recovery": dict(ref),
        "operator_recovery_id": value["recovery_id"],
    })


def block_record(release: Release, block_id: str) -> Mapping[str, Any] | None:
    ref = release.binding.get("operator_recovery")
    if ref is None:
        return None
    value = read_reference(ref)
    record = next(row for row in value["releases"] if row["release_id"] == release.release_id)
    return next(row for row in record["blocks"] if row["block_id"] == block_id)


def claim_area(release: Release, phase: str) -> str:
    return f"operator-recoveries/{release.binding['operator_recovery_id']}/{phase}"


def _manifest(reference: Mapping[str, Any], release: Release, cell_id: str, attempt: int) -> Mapping[str, Any]:
    path = release.root.parent / "attempts" / cell_id / f"attempt-{attempt:03d}" / "manifest.json"
    manifest = read_reference(reference)
    if (reference["path"] != str(path) or manifest.get("complete") is not True
            or manifest.get("release_id") != release.release_id or manifest.get("cell_id") != cell_id
            or manifest.get("attempt_id") != f"attempt-{attempt:03d}"
            or manifest.get("release_hashes") != dict(release.hashes)):
        raise ContractError("prior attempt is nonterminal or differs from its immutable release")
    for relative, record in manifest["artifacts"].items():
        artifact = path.parent / relative
        if (not artifact.resolve().is_relative_to(path.parent) or not artifact.is_file()
                or artifact.stat().st_size != record["bytes"] or sha256_file(artifact) != record["sha256"]):
            raise ContractError("retained attempt artifact changed")
    if manifest["result"] != load_json(path.with_name("result.json"), "prior result"):
        raise ContractError("retained attempt result changed")
    return manifest


def validate_block_start(release: Release, block_id: str) -> Mapping[str, Any]:
    record = block_record(release, block_id)
    if record is None:
        raise ContractError("block has no explicit operator recovery")
    first = release.cells[0]
    cells = selected_cells(release, first.model, first.family, first.stage, block_id)
    if (len(record["cells"]) != 6 or {row["cell_id"] for row in record["cells"]} != {c.cell_id for c in cells}):
        raise ContractError("recovery must enumerate all six frozen cells")
    for name, directory in (("dispatch", "block-claims"), ("execution", "block-executions")):
        path = release.root.parent / directory / f"{block_id}.json"
        reference = record["claims"][name]
        if reference is None:
            if path.exists():
                raise ContractError("unregistered prior block claim/execution")
        else:
            prior = read_reference(reference)
            if (reference.get("path") != str(path) or prior.get("block_id") != block_id
                    or prior.get("release_id") != release.release_id):
                raise ContractError("retained block claim/execution changed")
    for row in record["cells"]:
        cell_id = row["cell_id"]
        if row["next_attempt"] is not None and (type(row["next_attempt"]) is not int or not 1 <= row["next_attempt"] <= 3):
            raise ContractError("recovery next attempt must be an exact integer within the frozen ceiling")
        directory = release.root.parent / "attempts" / cell_id
        expected = {f"attempt-{number:03d}" for number in range(1, len(row["attempts"]) + 1)}
        actual = {path.name for path in directory.iterdir()} if directory.exists() else set()
        if actual != expected:
            raise ContractError("unapproved, partial, or extra prior attempt; no automatic replay")
        manifests = [_manifest(item["manifest"], release, cell_id, number)
                     for number, item in enumerate(row["attempts"], 1)]
        pointer = release.root.parent / "cells" / f"{cell_id}.complete.json"
        if row["completion"] is not None:
            if row["completion"]["path"] != str(pointer) or row["next_attempt"] is not None:
                raise ContractError("completed cells cannot receive another attempt")
            read_reference(row["completion"])
            completed = verify_completion_pointer(release, pointer)
            if (len(manifests) != 1 or completed.get("attempt_id") != "attempt-001"
                    or manifests[0]["result"]["status"] not in {"valid_success", "valid_model_failure", "censored"}):
                raise ContractError("completed recovery cell does not match its retained attempt")
        else:
            if pointer.exists():
                raise ContractError("recovery cannot replay an already completed cell")
            if not manifests:
                if row["next_attempt"] != 1:
                    raise ContractError("untouched cell must start at attempt001")
            else:
                if (cell_id != RETRY_CELL or len(manifests) != 1 or row["next_attempt"] != 2
                        or manifests[0]["result"]["status"] != "technical_invalid"):
                    raise ContractError("only the explicit DIST startup-invalid attempt002 is authorized")
                request_index = directory / "attempt-001" / "request_index.jsonl"
                actions = directory / "attempt-001" / "actions"
                if ((request_index.exists() and request_index.read_bytes().strip())
                        or (actions.exists() and any(actions.rglob("*")))
                        or manifests[0]["result"].get("executed_action_count", 0) != 0):
                    raise ContractError("DIST retry requires zero recorded requests and zero actions")
    return record


def begin_recovery(release: Release, block_id: str, phase: str, **owner: Any) -> None:
    validate_block_start(release, block_id)
    begin_once(release.root.parent, claim_area(release, phase), block_id,
               release_id=release.release_id, release_hashes=dict(release.hashes),
               operator_recovery=release.binding["operator_recovery"],
               execution_source={"root": release.binding["source_root"], "commit": release.binding["source_commit"]},
               **owner)


def expected_attempt(release: Release, block_id: str, cell_id: str) -> int | None:
    record = block_record(release, block_id)
    if record is None:
        return None
    return next(row["next_attempt"] for row in record["cells"] if row["cell_id"] == cell_id)


def execution_identity(release: Release) -> dict[str, Any]:
    return {
        "operator_recovery": release.binding["operator_recovery"],
        "source_root": release.binding["source_root"], "source_commit": release.binding["source_commit"],
        "environment_binding": release.binding["environment_binding"],
        "existing_pod_supervisor_entrypoint": release.binding["existing_pod_supervisor_entrypoint"],
        "immutable_release_id": release.release_id, "immutable_release_hashes": dict(release.hashes),
    }


def main() -> None:
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Read-only operator recovery validation; never clears a hold.")
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--sha256", required=True)
    args = parser.parse_args()
    ref = {"path": str(args.receipt), "sha256": args.sha256}
    value = load_recovery(ref)
    checked = []
    for record in value["releases"]:
        release = effective_release(load_release(Path(record["path"])), ref)
        for block in record["blocks"]:
            validate_block_start(release, block["block_id"])
            checked.append(block["block_id"])
    print(json.dumps({"status": "validated_only_no_launch", "recovery_id": value["recovery_id"], "blocks": checked}))


if __name__ == "__main__":
    main()
