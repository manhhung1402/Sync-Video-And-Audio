from pathlib import Path

import pytest

from syncvideo_audio import (
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


def sample_project() -> TimelineProject:
    return TimelineProject(
        name="Demo dự án",
        canvas=CanvasSpec(width=1080, height=1920, fps=30),
        audio=AudioTrack(Path("D:/media/narration.mp3"), seconds_to_us(10.0)),
        clips=[
            TimelineClip(
                media_type=MediaType.IMAGE,
                path=Path("D:/media/img-001.png"),
                start_us=0,
                duration_us=seconds_to_us(6.0),
                motion=MotionPreset.ZOOM_IN,
                scene_index=1,
            ),
            TimelineClip(
                media_type=MediaType.VIDEO,
                path=Path("D:/media/vid-002.mp4"),
                start_us=seconds_to_us(6.0),
                duration_us=seconds_to_us(4.0),
                source_duration_us=seconds_to_us(5.0),
                speed=1.25,
                scene_index=2,
            ),
        ],
        captions=[TimelineCaption("Xin chào", 0, seconds_to_us(2.0))],
    )


def test_time_conversion_rounds_to_microseconds() -> None:
    assert seconds_to_us(1.2345674) == 1_234_567
    assert seconds_to_us(1.2345676) == 1_234_568
    assert us_to_seconds(1_250_000) == 1.25


def test_manifest_round_trip_and_atomic_write(tmp_path: Path) -> None:
    original = sample_project()
    output = original.write_json(tmp_path / "nested" / "timeline.json")

    restored = TimelineProject.read_json(output)

    assert restored.to_dict() == original.to_dict()
    assert not list(output.parent.glob("*.tmp"))


def test_manifest_rejects_overlapping_visual_clips() -> None:
    with pytest.raises(ValueError, match="overlaps"):
        TimelineProject(
            name="bad",
            canvas=CanvasSpec(),
            audio=AudioTrack(Path("audio.mp3"), seconds_to_us(10)),
            clips=[
                TimelineClip(MediaType.IMAGE, Path("1.png"), 0, seconds_to_us(6)),
                TimelineClip(MediaType.IMAGE, Path("2.png"), seconds_to_us(5), seconds_to_us(5)),
            ],
        )


def test_manifest_rejects_items_beyond_audio_duration() -> None:
    with pytest.raises(ValueError, match="exceeds"):
        TimelineProject(
            name="bad",
            canvas=CanvasSpec(),
            audio=AudioTrack(Path("audio.mp3"), seconds_to_us(3)),
            captions=[TimelineCaption("too long", 0, seconds_to_us(4))],
        )


def test_video_cannot_receive_still_motion() -> None:
    with pytest.raises(ValueError, match="still images"):
        TimelineClip(
            MediaType.VIDEO,
            Path("video.mp4"),
            0,
            seconds_to_us(1),
            motion=MotionPreset.ZOOM_IN,
        )


def test_manifest_rejects_unknown_schema() -> None:
    data = sample_project().to_dict()
    data["schemaVersion"] = 999
    with pytest.raises(ValueError, match="unsupported"):
        TimelineProject.from_dict(data)
