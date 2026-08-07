"""Builders for the unencrypted CapCut Desktop 9.1 draft schema.

CapCut's format is undocumented and additive.  These builders deliberately
emit the conservative subset observed in CapCut International 9.1 projects.
Keeping schema construction separate from filesystem export makes future
version adapters straightforward.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from .manifest import CanvasSpec, MediaType, TimelineClip, TimelineProject
from .probe import MediaInfo


CAPCUT_CONTENT_VERSION = 360_000
CAPCUT_NEW_VERSION = "179.0.0"
CAPCUT_APP_VERSION = "9.1.0"
PHOTO_SOURCE_DURATION_US = 10_800_000_000

MATERIAL_BUCKETS = (
    "flowers", "videos", "tail_leaders", "audios", "images", "texts", "effects",
    "stickers", "canvases", "transitions", "audio_effects", "audio_fades", "beats",
    "material_animations", "placeholders", "placeholder_infos", "speeds", "common_mask",
    "chromas", "text_templates", "realtime_denoises", "audio_pannings",
    "audio_pitch_shifts", "video_trackings", "hsl", "drafts", "color_curves",
    "hsl_curves", "primary_color_wheels", "log_color_wheels", "video_effects",
    "ai_text_effects", "audio_balances", "handwrites", "manual_deformations",
    "manual_beautys", "plugin_effects", "sound_channel_mappings", "green_screens",
    "shapes", "material_colors", "digital_humans", "digital_human_model_dressing",
    "smart_crops", "ai_translates", "audio_track_indexes", "loudnesses",
    "vocal_beautifys", "vocal_separations", "smart_relights", "time_marks",
    "multi_language_refs", "video_shadows", "video_strokes", "video_radius",
)


def capcut_id() -> str:
    return str(uuid4()).upper()


def capcut_path(path: Path) -> str:
    return Path(path).resolve().as_posix()


def timerange(start: int, duration: int) -> dict[str, int]:
    return {"start": start, "duration": duration}


def empty_materials() -> dict[str, list[dict[str, Any]]]:
    return {name: [] for name in MATERIAL_BUCKETS}


def make_content(project: TimelineProject, timeline_id: str, timestamp_us: int) -> dict[str, Any]:
    return {
        "canvas_config": {
            "background": None,
            "height": project.canvas.height,
            "ratio": "original",
            "width": project.canvas.width,
        },
        "color_space": 0,
        "config": {
            "video_mute": False,
            "record_audio_last_index": 1,
            "extract_audio_last_index": 1,
            "original_sound_last_index": 1,
            "subtitle_recognition_id": "",
            "subtitle_taskinfo": [],
            "lyrics_recognition_id": "",
            "lyrics_taskinfo": [],
            "subtitle_sync": True,
            "lyrics_sync": True,
            "voice_change_sync": False,
            "sticker_max_index": 1,
            "adjust_max_index": 1,
            "material_save_mode": 0,
            "export_range": None,
            "maintrack_adsorb": True,
            "combination_max_index": 1,
            "attachment_info": [],
            "zoom_info_params": None,
            "system_font_list": [],
            "multi_language_mode": "none",
            "multi_language_main": "none",
            "multi_language_current": "none",
            "multi_language_list": [],
            "subtitle_keywords_config": None,
            "use_float_render": False,
        },
        "cover": None,
        "create_time": timestamp_us,
        "duration": project.duration_us,
        "extra_info": None,
        "fps": float(project.canvas.fps),
        "free_render_index_mode_on": False,
        "group_container": None,
        "id": timeline_id,
        "is_drop_frame_timecode": False,
        "keyframe_graph_list": [],
        "keyframes": {name: [] for name in (
            "adjusts", "audios", "effects", "filters", "handwrites", "stickers", "texts", "videos"
        )},
        "last_modified_platform": _platform(),
        "lyrics_effects": [],
        "materials": empty_materials(),
        "mutable_config": None,
        "name": "",
        "new_version": CAPCUT_NEW_VERSION,
        "path": "",
        "platform": _platform(),
        "relationships": [],
        "render_index_track_mode_on": False,
        "retouch_cover": None,
        "source": "default",
        "static_cover_image_path": "",
        "time_marks": None,
        "tracks": [],
        "update_time": timestamp_us,
        "version": CAPCUT_CONTENT_VERSION,
    }


def add_visual_clip(
    content: dict[str, Any], clip: TimelineClip, media_path: Path, info: MediaInfo
) -> dict[str, Any]:
    materials = content["materials"]
    material_id = capcut_id()
    source_duration = (
        PHOTO_SOURCE_DURATION_US
        if clip.media_type is MediaType.IMAGE
        else max(info.duration_us, clip.source_start_us + (clip.source_duration_us or clip.duration_us))
    )
    materials["videos"].append(_visual_material(material_id, clip, media_path, info, source_duration))

    refs = _visual_support_materials(materials)
    source_clip_duration = clip.source_duration_us or round(clip.duration_us * clip.speed)
    segment = _base_segment(
        material_id=material_id,
        start=clip.start_us,
        duration=clip.duration_us,
        source_start=clip.source_start_us,
        source_duration=source_clip_duration,
        speed=clip.speed,
        volume=clip.volume,
        refs=refs,
        visual=True,
    )
    return segment


def add_audio(content: dict[str, Any], project: TimelineProject, media_path: Path) -> dict[str, Any]:
    materials = content["materials"]
    material_id = capcut_id()
    materials["audios"].append({
        "id": material_id,
        "unique_id": "",
        "type": "extract_music",
        "name": media_path.stem,
        "duration": project.audio.duration_us,
        "path": capcut_path(media_path),
        "category_name": "local",
        "wave_points": [],
        "music_id": material_id,
        "app_id": 0,
        "text_id": "",
        "tone_type": "",
        "source_platform": 0,
        "video_id": "",
        "effect_id": "",
        "resource_id": "",
        "third_resource_id": "",
        "category_id": "",
        "intensifies_path": "",
        "formula_id": "",
        "check_flag": 3,
        "team_id": "",
        "local_material_id": material_id,
        "copyright_limit_type": "none",
        "wave_points": [],
    })
    refs = _audio_support_materials(materials)
    return _base_segment(
        material_id=material_id,
        start=0,
        duration=project.audio.duration_us,
        source_start=0,
        source_duration=project.audio.duration_us,
        speed=1.0,
        volume=project.audio.volume,
        refs=refs,
        visual=False,
    )


def make_track(track_type: str, segments: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "attribute_flag": 0,
        "flag": 0,
        "id": capcut_id(),
        "segments": segments,
        "type": track_type,
    }


def _platform() -> dict[str, Any]:
    return {"app_id": 359289, "app_source": "cc", "app_version": CAPCUT_APP_VERSION, "os": "windows"}


def _visual_material(
    material_id: str,
    clip: TimelineClip,
    media_path: Path,
    info: MediaInfo,
    duration: int,
) -> dict[str, Any]:
    width = info.width or 0
    height = info.height or 0
    return {
        "id": material_id,
        "unique_id": "",
        "type": "photo" if clip.media_type is MediaType.IMAGE else "video",
        "duration": duration,
        "path": capcut_path(media_path),
        "media_path": "",
        "local_id": "",
        "has_audio": clip.media_type is MediaType.VIDEO,
        "reverse_path": "",
        "intensifies_path": "",
        "reverse_intensifies_path": "",
        "intensifies_audio_path": "",
        "cartoon_path": "",
        "width": width,
        "height": height,
        "category_id": "",
        "category_name": "local",
        "material_id": "",
        "material_name": media_path.name,
        "material_url": "",
        "crop": {
            "upper_left_x": 0.0, "upper_left_y": 0.0,
            "upper_right_x": 1.0, "upper_right_y": 0.0,
            "lower_left_x": 0.0, "lower_left_y": 1.0,
            "lower_right_x": 1.0, "lower_right_y": 1.0,
        },
        "crop_ratio": "free",
        "audio_fade": None,
        "crop_scale": 1.0,
        "extra_type_option": 0,
        "stable": {"stable_level": 0, "matrix_path": "", "time_range": timerange(0, 0)},
        "source": 0,
        "source_platform": 0,
        "formula_id": "",
        "check_flag": 62_978_047,
        "local_material_id": capcut_id().lower(),
        "picture_from": "none",
        "is_ai_generate_content": False,
        "aigc_type": "none",
        "is_copyright": False,
    }


def _base_segment(
    *, material_id: str, start: int, duration: int, source_start: int,
    source_duration: int, speed: float, volume: float, refs: list[str], visual: bool,
) -> dict[str, Any]:
    segment: dict[str, Any] = {
        "id": capcut_id(),
        "source_timerange": timerange(source_start, source_duration),
        "target_timerange": timerange(start, duration),
        "render_timerange": timerange(0, 0),
        "desc": "",
        "state": 0,
        "speed": speed,
        "is_loop": False,
        "is_tone_modify": False,
        "reverse": False,
        "intensifies_audio": False,
        "cartoon": False,
        "volume": volume,
        "last_nonzero_volume": volume if volume > 0 else 1.0,
        "clip": ({
            "scale": {"x": 1.0, "y": 1.0},
            "rotation": 0.0,
            "transform": {"x": 0.0, "y": 0.0},
            "flip": {"vertical": False, "horizontal": False},
            "alpha": 1.0,
        } if visual else None),
        "uniform_scale": ({"on": True, "value": 1.0} if visual else None),
        "material_id": material_id,
        "extra_material_refs": refs,
        "render_index": 0,
        "keyframe_refs": [],
        "enable_lut": visual,
        "enable_adjust": visual,
        "enable_hsl": False,
        "visible": True,
        "group_id": "",
        "enable_color_curves": True,
        "enable_hsl_curves": True,
        "track_render_index": 0 if visual else 1,
        "hdr_settings": ({"mode": 1, "intensity": 1.0, "nits": 1000} if visual else None),
        "enable_color_wheels": True,
        "track_attribute": 0,
        "is_placeholder": False,
        "template_id": "",
        "enable_smart_color_adjust": False,
        "template_scene": "default",
        "common_keyframes": [],
        "caption_info": None,
        "responsive_layout": {
            "enable": False, "target_follow": "", "size_layout": 0,
            "horizontal_pos_layout": 0, "vertical_pos_layout": 0,
        },
        "enable_color_match_adjust": False,
        "enable_color_correct_adjust": False,
        "enable_adjust_mask": False,
        "raw_segment_id": "",
        "lyric_keyframes": None,
        "enable_video_mask": True,
        "digital_human_template_group_id": "",
        "color_correct_alg_result": "",
        "source": "segmentsourcenormal",
        "enable_mask_stroke": False,
        "enable_mask_shadow": False,
        "enable_color_adjust_pro": False,
    }
    return segment


def _visual_support_materials(materials: dict[str, list[dict[str, Any]]]) -> list[str]:
    speed_id, placeholder_id, sound_id, vocal_id = _common_support_materials(materials)
    canvas_id = capcut_id()
    materials["canvases"].append({
        "album_image": "", "blur": 0.0, "color": "", "id": canvas_id,
        "image": "", "image_id": "", "image_name": "", "source_platform": 0,
        "team_id": "", "type": "canvas_color",
    })
    color_id = capcut_id()
    materials["material_colors"].append({
        "id": color_id,
        "is_color_clip": False,
        "is_gradient": False,
        "solid_color": "",
        "gradient_colors": [],
        "gradient_percents": [],
        "gradient_angle": 90.0,
        "width": 0.0,
        "height": 0.0,
    })
    return [speed_id, placeholder_id, canvas_id, sound_id, color_id, vocal_id]


def _audio_support_materials(materials: dict[str, list[dict[str, Any]]]) -> list[str]:
    speed_id, placeholder_id, sound_id, vocal_id = _common_support_materials(materials)
    beats_id = capcut_id()
    materials["beats"].append({
        "ai_beats": {
            "beat_speed_infos": [], "beats_path": "", "beats_url": "",
            "melody_path": "", "melody_url": "", "melody_percents": [0.6],
        },
        "enable_ai_beats": False, "gear": 404, "gear_count": 0, "id": beats_id,
        "mode": 404, "type": "beats", "user_beats": [], "user_delete_ai_beats": None,
    })
    return [speed_id, placeholder_id, beats_id, sound_id, vocal_id]


def _common_support_materials(
    materials: dict[str, list[dict[str, Any]]]
) -> tuple[str, str, str, str]:
    speed_id = capcut_id()
    placeholder_id = capcut_id()
    sound_id = capcut_id()
    vocal_id = capcut_id()
    materials["speeds"].append({"curve_speed": None, "id": speed_id, "mode": 0, "speed": 1.0, "type": "speed"})
    materials["placeholder_infos"].append({
        "id": placeholder_id, "meta_type": "none", "type": "placeholder_info",
        "res_path": "", "res_text": "", "error_path": "", "error_text": "",
    })
    materials["sound_channel_mappings"].append({
        "audio_channel_mapping": 0, "id": sound_id,
        "is_config_open": False, "type": "",
    })
    materials["vocal_separations"].append({
        "choice": 0, "id": vocal_id, "production_path": "",
        "removed_sounds": [], "time_range": None, "type": "vocal_separation",
        "final_algorithm": "", "enter_from": "",
    })
    return speed_id, placeholder_id, sound_id, vocal_id


def make_timeline_project(timeline_id: str, timestamp_us: int) -> dict[str, Any]:
    return {
        "config": {
            "color_space": -1, "mixed_track_mode_on": False,
            "render_index_track_mode_on": False, "use_float_render": False,
        },
        "create_time": timestamp_us,
        "id": capcut_id(),
        "main_timeline_id": timeline_id,
        "timelines": [{
            "create_time": timestamp_us, "id": timeline_id,
            "is_marked_delete": False, "name": "Timeline 01", "update_time": timestamp_us,
        }],
        "update_time": timestamp_us,
        "version": 0,
    }


def make_meta(project: TimelineProject, draft_id: str, draft_folder: Path, timestamp_us: int) -> dict[str, Any]:
    root = draft_folder.parent
    return {
        "cloud_draft_cover": False,
        "cloud_draft_sync": False,
        "cloud_package_completed_time": "",
        "draft_cloud_last_action_download": False,
        "draft_cloud_package_type": "",
        "draft_cover": "",
        "draft_deeplink_url": "",
        "draft_fold_path": capcut_path(draft_folder),
        "draft_id": draft_id,
        "draft_is_ae_produce": False,
        "draft_is_ai_packaging_used": False,
        "draft_is_ai_shorts": False,
        "draft_is_ai_translate": False,
        "draft_is_article_video_draft": False,
        "draft_is_cloud_temp_draft": False,
        "draft_is_from_deeplink": "false",
        "draft_is_invisible": False,
        "draft_is_pippit_draft": False,
        "draft_is_web_article_video": False,
        "draft_materials": [{"type": kind, "value": []} for kind in (0, 1, 2, 3, 6, 7)],
        "draft_materials_copied_info": [],
        "draft_name": project.name,
        "draft_need_rename_folder": False,
        "draft_new_version": "",
        "draft_removable_storage_device": draft_folder.drive.rstrip(":") if draft_folder.drive else "",
        "draft_root_path": str(root.resolve()),
        "draft_segment_extra_info": [],
        "draft_timeline_materials_size_": 0,
        "draft_type": "",
        "draft_web_article_video_enter_from": "",
        "tm_draft_cloud_entry_id": -1,
        "tm_draft_cloud_modified": 0,
        "tm_draft_cloud_parent_entry_id": -1,
        "tm_draft_cloud_space_id": -1,
        "tm_draft_cloud_user_id": -1,
        "tm_draft_create": timestamp_us,
        "tm_draft_modified": timestamp_us,
        "tm_draft_removed": 0,
        "tm_duration": project.duration_us,
    }


def canvas_fit_scale(canvas: CanvasSpec, info: MediaInfo) -> float:
    """Scale that fills the canvas without letterboxing."""

    if not info.width or not info.height:
        return 1.0
    return max(canvas.width / info.width, canvas.height / info.height)
