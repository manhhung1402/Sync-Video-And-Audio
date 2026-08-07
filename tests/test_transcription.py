import json
from pathlib import Path

import pytest

from syncvideo_audio.transcription import (
    TimedWord,
    TranscriptionError,
    align_transcript_lines,
    load_transcript,
    split_transcript_sentences,
)


def test_line_breaks_do_not_create_scenes_without_punctuation(tmp_path: Path) -> None:
    transcript = tmp_path / "voice.txt"
    transcript.write_text(
        "Câu thứ nhất\n\nvẫn đang tiếp tục.\nCâu thứ hai",
        encoding="utf-8",
    )
    assert load_transcript(transcript) == [
        "Câu thứ nhất vẫn đang tiếp tục.",
        "Câu thứ hai",
    ]


def test_splits_single_paragraph_into_sentences(tmp_path: Path) -> None:
    transcript = tmp_path / "voice.txt"
    transcript.write_text("Một câu. Hai câu! Ba câu?", encoding="utf-8")
    assert load_transcript(transcript) == ["Một câu.", "Hai câu!", "Ba câu?"]


def test_loads_json_scene_text(tmp_path: Path) -> None:
    transcript = tmp_path / "voice.json"
    transcript.write_text(
        json.dumps({"scenes": [{"sourceText": "Một."}, {"text": "Hai。"}]}),
        encoding="utf-8",
    )
    assert load_transcript(transcript) == ["Một.", "Hai。"]


def test_srt_cues_are_joined_before_sentence_splitting(tmp_path: Path) -> None:
    transcript = tmp_path / "voice.srt"
    transcript.write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nCâu này\n\n"
        "2\n00:00:01,000 --> 00:00:02,000\nvẫn chưa kết thúc. Câu sau.",
        encoding="utf-8",
    )
    assert load_transcript(transcript) == [
        "Câu này vẫn chưa kết thúc.",
        "Câu sau.",
    ]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "Soft light appears. Birds begin to sing! Is morning here?",
            ["Soft light appears.", "Birds begin to sing!", "Is morning here?"],
        ),
        ("朝です。「元気ですか？」はい！", ["朝です。", "「元気ですか？」", "はい！"]),
        ("早晨开始了。鸟儿在歌唱！你听到了吗？", ["早晨开始了。", "鸟儿在歌唱！", "你听到了吗？"]),
        (
            "아침이 시작됩니다.\n새들이 노래합니다! 들리시나요?",
            ["아침이 시작됩니다.", "새들이 노래합니다!", "들리시나요?"],
        ),
    ],
)
def test_splits_multilingual_transcript_without_requiring_spaces(
    text: str,
    expected: list[str],
) -> None:
    assert split_transcript_sentences(text) == expected


def test_decimal_point_does_not_split_a_sentence() -> None:
    assert split_transcript_sentences("Giá trị là 3.14. Câu sau.") == [
        "Giá trị là 3.14.",
        "Câu sau.",
    ]


def test_aligns_reference_lines_to_whisper_words_and_covers_audio() -> None:
    lines = ["Xin chào mọi người.", "Hôm nay chúng ta bắt đầu.", "Cảm ơn bạn."]
    recognized = [
        TimedWord("xin", 200_000, 400_000),
        TimedWord("chào", 420_000, 650_000),
        TimedWord("mọi", 670_000, 850_000),
        TimedWord("người", 870_000, 1_050_000),
        TimedWord("hôm", 1_500_000, 1_700_000),
        TimedWord("nay", 1_720_000, 1_900_000),
        TimedWord("chúng", 1_920_000, 2_100_000),
        TimedWord("ta", 2_120_000, 2_250_000),
        TimedWord("bắt", 2_270_000, 2_450_000),
        TimedWord("đầu", 2_470_000, 2_700_000),
        TimedWord("cảm", 3_200_000, 3_400_000),
        TimedWord("ơn", 3_420_000, 3_580_000),
        TimedWord("bạn", 3_600_000, 3_800_000),
    ]
    aligned = align_transcript_lines(lines, recognized, 4_000_000)

    assert aligned[0].start_us == 0
    assert 1_000_000 < aligned[0].end_us < 1_500_000
    assert 2_700_000 < aligned[1].end_us < 3_200_000
    assert aligned[-1].end_us == 4_000_000
    assert [item.text for item in aligned] == lines


def test_rejects_multiple_lines_when_whisper_has_only_one_token() -> None:
    with pytest.raises(TranscriptionError, match="không đủ timestamp"):
        align_transcript_lines(
            ["Câu một.", "Câu hai."],
            [TimedWord("câu", 100_000, 400_000)],
            1_000_000,
        )


def test_aligns_japanese_characters_when_whisper_returns_phrase_chunks() -> None:
    aligned = align_transcript_lines(
        ["朝が始まります。", "鳥が歌います。"],
        [
            TimedWord("朝が始まります", 100_000, 900_000),
            TimedWord("鳥が歌います", 1_500_000, 2_300_000),
        ],
        2_500_000,
    )
    assert aligned[0].end_us == 1_200_000
    assert aligned[1].end_us == 2_500_000
