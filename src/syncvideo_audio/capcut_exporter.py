"""Atomic exporter for editable CapCut Desktop native drafts."""

from __future__ import annotations

import json
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .capcut_keyframes import MotionSettings, apply_motion_keyframes
from .capcut_schema import (
    add_audio,
    add_visual_clip,
    capcut_id,
    make_content,
    make_meta,
    make_timeline_project,
    make_track,
)
from .manifest import MediaType, TimelineProject
from .probe import FfprobeMediaProbe, MediaInfo, MediaProbe, ProbeError
from .runtime import ProgressCallback, report_progress


class CapCutExportError(RuntimeError):
    """Raised when a native draft cannot be safely exported."""


@dataclass(frozen=True, slots=True)
class CapCutExportResult:
    draft_folder: Path
    draft_id: str
    timeline_id: str
    copied_assets: tuple[Path, ...]


class CapCutDraftExporter:
    def __init__(
        self,
        probe: MediaProbe | None = None,
        motion_settings: MotionSettings = MotionSettings(),
    ) -> None:
        self.probe = probe or FfprobeMediaProbe()
        self.motion_settings = motion_settings

    def export(
        self,
        project: TimelineProject,
        draft_root: str | Path,
        *,
        folder_name: str | None = None,
        copy_assets: bool = True,
        progress_callback: ProgressCallback | None = None,
    ) -> CapCutExportResult:
        """Create a complete draft directory without exposing partial output."""

        root = Path(draft_root).resolve()
        root.mkdir(parents=True, exist_ok=True)
        name = _safe_folder_name(folder_name or project.name)
        destination = root / name
        if destination.exists():
            raise FileExistsError(f"CapCut draft already exists: {destination}")

        staging = root / f".{name}.{capcut_id()}.tmp"
        draft_id = capcut_id()
        timeline_id = capcut_id()
        timestamp_us = time.time_ns() // 1_000
        copied_assets: list[Path] = []
        try:
            staging.mkdir()
            assets = staging / "Resources" / "syncvideo_media"
            staged_asset_paths = self._prepare_assets(
                project, assets, copy_assets, copied_assets, progress_callback
            )
            asset_paths = {
                source: (destination / path.relative_to(staging) if copy_assets else path)
                for source, path in staged_asset_paths.items()
            }
            content = self._build_content(project, timeline_id, timestamp_us, asset_paths)
            self._write_structure(
                staging, destination, project, draft_id, timeline_id, timestamp_us, content
            )
            _validate_content_references(content)
            os.replace(staging, destination)
        except BaseException:
            if staging.exists():
                shutil.rmtree(staging)
            raise

        final_assets = tuple(destination / path.relative_to(staging) for path in copied_assets)
        report_progress(progress_callback, 1.0, "Đã tạo xong CapCut draft")
        return CapCutExportResult(destination, draft_id, timeline_id, final_assets)

    def _prepare_assets(
        self,
        project: TimelineProject,
        assets: Path,
        copy_assets: bool,
        copied_assets: list[Path],
        progress_callback: ProgressCallback | None,
    ) -> dict[Path, Path]:
        sources = [project.audio.path, *(clip.path for clip in project.clips)]
        unique: dict[Path, Path] = {}
        for index, source_value in enumerate(sources):
            report_progress(
                progress_callback,
                0.05 + 0.45 * index / max(1, len(sources)),
                f"Đang copy asset {index + 1}/{len(sources)}…",
            )
            source = Path(source_value).resolve()
            if not source.is_file():
                raise FileNotFoundError(f"media file does not exist: {source}")
            if source in unique:
                continue
            if copy_assets:
                assets.mkdir(parents=True, exist_ok=True)
                target = assets / f"{len(unique) + 1:04d}_{source.name}"
                shutil.copy2(source, target)
                unique[source] = target
                copied_assets.append(target)
            else:
                unique[source] = source
        return unique

    def _build_content(
        self,
        project: TimelineProject,
        timeline_id: str,
        timestamp_us: int,
        asset_paths: dict[Path, Path],
    ) -> dict[str, Any]:
        content = make_content(project, timeline_id, timestamp_us)
        visual_segments: list[dict[str, Any]] = []
        for clip in project.clips:
            source = clip.path.resolve()
            info = self._visual_info(clip.media_type, source, project)
            segment = add_visual_clip(content, clip, asset_paths[source], info)
            apply_motion_keyframes(
                segment,
                clip.motion,
                clip.duration_us,
                self.motion_settings,
            )
            visual_segments.append(segment)
        if visual_segments:
            content["tracks"].append(make_track("video", visual_segments))
        audio_segment = add_audio(content, project, asset_paths[project.audio.path.resolve()])
        content["tracks"].append(make_track("audio", [audio_segment]))
        return content

    def _visual_info(self, media_type: MediaType, source: Path, project: TimelineProject) -> MediaInfo:
        try:
            info = self.probe.probe(source)
        except ProbeError:
            if media_type is MediaType.VIDEO:
                raise
            return MediaInfo(0, project.canvas.width, project.canvas.height)
        if media_type is MediaType.VIDEO and info.duration_us <= 0:
            raise CapCutExportError(f"video duration is unavailable: {source}")
        return info

    @staticmethod
    def _write_structure(
        staging: Path,
        destination: Path,
        project: TimelineProject,
        draft_id: str,
        timeline_id: str,
        timestamp_us: int,
        content: dict[str, Any],
    ) -> None:
        timeline_dir = staging / "Timelines" / timeline_id
        timeline_dir.mkdir(parents=True)
        _write_json(staging / "draft_content.json", content)
        _write_json(timeline_dir / "draft_content.json", content)
        _write_json(
            staging / "draft_meta_info.json",
            make_meta(project, draft_id, destination, timestamp_us),
        )
        _write_json(staging / "Timelines" / "project.json", make_timeline_project(timeline_id, timestamp_us))
        _write_json(staging / "timeline_layout.json", {
            "dockItems": [{
                "dockIndex": 0, "ratio": 1, "timelineIds": [timeline_id],
                "timelineNames": ["Timeline 01"],
            }],
            "layoutOrientation": 1,
        })
        _write_json(staging / "draft_agency_config.json", {
            "is_auto_agency_enabled": False,
            "is_auto_agency_popup": False,
            "is_single_agency_mode": False,
            "marterials": None,
            "use_converter": False,
            "video_resolution": 720,
        })
        (staging / "draft_biz_config.json").write_text("", encoding="utf-8")
        (staging / "draft_settings").write_text(
            f"[General]\ndraft_create_time={timestamp_us // 1_000_000}\n"
            f"draft_last_edit_time={timestamp_us // 1_000_000}\nreal_edit_seconds=0\nreal_edit_keys=0\n",
            encoding="utf-8",
        )
        _write_json(staging / "draft_virtual_store.json", {"draft_materials": [], "draft_virtual_store": []})
        _write_json(staging / "key_value.json", {})


def safe_folder_name(value: str) -> str:
    invalid = '<>:"/\\|?*'
    cleaned = "".join("_" if char in invalid or ord(char) < 32 else char for char in value).strip(" .")
    if not cleaned:
        raise ValueError("CapCut draft folder name is empty after sanitization")
    return cleaned


_safe_folder_name = safe_folder_name


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def _validate_content_references(content: dict[str, Any]) -> None:
    material_ids = {
        item["id"]
        for bucket in content["materials"].values()
        for item in bucket
        if isinstance(item, dict) and "id" in item
    }
    segment_ids: set[str] = set()
    for track in content["tracks"]:
        for segment in track["segments"]:
            if segment["id"] in segment_ids:
                raise CapCutExportError(f"duplicate segment id: {segment['id']}")
            segment_ids.add(segment["id"])
            if segment["material_id"] not in material_ids:
                raise CapCutExportError(f"missing material: {segment['material_id']}")
            missing = set(segment["extra_material_refs"]) - material_ids
            if missing:
                raise CapCutExportError(f"missing extra materials: {sorted(missing)}")
