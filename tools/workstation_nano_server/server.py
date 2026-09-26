"""Finite two-rank FSDP transport around the unchanged pinned Nano service.

Only rank zero opens the official OpenPI websocket. Both ranks receive every
observation and call the same native infer method. No model weights, sampling
settings, transforms, or action postprocessing are replaced here.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import asdict
from datetime import timedelta
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import threading
import time
import traceback

SOURCE_PIN = "411d25b2e35bc441126f48c44a4b93e1c0564274"
CHECKPOINT_PIN = "6706d7680581c255ff61e0f3bb49d90eac55c79e"
CHECKPOINT_ID = "nvidia/Cosmos3-Nano-Policy-DROID"


def materialize_offloaded_fsdp(module, *, device, recurse=True):
    """Materialize only FSDP DTensors on CPU; native buffers stay on device."""
    import torch
    from torch.distributed.tensor import DTensor

    return module._apply(
        lambda tensor: torch.empty_like(
            tensor, device="cpu" if isinstance(tensor, DTensor) else device
        ),
        recurse=recurse,
    )


@contextmanager
def fsdp_cpu_offload(enabled):
    """Scoped placement hooks at the pinned Cosmos module import sites."""
    receipt = {"enabled": enabled}
    if not enabled:
        yield receipt
        return
    import importlib
    from types import MethodType
    import torch
    from torch.distributed.fsdp import CPUOffloadPolicy
    from torch.distributed.tensor import DTensor

    block_module = importlib.import_module("cosmos_framework.model.vfm.mot.parallelize_unified_mot")
    root_module = importlib.import_module("cosmos_framework.model.vfm.mot.parallelize_vfm_network")
    originals = [(module, module.fully_shard) for module in (block_module, root_module)]
    roots = []
    receipt.update({
        "policy": "torch.distributed.fsdp.CPUOffloadPolicy", "pin_memory": True,
        "reshard_after_forward": True, "fully_shard_calls": 0,
        "materialization_calls": 0,
        "checkpoint_load": "unchanged native DCP reader fills CPU-backed DTensor shards",
        "scope": "native FSDP network parameters; other parameters and buffers retain native placement",
    })

    def wrap(original, *, root):
        def fully_shard(*args, **kwargs):
            if "offload_policy" in kwargs or "reshard_after_forward" in kwargs:
                raise RuntimeError("pinned fully_shard signature changed; refusing placement override")
            kwargs.update(offload_policy=CPUOffloadPolicy(pin_memory=True), reshard_after_forward=True)
            result = original(*args, **kwargs)
            receipt["fully_shard_calls"] += 1
            if root:
                if "to_empty" in result.__dict__:
                    raise RuntimeError("network already overrides to_empty")
                roots.append(result)

                def to_empty(self, *, device, recurse=True):
                    receipt["materialization_calls"] += 1
                    # This override is consumed by OmniMoTModel.build_net only.
                    del self.to_empty
                    return materialize_offloaded_fsdp(self, device=device, recurse=recurse)

                result.to_empty = MethodType(to_empty, result)
            return result
        return fully_shard

    block_module.fully_shard = wrap(originals[0][1], root=False)
    root_module.fully_shard = wrap(originals[1][1], root=True)
    try:
        yield receipt
        if len(roots) != 1 or receipt["materialization_calls"] != 1:
            raise RuntimeError("expected one native FSDP network materialization")
        shards = [parameter for parameter in roots[0].parameters() if isinstance(parameter, DTensor)]
        if not shards or any(parameter.device.type != "cpu" or
                             parameter.to_local().device.type != "cpu" or
                             not parameter.to_local().is_pinned() or
                             parameter.dtype != torch.bfloat16 for parameter in shards):
            raise RuntimeError("loaded FSDP parameters must be pinned CPU BF16 shards")
        receipt.update({
            "validated_after_native_checkpoint_load": True,
            "parameter_tensors": len(shards),
            "local_parameter_bytes": sum(parameter.to_local().numel() * parameter.element_size()
                                         for parameter in shards),
            "parameter_device": "cpu", "parameter_dtype": "torch.bfloat16",
        })
        # CUDA's allocator can retain the temporary storage used by loading.
        torch.cuda.empty_cache()
    finally:
        for module, original in originals:
            module.fully_shard = original
        for network in roots:
            if "to_empty" in network.__dict__:
                del network.to_empty


class Coordinator:
    """Serial request protocol, shared by the serving and follower ranks."""

    def __init__(self, *, infer, broadcast, complete, record, max_requests, seed):
        self.native_infer = infer
        self.broadcast = broadcast
        self.complete = complete
        self.record = record
        self.max_requests = max_requests
        self.seed = seed
        self.requests = 0
        self.resets = 0
        self.lock = threading.Lock()

    def infer(self, observation):
        with self.lock:
            if observation.get("_workstation_control") == "reset":
                packet = {"kind": "reset", "index": self.resets + 1}
            elif "_workstation_control" in observation:
                raise ValueError("unknown workstation control")
            else:
                if self.requests >= self.max_requests:
                    raise RuntimeError("finite model request budget exhausted")
                packet = {"kind": "infer", "index": self.requests, "observation": observation}
            self.broadcast(packet)
            return self.consume(packet)

    def consume(self, packet):
        kind, index = packet["kind"], packet["index"]
        if kind == "reset":
            if index != self.resets + 1:
                raise RuntimeError("reset sequence mismatch")
            # Official history_length=1 constructs a fresh sample each call;
            # deterministic_seed=True removes mutable sampling-RNG state.
            self.resets = index
            result = {"status": "reset", "reset_index": index,
                      "policy_seed": self.seed, "history_length": 1}
        elif kind == "infer":
            if index != self.requests or self.requests >= self.max_requests:
                raise RuntimeError("request sequence or budget mismatch")
            self.requests += 1  # A failed native attempt still consumes budget.
            self.record("request-started", {"index": index, "reset_index": self.resets,
                                           "observation": packet["observation"]})
            result = self.native_infer(packet["observation"])
        else:
            raise RuntimeError("unknown rank command")
        ack = {"kind": kind, "index": index}
        acknowledgements = self.complete(ack)
        if len(acknowledgements) != 2 or any(value != ack for value in acknowledgements):
            raise RuntimeError("rank acknowledgements disagree")
        self.record("request-completed" if kind == "infer" else "reset", {
            "index": index, "reset_index": self.resets, "result": result,
            "rank_acknowledgements": acknowledgements,
        })
        retained = {"kind": "retained-" + kind, "index": index}
        if self.complete(retained) != [retained, retained]:
            raise RuntimeError("rank retention acknowledgements disagree")
        return result


def write_json(path, value):
    with Path(path).open("x") as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def check_identity(args):
    source = Path(args.source_root).resolve()
    actual = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    if actual != SOURCE_PIN:
        raise ValueError("Cosmos source does not match the pinned commit")
    if subprocess.check_output(["git", "-C", str(source), "status", "--porcelain", "--untracked-files=no"], text=True).strip():
        raise ValueError("pinned Cosmos source has tracked modifications")
    manifest_path = Path(args.checkpoint_manifest).resolve()
    manifest = json.loads(manifest_path.read_bytes())["checkpoint"]
    if manifest["id"] != CHECKPOINT_ID or manifest["revision"] != CHECKPOINT_PIN:
        raise ValueError("checkpoint manifest identity mismatch")
    checkpoint = Path(args.checkpoint_path).resolve()
    for relative, spec in manifest["files"].items():
        path = checkpoint / relative
        if not path.is_file() or path.stat().st_size != spec["bytes"]:
            raise ValueError(f"checkpoint file missing or truncated: {relative}")
    config_hash = hashlib.sha256((checkpoint / "config.json").read_bytes()).hexdigest()
    if config_hash != manifest["files"]["config.json"]["sha256"]:
        raise ValueError("checkpoint configuration hash mismatch")
    metadata = list((checkpoint / ".cache/huggingface/download").rglob("*.metadata"))
    if not metadata or any(path.read_text().splitlines()[0] != CHECKPOINT_PIN for path in metadata):
        raise ValueError("local Hugging Face download metadata does not attest pinned revision")
    return {
        "source_root": str(source), "source_commit": actual,
        "checkpoint_path": str(checkpoint), "checkpoint_id": CHECKPOINT_ID,
        "checkpoint_revision": CHECKPOINT_PIN, "config_sha256": config_hash,
        "checkpoint_manifest": str(manifest_path),
        "checkpoint_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "checkpoint_validation": "all manifest file sizes; config SHA256; HF download revision metadata",
        "weight_content_hashes_reverified": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--checkpoint-path", required=True)
    parser.add_argument("--checkpoint-manifest", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--receipt", help="Fresh rank-zero runtime receipt, also sent as websocket metadata")
    parser.add_argument("--host", choices=["127.0.0.1"], default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18026)
    parser.add_argument("--seed", type=int, default=6100)
    parser.add_argument("--max-requests", type=int, default=96)
    parser.add_argument("--wall-seconds", type=int, default=10800)
    parser.add_argument("--request-timeout", type=int, default=900)
    parser.add_argument("--offload-guardrails", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--offload-fsdp", action=argparse.BooleanOptionalAction, default=False,
                        help="Opt in to pinned CPU BF16 FSDP shards with layer-wise CUDA transfers")
    args = parser.parse_args()
    if min(args.max_requests, args.wall_seconds, args.request_timeout) <= 0:
        parser.error("budgets must be positive")
    rank = int(os.environ.get("RANK", "-1"))
    if os.environ.get("WORLD_SIZE") != "2" or rank not in (0, 1):
        parser.error("launch via torchrun --nproc_per_node=2")
    root = Path(args.output).resolve()
    root.mkdir(parents=True, exist_ok=True)
    rank_root = root / f"rank-{rank}"
    rank_root.mkdir(exist_ok=False)

    def terminate(reason, code=1):
        try:
            write_json(rank_root / "terminal.json", {"reason": reason, "exit_code": code,
                       "rank": rank, "pid": os.getpid(), "time": time.time()})
        finally:
            # Never wait on a failed peer's collective during shutdown. Torchrun
            # owns both child processes and tears down the remaining rank.
            os._exit(code)

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda signum, frame: terminate(f"signal-{signum}", 128 + signum))
    deadline = threading.Timer(args.wall_seconds, lambda: terminate("wall-budget-exhausted", 124))
    deadline.daemon = True
    deadline.start()
    try:
        identity = check_identity(args)
        import sys
        sys.path.insert(0, identity["source_root"])
        os.environ.setdefault("TORCH_NCCL_ASYNC_ERROR_HANDLING", "1")
        from cosmos_framework.scripts import action_policy_server_robolab as native
        import importlib.metadata
        import numpy as np
        import torch
        from torch import distributed as dist

        if not Path(native.__file__).resolve().is_relative_to(Path(identity["source_root"])):
            raise RuntimeError("native module imported outside the pinned source")
        class PlacementService(native.RobolabPolicyService):
            def _build_setup_args(self, native_args):
                setup = super()._build_setup_args(native_args)
                # This is an official OmniSetup option, absent from the policy
                # CLI. It moves auxiliary guardrails only, preserving BF16 model
                # weights and retaining guardrails rather than disabling them.
                return setup.model_copy(update={"offload_guardrail_models": args.offload_guardrails})

        native_args = native.RobolabServerArgs(
            checkpoint_path=identity["checkpoint_path"], hf_revision=CHECKPOINT_PIN,
            host=args.host, port=args.port, domain_name="droid_lerobot", decode_video=True,
            output_dir=root / "native", seed=args.seed, deterministic_seed=True,
            guidance=3.0, num_steps=4, shift=5.0, resolution="480", conditioning_fps=15.0,
            action_chunk_size=32, action_dim=8, action_space="joint_pos", use_state=True, history_length=1,
        )
        with fsdp_cpu_offload(args.offload_fsdp) as fsdp_placement:
            service = PlacementService(native_args)
        if service.setup_args.dp_shard_size != 2 or service.model.precision != torch.bfloat16:
            raise RuntimeError("runtime must resolve to two FSDP shards and native BF16 precision")
        control = dist.new_group(backend="gloo", timeout=timedelta(seconds=args.wall_seconds + 60))
        write_json(rank_root / "loaded-runtime.json", {
            **identity, "rank": rank, "world_size": 2, "pid": os.getpid(),
            "cuda_device": torch.cuda.get_device_name(), "device": torch.cuda.current_device(),
            "native_config": asdict(service.cfg), "setup": service.setup_args.model_dump(mode="json"),
            "offload_guardrails": args.offload_guardrails, "max_requests": args.max_requests,
            "fsdp_placement": fsdp_placement,
            "wall_seconds": args.wall_seconds, "request_timeout": args.request_timeout,
            "versions": {key: importlib.metadata.version(key) for key in ("torch", "numpy", "transformers")},
            "transport": "rank-zero websocket; Gloo observation broadcast; native two-rank FSDP",
            "forecast_status": "same-request decoded future; physical camera/time mapping unqualified",
        })

        def record(event, value):
            now = time.time()
            if event == "request-started":
                directory = rank_root / f"request-{value['index']:04d}"
                directory.mkdir()
                observation = value.pop("observation")
                arrays = {key: item for key, item in observation.items() if isinstance(item, np.ndarray)}
                if rank == 0:
                    np.savez(directory / "observation.npz", **arrays)
                value["prompt"] = observation.get("prompt")
                value["input_arrays"] = {key: {"shape": list(item.shape), "dtype": str(item.dtype),
                    "sha256": hashlib.sha256(item.tobytes()).hexdigest()} for key, item in arrays.items()}
                write_json(directory / "intent.json", {**value, "time": now, "seed": args.seed})
            elif event == "request-completed":
                directory = rank_root / f"request-{value['index']:04d}"
                result = value.pop("result")
                action, video = np.asarray(result["action"]), np.asarray(result["video"])
                if action.shape != (32, 8) or not np.isfinite(action).all():
                    raise RuntimeError(f"invalid native actions: {action.shape}")
                if video.dtype != np.uint8 or video.ndim != 4 or video.shape[0] != 33 or video.shape[-1] != 3:
                    raise RuntimeError(f"invalid native future: {video.shape}, {video.dtype}")
                if rank == 0:
                    np.save(directory / "actions.npy", action, allow_pickle=False)
                    np.save(directory / "future.npy", video, allow_pickle=False)
                write_json(directory / "result.json", {**value, "time": now, "seed": args.seed,
                    "action_shape": list(action.shape), "video_shape": list(video.shape),
                    "action_sha256": hashlib.sha256(action.tobytes()).hexdigest(),
                    "video_sha256": hashlib.sha256(video.tobytes()).hexdigest(),
                    "forecast_status": "decoded_unmapped"})
            else:
                write_json(rank_root / f"reset-{value['index']:04d}.json", {**value, "time": now})

        def broadcast(packet):
            objects = [packet]
            dist.broadcast_object_list(objects, src=0, group=control)
            return objects[0]

        def complete(ack):
            values = [None, None]
            dist.all_gather_object(values, ack, group=control)
            return values

        def infer(observation):
            request_deadline = threading.Timer(args.request_timeout, lambda: terminate("native-request-timeout", 124))
            request_deadline.daemon = True
            request_deadline.start()
            try:
                return service.infer(observation)
            finally:
                request_deadline.cancel()

        coordinator = Coordinator(infer=infer, broadcast=broadcast, complete=complete, record=record,
                                  max_requests=args.max_requests, seed=args.seed)
        dist.barrier(group=control)
        if rank == 0:
            class FailClosedPolicy:
                def infer(self, observation):
                    try:
                        return coordinator.infer(observation)
                    except BaseException:
                        terminate(traceback.format_exc())

            receipt = {**identity, "port": args.port, "host": args.host,
                       "world_size": 2, "time": time.time(), "maximum_model_requests": args.max_requests,
                       "config": asdict(service.cfg), "offload_guardrails": args.offload_guardrails,
                       "fsdp_placement": fsdp_placement,
                       "resolved_dp_shard_size": service.setup_args.dp_shard_size,
                       "resolved_cp_size": service.setup_args.cp_size,
                       "resolved_cfgp_size": service.setup_args.cfgp_size,
                       "status": "model_loaded_and_both_ranks_ready_to_bind_websocket",
                       "output": str(root), "server_pid": os.getpid()}
            write_json(root / "ready.json", receipt)
            if args.receipt and Path(args.receipt).resolve() != root / "ready.json":
                Path(args.receipt).parent.mkdir(parents=True, exist_ok=True)
                write_json(args.receipt, receipt)
            server_cls = native._load_openpi_websocket_policy_server()
            server_cls(policy=FailClosedPolicy(), host=args.host, port=args.port,
                       metadata=receipt).serve_forever()
        else:
            while True:
                coordinator.consume(broadcast(None))
    except BaseException:
        terminate(traceback.format_exc())


if __name__ == "__main__":
    main()
