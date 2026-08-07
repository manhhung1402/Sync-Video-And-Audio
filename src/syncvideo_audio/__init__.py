"""SyncVideo-Audio core package."""

from .manifest import (
    AudioTrack,
    CanvasSpec,
    MediaType,
    MotionPreset,
    TimelineCaption,
    TimelineClip,
    TimelineProject,
    seconds_to_us,
    us_to_seconds,
)

__all__ = [
    "AudioTrack",
    "CanvasSpec",
    "MediaType",
    "MotionPreset",
    "TimelineCaption",
    "TimelineClip",
    "TimelineProject",
    "seconds_to_us",
    "us_to_seconds",
]

__version__ = "0.1.0"

