"""CPU-only viewing-copy encoding from one finalized recorder artifact."""
from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import uuid

from tools.download_study_videos import (
    RESERVE_BYTES, VIDEO_SUFFIXES, checked_file, decode, directory, encoding_metadata,
    free_bytes, identity, metadata, publish_json, regular_file, relative_path,
)


def executable() -> str:
    installed = shutil.which("ffmpeg")
    if installed:
        return installed
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def run(arguments: list[str], *, timeout: float, pass_fds: tuple[int, ...] = (), data: bytes = b"") -> str:
    result = subprocess.run(arguments, input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            pass_fds=pass_fds, timeout=timeout)
    if result.returncode:
        raise ValueError(f"ffmpeg exited {result.returncode}: {result.stderr.decode(errors='replace').strip()}")
    return (result.stdout + result.stderr).decode(errors="replace")


def probe(ffmpeg: str, fd: int, *, timeout: float) -> tuple[dict, list[Fraction]]:
    """Decode every frame; showinfo exposes integer PTS without rounded FPS."""
    os.lseek(fd, 0, os.SEEK_SET)
    text = run([ffmpeg, "-nostdin", "-hide_banner", "-filter_threads", "1", "-copyts", "-hwaccel", "none",
                "-threads", "1", "-noautorotate", "-i", f"/dev/fd/{fd}",
                "-map", "0:v:0", "-an", "-sn", "-dn", "-vf", "showinfo",
                "-fps_mode", "passthrough", "-f", "null", "-"], timeout=timeout, pass_fds=(fd,))
    clocks = set(re.findall(r"config in time_base: (\d+)/(\d+), frame_rate: (\d+)/(\d+)", text))
    rows = re.findall(r" n:\s*(\d+) pts:\s*(-?\d+).*? s:(\d+)x(\d+)", text)
    codecs = re.findall(r"Video: ([A-Za-z0-9_]+)", text)
    if len(clocks) != 1 or not rows or not codecs:
        raise ValueError("decoder did not expose an unambiguous frame clock, geometry and codec")
    tick_n, tick_d, rate_n, rate_d = map(int, next(iter(clocks)))
    if min(tick_n, tick_d, rate_n, rate_d) <= 0:
        raise ValueError("source presentation timing is unavailable")
    tick, rate = Fraction(tick_n, tick_d), Fraction(rate_n, rate_d)
    shapes = {(int(row[2]), int(row[3])) for row in rows}
    if len(shapes) != 1 or any(int(row[0]) != index for index, row in enumerate(rows)):
        raise ValueError("decoded geometry or frame sequence changed")
    width, height = shapes.pop()
    points = [int(row[1]) * tick for row in rows]
    if any(b - a != 1 / rate for a, b in zip(points, points[1:])):
        raise ValueError("variable or discontinuous presentation timing is unsupported; no frames will be dropped")
    return {
        "width": width, "height": height, "frame_count": len(rows),
        "fps_numerator": rate.numerator, "fps_denominator": rate.denominator,
        "codec": codecs[0], "first_pts": str(points[0]), "time_base": str(tick),
        "presentation_pts_sha256": hashlib.sha256(json.dumps([str(p) for p in points]).encode()).hexdigest(),
    }, points


def load_manifest(root: Path, path: str, digest: str) -> tuple[dict, dict]:
    parts = PurePosixPath(relative_path(path)).parts
    with directory(root, parts[:-1]) as fd, regular_file(fd, parts[-1]) as stream:
        raw = stream.read()
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("attempt manifest SHA-256 differs from pinned identity")
    manifest = decode(raw)
    if (not isinstance(manifest, dict) or manifest.get("schema_version") != "sgw-01-attempt-manifest-v1"
            or manifest.get("complete") is not True
            or not isinstance(manifest.get("artifacts"), dict)
            or not isinstance(manifest.get("result"), dict)
            or path != f"attempts/{manifest.get('cell_id')}/{manifest.get('attempt_id')}/manifest.json"):
        raise ValueError("a finalized recorder attempt manifest with matching path is required")
    return manifest, {"path": path, "bytes": len(raw), "sha256": digest}


