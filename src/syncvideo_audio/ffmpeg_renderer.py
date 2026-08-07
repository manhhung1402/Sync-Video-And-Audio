"""MP4 preview backend driven by the same timeline manifest as CapCut."""

from __future__ import annotations

import os
import math
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .manifest import MediaType, MotionPreset, TimelineClip, TimelineProject, us_to_seconds
from .runtime import (
    ProgressCallback,
    hidden_subprocess_kwargs,
    report_progress,
    resolve_executable,
    resource_path,
)


class RenderError(RuntimeError):
    """Raised when FFmpeg cannot render the timeline."""


@dataclass(frozen=True, slots=True)
class RenderConfig:
    ffmpeg: str = "ffmpeg"
    crf: int = 18
    preset: str = "medium"
    audio_bitrate: str = "192k"

    def __post_init__(self) -> None:
        if not 0 <= self.crf <= 51:
            raise ValueError("CRF must be between 0 and 51")


class FfmpegRenderer:
    def __init__(self, config: RenderConfig = RenderConfig()) -> None:
        self.config = config

    def render(
        self,
        project: TimelineProject,
        destination: str | Path,
        *,
        overwrite: bool = False,
        burn_captions: bool = False,
        progress_callback: ProgressCallback | None = None,
    ) -> Path:
        output = Path(destination).resolve()
        if output.exists() and not overwrite:
            raise FileExistsError(f"render output already exists: {output}")
        if not project.clips:
            raise RenderError("timeline has no visual clips")
        output.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(prefix=f".{output.stem}.", dir=output.parent) as temporary_name:
            temporary = Path(temporary_name)
            normalized: list[Path] = []
            for index, clip in enumerate(project.clips):
                report_progress(
                    progress_callback,
                    0.05 + 0.68 * index / len(project.clips),
                    f"Đang render media {index + 1}/{len(project.clips)}…",
                )
                clip_output = temporary / f"clip-{index:05d}.mp4"
                frame_count = _timeline_frame_count(project, clip, index == len(project.clips) - 1)
                self._render_clip(project, clip, clip_output, frame_count)
                normalized.append(clip_output)
            visual = temporary / "visual.mp4"
            report_progress(progress_callback, 0.76, "Đang ghép các đoạn hình…")
            self._concat(normalized, visual, temporary / "concat.txt")
            if burn_captions and project.captions:
                captioned = temporary / "captioned.mp4"
                report_progress(progress_callback, 0.84, "Đang burn caption vào MP4…")
                self._burn_captions(project, visual, captioned, temporary / "captions.ass")
                visual = captioned
            final = temporary / "final.mp4"
            report_progress(progress_callback, 0.94, "Đang ghép audio vào MP4…")
            self._merge_audio(project, visual, final)
            os.replace(final, output)
        report_progress(progress_callback, 1.0, "Đã tạo xong MP4 preview")
        return output

    def _render_clip(
        self,
        project: TimelineProject,
        clip: TimelineClip,
        output: Path,
        frame_count: int,
    ) -> None:
        ffmpeg = resolve_executable(self.config.ffmpeg)
        if clip.media_type is MediaType.IMAGE:
            command = [
                ffmpeg, "-y", "-loglevel", "error",
                "-loop", "1", "-framerate", str(project.canvas.fps),
                "-i", str(clip.path),
                "-an", "-vf", build_image_filter(project, clip),
                "-frames:v", str(frame_count), "-r", str(project.canvas.fps),
                *self._video_encoder(), str(output),
            ]
        else:
            source_duration = clip.source_duration_us or round(clip.duration_us * clip.speed)
            command = [
                ffmpeg, "-y", "-loglevel", "error",
                "-ss", f"{us_to_seconds(clip.source_start_us):.6f}",
                "-t", f"{us_to_seconds(source_duration):.6f}",
                "-i", str(clip.path), "-an",
                "-vf", build_video_filter(project, clip),
                "-frames:v", str(frame_count), "-r", str(project.canvas.fps),
                *self._video_encoder(), str(output),
            ]
        self._run(command)

    def _concat(self, clips: Sequence[Path], output: Path, list_file: Path) -> None:
        lines = [f"file '{_concat_escape(path.resolve())}'" for path in clips]
        list_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self._run([
            resolve_executable(self.config.ffmpeg), "-y", "-loglevel", "error",
            "-f", "concat", "-safe", "0", "-i", str(list_file),
            "-c", "copy", str(output),
        ])

    def _merge_audio(self, project: TimelineProject, visual: Path, output: Path) -> None:
        self._run([
            resolve_executable(self.config.ffmpeg), "-y", "-loglevel", "error",
            "-i", str(visual), "-i", str(project.audio.path),
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "copy", "-c:a", "aac", "-b:a", self.config.audio_bitrate,
            "-t", f"{us_to_seconds(project.duration_us):.6f}", "-shortest", str(output),
        ])

    def _burn_captions(
        self,
        project: TimelineProject,
        visual: Path,
        output: Path,
        subtitle_file: Path,
    ) -> None:
        subtitle_file.write_text(build_ass_subtitles(project), encoding="utf-8")
        fonts_dir = resource_path("assets/fonts")
        subtitle_filter = f"ass=filename='{_ffmpeg_filter_path(subtitle_file)}'"
        if fonts_dir.is_dir():
            subtitle_filter += f":fontsdir='{_ffmpeg_filter_path(fonts_dir)}'"
        self._run([
            resolve_executable(self.config.ffmpeg),
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(visual),
            "-an",
            "-vf",
            subtitle_filter,
            *self._video_encoder(),
            str(output),
        ])

    def _video_encoder(self) -> list[str]:
        return [
            "-c:v", "libx264", "-crf", str(self.config.crf),
            "-preset", self.config.preset, "-pix_fmt", "yuv420p",
        ]

    @staticmethod
    def _run(command: Sequence[str]) -> None:
        try:
            subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                **hidden_subprocess_kwargs(),
            )
        except FileNotFoundError as error:
            raise RenderError(f"FFmpeg executable was not found: {command[0]}") from error
        except subprocess.CalledProcessError as error:
            detail = (error.stderr or error.stdout or "unknown FFmpeg error").strip()
            raise RenderError(detail) from error


