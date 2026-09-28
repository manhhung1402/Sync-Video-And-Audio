"""Deterministic audio/media timeline planning.

This module borrows the proven concepts from Auto-Grok (numbered media order,
scene mappings, still-shot expansion, and bounded video speed) while keeping a
clean implementation and a backend-neutral output.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence

from .manifest import (
    AudioTrack,
    CanvasSpec,
    MediaType,
    MotionPreset,
    TimelineCaption,
    TimelineClip,
    TimelineProject,
    seconds_to_us,
)
from .probe import FfprobeMediaProbe, MediaProbe
from .runtime import ProgressCallback, report_progress
from .transcription import (
    AudioTranscriber,
    TimedWord,
    WhisperConfig,
    _tokens,
    align_transcript_lines,
    correct_srt_spelling,
    default_transcriber,
    load_srt_timestamps,
    load_transcript,
    split_transcript_sentences,
)


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}
MEDIA_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS
# Media is commonly exported with one of these prefixes, but users also have
# folders containing names such as ``001.png`` or ``video_12_final.jpg``.
# Keep the numeric part separate from the rest of the name so all of those
# variants follow the same deterministic order.
NUMBERED_MEDIA_RE = re.compile(
    r"^(?:(?:img|image|vid|video|clip|scene|shot)[-_ ]*)?(\d+)(?=$|[-_. ])",
    re.IGNORECASE,
)
NATURAL_NUMBER_RE = re.compile(r"(\d+)")
MOTION_CYCLE = (
    MotionPreset.ZOOM_IN,
    MotionPreset.ZOOM_OUT,
    MotionPreset.PAN_LEFT_RIGHT,
    MotionPreset.PAN_RIGHT_LEFT,
    MotionPreset.PAN_TOP_BOTTOM,
    MotionPreset.PAN_BOTTOM_TOP,
)


class AlignmentMode(str, Enum):
    EQUAL = "equal"
    TRANSCRIPT = "transcript"


@dataclass(frozen=True, slots=True)
class MediaNumberingReport:
    """Numbering information recovered from ordered media filenames."""

    numbered_paths: tuple[tuple[int, tuple[Path, ...]], ...]
    unnumbered_paths: tuple[Path, ...]
    missing_numbers: tuple[int, ...]
    duplicate_numbers: tuple[int, ...]

    @property
    def fully_numbered(self) -> bool:
        return bool(self.numbered_paths) and not self.unnumbered_paths


@dataclass(frozen=True, slots=True)
class PlannerConfig:
    canvas: CanvasSpec = CanvasSpec()
    image_shot_duration_us: int = seconds_to_us(6.0)
    min_video_speed: float = 0.25
    max_video_speed: float = 4.0
    add_captions: bool = True
    motion_enabled: bool = True
    split_by_punctuation: bool = True
    max_caption_words: int = 8

    def __post_init__(self) -> None:
        if self.image_shot_duration_us <= 0:
            raise ValueError("image shot duration must be positive")
        if not 0 < self.min_video_speed <= self.max_video_speed:
            raise ValueError("video speed range is invalid")


@dataclass(frozen=True, slots=True)
class SceneSpec:
    path: Path
    start_us: int
    duration_us: int
    text: str = ""
    scene_index: int = 1
    # Per-token (start_us, end_us) stamps for this scene's text, in reading
    # order. Empty when the timing source had no word-level detail.
    word_times: tuple[tuple[int, int], ...] = ()

    @property
    def end_us(self) -> int:
        return self.start_us + self.duration_us


def sort_media(media_dir: str | Path) -> list[Path]:
    """Return supported media in stable human/numeric order.

    Numbered names are placed first (``img-2``, ``video_10``, ``001``), then
    unnumbered names are sorted naturally so ``scene2`` comes before
    ``scene10``.  ``Path.iterdir`` does not promise an order on Windows, so
    every branch includes the full filename as a deterministic tie-breaker.
    """

    root = Path(media_dir)
    if not root.is_dir():
        raise FileNotFoundError(f"media directory does not exist: {root}")
    files = [path for path in root.iterdir() if path.is_file() and path.suffix.lower() in MEDIA_EXTENSIONS]
    if not files:
        raise FileNotFoundError(f"no supported images or videos found in: {root}")

    def key(path: Path) -> tuple[int, int, tuple[tuple[int, object], ...], str]:
        match = NUMBERED_MEDIA_RE.match(path.stem)
        if match:
            return (0, int(match.group(1)), _natural_name_key(path.name), path.name.casefold())
        return (1, 0, _natural_name_key(path.name), path.name.casefold())

    return sorted(files, key=key)


def inspect_media_numbering(media: Sequence[str | Path]) -> MediaNumberingReport:
    """Find missing/duplicate scene numbers encoded in media filenames."""

    grouped: dict[int, list[Path]] = {}
    unnumbered: list[Path] = []
    for value in media:
        path = Path(value)
        number = _media_number(path)
        if number is None:
            unnumbered.append(path)
        else:
            grouped.setdefault(number, []).append(path)
    positive_numbers = {number for number in grouped if number > 0}
    maximum = max(positive_numbers, default=0)
    missing = tuple(number for number in range(1, maximum + 1) if number not in grouped)
    duplicates = tuple(sorted(number for number, paths in grouped.items() if len(paths) > 1))
    return MediaNumberingReport(
        numbered_paths=tuple(
            (number, tuple(paths)) for number, paths in sorted(grouped.items())
        ),
        unnumbered_paths=tuple(unnumbered),
        missing_numbers=missing,
        duplicate_numbers=duplicates,
    )


def load_scene_mapping(
    mapping_path: str | Path,
    media_dir: str | Path,
    audio_duration_us: int,
) -> list[SceneSpec]:
    """Load manual timestamps or proportionally place ordered story scenes."""

    source = Path(mapping_path)
    payload = json.loads(source.read_text(encoding="utf-8"))
    entries = payload.get("scenes") if isinstance(payload, dict) else payload
    if not isinstance(entries, list) or not entries or not all(isinstance(item, dict) for item in entries):
        raise ValueError("mapping must be a non-empty array or an object containing scenes")

    media = sort_media(media_dir)
    root = Path(media_dir).resolve()
    has_all_timestamps = all("audio_start" in item and "audio_end" in item for item in entries)
    has_any_timestamp = any("audio_start" in item or "audio_end" in item for item in entries)
    if has_any_timestamp and not has_all_timestamps:
        raise ValueError("every mapped scene must provide both audio_start and audio_end")

    if has_all_timestamps:
        boundaries = [
            (seconds_to_us(float(item["audio_start"])), seconds_to_us(float(item["audio_end"])))
            for item in entries
        ]
    else:
        weights = [_word_weight(_scene_text(item)) for item in entries]
        boundaries = _weighted_ranges(audio_duration_us, weights)

    scenes: list[SceneSpec] = []
    previous_end = 0
    for index, (item, (start_us, end_us)) in enumerate(zip(entries, boundaries, strict=True)):
        if start_us < previous_end:
            raise ValueError(f"mapping scene {index + 1} overlaps the previous scene")
        if end_us <= start_us:
            raise ValueError(f"mapping scene {index + 1} has a non-positive duration")
        if end_us > audio_duration_us:
            raise ValueError(f"mapping scene {index + 1} exceeds audio duration")
        path = _resolve_media(item, root, media, index)
        scenes.append(
            SceneSpec(
                path=path,
                start_us=start_us,
                duration_us=end_us - start_us,
                text=_scene_text(item),
                scene_index=_scene_number(item, index),
            )
        )
        previous_end = end_us
    return scenes


def build_timeline(
    *,
    project_name: str,
    audio_path: str | Path,
    media_dir: str | Path,
    mapping_path: str | Path | None = None,
    ordered_media_paths: Sequence[str | Path] | None = None,
    alignment_mode: AlignmentMode = AlignmentMode.EQUAL,
    transcript_path: str | Path | None = None,
    transcript_text: str | None = None,
    srt_path: str | Path | None = None,
    transcriber: AudioTranscriber | None = None,
    whisper_config: WhisperConfig | None = None,
    config: PlannerConfig | None = None,
    probe: MediaProbe | None = None,
    progress_callback: ProgressCallback | None = None,
) -> TimelineProject:
    """Plan an editable timeline without rendering media."""

    cfg = config or PlannerConfig()
    media_probe = probe or FfprobeMediaProbe()
    audio = Path(audio_path).resolve()
    report_progress(progress_callback, 0.0, "Đang kiểm tra audio và thứ tự media…")
    if not audio.is_file():
        raise FileNotFoundError(f"audio file does not exist: {audio}")
    audio_duration_us = media_probe.probe(audio).duration_us
    if audio_duration_us <= 0:
        raise ValueError("audio duration must be positive")

    mode = AlignmentMode(alignment_mode)
    if transcript_path is not None and transcript_text is not None:
        raise ValueError("provide either transcript file or pasted transcript text, not both")
    if mapping_path and (
        ordered_media_paths is not None
        or transcript_path is not None
        or transcript_text is not None
    ):
        raise ValueError("manual media order cannot be combined with a scene mapping")
    if mapping_path and mode is AlignmentMode.TRANSCRIPT:
        raise ValueError("scene mapping cannot be combined with transcript alignment")
    if srt_path is not None and mapping_path:
        raise ValueError("scene mapping cannot be combined with a prepared SRT")
    if srt_path is not None and mode is not AlignmentMode.TRANSCRIPT:
        raise ValueError("prepared SRT is only valid in transcript alignment mode")
    # Read once, then replayed verbatim as the caption track (see below).
    srt_cues: list[TimedWord] | None = None
    if mapping_path:
        scenes = load_scene_mapping(mapping_path, media_dir, audio_duration_us)
    else:
        media = (
            _validate_ordered_media(ordered_media_paths, media_dir)
            if ordered_media_paths is not None
            else sort_media(media_dir)
        )
        if mode is AlignmentMode.TRANSCRIPT:
            if transcript_path is None and not transcript_text:
                raise ValueError("transcript mode requires a transcript file or pasted text")
            transcript_lines = (
                load_transcript(
                    transcript_path, split_by_punctuation=cfg.split_by_punctuation
                )
                if transcript_path is not None
                else split_transcript_sentences(
                    transcript_text or "",
                    split_by_punctuation=cfg.split_by_punctuation,
                )
            )
            _validate_transcript_media_pairing(transcript_lines, media)
            if srt_path is not None:
                # SRT already carries the timing, so Whisper is skipped
                # entirely; the sentence text still comes from the transcript.
                report_progress(
                    progress_callback, 0.5, "Đang đọc timestamp từ file SRT có sẵn…"
                )
                timestamp_words = load_srt_timestamps(srt_path)
                # The transcript is the spelling authority: rewrite whatever the
                # SRT got wrong without ever moving a cue.
                srt_cues = correct_srt_spelling(timestamp_words, transcript_lines)
                report_progress(
                    progress_callback, 1.0, "Đã đọc xong timestamp từ file SRT"
                )
            else:
                timestamp_words = (transcriber or default_transcriber()).transcribe(
                    audio,
                    transcript_hint="\n".join(transcript_lines),
                    config=whisper_config or WhisperConfig(),
                    progress_callback=progress_callback,
                )
            aligned_lines = align_transcript_lines(
                transcript_lines,
                timestamp_words,
                audio_duration_us,
            )
            scenes = [
                SceneSpec(
                    path.resolve(),
                    line.start_us,
                    line.duration_us,
                    text=line.text,
                    scene_index=index + 1,
                    word_times=line.word_times,
                )
                for index, (path, line) in enumerate(zip(media, aligned_lines, strict=True))
            ]
        else:
            if transcript_path is not None or transcript_text is not None:
                raise ValueError("transcript is only valid in transcript alignment mode")
            ranges = _weighted_ranges(audio_duration_us, [1] * len(media))
            scenes = [
                SceneSpec(path.resolve(), start, end - start, scene_index=index + 1)
                for index, (path, (start, end)) in enumerate(zip(media, ranges, strict=True))
            ]

    clips: list[TimelineClip] = []
    captions: list[TimelineCaption] = []
    motion_index = 0
    for scene in scenes:
        suffix = scene.path.suffix.lower()
        if suffix in IMAGE_EXTENSIONS:
            image_clips = _plan_image(scene, cfg, motion_index)
            clips.extend(image_clips)
            motion_index += len(image_clips)
        elif suffix in VIDEO_EXTENSIONS:
            video_clips = _plan_video(
                scene,
                cfg,
                media_probe.probe(scene.path).duration_us,
                motion_index,
            )
            clips.extend(video_clips)
            motion_index += len(video_clips)
        else:
            raise ValueError(f"unsupported scene media: {scene.path}")
        if cfg.add_captions and srt_cues is None and scene.text.strip():
            captions.extend(
                _plan_scene_captions(
                    scene.text.strip(),
                    scene.start_us,
                    scene.duration_us,
                    max_words=cfg.max_caption_words,
                    word_times=scene.word_times,
                )
            )

    if cfg.add_captions and srt_cues is not None:
        # A prepared SRT is already cut to caption length and already aligned to
        # the speech, so it is used verbatim. Re-splitting it would only move
        # captions off the words they were timed against, and it is emitted once
        # for the whole project rather than once per scene.
        captions = [
            TimelineCaption(cue.text, cue.start_us, cue.end_us - cue.start_us)
            for cue in srt_cues
        ]

    project = TimelineProject(
        name=project_name,
        canvas=cfg.canvas,
        audio=AudioTrack(audio, audio_duration_us),
        clips=clips,
        captions=captions,
    )
    _validate_contiguous(project.clips, project.duration_us)
    report_progress(progress_callback, 1.0, "Đã lập xong timeline")
    return project


def _validate_ordered_media(
    values: Sequence[str | Path], media_dir: str | Path
) -> list[Path]:
    if not values:
        raise ValueError("manual media order cannot be empty")
    root = Path(media_dir).resolve()
    media: list[Path] = []
    seen: set[Path] = set()
    for value in values:
        path = Path(value).resolve()
        if not (path == root or root in path.parents):
            raise ValueError(f"ordered media is outside the media directory: {path}")
        if not path.is_file() or path.suffix.lower() not in MEDIA_EXTENSIONS:
            raise FileNotFoundError(f"ordered media is missing or unsupported: {path}")
        if path in seen:
            raise ValueError(f"ordered media contains a duplicate: {path}")
        seen.add(path)
        media.append(path)
    return media


def _plan_image(scene: SceneSpec, config: PlannerConfig, motion_index: int) -> list[TimelineClip]:
    shot_count = max(1, round(scene.duration_us / config.image_shot_duration_us))
    ranges = _equal_ranges(scene.start_us, scene.duration_us, shot_count)
    return [
        TimelineClip(
            media_type=MediaType.IMAGE,
            path=scene.path.resolve(),
            start_us=start,
            duration_us=end - start,
            motion=(
                MOTION_CYCLE[(motion_index + shot_index) % len(MOTION_CYCLE)]
                if config.motion_enabled
                else MotionPreset.NONE
            ),
            scene_index=scene.scene_index,
        )
        for shot_index, (start, end) in enumerate(ranges)
    ]


def _plan_video(
    scene: SceneSpec,
    config: PlannerConfig,
    source_duration_us: int,
    motion_index: int,
) -> list[TimelineClip]:
    if source_duration_us <= 0:
        raise ValueError(f"video duration must be positive: {scene.path}")
    raw_speed = source_duration_us / scene.duration_us
    if raw_speed > config.max_video_speed:
        speed = config.max_video_speed
        used_source_us = max(1, round(scene.duration_us * speed))
        loop_count = 1
    elif raw_speed < config.min_video_speed:
        loop_count = max(1, math.ceil(config.min_video_speed * scene.duration_us / source_duration_us))
        speed = source_duration_us * loop_count / scene.duration_us
        used_source_us = source_duration_us
    else:
        speed = raw_speed
        used_source_us = source_duration_us
        loop_count = 1

    ranges = _equal_ranges(scene.start_us, scene.duration_us, loop_count)
    return [
        TimelineClip(
            media_type=MediaType.VIDEO,
            path=scene.path.resolve(),
            start_us=start,
            duration_us=end - start,
            source_duration_us=used_source_us,
            speed=speed,
            volume=0.0,
            motion=(
                MOTION_CYCLE[(motion_index + loop_index) % len(MOTION_CYCLE)]
                if config.motion_enabled
                else MotionPreset.NONE
            ),
            scene_index=scene.scene_index,
        )
        for loop_index, (start, end) in enumerate(ranges)
    ]


def _resolve_media(item: Mapping[str, Any], root: Path, media: Sequence[Path], index: int) -> Path:
    requested = [item.get("clip"), item.get("imageFile"), item.get("image_file")]
    for raw_name in requested:
        if not raw_name:
            continue
        name = str(raw_name).strip()
        candidate = (root / name).resolve()
        if (candidate == root or root in candidate.parents) and candidate.is_file() and candidate.suffix.lower() in MEDIA_EXTENSIONS:
            return candidate
        suffix_matches = [path for path in media if path.name.lower().endswith(name.lower())]
        if len(suffix_matches) == 1:
            return suffix_matches[0].resolve()

    number = _scene_number(item, index)
    for path in media:
        media_number = _media_number(path)
        if media_number == number:
            return path.resolve()
    if index < len(media):
        return media[index].resolve()
    raise FileNotFoundError(f"no media found for scene {number}")


def _scene_number(item: Mapping[str, Any], index: int) -> int:
    raw = item.get("sceneIndex", item.get("scene_index", index + 1))
    try:
        return int(raw)
    except (TypeError, ValueError):
        return index + 1


def _scene_text(item: Mapping[str, Any]) -> str:
    return str(item.get("sourceText", item.get("source_text", item.get("text", ""))))


def _media_number(path: Path) -> int | None:
    match = NUMBERED_MEDIA_RE.match(path.stem)
    return int(match.group(1)) if match else None


def _validate_transcript_media_pairing(
    transcript_lines: Sequence[str],
    media: Sequence[Path],
) -> None:
    report = inspect_media_numbering(media)
    common = (
        f"transcript có {len(transcript_lines)} câu nhưng media có {len(media)} file; "
        "cần đúng một câu được tách theo dấu kết câu cho mỗi file theo thứ tự đánh số"
    )

    if report.fully_numbered:
        numbered = {number: paths for number, paths in report.numbered_paths}
        expected = set(range(1, len(transcript_lines) + 1))
        missing = sorted(expected - set(numbered))
        extras = sorted(set(numbered) - expected)
        duplicates = sorted(
            number for number, paths in report.numbered_paths if len(paths) > 1
        )
        if missing or extras or duplicates or len(media) != len(transcript_lines):
            details: list[str] = [common]
            if missing:
                details.append("\nThiếu hình cho các câu:")
                details.extend(
                    f'- Câu {number:03d}: "{_preview_sentence(transcript_lines[number - 1])}"'
                    for number in missing
                )
            if duplicates:
                details.append("\nTrùng số trong tên file:")
                for number in duplicates:
                    names = ", ".join(path.name for path in numbered[number])
                    details.append(f"- Số {number:03d}: {names}")
            if extras:
                details.append("\nMedia không có câu thuyết minh tương ứng:")
                for number in extras:
                    names = ", ".join(path.name for path in numbered[number])
                    details.append(f"- Số {number:03d}: {names}")
            raise ValueError("\n".join(details))
        return

    if len(transcript_lines) != len(media):
        details = [common]
        if not report.numbered_paths and len(transcript_lines) > len(media):
            details.append("\nCác câu chưa có media ở cuối danh sách:")
            details.extend(
                f'- Câu {number:03d}: "{_preview_sentence(transcript_lines[number - 1])}"'
                for number in range(len(media) + 1, len(transcript_lines) + 1)
            )
        elif report.unnumbered_paths:
            names = ", ".join(path.name for path in report.unnumbered_paths[:8])
            suffix = "…" if len(report.unnumbered_paths) > 8 else ""
            details.append(
                "\nKhông thể xác định chính xác câu bị thiếu vì một số file không có "
                f"số thứ tự ở đầu tên: {names}{suffix}"
            )
        raise ValueError("\n".join(details))


def _preview_sentence(text: str, limit: int = 120) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 1].rstrip() + "…"


def _natural_name_key(value: str) -> tuple[tuple[int, object], ...]:
    """Build a comparison key where digit runs are compared numerically."""

    return tuple(
        (0, int(part)) if part.isdigit() else (1, part.casefold())
        for part in NATURAL_NUMBER_RE.split(value)
        if part
    )


def _word_weight(text: str) -> int:
    return max(1, len(re.findall(r"\w+", text, flags=re.UNICODE)))


def _weighted_ranges(total_us: int, weights: Sequence[int]) -> list[tuple[int, int]]:
    if total_us <= 0 or not weights or any(weight <= 0 for weight in weights):
        raise ValueError("duration and weights must be positive")
    weight_total = sum(weights)
    boundaries = [0]
    cumulative = 0
    for weight in weights[:-1]:
        cumulative += weight
        boundaries.append(round(total_us * cumulative / weight_total))
    boundaries.append(total_us)
    return list(zip(boundaries, boundaries[1:]))


def _equal_ranges(start_us: int, duration_us: int, count: int) -> list[tuple[int, int]]:
    boundaries = [start_us + round(duration_us * index / count) for index in range(count)]
    boundaries.append(start_us + duration_us)
    return list(zip(boundaries, boundaries[1:]))


def _validate_contiguous(clips: Sequence[TimelineClip], duration_us: int) -> None:
    cursor = 0
    for index, clip in enumerate(clips):
        if clip.start_us != cursor:
            raise ValueError(f"visual timeline has a gap before clip {index}")
        cursor = clip.end_us
    if cursor != duration_us:
        raise ValueError("visual timeline duration does not match audio duration")


def split_caption_text(text: str, max_words: int = 8) -> list[str]:
    """Split long caption text into balanced chunks of at most max_words words."""

    words = text.split()
    if not words:
        return []
    if max_words <= 0 or len(words) <= max_words:
        return [text.strip()]

    total_words = len(words)
    num_chunks = math.ceil(total_words / max_words)

    base_size = total_words // num_chunks
    remainder = total_words % num_chunks
    chunk_sizes = [base_size + (1 if i < remainder else 0) for i in range(num_chunks)]

    chunks: list[str] = []
    index = 0
    for chunk_index, size in enumerate(chunk_sizes):
        if chunk_index == len(chunk_sizes) - 1:
            chunk_words = words[index:]
        else:
            target_end = index + size
            best_end = target_end
            for offset in (0, -1, 1):
                candidate = target_end + offset
                if index < candidate < len(words) and words[candidate - 1].endswith(
                    (",", ";", ":", "\u2014", "-")
                ):
                    best_end = candidate
                    break
            chunk_words = words[index:best_end]
            index = best_end
        chunk = " ".join(chunk_words).strip()
        if chunk:
            chunks.append(chunk)
    return chunks


def _plan_scene_captions(
    text: str,
    start_us: int,
    duration_us: int,
    max_words: int = 8,
    word_times: Sequence[tuple[int, int]] = (),
) -> list[TimelineCaption]:
    """Generate one or more contiguous, short TimelineCaption objects for a scene.

    When ``word_times`` is available the scene text is re-tokenised with the same
    rules the aligner used, so each chunk can start on the first word it shows and
    end on the last one. That keeps a split caption locked to the speech it
    covers instead of drifting by a character-count guess.

    A prepared SRT never reaches this function: it is already cut to caption
    length and already aligned, so it is emitted verbatim by ``build_timeline``.
    """

    chunks = split_caption_text(text, max_words)
    if not chunks:
        return []
    if len(chunks) == 1:
        return [TimelineCaption(chunks[0], start_us, duration_us)]

    exact = _caption_ranges_from_word_times(chunks, word_times, start_us, duration_us)
    if exact is not None:
        return [
            TimelineCaption(chunk, chunk_start, chunk_end - chunk_start)
            for chunk, (chunk_start, chunk_end) in zip(chunks, exact, strict=True)
        ]

    # No word-level source: weight by words, which is the unit the split uses.
    weights = [_word_weight(chunk) for chunk in chunks]
    ranges = _weighted_ranges(duration_us, weights)
    return [
        TimelineCaption(chunk, start_us + chunk_start, chunk_end - chunk_start)
        for chunk, (chunk_start, chunk_end) in zip(chunks, ranges, strict=True)
    ]


def _caption_ranges_from_word_times(
    chunks: Sequence[str],
    word_times: Sequence[tuple[int, int]],
    start_us: int,
    duration_us: int,
    clamp_to_scene: bool = True,
) -> list[tuple[int, int]] | None:
    """Place every chunk on its own words, or return None when that is impossible."""

    if not word_times:
        return None
    # The aligner slices token_times by *recognized* token, so the counts only
    # line up when the scene text re-tokenises to exactly the same sequence.
    tokens = [token for chunk in chunks for token in _tokens(chunk)]
    if len(tokens) != len(word_times):
        return None

    ranges: list[tuple[int, int]] = []
    index = 0
    for position, chunk in enumerate(chunks):
        chunk_length = len(_tokens(chunk))
        if not chunk_length:
            return None
        chunk_start = word_times[index][0]
        chunk_end = word_times[index + chunk_length - 1][1]
        index += chunk_length
        if position:
            # Chunks must stay contiguous and inside the scene, so a cue whose
            # stamps run past its neighbour gets clamped to the same instant.
            chunk_start = max(chunk_start, ranges[-1][1])
        chunk_end = max(chunk_end, chunk_start)
        ranges.append((chunk_start, chunk_end))

    if clamp_to_scene:
        scene_end = start_us + duration_us
        if ranges[0][0] < start_us or ranges[-1][1] > scene_end:
            # Only shrink to the scene bounds; never stretch, so timings stay real.
            ranges[0] = (max(ranges[0][0], start_us), ranges[0][1])
            ranges[-1] = (ranges[-1][0], min(ranges[-1][1], scene_end))
            for position in range(1, len(ranges)):
                if ranges[position][0] < ranges[position - 1][1]:
                    ranges[position] = (ranges[position - 1][1], ranges[position][1])
    if any(end <= begin for begin, end in ranges):
        return None
    return ranges