def prediction_frames(root: Path, manifest_path: str, manifest: dict, artifact: str,
                      stream, request_record: str | None) -> tuple[object, dict]:
    import numpy as np

    if not request_record or not request_record.startswith("predictions/"):
        raise ValueError("prediction arrays require their retained predictions/request-NNNN.json")
    record_path = str(PurePosixPath(manifest_path).parent / relative_path(request_record))
    if request_record not in manifest["artifacts"]:
        raise ValueError("request record is absent from the immutable attempt manifest")
    record_identity = {"path": record_path, **identity(manifest["artifacts"][request_record])}
    request = metadata(root, record_identity)
    if not isinstance(request, dict) or request.get("future_status") not in {"decoded_unmapped", "exposed_and_retained"}:
        raise ValueError("request did not expose decoded RGB frames; latent/unavailable data cannot be encoded")
    response = request.get("raw_response")
    if not isinstance(response, dict):
        raise ValueError("request lacks raw response provenance")
    trace = response.get("native_trace", {})
    trace = trace if isinstance(trace, dict) else {}
    candidates = [response.get("future"), trace.get("future")]
    descriptors = [item for item in candidates if isinstance(item, dict) and item.get("path") == artifact]
    if not descriptors or any(item.get("sha256") != manifest["artifacts"][artifact]["sha256"] for item in descriptors):
        raise ValueError("array is not the decoded future referenced by this request")
    frames = np.load(stream, allow_pickle=False)
    if (not isinstance(frames, np.ndarray) or frames.dtype != np.uint8 or frames.ndim != 4
            or frames.shape[-1] != 3 or any(size <= 0 for size in frames.shape)):
        raise ValueError("only nonempty THWC uint8 RGB arrays are supported; no latent decoding or shape guessing")
    if any(item.get("shape") != list(frames.shape) or item.get("dtype") != "uint8" for item in descriptors):
        raise ValueError("decoded array dimensions/dtype differ from retained request metadata")
    return frames, {
        "request_record": record_identity, "future_status": request["future_status"],
        "recorded_future_metadata": response.get("future_metadata", trace.get("future_metadata")),
    }


