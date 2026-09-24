"""Tiny actual CPU codec roundtrips; no cluster, model or study recording use."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from experiments.workshops.spatial_grounding_v1.recorder import AttemptRecorder
from tools import download_study_videos as downloader
from tools import encode_study_video as encoder
from tests.test_download_study_videos import package, record, save_json


@pytest.fixture
def ffmpeg():
    return encoder.executable()


def source_case(tmp_path, ffmpeg, *, frames=None, status="decoded_unmapped", video=False):
    root = tmp_path / "cohort"
    root.mkdir()
    recorder = AttemptRecorder(
        SimpleNamespace(root=root / "release-test", release_id="release-test", hashes={"queue.jsonl": "a" * 64}),
        SimpleNamespace(cell_id="N3-LAT-P01-D-POS"), "attempt-001",
    )
    recorder.path.mkdir(parents=True)
    outcome = {"status": "technical_invalid", "technical_cause": "synthetic CPU codec fixture"}
    if video:
        artifact = "videos/viewport.mp4"
        path = recorder.path / artifact
        path.parent.mkdir()
        subprocess.run([
            ffmpeg, "-nostdin", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=64x48:rate=30000/1001",
            "-frames:v", "5", "-c:v", "libx264", "-threads", "1", "-crf", "0", "-pix_fmt", "yuv420p", str(path),
        ], check=True, timeout=30)
        outcome["viewport_artifact"] = {
            **record(path, artifact), "fps": 30000 / 1001, "frame_count": 5,
        }
    else:
        if frames is None:
            frames = np.zeros((5, 48, 64, 3), dtype=np.uint8)
            frames[:, :, :, 0] = np.arange(5, dtype=np.uint8)[:, None, None] * 40
            frames[:, 10:30, 10:30, 1] = 255
        recorder.prediction(SimpleNamespace(
            raw_request={}, raw_response={
                "future": frames, "future_metadata": {"conditioning_fps": 15, "physical_time_alignment": "unqualified"}},
            request_index=0, future_status=status, request_id="synthetic-request",
        ))
        artifact = "predictions/request-0000-arrays/array-00000.npy"
    recorder.artifact_manifest(outcome)
    manifest = recorder.path / "manifest.json"
    return {
        "root": root, "manifest_path": manifest.relative_to(root).as_posix(),
        "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        "artifact": artifact, "output": "viewing/attempts/N3-LAT-P01-D-POS/attempt-001/copy.mp4",
        "reserve_bytes": 0, "ffmpeg": ffmpeg,
        **({} if video else {"request_record": "predictions/request-0000.json", "playback_fps": "15"}),
    }


@pytest.mark.parametrize("codec", ["h264", "h265"])
def test_real_array_roundtrip_and_downloader_compatibility(tmp_path, ffmpeg, package, codec):
    args = source_case(tmp_path, ffmpeg)
    root = args["root"]
    manifest = root / args["manifest_path"]
    original = manifest.parent / args["artifact"]
    before = (manifest.read_bytes(), original.read_bytes())
    entry = encoder.encode(**args, codec=codec)
    assert entry["encoding"]["output"]["codec"] == ("h264" if codec == "h264" else "hevc")
    assert entry["encoding"]["output"]["frame_count"] == 5
    assert entry["encoding"]["output"]["width"] == 64
    assert entry["encoding"]["source"]["fps_numerator"] is None
    assert entry["encoding"]["timing_basis"] == "playback_only"
    assert entry["encoding"]["physical_time"] == {"status": "unavailable"}
    assert entry["encoding"]["recorded_future_metadata"]["physical_time_alignment"] == "unqualified"
    arguments = entry["encoding"]["arguments"]
    assert arguments[arguments.index("-crf") + 1] == "18"
    assert arguments[arguments.index("-preset") + 1] == "medium"
    assert before == (manifest.read_bytes(), original.read_bytes())
    sidecar = root / (args["output"] + ".entry.json")
    assert json.loads(sidecar.read_bytes()) == entry
    assert not list(root.rglob("*.partial"))
    value = package["value"]
    completion = json.loads((package["root"] / value["completion_receipt"]["path"]).read_bytes())
    value["completion_receipt"] = save_json(root, "delivery/completion.json", completion)
    value["attempt_manifests"] = [record(manifest, args["manifest_path"])]
    value["videos"] = [entry]
    index = save_json(root, "delivery/videos.json", value)
    report = downloader.archive(
        index=root / index["path"], index_sha256=index["sha256"], metadata_root=root,
        destination=tmp_path / "archive", source=downloader.Source("local", str(root)), reserve_bytes=0,
    )
    assert report["index_coverage_complete"]
    assert report["files"][0]["category"] == "technical"
    with pytest.raises(FileExistsError, match="overwrite"):
        encoder.encode(**args, codec=codec)
    assert before == (manifest.read_bytes(), original.read_bytes())


def test_real_viewport_preserves_fractional_presentation_timing(tmp_path, ffmpeg):
    args = source_case(tmp_path, ffmpeg, video=True)
    entry = encoder.encode(**args)
    source, output = entry["encoding"]["source"], entry["encoding"]["output"]
    assert source["frame_count"] == output["frame_count"] == 5
    assert source["presentation_pts_sha256"] == output["presentation_pts_sha256"]
    assert (output["fps_numerator"], output["fps_denominator"]) == (30000, 1001)
    assert entry["encoding"]["timing_basis"] == "recorded_presentation"
    assert entry["encoding"]["physical_time"]["status"] == "unavailable"
    assert entry["encoding"]["recorded_viewport_metadata"]["frame_count"] == 5


def test_odd_geometry_is_not_resized(tmp_path, ffmpeg):
    frames = np.zeros((3, 49, 65, 3), dtype=np.uint8)
    args = source_case(tmp_path, ffmpeg, frames=frames)
    entry = encoder.encode(**args)
    assert (entry["encoding"]["output"]["width"], entry["encoding"]["output"]["height"]) == (65, 49)
    assert "yuv444p" in entry["encoding"]["arguments"]


@pytest.mark.parametrize("frames", [
    np.zeros((3, 48, 64, 3), dtype=np.float32),
    np.zeros((1, 16, 3, 6, 8), dtype=np.float32),
    np.zeros((3, 48, 64, 4), dtype=np.uint8),
    np.zeros((0, 48, 64, 3), dtype=np.uint8),
])
def test_unsupported_latent_dtype_shape_rejected(tmp_path, ffmpeg, frames):
    args = source_case(tmp_path, ffmpeg, frames=frames)
    with pytest.raises(ValueError, match="THWC uint8 RGB"):
        encoder.encode(**args)
    assert not (args["root"] / args["output"]).exists()


@pytest.mark.parametrize("status", ["not_exposed", "decode_error", "latent_only_retained"])
def test_unavailable_predictions_are_not_encoded(tmp_path, ffmpeg, status):
    args = source_case(tmp_path, ffmpeg, status=status)
    with pytest.raises(ValueError, match="did not expose"):
        encoder.encode(**args)
    assert not list(args["root"].rglob("*.partial"))


@pytest.mark.parametrize("change", ["no_rate", "negative_rate", "unknown_request", "hash", "traversal"])
def test_bad_inputs_fail_without_publication(tmp_path, ffmpeg, change):
    args = source_case(tmp_path, ffmpeg)
    if change == "no_rate":
        args.pop("playback_fps")
    elif change == "negative_rate":
        args["playback_fps"] = "-15"
    elif change == "unknown_request":
        args["request_record"] = "predictions/request-9999.json"
    elif change == "hash":
        args["manifest_sha256"] = "0" * 64
    else:
        args["output"] = "viewing/../escaped.mp4"
    with pytest.raises(ValueError):
        encoder.encode(**args)
    assert not list(args["root"].rglob("*.entry.json"))


def test_space_shortfall_has_no_partial(tmp_path, ffmpeg, monkeypatch):
    args = source_case(tmp_path, ffmpeg)
    monkeypatch.setattr(encoder, "free_bytes", lambda fd: 0)
    with pytest.raises(OSError, match="required=.*available=.*shortfall="):
        encoder.encode(**args)
    assert not list(args["root"].rglob("*.partial"))


def test_failed_codec_run_retains_partial_not_final(tmp_path, ffmpeg, monkeypatch):
    args = source_case(tmp_path, ffmpeg)
    actual = encoder.run

    def fail(arguments, **kwargs):
        if "libx264" in arguments:
            raise ValueError("synthetic codec failure")
        return actual(arguments, **kwargs)

    monkeypatch.setattr(encoder, "run", fail)
    with pytest.raises(ValueError, match="retained partial.*synthetic codec failure"):
        encoder.encode(**args)
    assert len(list(args["root"].rglob("*.partial"))) == 1
    assert not (args["root"] / args["output"]).exists()
    assert not list(args["root"].rglob("*.entry.json"))


@pytest.mark.parametrize("corruption", ["count", "timing", "codec"])
def test_bad_output_measurement_never_publishes(tmp_path, ffmpeg, monkeypatch, corruption):
    args = source_case(tmp_path, ffmpeg)
    actual = encoder.probe

    def truncated(*a, **kw):
        value, points = actual(*a, **kw)
        if corruption == "count":
            value["frame_count"] -= 1
        elif corruption == "timing":
            points[-1] += 1
        else:
            value["codec"] = "rawvideo"
        return value, points

    monkeypatch.setattr(encoder, "probe", truncated)
    with pytest.raises(ValueError, match="frame count"):
        encoder.encode(**args)
    assert not (args["root"] / args["output"]).exists()


def test_cli_encodes_actual_tiny_array(tmp_path, ffmpeg):
    args = source_case(tmp_path, ffmpeg)
    completed = subprocess.run([
        sys.executable, "-m", "tools.encode_study_video",
        "--root", str(args["root"]), "--manifest", args["manifest_path"],
        "--manifest-sha256", args["manifest_sha256"], "--artifact", args["artifact"],
        "--output", args["output"], "--request-record", args["request_record"],
        "--playback-fps", "30000/1001", "--reserve-bytes", "0", "--ffmpeg", ffmpeg,
    ], capture_output=True, text=True, timeout=30)
    assert completed.returncode == 0, completed.stderr
    value = json.loads(completed.stdout)
    assert value["encoding"]["output"]["fps_numerator"] == 30000
    assert value["encoding"]["output"]["fps_denominator"] == 1001
    assert value["encoding"]["timing_basis"] == "playback_only"


def test_source_digest_change_and_symlink_output_fail(tmp_path, ffmpeg):
    args = source_case(tmp_path, ffmpeg)
    master = (args["root"] / args["manifest_path"]).parent / args["artifact"]
    destination = args["root"] / args["output"]
    destination.parent.mkdir(parents=True)
    destination.symlink_to(master)
    before = master.read_bytes()
    with pytest.raises(FileExistsError):
        encoder.encode(**args)
    assert master.read_bytes() == before
    destination.unlink()
    master.write_bytes(b"changed synthetic original")
    with pytest.raises(ValueError, match="mismatch"):
        encoder.encode(**args)
