"""Runtime helpers shared by the GUI, renderers, and bundled tools."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Callable


ProgressCallback = Callable[[float, str], None]


def report_progress(callback: ProgressCallback | None, value: float, message: str) -> None:
    if callback is not None:
        callback(max(0.0, min(1.0, value)), message)


def hidden_subprocess_kwargs() -> dict[str, object]:
    """Prevent console windows from flashing when the GUI runs child tools."""

    if os.name != "nt":
        return {}
    return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}


def resource_path(relative: str) -> Path:
    """Resolve a packaged asset or a source-tree asset."""

    bundle_root = getattr(__import__("sys"), "_MEIPASS", None)
    if bundle_root:
        return Path(bundle_root) / relative
    return Path(__file__).resolve().parents[2] / relative


def resolve_executable(name: str) -> str:
    """Prefer a bundled tool, then fall back to the user's PATH."""

    candidate = Path(name)
    if candidate.is_file():
        return str(candidate)
    for relative in (f"assets/tools/{candidate.name}", f"tools/{candidate.name}"):
        bundled = resource_path(relative)
        if os.name == "nt" and bundled.suffix.lower() != ".exe":
            bundled = bundled.with_suffix(".exe")
        if bundled.is_file():
            return str(bundled)
    return shutil.which(name) or name
