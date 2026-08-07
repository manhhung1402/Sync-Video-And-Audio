from pathlib import Path

from syncvideo_audio import (
    AudioTrack,
    CanvasSpec,
    MediaType,
    MotionPreset,
    TimelineClip,
    TimelineProject,
)
from syncvideo_audio.ffmpeg_renderer import build_image_filter, build_video_filter
from syncvideo_audio.ffmpeg_renderer import _timeline_frame_count


def project(tmp_path: Path, clip: TimelineClip) -> TimelineProject:
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"audio")
    return TimelineProject("render", CanvasSpec(1080, 1920, 30), AudioTrack(audio, clip.duration_us), [clip])


def test_image_filter_uses_manifest_motion_and_canvas(tmp_path: Path) -> None:
    image = tmp_path / "image.png"
    image.write_bytes(b"image")
    clip = TimelineClip(MediaType.IMAGE, image, 0, 2_000_000, motion=MotionPreset.PAN_LEFT_RIGHT)
    value = build_image_filter(project(tmp_path, clip), clip)
    assert "scale=1080:1920" in value
    assert "perspective=" in value
    assert "fps=30" in value


def test_video_filter_uses_manifest_speed(tmp_path: Path) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    clip = TimelineClip(
        MediaType.VIDEO,
        video,
        0,
        1_000_000,
        source_duration_us=2_000_000,
        speed=2.0,
        motion=MotionPreset.ZOOM_IN,
    )
    value = build_video_filter(project(tmp_path, clip), clip)
    assert value.startswith("setpts=PTS/2.000000000")
    assert "crop=1080:1920" in value
    assert "perspective=" in value
    assert "tpad=stop_mode=clone" in value


def test_frame_allocation_never_ends_before_audio(tmp_path: Path) -> None:
    image = tmp_path / "image.png"
    image.write_bytes(b"image")
    clips = [
        TimelineClip(MediaType.IMAGE, image, 0, 1_233_333),
        TimelineClip(MediaType.IMAGE, image, 1_233_333, 1_233_334),
        TimelineClip(MediaType.IMAGE, image, 2_466_667, 1_233_333),
    ]
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"audio")
    timeline = TimelineProject(
        "fractional", CanvasSpec(360, 640, 12), AudioTrack(audio, 3_700_000), clips
    )
    counts = [
        _timeline_frame_count(timeline, clip, index == len(clips) - 1)
        for index, clip in enumerate(clips)
    ]
    assert counts == [15, 15, 15]
    assert sum(counts) / timeline.canvas.fps >= 3.7
