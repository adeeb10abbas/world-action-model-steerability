"""CPU-only rendering checks; no Kubernetes or native runtime calls."""
import json
import subprocess

import pytest

from tools.render_runtime_closed_loop_jobs import JOBS, ROOT, render


MATERIALIZATION = json.loads((JOBS.parent / "live-materialization.json").read_text())
HASHES = {
    "N3": "eea22dbeb7bb2dc8cc63c6227203450cac9602e3f63162062b388af73cd1589a",
    "E3": "a228d1ce7ebd95613cfdad7089d69e66d3c9db9e0d012404c2d8c74b80f87393",
    "F3": "8c119556d258834e060cffca033c3e949d2b9c70d9444bae2474c5d64ea13ddc",
}


@pytest.mark.parametrize("model", HASHES)
@pytest.mark.parametrize("role", ("policy", "simulator"))
def test_original_submitted_manifests_reproduce_exactly(model, role):
    value = render(model=model, role=role, materialization=MATERIALIZATION,
                   registration_sha256=HASHES[model])
    assert value == json.loads((JOBS / f"live-{model.lower()}-{role}-a.json").read_text())
    script = value["spec"]["template"]["spec"]["containers"][0]["args"][0]
    subprocess.run(["bash", "-n"], input=script, text=True, check=True)


@pytest.mark.parametrize("model", HASHES)
@pytest.mark.parametrize("role", ("policy", "simulator"))
def test_distinct_attempt_can_reuse_one_compatible_lane_without_weaker_guards(model, role):
    value = render(
        model=model, role=role, materialization=MATERIALIZATION,
        registration_sha256="b" * 64, attempt_suffix="b",
        simulator_node="dcwipphhgc191.edc.nam.gm.com",
    )
    spec = value["spec"]["template"]["spec"]
    container = spec["containers"][0]
    env = {item["name"]: item for item in container["env"]}
    assert value["metadata"]["name"] == f"sgw01-ali-live-{model.lower()}-{role}-20260924b"
    assert env["OUT"]["value"] == f"{ROOT}/closed-loop-{model}-b/{role}"
    assert env["REGISTRATION"]["value"] == f"{ROOT}/closed-loop-{model}-b/registration.json"
    assert env["REGISTRATION_SHA256"]["value"] == "b" * 64
    assert spec["nodeName"] == (
        "dcwipphai0061.edc.nam.gm.com" if role == "policy" else "dcwipphhgc191.edc.nam.gm.com"
    )
    assert env["EXPECTED_GPU_NAME"]["value"] == (
        "NVIDIA A100-SXM4-80GB" if role == "policy" else "NVIDIA A40"
    )
    assert value["spec"]["backoffLimit"] == 0
    assert value["spec"]["activeDeadlineSeconds"] == 3600
    assert spec["restartPolicy"] == "Never"
    assert spec["automountServiceAccountToken"] is False
    assert container["resources"]["limits"]["nvidia.com/gpu"] == "1"
    assert env["JOB_UID"]["valueFrom"]["fieldRef"]["fieldPath"].endswith("controller-uid']")
    script = container["args"][0]
    assert 'mkdir "$OUT"' in script
    assert "flock --nonblock 9" in script
    assert "GPU-60b3065c-79cb-61e6-b92a-32d0ae3750f3" in script
    subprocess.run(["bash", "-n"], input=script, text=True, check=True)


@pytest.mark.parametrize("overrides", (
    {"attempt_suffix": "../a"},
    {"attempt_suffix": "a\nb"},
    {"simulator_node": "dcwipphhgc225.edc.nam.gm.com"},
    {"simulator_node": "unknown"},
    {"policy_node": "dcwipphhgc225.edc.nam.gm.com"},
))
def test_rejects_unsafe_attempts_and_unregistered_nodes(overrides):
    with pytest.raises(ValueError):
        render(model="N3", role="simulator", materialization=MATERIALIZATION,
               registration_sha256=HASHES["N3"], **overrides)


@pytest.mark.parametrize("model,policy,simulator", (
    ("E3", "dcwipphai0062.edc.nam.gm.com", "dcwipphhgc194.edc.nam.gm.com"),
    ("F3", "dcwipphai0063.edc.nam.gm.com", "dcwipphhgc190.edc.nam.gm.com"),
))
def test_prospective_independent_lanes_retain_exact_hardware_guards(model, policy, simulator):
    for role, node, gpu in (("policy", policy, "NVIDIA A100-SXM4-80GB"),
                            ("simulator", simulator, "NVIDIA A40")):
        value = render(model=model, role=role, materialization=MATERIALIZATION,
                       registration_sha256="b" * 64, attempt_suffix="b",
                       policy_node=policy, simulator_node=simulator)
        spec = value["spec"]["template"]["spec"]
        assert spec["nodeName"] == node
        env = {item["name"]: item for item in spec["containers"][0]["env"]}
        assert env["EXPECTED_GPU_NAME"]["value"] == gpu
