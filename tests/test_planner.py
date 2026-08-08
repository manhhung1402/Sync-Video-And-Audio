import json
from pathlib import Path

import pytest

from syncvideo_audio import (
    AlignmentMode,
    CanvasSpec,
    MediaInfo,
    MediaType,
    MotionPreset,
    PlannerConfig,
    build_timeline,
    seconds_to_us,
    sort_media,
)
from syncvideo_audio.transcription import TimedWord, WhisperConfig


class FakeProbe:
    def __init__(self, durations: dict[str, float]) -> None:
        self.durations = durations

    def probe(self, path: Path) -> MediaInfo:
        return MediaInfo(seconds_to_us(self.durations[path.name]))


class FakeTranscriber:
    def __init__(self, words: list[TimedWord]) -> None:
        self.words = words
        self.calls: list[tuple[Path, str, WhisperConfig]] = []

    def transcribe(
        self,
        audio_path: Path,
        *,
        transcript_hint: str,
        config: WhisperConfig,
        progress_callback=None,
    ) -> list[TimedWord]:
        self.calls.append((audio_path, transcript_hint, config))
        return self.words


def touch(path: Path) -> Path:
    path.write_bytes(b"fixture")
    return path


def test_sort_media_uses_numeric_prefix_then_alphabetic(tmp_path: Path) -> None:
    for name in ["img-010.png", "other.jpg", "vid-002.mp4", "img-001.png", "ignored.txt"]:
        touch(tmp_path / name)

    assert [path.name for path in sort_media(tmp_path)] == [
        "img-001.png",
        "vid-002.mp4",
        "img-010.png",
        "other.jpg",
    ]


def test_sort_media_handles_common_numbering_patterns_naturally(tmp_path: Path) -> None:
    for name in [
        "video_10-final.mp4",
        "scene10.jpg",
        "001-cover.png",
        "video_2-final.mp4",
        "img-003-extra.png",
        "scene2.jpg",
        "scene-final.jpg",
        "notes.jpg",
        "ignored.txt",
    ]:
        touch(tmp_path / name)

    assert [path.name for path in sort_media(tmp_path)] == [
        "001-cover.png",
        "scene2.jpg",
        "video_2-final.mp4",
        "img-003-extra.png",
        "scene10.jpg",
        "video_10-final.mp4",
        "notes.jpg",
        "scene-final.jpg",
    ]


def test_manual_media_order_is_preserved(tmp_path: Path) -> None:
    audio = touch(tmp_path / "audio.wav")
    media = tmp_path / "media"
    media.mkdir()
    first = touch(media / "img-001.png")
    second = touch(media / "img-002.png")

    project = build_timeline(
        project_name="manual-order",
        audio_path=audio,
        media_dir=media,
        ordered_media_paths=[second, first],
        probe=FakeProbe({"audio.wav": 2}),
    )

    assert [clip.path for clip in project.clips] == [second.resolve(), first.resolve()]


def test_transcript_mode_pairs_numbered_media_with_timestamped_lines(tmp_path: Path) -> None:
    audio = touch(tmp_path / "audio.wav")
    media = tmp_path / "media"
    media.mkdir()
    first = touch(media / "img-001.png")
    second = touch(media / "img-002.png")
    transcript = tmp_path / "transcript.txt"
    transcript.write_text("Câu đầu tiên.\nCâu thứ hai.\n", encoding="utf-8")
    transcriber = FakeTranscriber([
        TimedWord("câu", 200_000, 400_000),
        TimedWord("đầu", 420_000, 700_000),
        TimedWord("tiên", 720_000, 1_000_000),
        TimedWord("câu", 2_000_000, 2_200_000),
        TimedWord("thứ", 2_220_000, 2_400_000),
        TimedWord("hai", 2_420_000, 2_700_000),
    ])

    project = build_timeline(
        project_name="transcript-sync",
        audio_path=audio,
        media_dir=media,
        alignment_mode=AlignmentMode.TRANSCRIPT,
        transcript_path=transcript,
        transcriber=transcriber,
        probe=FakeProbe({"audio.wav": 3}),
    )

    assert [clip.path for clip in project.clips] == [first.resolve(), second.resolve()]
    assert project.clips[0].end_us == 1_500_000
    assert project.clips[1].start_us == 1_500_000
    assert [caption.text for caption in project.captions] == ["Câu đầu tiên.", "Câu thứ hai."]
    assert transcriber.calls[0][1] == "Câu đầu tiên.\nCâu thứ hai."


def test_transcript_mode_requires_one_sentence_per_media(tmp_path: Path) -> None:
    audio = touch(tmp_path / "audio.wav")
    media = tmp_path / "media"
    media.mkdir()
    touch(media / "img-001.png")
    touch(media / "img-002.png")
    transcript = tmp_path / "transcript.txt"
    transcript.write_text("Chỉ có một câu không dấu câu", encoding="utf-8")

    with pytest.raises(ValueError, match="một câu được tách theo dấu kết câu"):
        build_timeline(
            project_name="mismatch",
            audio_path=audio,
            media_dir=media,
            alignment_mode=AlignmentMode.TRANSCRIPT,
            transcript_path=transcript,
            transcriber=FakeTranscriber([]),
            probe=FakeProbe({"audio.wav": 3}),
        )


