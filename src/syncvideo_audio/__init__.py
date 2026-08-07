"""SyncVideo-Audio core package."""

from .capcut_exporter import CapCutDraftExporter, CapCutExportError, CapCutExportResult
from .capcut_keyframes import MotionSettings, apply_motion_keyframes
from .capcut_registry import CapCutRegistry
from .ffmpeg_renderer import FfmpegRenderer, RenderConfig, RenderError

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
from .planner import AlignmentMode, PlannerConfig, SceneSpec, build_timeline, load_scene_mapping, sort_media
from .pipeline import OutputMode, PipelineOutputs, export_timeline
from .probe import FfprobeMediaProbe, MediaInfo, ProbeError

__all__ = [
    "AudioTrack",
    "AlignmentMode",
    "CapCutDraftExporter",
    "CapCutExportError",
    "CapCutExportResult",
    "CapCutRegistry",
    "CanvasSpec",
    "MediaType",
    "MotionPreset",
    "MotionSettings",
    "FfmpegRenderer",
    "OutputMode",
    "PipelineOutputs",
    "TimelineCaption",
    "TimelineClip",
    "TimelineProject",
    "seconds_to_us",
    "us_to_seconds",
    "FfprobeMediaProbe",
    "MediaInfo",
    "PlannerConfig",
    "ProbeError",
    "RenderConfig",
    "RenderError",
    "SceneSpec",
    "build_timeline",
    "export_timeline",
    "apply_motion_keyframes",
    "load_scene_mapping",
    "sort_media",
]

__version__ = "0.1.0"