def encode(*, root: Path, manifest_path: str, manifest_sha256: str, artifact: str, output: str,
           request_record: str | None = None, playback_fps: str | None = None, codec: str = "h264",
           crf: int = 18, preset: str = "medium", reserve_bytes: int = RESERVE_BYTES,
           timeout: float = 600, ffmpeg: str | None = None) -> dict:
    if (codec not in {"h264", "h265"} or type(crf) is not int or not 0 <= crf <= 51
            or preset not in {"ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower"}
            or type(reserve_bytes) is not int or reserve_bytes < 0
            or not math.isfinite(timeout) or timeout <= 0):
        raise ValueError("invalid codec, quality, preset, headroom or timeout")
    artifact, output = relative_path(artifact), relative_path(output)
    if not output.startswith("viewing/") or not output.endswith(".mp4"):
        raise ValueError("output must be a separate viewing/*.mp4 path")
    manifest, manifest_identity = load_manifest(root, manifest_path, manifest_sha256)
    if artifact not in manifest["artifacts"]:
        raise ValueError("source artifact is absent from the immutable attempt manifest")
    expected = identity(manifest["artifacts"][artifact])
    source_path = PurePosixPath(manifest_path).parent / artifact
    source_parts, output_parts = source_path.parts, PurePosixPath(output).parts
    sidecar = output_parts[-1] + ".entry.json"
    ffmpeg = ffmpeg or executable()
    version = run([ffmpeg, "-version"], timeout=timeout).splitlines()[0]
    with directory(root, source_parts[:-1]) as source_fd, directory(root, output_parts[:-1], create=True) as output_fd:
        for name in (output_parts[-1], sidecar):
            try:
                os.stat(name, dir_fd=output_fd, follow_symlinks=False)
            except FileNotFoundError:
                continue
            raise FileExistsError(f"refusing to overwrite viewing copy or entry: {output}")
        checked_file(source_fd, source_parts[-1], expected)
        with regular_file(source_fd, source_parts[-1]) as original:
            extra = {}
            data = b""
            if artifact.endswith(".npy") and artifact.startswith("predictions/"):
                if playback_fps is None:
                    raise ValueError("unmapped decoded frames require explicit --playback-fps (not physical FPS)")
                try:
                    rate = Fraction(playback_fps)
                except (ValueError, ZeroDivisionError) as exc:
                    raise ValueError("playback FPS must be a positive rational number") from exc
                if rate <= 0:
                    raise ValueError("playback FPS must be positive")
                frames, extra = prediction_frames(root, manifest_path, manifest, artifact, original, request_record)
                count, height, width, _ = frames.shape
                source = {"width": width, "height": height, "frame_count": count,
                          "fps_numerator": None, "fps_denominator": None}
                points = [Fraction(i, 1) / rate for i in range(count)]
                input_arguments = ["-f", "rawvideo", "-pixel_format", "rgb24", "-video_size", f"{width}x{height}",
                                   "-framerate", str(rate), "-i", "pipe:0"]
                data = frames.tobytes(order="C")
                basis = "playback_only"
            elif PurePosixPath(artifact).suffix.lower() in VIDEO_SUFFIXES:
                if playback_fps is not None or request_record is not None:
                    raise ValueError("existing videos retain their recorded presentation timing, not an override")
                source, points = probe(ffmpeg, original.fileno(), timeout=timeout)
                rate = Fraction(source["fps_numerator"], source["fps_denominator"])
                width, height, count = (source[key] for key in ("width", "height", "frame_count"))
                registered = manifest.get("result", {}).get("viewport_artifact")
                if isinstance(registered, dict) and registered.get("path") == artifact:
                    if (identity(registered) != expected or registered.get("frame_count") != count
                            or not isinstance(registered.get("fps"), (int, float))
                            or not math.isclose(registered["fps"], float(rate), rel_tol=1e-6, abs_tol=1e-9)):
                        raise ValueError("video measurements differ from recorder viewport metadata")
                    extra["recorded_viewport_metadata"] = registered
                extra["recorded_episode_mapping"] = manifest["result"].get("episode_mapping")
                input_arguments = ["-copyts", "-hwaccel", "none", "-threads", "1", "-noautorotate",
                                   "-i", f"/dev/fd/{original.fileno()}"]
                basis = "recorded_presentation"
            else:
                raise ValueError("source must be an existing video or exposed predictions/*.npy RGB array")
            # A conservative reservation plus an explicit encoder size cap; a
            # capped/truncated result still fails the full decoded-frame check.
            budget = width * height * count * 3 * 2 + 1024**2
            available = free_bytes(output_fd)
            if available < budget + reserve_bytes:
                raise OSError(f"insufficient encoding space: required={budget + reserve_bytes}, "
                              f"available={available}, shortfall={budget + reserve_bytes - available}")
            temporary = f".encode-{uuid.uuid4().hex}.partial"
            created = os.open(temporary, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=output_fd)
            with os.fdopen(created, "r+b") as encoded:
                command = [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error",
                           "-filter_threads", "1", *input_arguments,
                           "-map", "0:v:0", "-an", "-sn", "-dn", "-c:v", "libx264" if codec == "h264" else "libx265",
                           "-threads", "1",
                           *(["-x265-params", "pools=1:frame-threads=1"] if codec == "h265" else []),
                           "-preset", preset, "-crf", str(crf),
                           "-pix_fmt", "yuv444p" if width % 2 or height % 2 else "yuv420p",
                           "-fps_mode", "passthrough", "-video_track_timescale",
                           str(math.lcm(rate.numerator, *(point.denominator for point in points))),
                           "-fs", str(budget), "-f", "mp4", "-y", f"/dev/fd/{encoded.fileno()}"]
                try:
                    original.seek(0)
                    run(command, timeout=timeout, pass_fds=(original.fileno(), encoded.fileno()), data=data)
                    os.fsync(encoded.fileno())
                    observed, output_points = probe(ffmpeg, encoded.fileno(), timeout=timeout)
                    if (any(observed[key] != source[key] for key in ("width", "height", "frame_count"))
                            or output_points != points or observed["codec"] != ("h264" if codec == "h264" else "hevc")):
                        raise ValueError("encoded codec, decoded geometry/frame count or presentation timestamps changed")
                    if Fraction(observed["fps_numerator"], observed["fps_denominator"]) != rate:
                        raise ValueError("encoded presentation rate changed")
                    encoded.seek(0)
                    digest = hashlib.file_digest(encoded, "sha256").hexdigest()
                    size = os.fstat(encoded.fileno()).st_size
                    if not 0 < size <= budget:
                        raise ValueError("encoded byte length exceeds reserved output budget")
                    checked_file(source_fd, source_parts[-1], expected)
                    entry = {
                        "path": output, "bytes": size, "sha256": digest,
                        "original": {"manifest_path": manifest_path, "path": artifact, **expected},
                        "encoding": {
                            "codec": codec, "encoder": version, "arguments": command,
                            "source": source, "output": observed, "timing_basis": basis,
                            "physical_time": {"status": "unavailable"}, "attempt_manifest": manifest_identity,
                            "source_path": str(source_path), "output_path": output, **extra,
                        },
                    }
                    encoding_metadata(entry["encoding"], root)
                    os.link(temporary, output_parts[-1], src_dir_fd=output_fd, dst_dir_fd=output_fd,
                            follow_symlinks=False)
                    os.fsync(output_fd)
                    publish_json(output_fd, sidecar, entry)
                    os.unlink(temporary, dir_fd=output_fd)
                    os.fsync(output_fd)
                    return entry
                except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
                    raise ValueError(f"encoding failed; retained partial {PurePosixPath(*output_parts[:-1], temporary)}: "
                                     f"{exc}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--manifest", dest="manifest_path", required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--artifact", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--request-record")
    parser.add_argument("--playback-fps")
    parser.add_argument("--codec", choices=("h264", "h265"), default="h264")
    parser.add_argument("--crf", type=int, default=18)
    parser.add_argument("--preset", default="medium")
    parser.add_argument("--reserve-bytes", type=int, default=RESERVE_BYTES)
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--ffmpeg")
    try:
        entry = encode(**vars(parser.parse_args()))
    except (OSError, ValueError, ImportError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps(entry, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
