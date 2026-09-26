"""Tiny two-GPU qualification of CPU-shard placement and native safetensors DCP.

Run with the pinned Cosmos source on PYTHONPATH, using torchrun with two ranks.
No Nano weights, simulator, or server are loaded. --output must be a fresh path.
"""
import argparse
import importlib
import json
import os
from pathlib import Path

import torch
from torch import distributed as dist, nn
from torch.distributed.checkpoint.state_dict import get_model_state_dict
from torch.distributed.device_mesh import init_device_mesh
from torch.distributed.tensor import DTensor
from safetensors.torch import save_file

from server import fsdp_cpu_offload


class Network(nn.Module):
    def __init__(self):
        super().__init__()
        self.language_model = nn.Sequential(nn.Linear(64, 128), nn.GELU(), nn.Linear(128, 64))
        self.latent_pos_embed = nn.Embedding(2, 64)
        self.register_buffer("offset", torch.zeros(64), persistent=False)

    def forward(self, value):
        return self.language_model(value) + self.latent_pos_embed.weight[0] + self.offset


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    rank = int(os.environ["LOCAL_RANK"])
    torch.cuda.set_device(rank)
    dist.init_process_group("nccl")
    mesh = init_device_mesh("cuda", (2,))
    output = Path(args.output)
    checkpoint = output / "checkpoint"
    torch.manual_seed(1234)
    reference = Network().to(dtype=torch.bfloat16)
    if rank == 0:
        (checkpoint / "transformer").mkdir(parents=True, exist_ok=False)
        save_file(reference.state_dict(), checkpoint / "transformer/weights.safetensors")
        (checkpoint / "model.safetensors.index.json").write_text(json.dumps({
            "weight_map": {name: "transformer/weights.safetensors" for name in reference.state_dict()},
        }))
    dist.barrier()
    block_module = importlib.import_module("cosmos_framework.model.vfm.mot.parallelize_unified_mot")
    root_module = importlib.import_module("cosmos_framework.model.vfm.mot.parallelize_vfm_network")
    from cosmos_framework.inference.model import _DiffusersHuggingFaceStorageReader, _DiffusersLoadPlanner

    with fsdp_cpu_offload(True) as placement:
        with torch.device("meta"):
            network = Network()
        for block in (network.language_model[0], network.language_model[2]):
            block_module.fully_shard(block, mesh=mesh)
        root_module.fully_shard(network, mesh=mesh, ignored_params=set(network.latent_pos_embed.parameters()))
        network.to(dtype=torch.bfloat16)
        network.to_empty(device="cuda")
        # Exercise the native initialization pattern before loading replaces it.
        with torch.no_grad():
            for parameter in network.parameters():
                nn.init.trunc_normal_(parameter, std=0.1)
            network.offset.zero_()
        state = get_model_state_dict(network)
        reader = _DiffusersHuggingFaceStorageReader(checkpoint)
        planner = _DiffusersLoadPlanner(checkpoint)
        # Expose local fixture/planning errors before DCP packages exceptions.
        planner.set_up_planner(state, reader.read_metadata())
        planner.create_local_plan()
        torch.distributed.checkpoint.load(state, storage_reader=reader, planner=planner)
    assert network.offset.device.type == "cuda"
    assert network.latent_pos_embed.weight.device.type == "cuda"
    reference = reference.cuda()
    value = torch.arange(128, device="cuda", dtype=torch.bfloat16).reshape(2, 64) / 128
    torch.cuda.reset_peak_memory_stats()
    with torch.inference_mode():
        expected = reference(value)
        for _ in range(3):
            actual = network(value)
            torch.testing.assert_close(actual, expected, rtol=0, atol=0)
            assert all(parameter.device.type == "cpu" and parameter.to_local().is_pinned()
                       for parameter in network.parameters() if isinstance(parameter, DTensor))
    result = {"rank": rank, "status": "passed", "torch": torch.__version__,
              "placement": placement, "exact_reference_match": True, "repeated_forwards": 3,
              "peak_cuda_allocated_bytes": torch.cuda.max_memory_allocated(),
              "scope": "toy; native safetensors reader/planner, BF16, 2 NCCL ranks; no Nano weights"}
    (output / f"rank-{rank}.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result), flush=True)
    dist.barrier()
    dist.destroy_process_group()


if __name__ == "__main__":
    main()