def test_transcript_mode_accepts_pasted_text_and_splits_on_punctuation(tmp_path: Path) -> None:
    audio = touch(tmp_path / "audio.wav")
    media = tmp_path / "media"
    media.mkdir()
    touch(media / "img-001.png")
    touch(media / "img-002.png")
    transcriber = FakeTranscriber([
        TimedWord("朝", 100_000, 500_000),
        TimedWord("鳥", 1_500_000, 1_900_000),
    ])

    project = build_timeline(
        project_name="pasted-transcript",
        audio_path=audio,
        media_dir=media,
        alignment_mode=AlignmentMode.TRANSCRIPT,
        transcript_text="朝です。\n鳥です。",
        transcriber=transcriber,
        probe=FakeProbe({"audio.wav": 2}),
    )

    assert [caption.text for caption in project.captions] == ["朝です。", "鳥です。"]


def test_planner_without_mapping_fills_audio_and_expands_long_stills(tmp_path: Path) -> None:
    audio = touch(tmp_path / "narration.wav")
    media = tmp_path / "media"
    media.mkdir()
    touch(media / "img-001.png")
    touch(media / "img-002.png")

    project = build_timeline(
        project_name="Demo",
        audio_path=audio,
        media_dir=media,
        config=PlannerConfig(canvas=CanvasSpec(1080, 1920, 30), image_shot_duration_us=seconds_to_us(6)),
        probe=FakeProbe({"narration.wav": 24}),
    )

    assert len(project.clips) == 4
    assert [clip.start_us for clip in project.clips] == [0, 6_000_000, 12_000_000, 18_000_000]
    assert [clip.motion for clip in project.clips] == list(
        (
            MotionPreset.ZOOM_IN,
            MotionPreset.ZOOM_OUT,
            MotionPreset.PAN_LEFT_RIGHT,
            MotionPreset.PAN_RIGHT_LEFT,
        )
    )
    assert project.clips[-1].end_us == project.audio.duration_us


def test_manual_mapping_builds_captions_and_resolves_media(tmp_path: Path) -> None:
    audio = touch(tmp_path / "narration.wav")
    media = tmp_path / "media"
    media.mkdir()
    touch(media / "img-001.png")
    touch(media / "vid-002.mp4")
    mapping = tmp_path / "mapping.json"
    mapping.write_text(
        json.dumps(
            [
                {"clip": "img-001.png", "audio_start": 0, "audio_end": 4, "text": "Cảnh một"},
                {"sceneIndex": 2, "audio_start": 4, "audio_end": 10, "text": "Cảnh hai"},
            ]
        ),
        encoding="utf-8",
    )

    project = build_timeline(
        project_name="Mapped",
        audio_path=audio,
        media_dir=media,
        mapping_path=mapping,
        probe=FakeProbe({"narration.wav": 10, "vid-002.mp4": 3}),
    )

    assert [clip.media_type for clip in project.clips] == [MediaType.IMAGE, MediaType.VIDEO]
    assert [caption.text for caption in project.captions] == ["Cảnh một", "Cảnh hai"]
    assert project.clips[1].speed == pytest.approx(0.5)
    assert all(clip.motion is not MotionPreset.NONE for clip in project.clips)


def test_story_mapping_allocates_time_by_word_weight(tmp_path: Path) -> None:
    audio = touch(tmp_path / "narration.wav")
    media = tmp_path / "media"
    media.mkdir()
    touch(media / "img-001.png")
    touch(media / "img-002.png")
    mapping = tmp_path / "story.json"
    mapping.write_text(
        json.dumps(
            {
                "scenes": [
                    {"sceneIndex": 1, "sourceText": "một"},
                    {"sceneIndex": 2, "sourceText": "hai ba bốn"},
                ]
            }
        ),
        encoding="utf-8",
    )

    project = build_timeline(
        project_name="Story",
        audio_path=audio,
        media_dir=media,
        mapping_path=mapping,
        config=PlannerConfig(image_shot_duration_us=seconds_to_us(60)),
        probe=FakeProbe({"narration.wav": 20}),
    )

    assert [clip.duration_us for clip in project.clips] == [5_000_000, 15_000_000]


def test_short_video_is_repeated_as_editable_segments(tmp_path: Path) -> None:
    audio = touch(tmp_path / "narration.wav")
    media = tmp_path / "media"
    media.mkdir()
    touch(media / "vid-001.mp4")

    project = build_timeline(
        project_name="Loop",
        audio_path=audio,
        media_dir=media,
        config=PlannerConfig(min_video_speed=0.5, max_video_speed=4.0),
        probe=FakeProbe({"narration.wav": 20, "vid-001.mp4": 2}),
    )

    assert len(project.clips) == 5
    assert all(clip.speed == pytest.approx(0.5) for clip in project.clips)
    assert all(clip.source_duration_us == 2_000_000 for clip in project.clips)
    assert project.clips[-1].end_us == 20_000_000


def test_long_video_is_trimmed_at_maximum_speed(tmp_path: Path) -> None:
    audio = touch(tmp_path / "narration.wav")
    media = tmp_path / "media"
    media.mkdir()
    touch(media / "vid-001.mp4")

    project = build_timeline(
        project_name="Trim",
        audio_path=audio,
        media_dir=media,
        probe=FakeProbe({"narration.wav": 5, "vid-001.mp4": 100}),
    )

    assert len(project.clips) == 1
    assert project.clips[0].speed == 4.0
    assert project.clips[0].source_duration_us == 20_000_000


def test_partial_timestamp_mapping_is_rejected(tmp_path: Path) -> None:
    audio = touch(tmp_path / "narration.wav")
    media = tmp_path / "media"
    media.mkdir()
    touch(media / "img-001.png")
    mapping = tmp_path / "mapping.json"
    mapping.write_text(json.dumps([{"audio_start": 0}]), encoding="utf-8")

    with pytest.raises(ValueError, match="both"):
        build_timeline(
            project_name="Bad",
            audio_path=audio,
            media_dir=media,
            mapping_path=mapping,
            probe=FakeProbe({"narration.wav": 5}),
        )
