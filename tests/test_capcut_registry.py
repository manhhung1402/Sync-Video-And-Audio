import json
from pathlib import Path

from syncvideo_audio import CapCutDraftExporter, CapCutRegistry

from test_capcut_exporter import FakeProbe, make_project


def test_discovers_active_draft_root_by_frequency(tmp_path: Path) -> None:
    registry_file = tmp_path / "root_meta_info.json"
    registry_file.write_text(json.dumps({
        "root_path": str(tmp_path / "default"),
        "all_draft_store": [
            {"draft_root_path": str(tmp_path / "custom")},
            {"draft_root_path": str(tmp_path / "custom")},
            {"draft_root_path": str(tmp_path / "other")},
        ],
    }), encoding="utf-8")
    assert CapCutRegistry(registry_file).draft_root() == (tmp_path / "custom").resolve()


def test_registers_exported_draft_without_losing_existing_entries(tmp_path: Path) -> None:
    registry_file = tmp_path / "root_meta_info.json"
    registry_file.write_text(json.dumps({
        "draft_ids": 7,
        "root_path": str(tmp_path),
        "all_draft_store": [{"draft_id": "existing", "draft_name": "Keep me"}],
    }), encoding="utf-8")
    result = CapCutDraftExporter(FakeProbe()).export(make_project(tmp_path), tmp_path / "drafts")

    CapCutRegistry(registry_file).register(result)
    data = json.loads(registry_file.read_text(encoding="utf-8"))

    assert data["draft_ids"] == 7
    assert data["all_draft_store"][0]["draft_id"] == result.draft_id
    assert data["all_draft_store"][0]["draft_fold_path"] == result.draft_folder.as_posix()
    assert data["all_draft_store"][1]["draft_id"] == "existing"
    assert not list(tmp_path.glob(".root_meta_info.json.*.tmp"))
