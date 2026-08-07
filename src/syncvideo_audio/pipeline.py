"""Application service that fans one timeline out to hand-off formats."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .capcut_exporter import CapCutDraftExporter, CapCutExportResult
from .capcut_registry import CapCutRegistry
from .ffmpeg_renderer import FfmpegRenderer
from .manifest import TimelineProject


class OutputMode(str, Enum):
    MP4 = "mp4"
    CAPCUT = "capcut"
    BOTH = "both"


@dataclass(frozen=True, slots=True)
class PipelineOutputs:
    manifest: Path
    mp4: Path | None = None
    capcut: CapCutExportResult | None = None
    registered_with_capcut: bool = False


def export_timeline(
    project: TimelineProject,
    *,
    mode: OutputMode,
    output_dir: str | Path,
    draft_root: str | Path | None = None,
    register_with_capcut: bool = True,
    overwrite_mp4: bool = False,
    renderer: FfmpegRenderer | None = None,
    capcut_exporter: CapCutDraftExporter | None = None,
    registry: CapCutRegistry | None = None,
) -> PipelineOutputs:
    mode = OutputMode(mode)
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    stem = _safe_file_stem(project.name)
    manifest = project.write_json(output / f"{stem}.timeline.json")

    mp4_path: Path | None = None
    capcut_result: CapCutExportResult | None = None
    registered = False
    if mode in (OutputMode.MP4, OutputMode.BOTH):
        mp4_path = (renderer or FfmpegRenderer()).render(
            project,
            output / f"{stem}.mp4",
            overwrite=overwrite_mp4,
        )
    if mode in (OutputMode.CAPCUT, OutputMode.BOTH):
        active_registry = registry or CapCutRegistry.discover()
        root = Path(draft_root).resolve() if draft_root else _require_draft_root(active_registry)
        capcut_result = (capcut_exporter or CapCutDraftExporter()).export(
            project,
            root,
            folder_name=project.name,
        )
        if register_with_capcut and active_registry:
            active_registry.register(capcut_result)
            registered = True
    return PipelineOutputs(manifest, mp4_path, capcut_result, registered)


def _require_draft_root(registry: CapCutRegistry | None) -> Path:
    if registry is None:
        raise ValueError("CapCut draft root was not provided and CapCut Desktop was not detected")
    return registry.draft_root()


def _safe_file_stem(value: str) -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip(" .")
    return value or "timeline"
