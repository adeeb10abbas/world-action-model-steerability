"""CPU contracts for the two-rank coordinator; no models or CUDA imports."""
import importlib.util
from pathlib import Path
import unittest


class CoordinatorTests(unittest.TestCase):
    def load(self):
        path = Path(__file__).with_name("server.py")
        self.assertTrue(path.exists(), "the bounded coordinator must exist")
        spec = importlib.util.spec_from_file_location("workstation_server", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_limit_blocks_extra_request_before_broadcast_or_model(self):
        module = self.load()
        sent, inferred = [], []
        coordinator = module.Coordinator(
            infer=lambda value: inferred.append(value) or {"action": [1]},
            broadcast=sent.append, complete=lambda value: [value, value],
            record=lambda *args: None, max_requests=1, seed=6100,
        )
        self.assertEqual(coordinator.infer({"prompt": "left"})["action"], [1])
        with self.assertRaisesRegex(RuntimeError, "request budget"):
            coordinator.infer({"prompt": "right"})
        self.assertEqual(len(sent), 1)
        self.assertEqual(len(inferred), 1)

    def test_reset_is_synchronized_without_consuming_inference_budget(self):
        module = self.load()
        sent, inferred = [], []
        coordinator = module.Coordinator(
            infer=lambda value: inferred.append(value) or {"action": [1]},
            broadcast=sent.append, complete=lambda value: [value, value],
            record=lambda *args: None, max_requests=1, seed=6100,
        )
        response = coordinator.infer({"_workstation_control": "reset"})
        self.assertEqual(response["status"], "reset")
        self.assertEqual(response["reset_index"], 1)
        self.assertEqual(inferred, [])
        self.assertEqual(sent[0]["kind"], "reset")
        self.assertEqual(coordinator.infer({"prompt": "left"})["action"], [1])

    def test_worker_receives_exact_observation_and_detects_out_of_order_request(self):
        module = self.load()
        observed = []
        worker = module.Coordinator(
            infer=lambda value: observed.append(value) or {"action": [2]},
            broadcast=lambda value: None, complete=lambda value: [value, value],
            record=lambda *args: None, max_requests=2, seed=6100,
        )
        packet = {"kind": "infer", "index": 0, "observation": {"prompt": "left", "pixels": [7]}}
        worker.consume(packet)
        self.assertEqual(observed, [{"prompt": "left", "pixels": [7]}])
        with self.assertRaisesRegex(RuntimeError, "sequence"):
            worker.consume(packet)
        self.assertEqual(len(observed), 1)

    def test_peer_ack_failure_prevents_successful_response(self):
        module = self.load()
        coordinator = module.Coordinator(
            infer=lambda value: {"action": [1]}, broadcast=lambda value: None,
            complete=lambda value: [value, {"kind": "infer", "index": 900}],
            record=lambda *args: None, max_requests=1, seed=6100,
        )
        with self.assertRaisesRegex(RuntimeError, "rank acknowledgements"):
            coordinator.infer({"prompt": "left"})


if __name__ == "__main__":
    unittest.main()
