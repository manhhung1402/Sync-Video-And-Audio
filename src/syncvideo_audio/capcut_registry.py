"""Discovery and safe registration of drafts in CapCut Desktop's local index."""

from __future__ import annotations

import json
import os
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from .capcut_exporter import CapCutExportResult


REGISTRY_RELATIVE_PATH = Path("CapCut/User Data/Projects/com.lveditor.draft/root_meta_info.json")


class CapCutRegistry:
    def __init__(self, registry_file: str | Path) -> None:
        self.registry_file = Path(registry_file).resolve()

    @classmethod
    def discover(cls, local_app_data: str | Path | None = None) -> "CapCutRegistry | None":
        base_value = local_app_data or os.environ.get("LOCALAPPDATA")
        if not base_value:
            return None
        candidate = Path(base_value) / REGISTRY_RELATIVE_PATH
        return cls(candidate) if candidate.is_file() else None

    def draft_root(self) -> Path:
        data = self._read()
        stores = data.get("all_draft_store", [])
        roots = [
            str(item.get("draft_root_path", "")).strip()
            for item in stores
            if isinstance(item, dict) and item.get("draft_root_path")
        ]
        if roots:
            selected = Counter(roots).most_common(1)[0][0]
            return Path(selected).resolve()
        root = str(data.get("root_path", "")).strip()
        if not root:
            raise ValueError(f"CapCut registry has no draft root: {self.registry_file}")
        return Path(root).resolve()

    def register(self, result: CapCutExportResult) -> None:
        data = self._read()
        stores = data.setdefault("all_draft_store", [])
        if not isinstance(stores, list):
            raise ValueError("CapCut all_draft_store must be an array")
        meta = json.loads(
            (result.draft_folder / "draft_meta_info.json").read_text(encoding="utf-8")
        )
        content = json.loads(
            (result.draft_folder / "draft_content.json").read_text(encoding="utf-8")
        )
        fold = result.draft_folder.resolve().as_posix()
        stores[:] = [
            item
            for item in stores
            if not (
                isinstance(item, dict)
                and (item.get("draft_id") == result.draft_id or item.get("draft_fold_path") == fold)
            )
        ]
        stores.insert(0, {
            "cloud_draft_cover": False,
            "cloud_draft_sync": False,
            "draft_cloud_last_action_download": False,
            "draft_cover": "",
            "draft_fold_path": fold,
            "draft_id": result.draft_id,
            "draft_is_ai_shorts": False,
            "draft_is_cloud_temp_draft": False,
            "draft_is_invisible": False,
            "draft_is_pippit_draft": False,
            "draft_is_web_article_video": False,
            "draft_json_file": (result.draft_folder / "draft_content.json").resolve().as_posix(),
            "draft_name": meta["draft_name"],
            "draft_new_version": "",
            "draft_root_path": str(result.draft_folder.parent.resolve()),
            "draft_timeline_materials_size": 0,
            "draft_type": "",
            "draft_web_article_video_enter_from": "",
            "streaming_edit_draft_ready": True,
            "tm_draft_cloud_entry_id": -1,
            "tm_draft_cloud_modified": 0,
            "tm_draft_cloud_parent_entry_id": -1,
            "tm_draft_cloud_space_id": -1,
            "tm_draft_cloud_user_id": -1,
            "tm_draft_create": meta["tm_draft_create"],
            "tm_draft_modified": meta["tm_draft_modified"],
            "tm_draft_removed": 0,
            "tm_duration": content["duration"],
        })
        self._write(data)

    def _read(self) -> dict[str, Any]:
        data = json.loads(self.registry_file.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("CapCut registry root must be an object")
        return data

    def _write(self, data: dict[str, Any]) -> None:
        payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        handle, temporary_name = tempfile.mkstemp(
            dir=self.registry_file.parent,
            prefix=f".{self.registry_file.name}.",
            suffix=".tmp",
            text=True,
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(handle, "w", encoding="utf-8", newline="") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.registry_file)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
