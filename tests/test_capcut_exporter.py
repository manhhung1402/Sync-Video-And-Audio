import json
from pathlib import Path

import pytest

from syncvideo_audio import (
    AudioTrack,
    CanvasSpec,
    CapCutDraftExporter,
    MediaInfo,
    MediaType,
    MotionPreset,
    TimelineClip,
    TimelineProject,
)


class FakeProbe:
    def probe(self, path: Path) -> MediaInfo:
        if path.suffix == ".mp4":
            return MediaInfo(duration_us=3_000_000, width=1920, height=1080, codec="h264")
        return MediaInfo(duration_us=0, width=1200, height=1600, codec="png")


def make_project(tmp_path: Path) -> TimelineProject:
    audio = tmp_path / "voice over.wav"
    image = tmp_path / "ảnh một.png"
    video = tmp_path / "clip.mp4"
    audio.write_bytes(b"audio")
    image.write_bytes(b"image")
    video.write_bytes(b"video")
    return TimelineProject(
        name="Demo: Native / Draft",
        canvas=CanvasSpec(1080, 1920, 30),
        audio=AudioTrack(audio, 5_000_000, 0.9),
        clips=[
            TimelineClip(MediaType.IMAGE, image, 0, 2_000_000, motion=MotionPreset.ZOOM_IN),
            TimelineClip(
                MediaType.VIDEO,
                video,
                2_000_000,
                3_000_000,
                source_start_us=0,
                source_duration_us=3_000_000,
                volume=0.25,
            ),
        ],
    )


def test_exports_capcut_91_native_draft_atomically(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    result = CapCutDraftExporter(FakeProbe()).export(project, tmp_path / "drafts")

    assert result.draft_folder.name == "Demo_ Native _ Draft"
    expected_files = {
        "draft_content.json",
        "draft_meta_info.json",
        "draft_agency_config.json",
        "draft_biz_config.json",
        "draft_settings",
        "draft_virtual_store.json",
        "key_value.json",
        "timeline_layout.json",
        "Timelines/project.json",
        f"Timelines/{result.timeline_id}/draft_content.json",
    }
    actual = {
        path.relative_to(result.draft_folder).as_posix()
        for path in result.draft_folder.rglob("*")
        if path.is_file()
    }
    assert expected_files <= actual
    assert len(result.copied_assets) == 3
    assert all(path.is_file() for path in result.copied_assets)
    assert not list((tmp_path / "drafts").glob("*.tmp"))
    meta = json.loads((result.draft_folder / "draft_meta_info.json").read_text(encoding="utf-8"))
    assert Path(meta["draft_fold_path"]) == result.draft_folder


def test_content_has_editable_tracks_and_resolved_materials(tmp_path: Path) -> None:
    result = CapCutDraftExporter(FakeProbe()).export(make_project(tmp_path), tmp_path / "drafts")
    content = json.loads((result.draft_folder / "draft_content.json").read_text(encoding="utf-8"))
    mirror = json.loads(
        (result.draft_folder / "Timelines" / result.timeline_id / "draft_content.json").read_text(encoding="utf-8")
    )

    assert content == mirror
    assert content["version"] == 360_000
    assert content["new_version"] == "179.0.0"
    assert content["duration"] == 5_000_000
    assert [track["type"] for track in content["tracks"]] == ["video", "audio"]
    assert [item["type"] for item in content["materials"]["videos"]] == ["photo", "video"]
    video_segments = content["tracks"][0]["segments"]
    assert video_segments[0]["common_keyframes"][0]["property_type"] == "KFTypeScaleX"
    assert video_segments[1]["common_keyframes"] == []
    assert content["tracks"][1]["segments"][0]["common_keyframes"] == []

    ids = {
        item["id"]
        for bucket in content["materials"].values()
        for item in bucket
        if "id" in item
    }
    for track in content["tracks"]:
        for segment in track["segments"]:
            assert segment["material_id"] in ids
            assert set(segment["extra_material_refs"]) <= ids

    buckets_by_id = {
        item["id"]: bucket
        for bucket, items in content["materials"].items()
        for item in items
        if "id" in item
    }
    assert [buckets_by_id[item] for item in video_segments[0]["extra_material_refs"]] == [
        "speeds",
        "placeholder_infos",
        "canvases",
        "sound_channel_mappings",
        "material_colors",
        "vocal_separations",
    ]
    assert [
        buckets_by_id[item]
        for item in content["tracks"][1]["segments"][0]["extra_material_refs"]
    ] == [
        "speeds",
        "placeholder_infos",
        "beats",
        "sound_channel_mappings",
        "vocal_separations",
    ]

    asset_paths = [Path(item["path"]) for item in content["materials"]["videos"]]
    asset_paths += [Path(content["materials"]["audios"][0]["path"])]
    assert all(path.is_absolute() and path.is_file() for path in asset_paths)


def test_refuses_to_overwrite_existing_draft(tmp_path: Path) -> None:
    exporter = CapCutDraftExporter(FakeProbe())
    project = make_project(tmp_path)
    exporter.export(project, tmp_path / "drafts")

    with pytest.raises(FileExistsError):
        exporter.export(project, tmp_path / "drafts")


def test_failed_export_removes_staging_directory(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    project.audio.path.unlink()
    root = tmp_path / "drafts"

    with pytest.raises(FileNotFoundError):
        CapCutDraftExporter(FakeProbe()).export(project, root)

    assert root.is_dir()
    assert list(root.iterdir()) == []
