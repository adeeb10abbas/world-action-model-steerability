"""CPU-only identity/protocol tests; no native environment or model is loaded."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

import numpy as np
import pytest

from experiments.workshops.spatial_grounding_v1 import native_mailbox_receiver as native
from experiments.workshops.spatial_grounding_v1 import simulator_mailbox as mailbox
from experiments.workshops.spatial_grounding_v1 import worker
from experiments.workshops.spatial_grounding_v1.adapters import AdapterError
from experiments.workshops.spatial_grounding_v1.robolab_jointpos_environment import JointPositionBinding
from tests.test_sgw_simulator_mailbox import FakeEnvironment


@pytest.fixture
def bare_sim(tmp_path, monkeypatch):
    pod_uid = "00000000-0000-4000-8000-000000000010"
    gpu_uuid = "GPU-00000000-0000-4000-8000-000000000020"
    binding_path = tmp_path / "binding.json"
    mailbox._write(binding_path, {"source_commit": "a" * 40})
    entry = tmp_path / "supervisor.py"
    entry.write_text("# CPU fixture only\n")
    entry_ref = {"path": str(entry), "sha256": mailbox._digest(entry)}
    now = datetime.now(timezone.utc)
    supervisor = {
        "schema": "sgw-01-existing-pod-supervisor-v1", "role": "simulator",
        "pod_name": "a40e", "pod_uid": pod_uid, "gpu_uuid": gpu_uuid, "source_commit": "a" * 40,
        "entrypoint": entry_ref, "started_at_utc": now.isoformat(), "deadline_seconds": 3600,
        "deadline_utc": (now + timedelta(seconds=3600)).isoformat(),
    }
    start = tmp_path / "start.json"
    mailbox._write(start, supervisor)
    identity = {
        "identity_schema": mailbox.POD_IDENTITY_SCHEMA, "release_id": "release", "cell_id": "cell",
        "attempt_id": "attempt", "channel_nonce": "1" * 32, "candidate_sha256": "b" * 64,
        "binding_sha256": mailbox._digest(binding_path), "simulator_owner_kind": "Pod",
        "simulator_pod_name": "a40e", "simulator_pod_uid": pod_uid, "simulator_gpu_uuid": gpu_uuid,
        "simulator_renderer_gpu_index": 0, "simulator_multi_gpu": False,
        "simulator_job_uid": None, "simulator_job_name": None,
        "simulator_supervisor_identity_receipt": {"path": str(start), "sha256": mailbox._digest(start)},
        "simulator_supervisor_entrypoint": entry_ref,
    }
    cell = {"cell_id": "cell", "status": "RELEASED", "candidate_sha256": identity["candidate_sha256"],
            "binding_sha256": identity["binding_sha256"]}
    calls = []

    def checked_cell(row):
        if row["status"] != "RELEASED":
            raise AdapterError("cell has no released joint-position environment binding")
        calls.append(("cell", row))
        return {"candidate_file_sha256": "b" * 64}, None

    def supervisor_check(reference, *, source_commit, entrypoint, environ=None):
        # The shared verifier's real source/kernel checks have separate CPU
        # tests. This boundary retains real hash reads and records propagation.
        value = worker._receipt(reference, "synthetic simulator supervisor")
        assert source_commit == "a" * 40 and entrypoint == entry_ref
        calls.append(("supervisor", reference))
        return value

    monkeypatch.setattr(JointPositionBinding, "load",
                        classmethod(lambda cls: SimpleNamespace(cell=checked_cell)))
    monkeypatch.setattr(worker, "verify_existing_pod_supervisor", supervisor_check)
    monkeypatch.setenv("SGW01_ENV_BINDING", str(binding_path))
    monkeypatch.setenv("SGW01_ENV_BINDING_SHA256", identity["binding_sha256"])
    monkeypatch.setenv("POD_UID", pod_uid)
    monkeypatch.setenv("POD_NAME", "a40e")
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", gpu_uuid)
    monkeypatch.setenv("SGW01_SIMULATOR_DEVICE", "cuda:0")
    monkeypatch.delenv("JOB_UID", raising=False)
    monkeypatch.delenv("JOB_NAME", raising=False)
    return SimpleNamespace(root=tmp_path, identity=identity, cell=cell, supervisor=supervisor, calls=calls, start=start)


def test_pod_identity_normalizes_null_jobs_without_fabricating_them(bare_sim):
    path = bare_sim.root / "identity.json"
    mailbox._write(path, bare_sim.identity)
    identity = native._load_identity(path, mailbox._digest(path))
    assert "simulator_job_uid" not in identity and "simulator_job_name" not in identity
    expiry = native._verify_native_authority(bare_sim.cell, identity)
    assert expiry > time.time()
    assert [key for key, _ in bare_sim.calls] == ["cell", "supervisor"]
    assert mailbox._read(path)["simulator_job_uid"] is None


def test_legacy_job_guard_cannot_reuse_pod_uid_as_job_uid(monkeypatch):
    uid = "00000000-0000-4000-8000-000000000001"
    monkeypatch.setenv("JOB_UID", uid)
    monkeypatch.setenv("POD_UID", uid)
    with pytest.raises(AdapterError, match="Downward API"):
        native._verify_native_authority({}, {"simulator_job_uid": uid, "simulator_pod_uid": uid})


@pytest.mark.parametrize("fault", ["job", "name", "pod", "gpu", "schema", "missing-supervisor", "hash", "unreleased", "role"])
def test_bare_native_authority_rejects_identity_or_supervisor_substitution(bare_sim, monkeypatch, fault):
    identity = dict(bare_sim.identity)
    if fault == "job": identity["simulator_job_uid"] = identity["simulator_pod_uid"]
    elif fault == "name": monkeypatch.setenv("POD_NAME", "a40f")
    elif fault == "pod": monkeypatch.setenv("POD_UID", "00000000-0000-4000-8000-000000000099")
    elif fault == "gpu": monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0")
    elif fault == "schema": identity.pop("identity_schema")
    elif fault == "missing-supervisor": identity.pop("simulator_supervisor_identity_receipt")
    elif fault == "hash":
        identity["simulator_supervisor_identity_receipt"] = {**identity["simulator_supervisor_identity_receipt"], "sha256": "f" * 64}
    elif fault == "unreleased": bare_sim.cell["status"] = "PLANNED_NOT_RELEASED"
    else:
        bare_sim.supervisor["role"] = "policy"
        bare_sim.start.write_text(json.dumps(bare_sim.supervisor))
        identity["simulator_supervisor_identity_receipt"] = {"path": str(bare_sim.start), "sha256": mailbox._digest(bare_sim.start)}
    with pytest.raises((AdapterError, worker.ResourceBlocked)):
        native._verify_native_authority(bare_sim.cell, identity)


def test_pod_protocol_keeps_hashes_counts_arrays_close_and_no_replay(bare_sim):
    root = bare_sim.root / "mailbox"
    for directory in ("requests", "responses", "faults"):
        (root / directory).mkdir(parents=True)
    environment = FakeEnvironment()
    receiver = mailbox.MailboxReceiver(root=root, identity=bare_sim.identity, environment=environment)

    def refresh(_directory):
        receiver.serve_one(sorted((root / "requests").glob("*.json"))[-1])

    client = mailbox.MailboxClient(root=root, identity=bare_sim.identity, metadata_refresh=refresh)
    client.reset()
    client.step(np.arange(8, dtype=np.float32))
    client.step(np.zeros(8, dtype=np.float32))
    assert client.snapshot()["action_step"] == 2
    assert client.policy_observation()["image_obs"]["camera/0"].shape == (2, 2, 3)
    client.close()
    receipt = native.verify_receiver_completion(root, bare_sim.identity)
    assert receipt["command_count"] == 4 and environment.close_count == 1
    assert "simulator_job_uid" not in receipt["identity"]
    assert receipt["identity"]["simulator_supervisor_identity_receipt"] == bare_sim.identity["simulator_supervisor_identity_receipt"]
    with pytest.raises(mailbox.MailboxError):
        receiver.serve_one(root / "requests/0001-reset.json")
    with pytest.raises(AdapterError, match="clean completion"):
        native.verify_receiver_completion(root, bare_sim.identity)


def test_existing_mailbox_factory_accepts_only_explicit_v2_pod_owner(bare_sim, monkeypatch):
    root = bare_sim.root / "mailbox"
    root.mkdir()
    identity_file = bare_sim.root / "identity.json"
    mailbox._write(identity_file, bare_sim.identity)
    monkeypatch.setenv("SGW01_SIMULATOR_MAILBOX_ROOT", str(root))
    monkeypatch.setenv("SGW01_SIMULATOR_MAILBOX_IDENTITY", str(identity_file))
    monkeypatch.setenv("SGW01_SIMULATOR_MAILBOX_IDENTITY_SHA256", mailbox._digest(identity_file))
    client = mailbox.create_mailbox_environment(cell=bare_sim.cell, evidence_root=bare_sim.root / "evidence")
    assert client.identity == mailbox.normalize_identity(bare_sim.identity)
    assert client.command == 0


def test_expired_supervisor_stops_cli_before_creating_mailbox_or_loading_native(bare_sim, monkeypatch):
    identity_file, cell_file = bare_sim.root / "identity.json", bare_sim.root / "cell.json"
    mailbox._write(identity_file, bare_sim.identity)
    mailbox._write(cell_file, bare_sim.cell)
    root = bare_sim.root / "mailbox"
    monkeypatch.setattr(native, "_verify_native_authority", lambda *_: time.time() - 1)
    monkeypatch.setattr(sys, "argv", ["native", "--mailbox-root", str(root), "--identity", str(identity_file),
                                    "--identity-sha256", mailbox._digest(identity_file), "--deadline-seconds", "999",
                                    "--release-cell-json", str(cell_file), "--release-cell-sha256", mailbox._digest(cell_file)])
    with pytest.raises(AdapterError, match="expired before native startup"):
        native.main()
    assert not root.exists()
