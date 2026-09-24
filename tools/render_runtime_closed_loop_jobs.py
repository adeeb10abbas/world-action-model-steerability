"""Render the current finite technical Jobs from the reviewed submitted templates."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

ROOT = "/data/users/ali/sgw-01/current-20260924a"
JOBS = Path(__file__).resolve().parents[1] / "handoff/cluster-execution-20260924/jobs"
TEMPLATES = {"N3": "n3-check-c.json", "E3": "e3-check-a.json", "F3": "f3-check-a.json"}
SIMULATOR_NODES = {model: f"dcwipphhgc{node}.edc.nam.gm.com"
                   for model, node in (("N3", 191), ("E3", 192), ("F3", 193))}


def render(
    *, model: str, role: str, materialization: dict, registration_sha256: str,
    attempt_suffix: str = "a", simulator_node: str | None = None,
) -> dict:
    source, commit = materialization["source_root"], materialization["source_commit"]
    if (model not in TEMPLATES or role not in ("policy", "simulator")
            or not re.fullmatch("[0-9a-f]{40}", commit)
            or not re.fullmatch("[0-9a-f]{64}", registration_sha256)
            or not re.fullmatch("[a-z][a-z0-9]{0,7}", attempt_suffix)
            or (simulator_node is not None and simulator_node not in SIMULATOR_NODES.values())
            or not Path(source).is_relative_to(ROOT)):
        raise ValueError("explicit current source, model, role and registration hash are required")
    name = f"sgw01-ali-live-{model.lower()}-{role}-20260924{attempt_suffix}"
    attempt = f"{ROOT}/closed-loop-{model}-{attempt_suffix}"
    output = f"{attempt}/{role}"
    template = TEMPLATES[model] if role == "policy" else "destination-check.json"
    value = json.loads((JOBS / template).read_text())
    value["metadata"]["name"] = name
    spec = value["spec"]["template"]["spec"]
    spec["schedulerName"] = name
    spec["nodeName"] = (
        "dcwipphai0061.edc.nam.gm.com" if role == "policy"
        else simulator_node or SIMULATOR_NODES[model]
    )
    value["spec"]["activeDeadlineSeconds"] = 3600
    container = spec["containers"][0]
    container["name"] = role
    env = {item["name"]: item for item in container["env"]}
    old_source, old_output = env["SOURCE"]["value"], env["OUT"]["value"]
    for item in env.values():
        if "value" in item:
            item["value"] = item["value"].replace(old_source, source).replace(old_output, output)
    updates = {
        "SOURCE": source, "OUT": output, "MODEL": model,
        "REGISTRATION": f"{attempt}/registration.json", "REGISTRATION_SHA256": registration_sha256,
        "IDENTITY": f"{attempt}/identity.json",
        "EXPECTED_GPU_NAME": "NVIDIA A100-SXM4-80GB" if role == "policy" else "NVIDIA A40",
    }
    if role == "simulator":
        binding = materialization["files"]["environment-binding.json"]
        updates.update(SGW01_ENV_BINDING=binding["path"], SGW01_ENV_BINDING_SHA256=binding["sha256"],
                       SGW01_SIMULATOR_DEVICE="cuda:0")
    env.update({key: {"name": key, "value": value} for key, value in updates.items()})
    for key, field in (("JOB_UID", "metadata.labels['batch.kubernetes.io/controller-uid']"),
                       ("POD_UID", "metadata.uid")):
        env[key] = {"name": key, "valueFrom": {"fieldRef": {"fieldPath": field}}}
    container["env"] = list(env.values())
    script = f"""set -euo pipefail
mkdir "$OUT"
exec > >(tee "$OUT/job.log") 2>&1
cd "$SOURCE"
test "$(git rev-parse HEAD)" = {commit}
test -z "$(git status --porcelain)"
CUDA_VISIBLE_DEVICES=$("$PY" -m experiments.workshops.spatial_grounding_v1.gpu_idle_probe --expected-count 1 --expected-name "$EXPECTED_GPU_NAME" --output "$OUT/gpu-idle.json")
export CUDA_VISIBLE_DEVICES
test "$CUDA_VISIBLE_DEVICES" != GPU-60b3065c-79cb-61e6-b92a-32d0ae3750f3
mkdir -p /data/users/ali/sgw-01/locks {ROOT}/locks
exec 9>"/data/users/ali/sgw-01/locks/gpu-$CUDA_VISIBLE_DEVICES.lock"
flock --nonblock 9
"""
    if role == "policy":
        script += f'exec 8>{ROOT}/locks/{model}.lock\nflock --nonblock 8\n'
    else:
        script += 'mkdir -p "$HOME/.cache" "$XDG_CACHE_HOME" "$WARP_CACHE_PATH" "$MPLCONFIGDIR"\n'
    script += """for attempt in $(seq 1 180); do
  if test -f "${IDENTITY%.json}.sha256"; then break; fi
  sleep 1
done
test -f "${IDENTITY%.json}.sha256"
IDENTITY_SHA256=$(cat "${IDENTITY%.json}.sha256")
"""
    module = "runtime_closed_loop_check" if role == "policy" else "native_runtime_check_receiver"
    prefix = 'bash tools/cluster_policy_bootstrap.sh "$MODEL" "$PY"' if role == "policy" else '"$PY"'
    script += (
        f'{prefix} -m experiments.workshops.spatial_grounding_v1.{module} '
        '--registration "$REGISTRATION" --registration-sha256 "$REGISTRATION_SHA256" '
        '--identity "$IDENTITY" --identity-sha256 "$IDENTITY_SHA256"'
        + (' --output "$OUT/evidence"' if role == "policy" else "") + "\nsync\n"
    )
    container["args"] = [script]
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=tuple(TEMPLATES), required=True)
    parser.add_argument("--role", choices=("policy", "simulator"), required=True)
    parser.add_argument("--materialization-receipt", type=Path, required=True)
    parser.add_argument("--registration-sha256", required=True)
    parser.add_argument("--attempt-suffix", default="a")
    parser.add_argument("--simulator-node", choices=tuple(SIMULATOR_NODES.values()))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    value = render(model=args.model, role=args.role,
                   materialization=json.loads(args.materialization_receipt.read_text()),
                   registration_sha256=args.registration_sha256,
                   attempt_suffix=args.attempt_suffix, simulator_node=args.simulator_node)
    with args.output.open("x") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    main()
