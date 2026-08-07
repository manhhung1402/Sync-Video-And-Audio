from syncvideo_audio import MotionPreset, MotionSettings, apply_motion_keyframes


def segment() -> dict:
    return {"common_keyframes": [], "uniform_scale": {"on": True, "value": 1.0}}


def values(item: dict) -> tuple[float, float]:
    frames = item["keyframe_list"]
    return frames[0]["values"][0], frames[1]["values"][0]


def test_zoom_in_uses_native_uniform_scale_property() -> None:
    target = segment()
    apply_motion_keyframes(target, MotionPreset.ZOOM_IN, 4_000_000)

    keyframes = target["common_keyframes"]
    assert [item["property_type"] for item in keyframes] == ["KFTypeScaleX"]
    assert values(keyframes[0]) == (1.0, 1.08)
    assert [frame["time_offset"] for frame in keyframes[0]["keyframe_list"]] == [0, 4_000_000]
    assert all(frame["curveType"] == "Line" for frame in keyframes[0]["keyframe_list"])


def test_pan_adds_overscan_and_directional_position() -> None:
    cases = {
        MotionPreset.PAN_LEFT_RIGHT: ("KFTypePositionX", (-0.025, 0.025)),
        MotionPreset.PAN_RIGHT_LEFT: ("KFTypePositionX", (0.025, -0.025)),
        MotionPreset.PAN_TOP_BOTTOM: ("KFTypePositionY", (0.025, -0.025)),
        MotionPreset.PAN_BOTTOM_TOP: ("KFTypePositionY", (-0.025, 0.025)),
    }
    for preset, (property_type, expected) in cases.items():
        target = segment()
        apply_motion_keyframes(target, preset, 2_000_000)

        scale, position = target["common_keyframes"]
        assert scale["property_type"] == "KFTypeScaleX"
        assert values(scale) == (1.06, 1.06)
        assert position["property_type"] == property_type
        assert values(position) == expected


def test_none_keeps_segment_untouched() -> None:
    target = segment()
    apply_motion_keyframes(target, MotionPreset.NONE, 1_000_000)
    assert target["common_keyframes"] == []


def test_motion_strength_is_configurable() -> None:
    target = segment()
    settings = MotionSettings(zoom_amount=0.12, pan_amount=0.04, pan_overscan=0.1)
    apply_motion_keyframes(target, MotionPreset.ZOOM_OUT, 1_000_000, settings)
    assert values(target["common_keyframes"][0]) == (1.12, 1.0)
