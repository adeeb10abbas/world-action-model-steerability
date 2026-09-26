"""Exercise real two-rank control collectives with CPU-only synthetic inference.

Run with CUDA_VISIBLE_DEVICES='' python -m torch.distributed.run --standalone
--nproc-per-node=2 tools/workstation_nano_server/cpu_gloo_check.py.
This validates transport only; it is not Nano or GPU qualification.
"""
from datetime import timedelta
import json
import os

import numpy as np
from torch import distributed as dist

from server import Coordinator


def main():
    if os.environ.get("CUDA_VISIBLE_DEVICES") != "":
        raise RuntimeError("this engineering check must hide all GPUs")
    dist.init_process_group("gloo", timeout=timedelta(seconds=30))
    rank = dist.get_rank()
    try:
        events = []

        def broadcast(packet):
            objects = [packet]
            dist.broadcast_object_list(objects, src=0)
            return objects[0]

        def complete(ack):
            values = [None, None]
            dist.all_gather_object(values, ack)
            return values

        def infer(observation):
            assert np.array_equal(observation["image"], np.arange(12).reshape(2, 2, 3))
            return {"action": np.full((32, 8), 1 if observation["prompt"] == "left" else -1)}

        coordinator = Coordinator(infer=infer, broadcast=broadcast, complete=complete,
                                  record=lambda event, value: events.append(event), max_requests=3, seed=6100)
        if rank == 0:
            assert coordinator.infer({"_workstation_control": "reset"})["reset_index"] == 1
            results = [coordinator.infer({"prompt": prompt, "image": np.arange(12).reshape(2, 2, 3)})
                       for prompt in ("left", "left", "right")]
            assert np.array_equal(results[0]["action"], results[1]["action"])
            assert not np.array_equal(results[0]["action"], results[2]["action"])
            try:
                coordinator.infer({"prompt": "left"})
                raise AssertionError("request budget was not enforced")
            except RuntimeError as exc:
                assert "request budget" in str(exc)
        else:
            for _ in range(4):
                coordinator.consume(broadcast(None))
        assert coordinator.requests == 3 and coordinator.resets == 1
        assert events.count("request-completed") == 3
        dist.barrier()
        print(json.dumps({"rank": rank, "status": "cpu_gloo_transport_passed", "model_requests": 0,
                          "engineering_messages": 4, "gpu_used": False}), flush=True)
    finally:
        dist.destroy_process_group()


if __name__ == "__main__":
    main()
