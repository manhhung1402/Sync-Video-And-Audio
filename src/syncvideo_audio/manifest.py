"""Versioned, backend-neutral timeline manifest.

All timeline values are stored as integer microseconds.  The manifest is the
contract between synchronization/planning and output backends such as CapCut
and FFmpeg.
"""

from __future__ import annotations

import json
import math
import os
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping


SCHEMA_VERSION = 1
MICROSECONDS_PER_SECOND = 1_000_000


def seconds_to_us(value: float) -> int:
    """Convert finite seconds to rounded integer microseconds."""

    if not math.isfinite(value):
        raise ValueError("seconds must be finite")
    return int(round(value * MICROSECONDS_PER_SECOND))


def us_to_seconds(value: int) -> float:
    """Convert integer microseconds to seconds."""

    return value / MICROSECONDS_PER_SECOND


class MediaType(str, Enum):
    IMAGE = "image"
    VIDEO = "video"


class MotionPreset(str, Enum):
    NONE = "none"
    ZOOM_IN = "zoom_in"
    ZOOM_OUT = "zoom_out"
    PAN_LEFT_RIGHT = "pan_left_right"
    PAN_RIGHT_LEFT = "pan_right_left"
    PAN_TOP_BOTTOM = "pan_top_bottom"
    PAN_BOTTOM_TOP = "pan_bottom_top"


@dataclass(frozen=True, slots=True)
class CanvasSpec:
    width: int = 1920
    height: int = 1080
    fps: int = 30

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("canvas width and height must be positive")
        if not 1 <= self.fps <= 240:
            raise ValueError("canvas fps must be between 1 and 240")

    def to_dict(self) -> dict[str, int]:
        return {"width": self.width, "height": self.height, "fps": self.fps}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CanvasSpec":
        return cls(width=int(data["width"]), height=int(data["height"]), fps=int(data["fps"]))


@dataclass(frozen=True, slots=True)
class AudioTrack:
    path: Path
    duration_us: int
    volume: float = 1.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", Path(self.path))
        if self.duration_us <= 0:
            raise ValueError("audio duration must be positive")
        if self.volume < 0:
            raise ValueError("audio volume cannot be negative")

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "durationUs": self.duration_us,
            "volume": self.volume,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AudioTrack":
        return cls(
            path=Path(str(data["path"])),
            duration_us=int(data["durationUs"]),
            volume=float(data.get("volume", 1.0)),
        )


@dataclass(frozen=True, slots=True)
class TimelineClip:
    media_type: MediaType
    path: Path
    start_us: int
    duration_us: int
    source_start_us: int = 0
    source_duration_us: int | None = None
    speed: float = 1.0
    volume: float = 0.0
    motion: MotionPreset = MotionPreset.NONE
    scene_index: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "media_type", MediaType(self.media_type))
        object.__setattr__(self, "path", Path(self.path))
        object.__setattr__(self, "motion", MotionPreset(self.motion))
        if self.start_us < 0:
            raise ValueError("clip start cannot be negative")
        if self.duration_us <= 0:
            raise ValueError("clip duration must be positive")
        if self.source_start_us < 0:
            raise ValueError("source start cannot be negative")
        if self.source_duration_us is not None and self.source_duration_us <= 0:
            raise ValueError("source duration must be positive when provided")
        if not math.isfinite(self.speed) or self.speed <= 0:
            raise ValueError("clip speed must be finite and positive")
        if self.volume < 0:
            raise ValueError("clip volume cannot be negative")
        if self.media_type is MediaType.VIDEO and self.motion is not MotionPreset.NONE:
            raise ValueError("motion presets are only valid for still images")

    @property
    def end_us(self) -> int:
        return self.start_us + self.duration_us

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "type": self.media_type.value,
            "path": str(self.path),
            "startUs": self.start_us,
            "durationUs": self.duration_us,
            "sourceStartUs": self.source_start_us,
            "speed": self.speed,
            "volume": self.volume,
            "motion": self.motion.value,
        }
        if self.source_duration_us is not None:
            data["sourceDurationUs"] = self.source_duration_us
        if self.scene_index is not None:
            data["sceneIndex"] = self.scene_index
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TimelineClip":
        return cls(
            media_type=MediaType(str(data["type"])),
            path=Path(str(data["path"])),
            start_us=int(data["startUs"]),
            duration_us=int(data["durationUs"]),
            source_start_us=int(data.get("sourceStartUs", 0)),
            source_duration_us=(
                int(data["sourceDurationUs"]) if data.get("sourceDurationUs") is not None else None
            ),
            speed=float(data.get("speed", 1.0)),
            volume=float(data.get("volume", 0.0)),
            motion=MotionPreset(str(data.get("motion", MotionPreset.NONE.value))),
            scene_index=(int(data["sceneIndex"]) if data.get("sceneIndex") is not None else None),
        )