def build_video_filter(project: TimelineProject, clip: TimelineClip) -> str:
    width, height = project.canvas.width, project.canvas.height
    base = (
        f"setpts=PTS/{clip.speed:.9f},"
        f"scale={width}:{height}:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop={width}:{height}"
    )
    motion = _motion_perspective(project, clip, base)
    return f"{motion},tpad=stop_mode=clone:stop_duration=1,setsar=1,format=yuv420p"


def build_image_filter(project: TimelineProject, clip: TimelineClip) -> str:
    width, height = project.canvas.width, project.canvas.height
    base = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop={width}:{height}"
    )
    return _motion_perspective(project, clip, base)


def _motion_perspective(
    project: TimelineProject,
    clip: TimelineClip,
    base: str,
) -> str:
    fps = project.canvas.fps
    if clip.motion is MotionPreset.NONE:
        return f"{base},fps={fps},setsar=1,format=yuv420p"

    total_frames = max(2, round(clip.duration_us / 1_000_000 * fps))
    progress = f"min(1,in/{max(1, total_frames - 1)})"
    eased = f"({progress})*({progress})*(3-2*({progress}))"
    inset = "0.03"
    span = "0.94"
    motions = {
        MotionPreset.ZOOM_IN: (
            f"W*{inset}*{eased}", f"H*{inset}*{eased}",
            f"W-W*{inset}*{eased}", f"H-H*{inset}*{eased}",
        ),
        MotionPreset.ZOOM_OUT: (
            f"W*{inset}*(1-{eased})", f"H*{inset}*(1-{eased})",
            f"W-W*{inset}*(1-{eased})", f"H-H*{inset}*(1-{eased})",
        ),
        MotionPreset.PAN_LEFT_RIGHT: (
            f"W*(1-{span})*{eased}", f"H*{inset}",
            f"W*(1-{span})*{eased}+W*{span}", f"H-H*{inset}",
        ),
        MotionPreset.PAN_RIGHT_LEFT: (
            f"W*(1-{span})*(1-{eased})", f"H*{inset}",
            f"W*(1-{span})*(1-{eased})+W*{span}", f"H-H*{inset}",
        ),
        MotionPreset.PAN_TOP_BOTTOM: (
            f"W*{inset}", f"H*(1-{span})*{eased}",
            f"W-W*{inset}", f"H*(1-{span})*{eased}+H*{span}",
        ),
        MotionPreset.PAN_BOTTOM_TOP: (
            f"W*{inset}", f"H*(1-{span})*(1-{eased})",
            f"W-W*{inset}", f"H*(1-{span})*(1-{eased})+H*{span}",
        ),
    }
    x0, y0, x1, y2 = motions[clip.motion]
    return (
        f"{base},perspective=x0='{x0}':y0='{y0}':x1='{x1}':y1='{y0}'"
        f":x2='{x0}':y2='{y2}':x3='{x1}':y3='{y2}'"
        f":interpolation=cubic:sense=source:eval=frame,"
        f"fps={fps},setpts=PTS-STARTPTS,setsar=1,format=yuv420p"
    )


def _concat_escape(path: Path) -> str:
    return path.as_posix().replace("'", "'\\''")


def build_ass_subtitles(project: TimelineProject) -> str:
    """Create a styled ASS track for hard-burning captions into the MP4 preview."""

    font_size = max(24, round(project.canvas.height * 42 / 1080))
    events = [
        f"Dialogue: 0,{_ass_timestamp(caption.start_us)},{_ass_timestamp(caption.end_us)},"
        f"Default,,0,0,0,,{_ass_escape(caption.text)}"
        for caption in project.captions
    ]
    return "\n".join([
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {project.canvas.width}",
        f"PlayResY: {project.canvas.height}",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Default,Noto Sans CJK SC,{font_size},&H00FFFFFF,&H00FFFFFF,&H00101010,&H80101010,"
        "-1,0,0,0,100,100,0,0,1,3,1,2,60,60,70,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        *events,
        "",
    ])


def _ass_timestamp(value_us: int) -> str:
    centiseconds = max(0, round(value_us / 10_000))
    hours, remainder = divmod(centiseconds, 360_000)
    minutes, remainder = divmod(remainder, 6_000)
    seconds, centis = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{seconds:02d}.{centis:02d}"


def _ass_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}").replace("\r\n", "\\N").replace("\n", "\\N")


def _ffmpeg_filter_path(path: Path) -> str:
    return path.resolve().as_posix().replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def _timeline_frame_count(
    project: TimelineProject,
    clip: TimelineClip,
    is_last: bool,
) -> int:
    fps = project.canvas.fps
    start_frame = round(clip.start_us * fps / 1_000_000)
    if is_last:
        end_frame = math.ceil(project.duration_us * fps / 1_000_000)
    else:
        end_frame = round(clip.end_us * fps / 1_000_000)
    return max(1, end_frame - start_frame)


def ffmpeg_available(executable: str = "ffmpeg") -> bool:
    resolved = resolve_executable(executable)
    return Path(resolved).is_file() or shutil.which(resolved) is not None
