"""Native CapCut keyframes for subtle still-image motion."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .capcut_schema import capcut_id
from .manifest import MotionPreset


@dataclass(frozen=True, slots=True)
class MotionSettings:
    zoom_amount: float = 0.08
    pan_amount: float = 0.025
    pan_overscan: float = 0.06

    def __post_init__(self) -> None:
        if not 0.0 < self.zoom_amount <= 0.5:
            raise ValueError("zoom amount must be between 0 and 0.5")
        if not 0.0 < self.pan_amount <= 0.25:
            raise ValueError("pan amount must be between 0 and 0.25")
        if not 0.0 <= self.pan_overscan <= 0.5:
            raise ValueError("pan overscan must be between 0 and 0.5")


DEFAULT_MOTION_SETTINGS = MotionSettings()


def apply_motion_keyframes(
    segment: dict[str, Any],
    preset: MotionPreset,
    duration_us: int,
    settings: MotionSettings = DEFAULT_MOTION_SETTINGS,
) -> None:
    """Apply a two-point, editable native keyframe motion to a visual segment."""

    preset = MotionPreset(preset)
    if duration_us <= 0:
        raise ValueError("keyframe duration must be positive")
    if preset is MotionPreset.NONE:
        return

    zoom = 1.0 + settings.zoom_amount
    overscan = 1.0 + settings.pan_overscan
    motion: list[tuple[str, float, float]]
    if preset is MotionPreset.ZOOM_IN:
        motion = [("KFTypeScaleX", 1.0, zoom)]
    elif preset is MotionPreset.ZOOM_OUT:
        motion = [("KFTypeScaleX", zoom, 1.0)]
    elif preset is MotionPreset.PAN_LEFT_RIGHT:
        motion = [
            ("KFTypeScaleX", overscan, overscan),
            ("KFTypePositionX", -settings.pan_amount, settings.pan_amount),
        ]
    elif preset is MotionPreset.PAN_RIGHT_LEFT:
        motion = [
            ("KFTypeScaleX", overscan, overscan),
            ("KFTypePositionX", settings.pan_amount, -settings.pan_amount),
        ]
    elif preset is MotionPreset.PAN_TOP_BOTTOM:
        motion = [
            ("KFTypeScaleX", overscan, overscan),
            ("KFTypePositionY", settings.pan_amount, -settings.pan_amount),
        ]
    elif preset is MotionPreset.PAN_BOTTOM_TOP:
        motion = [
            ("KFTypeScaleX", overscan, overscan),
            ("KFTypePositionY", -settings.pan_amount, settings.pan_amount),
        ]
    else:  # pragma: no cover - exhaustive guard for future enum additions
        raise ValueError(f"unsupported motion preset: {preset}")

    segment["common_keyframes"] = [
        _keyframe_list(property_type, duration_us, start, end)
        for property_type, start, end in motion
    ]
    segment["uniform_scale"] = {"on": True, "value": 1.0}


def _keyframe_list(
    property_type: str, duration_us: int, start_value: float, end_value: float
) -> dict[str, Any]:
    return {
        "id": capcut_id(),
        "keyframe_list": [
            _keyframe(0, start_value),
            _keyframe(duration_us, end_value),
        ],
        "material_id": "",
        "property_type": property_type,
    }


def _keyframe(time_offset: int, value: float) -> dict[str, Any]:
    return {
        "curveType": "Line",
        "graphID": "",
        "left_control": {"x": 0.0, "y": 0.0},
        "right_control": {"x": 0.0, "y": 0.0},
        "id": capcut_id(),
        "time_offset": time_offset,
        "values": [value],
    }
