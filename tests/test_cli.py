from syncvideo_audio.cli import build_parser


def test_build_cli_defaults_to_handoff_both() -> None:
    args = build_parser().parse_args([
        "build", "--audio", "voice.wav", "--media-dir", "media",
        "--name", "Demo", "--output-dir", "output",
    ])
    assert args.mode == "both"
    assert args.sync_mode == "equal"
    assert args.image_duration == 6.0
    assert args.no_motion is False


def test_export_cli_accepts_capcut_only() -> None:
    args = build_parser().parse_args([
        "export", "demo.timeline.json", "--mode", "capcut",
        "--output-dir", "output", "--draft-root", "drafts", "--no-register",
    ])
    assert args.mode == "capcut"
    assert args.no_register is True


def test_build_cli_accepts_transcript_alignment() -> None:
    args = build_parser().parse_args([
        "build",
        "--audio",
        "voice.wav",
        "--media-dir",
        "media",
        "--name",
        "Demo",
        "--output-dir",
        "output",
        "--sync-mode",
        "transcript",
        "--transcript",
        "voice.txt",
        "--language",
        "vi",
    ])
    assert args.sync_mode == "transcript"
    assert args.transcript.name == "voice.txt"
    assert args.language == "vi"
