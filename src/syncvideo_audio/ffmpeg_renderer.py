"""MP4 preview backend driven by the same timeline manifest as CapCut."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .manifest import MediaType, MotionPreset, TimelineClip, TimelineProject, us_to_seconds


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
                clip_output = temporary / f"clip-{index:05d}.mp4"
                self._render_clip(project, clip, clip_output)
                normalized.append(clip_output)
            visual = temporary / "visual.mp4"
            self._concat(normalized, visual, temporary / "concat.txt")
            final = temporary / "final.mp4"
            self._merge_audio(project, visual, final)
            os.replace(final, output)
        return output

    def _render_clip(self, project: TimelineProject, clip: TimelineClip, output: Path) -> None:
        seconds = us_to_seconds(clip.duration_us)
        if clip.media_type is MediaType.IMAGE:
            command = [
                self.config.ffmpeg, "-y", "-loglevel", "error",
                "-loop", "1", "-framerate", str(project.canvas.fps),
                "-i", str(clip.path),
                "-an", "-vf", build_image_filter(project, clip),
                "-t", f"{seconds:.6f}", "-r", str(project.canvas.fps),
                *self._video_encoder(), str(output),
            ]
        else:
            source_duration = clip.source_duration_us or round(clip.duration_us * clip.speed)
            command = [
                self.config.ffmpeg, "-y", "-loglevel", "error",
                "-ss", f"{us_to_seconds(clip.source_start_us):.6f}",
                "-t", f"{us_to_seconds(source_duration):.6f}",
                "-i", str(clip.path), "-an",
                "-vf", build_video_filter(project, clip),
                "-t", f"{seconds:.6f}", "-r", str(project.canvas.fps),
                *self._video_encoder(), str(output),
            ]
        self._run(command)

    def _concat(self, clips: Sequence[Path], output: Path, list_file: Path) -> None:
        lines = [f"file '{_concat_escape(path.resolve())}'" for path in clips]
        list_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self._run([
            self.config.ffmpeg, "-y", "-loglevel", "error",
            "-f", "concat", "-safe", "0", "-i", str(list_file),
            "-c", "copy", str(output),
        ])

    def _merge_audio(self, project: TimelineProject, visual: Path, output: Path) -> None:
        self._run([
            self.config.ffmpeg, "-y", "-loglevel", "error",
            "-i", str(visual), "-i", str(project.audio.path),
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "copy", "-c:a", "aac", "-b:a", self.config.audio_bitrate,
            "-t", f"{us_to_seconds(project.duration_us):.6f}", "-shortest", str(output),
        ])

    def _video_encoder(self) -> list[str]:
        return [
            "-c:v", "libx264", "-crf", str(self.config.crf),
            "-preset", self.config.preset, "-pix_fmt", "yuv420p",
        ]

    @staticmethod
    def _run(command: Sequence[str]) -> None:
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
        except FileNotFoundError as error:
            raise RenderError(f"FFmpeg executable was not found: {command[0]}") from error
        except subprocess.CalledProcessError as error:
            detail = (error.stderr or error.stdout or "unknown FFmpeg error").strip()
            raise RenderError(detail) from error


def build_video_filter(project: TimelineProject, clip: TimelineClip) -> str:
    width, height, fps = project.canvas.width, project.canvas.height, project.canvas.fps
    return (
        f"setpts=PTS/{clip.speed:.9f},"
        f"scale={width}:{height}:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop={width}:{height},fps={fps},setsar=1,format=yuv420p"
    )


def build_image_filter(project: TimelineProject, clip: TimelineClip) -> str:
    width, height, fps = project.canvas.width, project.canvas.height, project.canvas.fps
    base = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop={width}:{height}"
    )
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
    duration = us_to_seconds(clip.duration_us)
    return (
        f"{base},perspective=x0='{x0}':y0='{y0}':x1='{x1}':y1='{y0}'"
        f":x2='{x0}':y2='{y2}':x3='{x1}':y3='{y2}'"
        f":interpolation=cubic:sense=source:eval=frame,"
        f"fps={fps},trim=duration={duration:.6f},setpts=PTS-STARTPTS,setsar=1,format=yuv420p"
    )


def _concat_escape(path: Path) -> str:
    return path.as_posix().replace("'", "'\\''")


def ffmpeg_available(executable: str = "ffmpeg") -> bool:
    return shutil.which(executable) is not None
