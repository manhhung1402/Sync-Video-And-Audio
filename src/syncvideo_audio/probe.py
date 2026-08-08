"""Media metadata probing through ffprobe."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .manifest import seconds_to_us
from .runtime import hidden_subprocess_kwargs, resolve_executable


class ProbeError(RuntimeError):
    """Raised when media metadata cannot be determined."""


@dataclass(frozen=True, slots=True)
class MediaInfo:
    duration_us: int
    width: int | None = None
    height: int | None = None
    codec: str | None = None


class MediaProbe(Protocol):
    def probe(self, path: Path) -> MediaInfo: ...


class FfprobeMediaProbe:
    def __init__(self, executable: str = "ffprobe") -> None:
        self.executable = executable

    def probe(self, path: Path) -> MediaInfo:
        source = Path(path)
        if not source.is_file():
            raise ProbeError(f"media file does not exist: {source}")
        executable = resolve_executable(self.executable)
        command = [
            executable,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(source),
        ]
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=True,
                **hidden_subprocess_kwargs(),
            )
        except FileNotFoundError as error:
            raise ProbeError(f"ffprobe executable was not found: {executable}") from error
        except subprocess.CalledProcessError as error:
            detail = (error.stderr or "").strip()
            raise ProbeError(f"ffprobe failed for {source}: {detail}") from error

        try:
            payload = json.loads(result.stdout)
            streams = payload.get("streams", [])
            duration = _duration_from_probe_payload(payload, streams)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise ProbeError(f"ffprobe returned invalid duration for {source}") from error

        video_stream = next(
            (stream for stream in payload.get("streams", []) if stream.get("codec_type") == "video"),
            None,
        )
        return MediaInfo(
            duration_us=seconds_to_us(duration),
            width=_optional_int(video_stream, "width"),
            height=_optional_int(video_stream, "height"),
            codec=str(video_stream["codec_name"]) if video_stream and video_stream.get("codec_name") else None,
        )


def _duration_from_probe_payload(payload: object, streams: object) -> float:
    """Read duration from format metadata, with a stream-level WAV fallback."""

    if isinstance(payload, dict):
        format_info = payload.get("format")
        if isinstance(format_info, dict) and format_info.get("duration") not in (None, "N/A", ""):
            duration = float(format_info["duration"])
            if duration > 0:
                return duration

    candidates = streams if isinstance(streams, list) else []
    # Prefer an audio stream for audio-only files. Some WAV variants expose a
    # duration only on the stream and omit it from the top-level format.
    ordered = [
        *[item for item in candidates if isinstance(item, dict) and item.get("codec_type") == "audio"],
        *[item for item in candidates if isinstance(item, dict) and item.get("codec_type") != "audio"],
    ]
    for stream in ordered:
        raw_duration = stream.get("duration")
        if raw_duration not in (None, "N/A", ""):
            duration = float(raw_duration)
            if duration > 0:
                return duration
        duration_ts = stream.get("duration_ts")
        time_base = stream.get("time_base")
        if duration_ts not in (None, "N/A", "") and time_base:
            numerator, separator, denominator = str(time_base).partition("/")
            if separator and int(denominator) > 0:
                duration = int(duration_ts) * int(numerator) / int(denominator)
                if duration > 0:
                    return duration
    raise ValueError("no positive duration")


def _optional_int(stream: object, key: str) -> int | None:
    if not isinstance(stream, dict) or stream.get(key) is None:
        return None
    return int(stream[key])
