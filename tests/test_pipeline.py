from dataclasses import dataclass
from pathlib import Path

from syncvideo_audio import AudioTrack, CanvasSpec, MediaType, TimelineClip, TimelineProject
from syncvideo_audio.capcut_exporter import CapCutExportResult
from syncvideo_audio.pipeline import OutputMode, export_timeline


def make_project(tmp_path: Path) -> TimelineProject:
    audio = tmp_path / "audio.wav"
    image = tmp_path / "image.png"
    audio.write_bytes(b"audio")
    image.write_bytes(b"image")
    return TimelineProject(
        "Demo",
        CanvasSpec(360, 640, 12),
        AudioTrack(audio, 1_000_000),
        [TimelineClip(MediaType.IMAGE, image, 0, 1_000_000)],
    )


@dataclass
class FakeRenderer:
    calls: list[tuple[str, bool]]

    def render(self, project, destination, *, overwrite, burn_captions, progress_callback):
        self.calls.append((project.name, burn_captions))
        Path(destination).write_bytes(b"mp4")
        if progress_callback:
            progress_callback(1.0, "rendered")
        return Path(destination)


class FakeExporter:
    def __init__(self) -> None:
        self.names: list[str] = []

    def export(self, project, draft_root, *, folder_name, progress_callback):
        self.names.append(folder_name)
        folder = Path(draft_root) / folder_name
        folder.mkdir(parents=True)
        if progress_callback:
            progress_callback(1.0, "exported")
        return CapCutExportResult(folder, "draft", "timeline", ())


def test_pipeline_adds_index_for_existing_project_name(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    output = tmp_path / "output"
    draft_root = tmp_path / "drafts"
    output.mkdir()
    draft_root.mkdir()
    (output / "Demo.timeline.json").write_text("existing", encoding="utf-8")
    (draft_root / "Demo").mkdir()
    renderer = FakeRenderer([])
    exporter = FakeExporter()

    result = export_timeline(
        project,
        mode=OutputMode.BOTH,
        output_dir=output,
        draft_root=draft_root,
        register_with_capcut=False,
        renderer=renderer,
        capcut_exporter=exporter,
        burn_captions=True,
    )

    assert result.manifest.name == "Demo (2).timeline.json"
    assert renderer.calls == [("Demo (2)", True)]
    assert exporter.names == ["Demo (2)"]
