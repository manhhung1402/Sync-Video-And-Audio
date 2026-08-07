"""SyncVideo-Audio core package."""

from .capcut_exporter import CapCutDraftExporter, CapCutExportError, CapCutExportResult

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
from .planner import PlannerConfig, SceneSpec, build_timeline, load_scene_mapping, sort_media
from .probe import FfprobeMediaProbe, MediaInfo, ProbeError

__all__ = [
    "AudioTrack",
    "CapCutDraftExporter",
    "CapCutExportError",
    "CapCutExportResult",
    "CanvasSpec",
    "MediaType",
    "MotionPreset",
    "TimelineCaption",
    "TimelineClip",
    "TimelineProject",
    "seconds_to_us",
    "us_to_seconds",
    "FfprobeMediaProbe",
    "MediaInfo",
    "PlannerConfig",
    "ProbeError",
    "SceneSpec",
    "build_timeline",
    "load_scene_mapping",
    "sort_media",
]

__version__ = "0.1.0"
