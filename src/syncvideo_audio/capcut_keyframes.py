"""Native CapCut keyframes for subtle still-image motion."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .capcut_schema import capcut_id
from .manifest import MotionPreset


#: Pan overscan is derived from the travel amount instead of being tuned separately.
PAN_OVERSCAN_RATIO = 2.5
MAX_AMOUNT = 0.5


@dataclass(frozen=True, slots=True)
class MotionSettings:
    """One strength value per motion preset, in fractions of the frame."""

    zoom_in: float = 0.08
    zoom_out: float = 0.08
    pan_left_right: float = 0.025
    pan_right_left: float = 0.025
    pan_top_bottom: float = 0.025
    pan_bottom_top: float = 0.025

    def __post_init__(self) -> None:
        for name, value in self.amounts().items():
            if not 0.0 < value <= MAX_AMOUNT:
                raise ValueError(f"{name} must be between 0 and {MAX_AMOUNT}")

    def amounts(self) -> dict[str, float]:
        return {
            preset.value: float(getattr(self, preset.value))
            for preset in MotionPreset
            if preset is not MotionPreset.NONE
        }

    def amount_for(self, preset: MotionPreset) -> float:
        return float(getattr(self, MotionPreset(preset).value))


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

    amount = settings.amount_for(preset)
    zoom = 1.0 + amount
    overscan = 1.0 + min(amount * PAN_OVERSCAN_RATIO, MAX_AMOUNT)
    motion: list[tuple[str, float, float]]
    if preset is MotionPreset.ZOOM_IN:
        motion = [("KFTypeScaleX", 1.0, zoom)]
    elif preset is MotionPreset.ZOOM_OUT:
        motion = [("KFTypeScaleX", zoom, 1.0)]
    elif preset is MotionPreset.PAN_LEFT_RIGHT:
        motion = [
            ("KFTypeScaleX", overscan, overscan),
            ("KFTypePositionX", -amount, amount),
        ]
    elif preset is MotionPreset.PAN_RIGHT_LEFT:
        motion = [
            ("KFTypeScaleX", overscan, overscan),
            ("KFTypePositionX", amount, -amount),
        ]
    elif preset is MotionPreset.PAN_TOP_BOTTOM:
        motion = [
            ("KFTypeScaleX", overscan, overscan),
            ("KFTypePositionY", amount, -amount),
        ]
    elif preset is MotionPreset.PAN_BOTTOM_TOP:
        motion = [
            ("KFTypeScaleX", overscan, overscan),
            ("KFTypePositionY", -amount, amount),
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
