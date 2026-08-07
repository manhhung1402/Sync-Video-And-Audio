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
            duration = float(payload["format"]["duration"])
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


def _optional_int(stream: object, key: str) -> int | None:
    if not isinstance(stream, dict) or stream.get(key) is None:
        return None
    return int(stream[key])
