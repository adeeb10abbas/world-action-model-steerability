"""Configuration-only renderer tests with fake AppLauncher/settings."""
import json
import sys
import types
from types import SimpleNamespace

import pytest

from experiments.workshops.spatial_grounding_v1 import native_mailbox_receiver as native
from experiments.workshops.spatial_grounding_v1 import robolab_jointpos_environment
from experiments.workshops.spatial_grounding_v1 import simulator_mailbox as mailbox
from experiments.workshops.spatial_grounding_v1.adapters import AdapterError
from tests.test_sgw_simulator_mailbox import FakeEnvironment
from tests.test_sgw_simulator_pod_ownership import bare_sim


def test_graphics_pin_is_explicit_single_gpu_without_claiming_uuid_mapping(bare_sim):
    plan = native._graphics_plan(bare_sim.identity, 0)
    assert plan["launcher_args"] == {
        "headless": True, "enable_cameras": True, "device": "cuda:0",
        "active_gpu": 0, "physics_gpu": 0, "multi_gpu": False,
    }
    assert plan["configured_cuda_gpu_uuid"] == bare_sim.identity["simulator_gpu_uuid"]
    assert plan["physical_gpu_uuid_correspondence"] == "unqualified"


@pytest.mark.parametrize("fault", ["missing-pin", "different-cli-pin", "second-renderer", "multi", "cuda-device"])
def test_unqualified_renderer_remaps_and_multi_gpu_fail_closed(bare_sim, monkeypatch, fault):
    identity = dict(bare_sim.identity)
    cli = 0
    if fault == "missing-pin": identity.pop("simulator_renderer_gpu_index")
    elif fault == "different-cli-pin": cli = 1
    elif fault == "second-renderer": identity["simulator_renderer_gpu_index"] = 1; cli = 1
    elif fault == "multi": identity["simulator_multi_gpu"] = True
    else: monkeypatch.setenv("SGW01_SIMULATOR_DEVICE", "cuda:1")
    with pytest.raises(AdapterError):
        native._graphics_plan(identity, cli)


@pytest.mark.parametrize("mismatch", [None, "active_gpu", "multi_gpu", "physics_gpu"])
def test_actual_config_and_kit_readback_are_both_required(mismatch):
    config = {"active_gpu": 0, "physics_gpu": 0, "multi_gpu": False}
    values = {"/renderer/activeGpu": 0, "/physics/cudaDevice": 0, "/renderer/multiGpu/enabled": False}
    if mismatch:
        key = {"active_gpu": "/renderer/activeGpu", "physics_gpu": "/physics/cudaDevice",
               "multi_gpu": "/renderer/multiGpu/enabled"}[mismatch]
        values[key] = True if mismatch == "multi_gpu" else 1
    record = native._observe_graphics(SimpleNamespace(config=config), values)
    assert record["status"] == ("mismatch" if mismatch else "configured_settings_verified")
    assert record["graphics_isolation_qualified"] is False


@pytest.mark.parametrize("fault", [None, "multi_gpu", "package-version"])
def test_native_attempt_retains_graphics_intent_and_readback_before_serving_commands(bare_sim, monkeypatch, fault):
    root = bare_sim.root / "mailbox"
    identity_file, cell_file = bare_sim.root / "identity.json", bare_sim.root / "cell.json"
    mailbox._write(identity_file, bare_sim.identity)
    mailbox._write(cell_file, bare_sim.cell)
    monkeypatch.setattr(sys, "argv", [
        "native", "--mailbox-root", str(root), "--identity", str(identity_file),
        "--identity-sha256", mailbox._digest(identity_file), "--deadline-seconds", "10",
        "--release-cell-json", str(cell_file), "--release-cell-sha256", mailbox._digest(cell_file),
        "--renderer-gpu-index", "0",
    ])
    versions = {"isaaclab": "2.2.0", "isaacsim": "5.0.0.0"}
    if fault == "package-version":
        versions["isaaclab"] = "unregistered"
    monkeypatch.setattr(native.importlib.metadata, "version", lambda name: versions[name])
    launches, closes = [], []
    environment = FakeEnvironment()

    def launcher(arguments):
        launches.append(dict(arguments))
        mailbox._write(root / "requests/0001-close.json", {
            "identity": mailbox.normalize_identity(bare_sim.identity), "command_id": 1, "operation": "close",
        })
        return SimpleNamespace(app=SimpleNamespace(config=dict(arguments), close=lambda: closes.append(True)))

    app_module = types.ModuleType("isaaclab.app")
    app_module.AppLauncher = launcher
    monkeypatch.setitem(sys.modules, "isaaclab.app", app_module)
    monkeypatch.setattr(robolab_jointpos_environment, "create_environment", lambda **_: environment)
    settings_module = types.ModuleType("carb.settings")
    settings_module.get_settings = lambda: {
        "/renderer/activeGpu": 0, "/physics/cudaDevice": 0, "/renderer/multiGpu/enabled": fault == "multi_gpu",
    }
    carb = types.ModuleType("carb")
    carb.settings = settings_module
    monkeypatch.setitem(sys.modules, "carb", carb)
    monkeypatch.setitem(sys.modules, "carb.settings", settings_module)
    if fault:
        with pytest.raises(AdapterError):
            native.main()
        assert (root / "receiver_failure.json").exists()
        assert not (root / "receiver_complete.json").exists()
    else:
        native.main()
        assert native.verify_receiver_completion(root, bare_sim.identity)["command_count"] == 1
    requested = json.loads((root / "graphics_launch.json").read_text())
    assert requested["identity_sha256"] == mailbox._digest(identity_file)
    assert requested["launcher_args"]["multi_gpu"] is False
    if fault == "package-version":
        assert not launches
    else:
        assert len(launches) == len(closes) == environment.close_count == 1
        observed = json.loads((root / "graphics_observed.json").read_text())
        assert observed["status"] == ("mismatch" if fault else "configured_settings_verified")
        assert observed["physical_gpu_uuid_correspondence"] == "unqualified"
