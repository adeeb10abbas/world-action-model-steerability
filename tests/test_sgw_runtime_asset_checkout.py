"""RoboLab source checks delegate used asset integrity to bound file hashes."""

import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from experiments.workshops.spatial_grounding_v1 import runtime
from experiments.workshops.spatial_grounding_v1 import robolab_jointpos_environment as jointpos
from experiments.workshops.spatial_grounding_v1.adapters import AdapterError


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def checkout(root):
    root.mkdir()
    (root / "assets").mkdir()
    (root / "client.py").write_text("PINNED = True\n")
    (root / "assets/scene.usda").write_text("version https://git-lfs.github.com/spec/v1\n")
    git(root, "init", "-q")
    git(root, "add", ".")
    git(root, "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
        "-c", "commit.gpgsign=false", "commit", "-qm", "fixture")
    return git(root, "rev-parse", "HEAD")


def test_asset_exclusion_requires_opt_in_and_retains_pin(tmp_path):
    root = tmp_path / "robolab"
    revision = checkout(root)
    (root / "assets/scene.usda").write_text("materialized scene")
    with pytest.raises(AdapterError, match="dirty"):
        runtime._verify_git_checkout(root, revision, "study")
    assert runtime._verify_git_checkout(root, revision, "RoboLab", exclude_assets=True) == revision
    with pytest.raises(AdapterError, match="not pinned"):
        runtime._verify_git_checkout(root, "0" * 40, "RoboLab", exclude_assets=True)


@pytest.mark.parametrize("staged", [False, True])
def test_asset_exclusion_still_rejects_tracked_code_changes(tmp_path, staged):
    root = tmp_path / "robolab"
    revision = checkout(root)
    (root / "assets/scene.usda").write_text("materialized scene")
    (root / "client.py").write_text("PINNED = False\n")
    if staged:
        git(root, "add", "client.py")
    with pytest.raises(AdapterError, match="dirty"):
        runtime._verify_git_checkout(root, revision, "RoboLab", exclude_assets=True)


def test_jointpos_asset_exclusion_preserves_exact_manifest_validation(tmp_path, monkeypatch):
    study, robolab = tmp_path / "study", tmp_path / "robolab"
    study_revision, robolab_revision = checkout(study), checkout(robolab)
    scene = robolab / "assets/scene.usda"
    scene.write_text("materialized scene")
    manifest = tmp_path / "assets.json"
    manifest.write_text(json.dumps({"scene": {
        "path": str(scene), "bytes": scene.stat().st_size,
        "sha256": hashlib.sha256(scene.read_bytes()).hexdigest(),
    }, "assets": []}))
    binding = tmp_path / "binding.json"
    binding.write_text(json.dumps({
        "camera_configuration": jointpos.camera_configuration_identity(),
        "source_root": str(study), "source_commit": study_revision,
        "robolab_root": str(robolab), "robolab_commit": robolab_revision,
        "assets_manifest": str(manifest), "assets_manifest_sha256": jointpos._sha256(manifest),
        "cells": {"cell": {}},
    }))
    monkeypatch.setattr(jointpos, "D1_ROBOLAB_CLIENT_COMMIT", robolab_revision)
    monkeypatch.setenv("SGW01_ENV_BINDING", str(binding))
    monkeypatch.setenv("SGW01_ENV_BINDING_SHA256", jointpos._sha256(binding))
    assert jointpos.JointPositionBinding.load().robolab_root == robolab
    scene.write_text("MATERIALIZED SCENE")  # Same size; hash must catch corruption.
    with pytest.raises(AdapterError, match="asset payload changed"):
        jointpos.JointPositionBinding.load()
    scene.write_text("materialized scene")
    (study / "assets/scene.usda").write_text("study asset edit")
    with pytest.raises(AdapterError, match="SGW simulator.*dirty"):
        jointpos.JointPositionBinding.load()


def test_dreamzero_excludes_only_client_assets(tmp_path, monkeypatch):
    server, client = tmp_path / "server", tmp_path / "client"
    server_revision, client_revision = checkout(server), checkout(client)
    (client / "assets/scene.usda").write_text("materialized scene")
    checkpoint = tmp_path / "checkpoint"
    checkpoint.mkdir()
    (checkpoint / "weights").write_bytes(b"test weights")
    manifest = tmp_path / "artifacts/vla_wam_shared_v2/pilot/expansion/dreamzero_official_source_checkpoint_manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"checkpoint": {"revision": "test", "aggregate_sha256": "test",
        "files": [{"path": "weights", "bytes": 12,
                   "sha256": hashlib.sha256(b"test weights").hexdigest()}]}}))
    monkeypatch.setattr(runtime, "__file__", str(tmp_path / "experiments/workshops/spatial_grounding_v1/runtime.py"))
    monkeypatch.setattr(runtime, "D1_ROBOLAB_CLIENT_COMMIT", client_revision)
    monkeypatch.setattr(runtime, "DREAMZERO_CONFIG", {**runtime.DREAMZERO_CONFIG, "source_commit": server_revision})
    monkeypatch.setenv("SGW01_D1_SERVER_SOURCE_ROOT", str(server))
    monkeypatch.setenv("SGW01_D1_CLIENT_SOURCE_ROOT", str(client))
    monkeypatch.setenv("SGW01_D1_CHECKPOINT_PATH", str(checkpoint))
    assert runtime._verify_dreamzero_identity()["client_source_commit"] == client_revision
    (server / "assets/scene.usda").write_text("server asset edit")
    with pytest.raises(AdapterError, match="DreamZero server.*dirty"):
        runtime._verify_dreamzero_identity()