@dataclass(frozen=True, slots=True)
class TimelineCaption:
    text: str
    start_us: int
    duration_us: int

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("caption text cannot be blank")
        if self.start_us < 0:
            raise ValueError("caption start cannot be negative")
        if self.duration_us <= 0:
            raise ValueError("caption duration must be positive")

    @property
    def end_us(self) -> int:
        return self.start_us + self.duration_us

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "startUs": self.start_us, "durationUs": self.duration_us}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TimelineCaption":
        return cls(
            text=str(data["text"]),
            start_us=int(data["startUs"]),
            duration_us=int(data["durationUs"]),
        )


@dataclass(slots=True)
class TimelineProject:
    name: str
    canvas: CanvasSpec
    audio: AudioTrack
    clips: list[TimelineClip] = field(default_factory=list)
    captions: list[TimelineCaption] = field(default_factory=list)
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("project name cannot be blank")
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"unsupported timeline schema version: {self.schema_version}")
        self.clips = list(self.clips)
        self.captions = list(self.captions)
        self.validate()

    @property
    def duration_us(self) -> int:
        return self.audio.duration_us

    def validate(self) -> None:
        """Validate main-track ordering, bounds, and caption bounds."""

        previous_end = 0
        for index, clip in enumerate(self.clips):
            if clip.start_us < previous_end:
                raise ValueError(f"clip {index} overlaps the previous visual clip")
            if clip.end_us > self.duration_us:
                raise ValueError(f"clip {index} exceeds project duration")
            previous_end = clip.end_us
        for index, caption in enumerate(self.captions):
            if caption.end_us > self.duration_us:
                raise ValueError(f"caption {index} exceeds project duration")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "name": self.name,
            "durationUs": self.duration_us,
            "canvas": self.canvas.to_dict(),
            "audio": self.audio.to_dict(),
            "clips": [clip.to_dict() for clip in self.clips],
            "captions": [caption.to_dict() for caption in self.captions],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TimelineProject":
        project = cls(
            schema_version=int(data.get("schemaVersion", 0)),
            name=str(data["name"]),
            canvas=CanvasSpec.from_dict(data["canvas"]),
            audio=AudioTrack.from_dict(data["audio"]),
            clips=[TimelineClip.from_dict(item) for item in _mapping_list(data.get("clips", []), "clips")],
            captions=[
                TimelineCaption.from_dict(item)
                for item in _mapping_list(data.get("captions", []), "captions")
            ],
        )
        if "durationUs" in data and int(data["durationUs"]) != project.duration_us:
            raise ValueError("manifest duration does not match audio duration")
        return project

    def write_json(self, destination: str | Path) -> Path:
        """Atomically write a UTF-8 JSON manifest."""

        output = Path(destination)
        output.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n"
        handle, temporary_name = tempfile.mkstemp(
            dir=output.parent,
            prefix=f".{output.name}.",
            suffix=".tmp",
            text=True,
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, output)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
        return output

    @classmethod
    def read_json(cls, source: str | Path) -> "TimelineProject":
        data = json.loads(Path(source).read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("timeline manifest root must be an object")
        return cls.from_dict(data)


def _mapping_list(value: Any, field_name: str) -> Iterable[Mapping[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError(f"{field_name} must be a list of objects")
    return value

