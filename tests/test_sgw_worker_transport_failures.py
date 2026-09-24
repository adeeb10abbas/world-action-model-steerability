"""CPU HTTP failures and valid action payloads; no model or simulator execution."""

import json
from pathlib import Path
import threading
import traceback
from types import SimpleNamespace

import numpy as np
import pytest

from experiments.workshops.spatial_grounding_v1 import producer, runtime, worker
from experiments.workshops.spatial_grounding_v1.adapters import AdapterError, NanoPolicyAdapter
from experiments.workshops.spatial_grounding_v1.contract import ContractError, load_release
from tests.test_sgw_adapters import PROMPT, make_transport, reset_evidence
from tests.test_sgw_contract import make_release
from tests.test_sgw_worker import FakeAdapter


@pytest.mark.parametrize("phase", ["construction", "reset", "request"])
@pytest.mark.parametrize("server_error", ["OutOfMemoryError", "RuntimeError"])
def test_disconnected_http_preserves_typed_server_error_and_stops_without_replay(
    tmp_path, monkeypatch, phase, server_error,
):
    release = load_release(make_release(tmp_path))
    log_dir = tmp_path / "server-logs"
    log_dir.mkdir()
    stderr_path = log_dir / "server.stderr.log"
    monkeypatch.setenv("SGW01_SERVER_LOG_DIR", str(log_dir))
    monkeypatch.setenv("SGW01_CAMERA_NAME", "cpu-camera")
    calls = {"reset": 0, "request": 0}
    error_type = type(server_error, (RuntimeError,), {})
    recorded_stderr = []

    def reset(_packet):
        calls["reset"] += 1
        if phase != "request":
            raise error_type("synthetic native failure")
        return {"status": "reset"}

    def predict(_packet):
        calls["request"] += 1
        raise error_type("synthetic native failure")

    server = producer.make_nano_http_server(SimpleNamespace(reset=reset, predict=predict), host="127.0.0.1", port=0)
    transport = runtime._NanoHttpTransport(
        "127.0.0.1", server.server_address[1],
        lambda **_kwargs: pytest.fail("failed HTTP request reached trace reader"),
        {"config": {"history_length": 1}},
    )
    with stderr_path.open("a") as stderr:
        def handle_error(*_args):
            traceback.print_exc(file=stderr)
            stderr.flush()
            recorded_stderr.append(stderr_path.read_bytes())

        server.handle_error = handle_error
        thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True)
        thread.start()

        class HTTPAdapter(FakeAdapter):
            closed = 0

            def reset(self, cell, recorder):
                value = super().reset(cell, recorder)
                transport.reset()
                return value

            def run_episode(self, cell, recorder, _reset):
                recorder.request({"request_id": "cpu-request", "request_index": 0,
                                  "started_at_utc": worker.utc_now(),
                                  "prompt_sha256": cell.row["prompt_sha256"], "reset_sha256": "cpu-reset"})
                return transport({
                    "observation": {}, "prompt": PROMPT, "request_id": "cpu-request", "request_index": 0,
                    "registered_cell_id": cell.cell_id, "camera_id": "cpu-camera", "camera_name": "cpu-camera",
                    "reset_id": "cpu-reset", "reset_fingerprint": "cpu-reset-fingerprint", "sampling_seed": 1140,
                })

            def close(self):
                self.closed += 1

        adapter = HTTPAdapter()
        if phase == "construction":
            monkeypatch.setattr(worker, "load_adapter", lambda _model: transport.reset())
        try:
            with pytest.raises(ContractError, match="without replay") as raised:
                worker.run_partition(release, model="N3", family="LAT", stage="P", max_valid=6, max_attempts=3,
                                     worker_id="http-failure", adapter=None if phase == "construction" else adapter)
            assert isinstance(raised.value.__cause__, AdapterError)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
        assert not thread.is_alive()
    assert calls == {"reset": 1, "request": int(phase == "request")}
    assert len(recorded_stderr) == 1 and stderr_path.read_bytes() == recorded_stderr[0]
    assert f"{server_error}: synthetic native failure" in stderr_path.read_text()
    assert not list((release.root.parent / "cells").glob("*.complete.json"))
    status = json.loads((release.root.parent / "status/http-failure.json").read_text())
    assert status["state"] == "technical_invalid"
    assert not worker._out_of_memory(status["reason"])
    attempts = list((release.root.parent / "attempts").glob("*/*"))
    assert len(attempts) == (0 if phase == "construction" else 1)
    if attempts:
        assert adapter.resets == adapter.closed == 1
        result = json.loads((attempts[0] / "result.json").read_text())
        assert result["status"] == "technical_invalid" and not worker._out_of_memory(result["technical_cause"])
        events = [json.loads(line) for line in (attempts[0] / "events.jsonl").read_text().splitlines()]
        failure = next(event for event in events if event["event"] == "technical_invalid")
        assert failure["error_type"] == "AdapterError"
        assert "RemoteDisconnected" in failure["traceback"] and "AdapterError" in failure["traceback"]
        manifest = json.loads((attempts[0] / "manifest.json").read_text())
        assert manifest["complete"] and manifest["result"]["status"] == "technical_invalid"
    else:
        assert status["phase"] == "model_construction"
        assert "RemoteDisconnected" in status["traceback"] and "AdapterError" in status["traceback"]


@pytest.mark.parametrize("future_status", ["not_exposed", "decode_error", "latent_only_retained"])
@pytest.mark.parametrize("behavior_status", ["valid_success", "valid_model_failure"])
def test_valid_actions_with_unavailable_forecast_keep_behavioral_outcome(tmp_path, future_status, behavior_status):
    release = load_release(make_release(tmp_path))
    calls = []

    def transport(request):
        calls.append(request["request_id"])
        response = make_transport("N3")(request)
        response["future"] = None
        response["native_trace"] = {**response, "future_status": future_status}
        if future_status == "decode_error":
            response["native_trace"]["future_metadata"] = {"decode_error": "OutOfMemoryError: synthetic decoder only"}
        return response

    class ActionsWithoutForecast(FakeAdapter):
        def run_episode(self, cell, recorder, reset):
            policy = NanoPolicyAdapter(cell_id=cell.cell_id, prompt=PROMPT, transport=transport)
            policy.reset(reset_fn=reset_evidence, reset_id="reset-1", camera_id="cam-1")
            prediction = policy.predict({}, PROMPT, action_step_start=0)
            assert prediction.returned_actions.shape == prediction.executable_actions.shape == (32, 8)
            assert prediction.future is None and prediction.future_status == future_status
            result = super().run_episode(cell, recorder, reset)
            np.save(recorder.path / "actions" / "returned-chunk.npy", prediction.returned_actions, allow_pickle=False)
            return {**result, "future_status": prediction.future_status,
                    "future_metadata": prediction.raw_response["native_trace"].get("future_metadata", {})}

    adapter = ActionsWithoutForecast()
    assert worker.run_partition(
        release, model="N3", family="LAT", stage="P", max_valid=6, max_attempts=3, worker_id="actions-valid",
        adapter=adapter, scorer=lambda _trace, _cell: {"status": behavior_status},
    ) == 0
    assert adapter.resets == len(calls) == 6
    for pointer_path in (release.root.parent / "cells").glob("*.complete.json"):
        pointer = json.loads(pointer_path.read_text())
        result = json.loads(Path(pointer["result"]["path"]).read_text())
        assert result["status"] == behavior_status and result["future_status"] == future_status
        if future_status == "decode_error":
            assert "OutOfMemoryError" in result["future_metadata"]["decode_error"]
