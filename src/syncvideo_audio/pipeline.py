"""Application service that fans one timeline out to hand-off formats."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path

from .capcut_exporter import CapCutDraftExporter, CapCutExportResult, safe_folder_name
from .capcut_registry import CapCutRegistry
from .ffmpeg_renderer import FfmpegRenderer
from .manifest import TimelineProject
from .runtime import ProgressCallback, report_progress


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
    burn_captions: bool = False,
    renderer: FfmpegRenderer | None = None,
    capcut_exporter: CapCutDraftExporter | None = None,
    registry: CapCutRegistry | None = None,
    progress_callback: ProgressCallback | None = None,
) -> PipelineOutputs:
    mode = OutputMode(mode)
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    active_registry = registry or CapCutRegistry.discover() if mode in (OutputMode.CAPCUT, OutputMode.BOTH) else registry
    root = (
        Path(draft_root).resolve()
        if draft_root
        else _require_draft_root(active_registry)
        if mode in (OutputMode.CAPCUT, OutputMode.BOTH)
        else None
    )
    project = replace(project, name=_unique_project_name(project.name, output, root, mode))
    stem = _safe_file_stem(project.name)
    report_progress(progress_callback, 0.05, "Đang ghi timeline manifest…")
    manifest = project.write_json(output / f"{stem}.timeline.json")

    mp4_path: Path | None = None
    capcut_result: CapCutExportResult | None = None
    registered = False
    if mode in (OutputMode.MP4, OutputMode.BOTH):
        mp4_path = (renderer or FfmpegRenderer()).render(
            project,
            output / f"{stem}.mp4",
            overwrite=overwrite_mp4,
            burn_captions=burn_captions,
            progress_callback=lambda value, message: report_progress(
                progress_callback, 0.20 + value * 0.62, message
            ),
        )
    if mode in (OutputMode.CAPCUT, OutputMode.BOTH):
        capcut_result = (capcut_exporter or CapCutDraftExporter()).export(
            project,
            root,
            folder_name=project.name,
            progress_callback=lambda value, message: report_progress(
                progress_callback, 0.84 + value * 0.14, message
            ),
        )
        if register_with_capcut and active_registry:
            active_registry.register(capcut_result)
            registered = True
    report_progress(progress_callback, 1.0, "Đã hoàn tất hand-off")
    return PipelineOutputs(manifest, mp4_path, capcut_result, registered)


def _require_draft_root(registry: CapCutRegistry | None) -> Path:
    if registry is None:
        raise ValueError("CapCut draft root was not provided and CapCut Desktop was not detected")
    return registry.draft_root()


def _safe_file_stem(value: str) -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip(" .")
    return value or "timeline"


def _unique_project_name(
    value: str,
    output: Path,
    draft_root: Path | None,
    mode: OutputMode,
) -> str:
    base = value.strip() or "Video mới"
    candidate = base
    index = 1
    while _project_name_conflicts(candidate, output, draft_root, mode):
        index += 1
        candidate = f"{base} ({index})"
    return candidate


def _project_name_conflicts(
    name: str,
    output: Path,
    draft_root: Path | None,
    mode: OutputMode,
) -> bool:
    stem = _safe_file_stem(name)
    if mode in (OutputMode.MP4, OutputMode.BOTH):
        if (output / f"{stem}.timeline.json").exists() or (output / f"{stem}.mp4").exists():
            return True
    return mode in (OutputMode.CAPCUT, OutputMode.BOTH) and draft_root is not None and (
        draft_root / safe_folder_name(name)
    ).exists()
