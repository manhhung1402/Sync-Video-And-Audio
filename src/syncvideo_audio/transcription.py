"""Transcript-guided timestamp alignment using a local Whisper CLI.

The transcript defines scene order and text. Whisper is used only to recover
timing from the voice track; no visual or semantic media analysis is involved.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Protocol, Sequence

from .manifest import seconds_to_us
from .runtime import (
    ProgressCallback,
    hidden_subprocess_kwargs,
    report_progress,
    resolve_executable,
    resource_path,
)

try:
    import faster_whisper as _faster_whisper
except ImportError:
    _faster_whisper = None


SENTENCE_TERMINATORS = frozenset(".!?…。｡．！？")
SENTENCE_CLOSERS = frozenset("\"'”’»」』】〉》〕〗〙〛)]}")


class TranscriptionError(RuntimeError):
    """Raised when Whisper cannot produce usable timestamps."""


@dataclass(frozen=True, slots=True)
class WhisperConfig:
    model: str = "small"
    language: str | None = None
    executable: str = "whisper"


@dataclass(frozen=True, slots=True)
class TimedWord:
    text: str
    start_us: int
    end_us: int

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("timed word text cannot be blank")
        if self.start_us < 0 or self.end_us <= self.start_us:
            raise ValueError("timed word range is invalid")


@dataclass(frozen=True, slots=True)
class AlignedTranscriptLine:
    text: str
    start_us: int
    duration_us: int

    @property
    def end_us(self) -> int:
        return self.start_us + self.duration_us


class AudioTranscriber(Protocol):
    def transcribe(
        self,
        audio_path: Path,
        *,
        transcript_hint: str,
        config: WhisperConfig,
        progress_callback: ProgressCallback | None = None,
    ) -> list[TimedWord]: ...


class FasterWhisperTranscriber:
    """In-process Whisper backend used by the packaged, console-free app."""

    def transcribe(
        self,
        audio_path: Path,
        *,
        transcript_hint: str,
        config: WhisperConfig,
        progress_callback: ProgressCallback | None = None,
    ) -> list[TimedWord]:
        if _faster_whisper is None:
            raise TranscriptionError("faster-whisper chưa được cài")

        source = Path(audio_path).resolve()
        cache_dir = _whisper_cache_dir()
        cache_dir.mkdir(parents=True, exist_ok=True)
        model_dir = _bundled_whisper_model_dir(config.model)
        if model_dir is None and getattr(sys, "_MEIPASS", None):
            raise TranscriptionError(
                "Bộ cài thiếu model Whisper. Hãy dùng bản cài full có thư mục assets/models."
            )
        model_source = str(model_dir) if model_dir is not None else config.model
        report_progress(progress_callback, 0.01, "Đang kiểm tra model Whisper…")
        report_progress(
            progress_callback,
            0.03,
            "Đang nạp model Whisper (máy yếu có thể mất vài phút)…",
        )
        try:
            model = _faster_whisper.WhisperModel(
                model_source,
                device="cpu",
                compute_type="int8",
                cpu_threads=max(1, min(4, os.cpu_count() or 1)),
                num_workers=1,
                download_root=str(cache_dir),
                local_files_only=model_dir is not None,
            )
        except (OSError, RuntimeError, ValueError, MemoryError) as error:
            raise TranscriptionError(
                "Không thể nạp model Whisper. Kiểm tra RAM (cần khoảng 1 GB trống), "
                "quyền truy cập thư mục cài đặt và dùng bản cài full."
            ) from error
        prompt = re.sub(r"\s+", " ", transcript_hint).strip()[:2000] or None
        segments, _info = model.transcribe(
            str(source),
            language=_normalize_language(config.language) if config.language else None,
            word_timestamps=True,
            initial_prompt=prompt,
            vad_filter=False,
        )
        words: list[TimedWord] = []
        for segment in segments:
            segment_words = getattr(segment, "words", None) or []
            if segment_words:
                for word in segment_words:
                    start_us = seconds_to_us(float(word.start))
                    end_us = seconds_to_us(float(word.end))
                    if str(word.word).strip() and end_us > start_us:
                        words.append(TimedWord(str(word.word).strip(), start_us, end_us))
            elif str(segment.text).strip():
                start_us = seconds_to_us(float(segment.start))
                end_us = seconds_to_us(float(segment.end))
                if end_us > start_us:
                    words.append(TimedWord(str(segment.text).strip(), start_us, end_us))
            report_progress(
                progress_callback,
                min(0.95, max(0.05, float(getattr(segment, "end", 0.0)) / 600.0)),
                "Whisper đang lấy timestamp…",
            )
        if not words:
            raise TranscriptionError("Whisper không nhận diện được từ nào trong audio")
        report_progress(progress_callback, 1.0, "Whisper đã lấy xong timestamp")
        return sorted(words, key=lambda word: (word.start_us, word.end_us))


def default_transcriber() -> AudioTranscriber:
    if _faster_whisper is None:
        return WhisperCliTranscriber()
    return FasterWhisperTranscriber()


class WhisperCliTranscriber:
    """Run OpenAI Whisper as an external command to keep the GUI build small."""

    def transcribe(
        self,
        audio_path: Path,
        *,
        transcript_hint: str,
        config: WhisperConfig,
        progress_callback: ProgressCallback | None = None,
    ) -> list[TimedWord]:
        report_progress(progress_callback, 0.0, "Whisper đang phân tích voice…")
        executable = resolve_executable(config.executable)
        if not Path(executable).is_file() and not shutil.which(executable):
            raise TranscriptionError(
                "Không tìm thấy Whisper CLI. Cài bằng: pip install openai-whisper"
            )
        source = Path(audio_path).resolve()
        with tempfile.TemporaryDirectory(prefix="syncvideo-whisper-") as temporary_name:
            temporary = Path(temporary_name)
            command = [
                executable,
                str(source),
                "--model",
                config.model,
                "--output_dir",
                str(temporary),
                "--output_format",
                "json",
                "--word_timestamps",
                "True",
                "--verbose",
                "False",
                "--task",
                "transcribe",
                "--fp16",
                "False",
            ]
            if config.language:
                command.extend(["--language", _normalize_language(config.language)])
            prompt = re.sub(r"\s+", " ", transcript_hint).strip()[:2000]
            if prompt:
                command.extend(["--initial_prompt", prompt])
            environment = os.environ.copy()
            environment["PYTHONIOENCODING"] = "utf-8"
            try:
                subprocess.run(
                    command,
                    check=True,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    env=environment,
                    **hidden_subprocess_kwargs(),
                )
            except subprocess.CalledProcessError as error:
                detail = (error.stderr or error.stdout or "Whisper thất bại").strip()
                raise TranscriptionError(detail) from error

            output = temporary / f"{source.stem}.json"
            if not output.is_file():
                candidates = list(temporary.glob("*.json"))
                if len(candidates) != 1:
                    raise TranscriptionError("Whisper không tạo được file timestamp JSON")
                output = candidates[0]
            payload = json.loads(output.read_text(encoding="utf-8"))
        words = _words_from_whisper(payload)
        if not words:
            raise TranscriptionError("Whisper không nhận diện được từ nào trong audio")
        report_progress(progress_callback, 1.0, "Whisper đã lấy xong timestamp")
        return words


def load_transcript(path: str | Path) -> list[str]:
    """Load TXT, SRT, or JSON and split scenes only at sentence punctuation."""

    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"transcript không tồn tại: {source}")
    suffix = source.suffix.lower()
    text = source.read_text(encoding="utf-8-sig")
    if suffix == ".json":
        text = " ".join(_json_transcript_texts(json.loads(text)))
    elif suffix == ".srt":
        text = _srt_transcript_text(text)
    return split_transcript_sentences(text)


def split_transcript_sentences(text: str) -> list[str]:
    """Split transcript by multilingual terminators, never by line breaks alone."""

    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        raise ValueError("transcript không có câu nào")

    sentences: list[str] = []
    start = 0
    index = 0
    while index < len(normalized):
        character = normalized[index]
        if character not in SENTENCE_TERMINATORS or _is_decimal_point(normalized, index):
            index += 1
            continue

        index += 1
        while index < len(normalized) and normalized[index] in SENTENCE_TERMINATORS:
            index += 1
        while index < len(normalized) and normalized[index] in SENTENCE_CLOSERS:
            index += 1
        sentence = normalized[start:index].strip()
        if sentence:
            sentences.append(sentence)
        start = index

    remainder = normalized[start:].strip()
    if remainder:
        sentences.append(remainder)
    if not sentences:
        raise ValueError("transcript không có câu nào")
    return sentences


def align_transcript_lines(
    lines: Sequence[str],
    words: Sequence[TimedWord],
    audio_duration_us: int,
) -> list[AlignedTranscriptLine]:
    """Align ordered transcript lines to Whisper words and cover all audio."""

    if audio_duration_us <= 0:
        raise ValueError("audio duration must be positive")
    if not lines:
        raise ValueError("transcript lines cannot be empty")
    if not words:
        raise TranscriptionError("Whisper word timestamps are empty")

    reference_tokens: list[str] = []
    reference_boundaries = [0]
    for line in lines:
        tokens = _tokens(line)
        if not tokens:
            raise ValueError(f"transcript line không có từ hợp lệ: {line!r}")
        reference_tokens.extend(tokens)
        reference_boundaries.append(len(reference_tokens))

    recognized_tokens: list[str] = []
    token_times: list[tuple[int, int]] = []
    for word in words:
        tokens = _tokens(word.text)
        for token in tokens:
            recognized_tokens.append(token)
            token_times.append((word.start_us, word.end_us))
    if not recognized_tokens:
        raise TranscriptionError("Whisper timestamps không chứa token hợp lệ")
    if len(lines) > 1 and len(recognized_tokens) < 2:
        raise TranscriptionError(
            "Whisper không đủ timestamp để chia transcript thành nhiều cảnh"
        )

    token_mapping = _matching_token_map(reference_tokens, recognized_tokens)
    boundaries = [0]
    line_count = len(lines)
    for line_index, reference_boundary in enumerate(reference_boundaries[1:-1], 1):
        recognized_boundary = _recognized_boundary(
            reference_boundary,
            len(reference_tokens),
            len(recognized_tokens),
            token_mapping,
        )
        timestamp = _boundary_timestamp(recognized_boundary, token_times)
        minimum = boundaries[-1] + 1
        maximum = audio_duration_us - (line_count - line_index)
        boundaries.append(max(minimum, min(timestamp, maximum)))
    boundaries.append(audio_duration_us)

    return [
        AlignedTranscriptLine(line.strip(), start, end - start)
        for line, start, end in zip(lines, boundaries[:-1], boundaries[1:], strict=True)
    ]


def _words_from_whisper(payload: Any) -> list[TimedWord]:
    if not isinstance(payload, dict):
        raise TranscriptionError("Whisper JSON root không hợp lệ")
    output: list[TimedWord] = []
    for segment in payload.get("segments", []):
        if not isinstance(segment, dict):
            continue
        raw_words = segment.get("words") or []
        if raw_words:
            for word in raw_words:
                if not isinstance(word, dict) or not str(word.get("word", "")).strip():
                    continue
                start = seconds_to_us(float(word["start"]))
                end = seconds_to_us(float(word["end"]))
                if end > start:
                    output.append(TimedWord(str(word["word"]).strip(), start, end))
        elif str(segment.get("text", "")).strip():
            start = seconds_to_us(float(segment["start"]))
            end = seconds_to_us(float(segment["end"]))
            if end > start:
                output.append(TimedWord(str(segment["text"]).strip(), start, end))
    return sorted(output, key=lambda word: (word.start_us, word.end_us))


def _matching_token_map(reference: Sequence[str], recognized: Sequence[str]) -> dict[int, int]:
    mapping: dict[int, int] = {}
    matcher = SequenceMatcher(a=reference, b=recognized, autojunk=False)
    for block in matcher.get_matching_blocks():
        for offset in range(block.size):
            mapping[block.a + offset] = block.b + offset
    return mapping


def _recognized_boundary(
    reference_boundary: int,
    reference_count: int,
    recognized_count: int,
    mapping: dict[int, int],
) -> int:
    previous = [(ref, rec) for ref, rec in mapping.items() if ref < reference_boundary]
    following = [(ref, rec) for ref, rec in mapping.items() if ref >= reference_boundary]
    if previous and following:
        left_recognized = max(previous)[1] + 1
        right_recognized = min(following)[1]
        boundary = round((left_recognized + right_recognized) / 2)
    else:
        boundary = round(recognized_count * reference_boundary / reference_count)
    return max(1, min(boundary, recognized_count - 1))


def _boundary_timestamp(boundary: int, token_times: Sequence[tuple[int, int]]) -> int:
    before_end = token_times[boundary - 1][1]
    after_start = token_times[boundary][0]
    return round((before_end + after_start) / 2)


def _tokens(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    tokens: list[str] = []
    buffered: list[str] = []
    for character in normalized:
        if _is_cjk_or_hangul(character):
            if buffered:
                tokens.append("".join(buffered))
                buffered.clear()
            tokens.append(character)
        elif character.isalnum() or unicodedata.category(character).startswith("M"):
            buffered.append(character)
        elif buffered:
            tokens.append("".join(buffered))
            buffered.clear()
    if buffered:
        tokens.append("".join(buffered))
    return tokens


def _json_transcript_texts(payload: Any) -> list[str]:
    entries = payload.get("scenes", payload.get("segments", payload)) if isinstance(payload, dict) else payload
    if not isinstance(entries, list):
        raise ValueError("transcript JSON phải là array hoặc object có scenes/segments")
    lines: list[str] = []
    for entry in entries:
        if isinstance(entry, str):
            value = entry
        elif isinstance(entry, dict):
            value = str(entry.get("text", entry.get("sourceText", "")))
        else:
            value = ""
        if value.strip():
            lines.append(value.strip())
    return lines


def _srt_transcript_text(text: str) -> str:
    cues: list[str] = []
    for block in re.split(r"\r?\n\s*\r?\n", text.strip()):
        content = [
            line.strip()
            for line in block.splitlines()
            if line.strip() and not line.strip().isdigit() and "-->" not in line
        ]
        if content:
            cues.append(" ".join(content))
    return " ".join(cues)


def _is_decimal_point(text: str, index: int) -> bool:
    return (
        text[index] == "."
        and index > 0
        and index + 1 < len(text)
        and text[index - 1].isdigit()
        and text[index + 1].isdigit()
    )


def _is_cjk_or_hangul(character: str) -> bool:
    codepoint = ord(character)
    return any(
        start <= codepoint <= end
        for start, end in (
            (0x3040, 0x30FF),  # Hiragana and Katakana
            (0x31F0, 0x31FF),  # Katakana phonetic extensions
            (0x3400, 0x4DBF),  # CJK extension A
            (0x4E00, 0x9FFF),  # Unified CJK ideographs
            (0xF900, 0xFAFF),  # CJK compatibility ideographs
            (0x1100, 0x11FF),  # Hangul jamo
            (0x3130, 0x318F),  # Hangul compatibility jamo
            (0xAC00, 0xD7AF),  # Hangul syllables
        )
    )


def _normalize_language(language: str) -> str:
    aliases = {
        "vn": "vi",
        "vietnamese": "vi",
        "jp": "ja",
        "japanese": "ja",
        "kr": "ko",
        "korean": "ko",
        "cn": "zh",
        "chinese": "zh",
    }
    normalized = language.strip().lower().replace("_", "-")
    return aliases.get(normalized, normalized.split("-", 1)[0])


def _whisper_cache_dir() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    root = Path(local_app_data) if local_app_data else Path.home() / ".cache"
    return root / "SyncVideo-Audio" / "models"


def _bundled_whisper_model_dir(model: str) -> Path | None:
    """Locate a model shipped inside source trees and PyInstaller bundles."""

    # PyInstaller stores spec ``datas`` under ``assets/``. Keep the legacy
    # models/ path as a compatibility fallback for older local builds.
    for relative in (f"assets/models/{model}", f"models/{model}"):
        candidate = resource_path(relative)
        if candidate.is_dir() and all(
            (candidate / filename).is_file()
            for filename in ("config.json", "model.bin", "tokenizer.json")
        ):
            return candidate
    return None
