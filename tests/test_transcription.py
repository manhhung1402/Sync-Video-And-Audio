import json
from pathlib import Path

import pytest

from syncvideo_audio.transcription import (
    TimedWord,
    TranscriptionError,
    align_transcript_lines,
    load_transcript,
)


def test_loads_one_scene_per_nonempty_text_line(tmp_path: Path) -> None:
    transcript = tmp_path / "voice.txt"
    transcript.write_text("Câu thứ nhất.\n\nCâu thứ hai.\n", encoding="utf-8")
    assert load_transcript(transcript) == ["Câu thứ nhất.", "Câu thứ hai."]


def test_splits_single_paragraph_into_sentences(tmp_path: Path) -> None:
    transcript = tmp_path / "voice.txt"
    transcript.write_text("Một câu. Hai câu! Ba câu?", encoding="utf-8")
    assert load_transcript(transcript) == ["Một câu.", "Hai câu!", "Ba câu?"]


def test_loads_json_scene_text(tmp_path: Path) -> None:
    transcript = tmp_path / "voice.json"
    transcript.write_text(
        json.dumps({"scenes": [{"sourceText": "Một"}, {"text": "Hai"}]}),
        encoding="utf-8",
    )
    assert load_transcript(transcript) == ["Một", "Hai"]


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
