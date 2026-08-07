"""Command-line entry point for planning and hand-off export."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .manifest import CanvasSpec, TimelineProject, seconds_to_us
from .pipeline import OutputMode, PipelineOutputs, export_timeline
from .planner import AlignmentMode, PlannerConfig, build_timeline
from .transcription import WhisperConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="syncvideo-audio",
        description="Sync ordered images/videos to narration and create an editable CapCut hand-off.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build", help="plan from media/audio and export outputs")
    build.add_argument("--audio", required=True, type=Path)
    build.add_argument("--media-dir", required=True, type=Path)
    build.add_argument("--name", required=True)
    build.add_argument("--mapping", type=Path)
    build.add_argument(
        "--sync-mode",
        choices=[mode.value for mode in AlignmentMode],
        default=AlignmentMode.EQUAL.value,
        help="equal: chia đều; transcript: dùng Whisper timestamp và ghép theo thứ tự media",
    )
    build.add_argument("--transcript", type=Path, help="TXT/SRT/JSON, một câu cho mỗi media")
    build.add_argument("--whisper-model", default="small")
    build.add_argument("--language", help="mã ngôn ngữ Whisper, ví dụ vi/en/ja")
    _add_output_arguments(build)
    build.add_argument("--width", type=int, default=1920)
    build.add_argument("--height", type=int, default=1080)
    build.add_argument("--fps", type=int, default=30)
    build.add_argument("--image-duration", type=float, default=6.0)
    build.add_argument("--no-motion", action="store_true")
    build.add_argument("--no-captions", action="store_true")

    export = subparsers.add_parser("export", help="export an existing editable timeline manifest")
    export.add_argument("manifest", type=Path)
    _add_output_arguments(export)
    return parser


def _add_output_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--mode", choices=[item.value for item in OutputMode], default="both")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--draft-root", type=Path)
    parser.add_argument("--no-register", action="store_true")
    parser.add_argument("--overwrite-mp4", action="store_true")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            project = build_timeline(
                project_name=args.name,
                audio_path=args.audio,
                media_dir=args.media_dir,
                mapping_path=args.mapping,
                alignment_mode=AlignmentMode(args.sync_mode),
                transcript_path=args.transcript,
                whisper_config=WhisperConfig(
                    model=args.whisper_model,
                    language=args.language,
                ),
                config=PlannerConfig(
                    canvas=CanvasSpec(args.width, args.height, args.fps),
                    image_shot_duration_us=seconds_to_us(args.image_duration),
                    add_captions=not args.no_captions,
                    motion_enabled=not args.no_motion,
                ),
            )
        else:
            project = TimelineProject.read_json(args.manifest)
        outputs = export_timeline(
            project,
            mode=OutputMode(args.mode),
            output_dir=args.output_dir,
            draft_root=args.draft_root,
            register_with_capcut=not args.no_register,
            overwrite_mp4=args.overwrite_mp4,
        )
    except (OSError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(json.dumps(_outputs_dict(outputs), ensure_ascii=False, indent=2))
    return 0


def _outputs_dict(outputs: PipelineOutputs) -> dict[str, object]:
    return {
        "manifest": str(outputs.manifest),
        "mp4": str(outputs.mp4) if outputs.mp4 else None,
        "capcutDraft": str(outputs.capcut.draft_folder) if outputs.capcut else None,
        "capcutDraftId": outputs.capcut.draft_id if outputs.capcut else None,
        "registeredWithCapCut": outputs.registered_with_capcut,
    }


if __name__ == "__main__":
    raise SystemExit(main())
