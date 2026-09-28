"""Runtime helpers shared by the GUI, renderers, and bundled tools."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable


ProgressCallback = Callable[[float, str], None]


# CTranslate2 ships Intel's libiomp5md.dll while native dependencies (torch,
# pyarrow) load Microsoft's libomp140.x86_64.dll from System32.  Loading both
# runtimes makes the second call abort(), which kills the GUI with no traceback
# during transcription.  This must run before those imports, hence module scope
# rather than configure_runtime_storage().
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")


def app_data_root() -> Path:
    """Return writable app storage on the same drive as the packaged app.

    ``SYNCVIDEO_DATA_DIR`` is primarily useful for the source/CLI build.  A
    packaged onedir build keeps its data beside the executable so choosing a
    non-system install drive also keeps caches and temporary files there.
    """

    override = os.environ.get("SYNCVIDEO_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "data"
    return Path(__file__).resolve().parents[2] / ".runtime"


def runtime_temp_dir() -> Path:
    return app_data_root() / "temp"


def configure_runtime_storage() -> Path:
    """Keep Python and dependency caches out of Windows' TEMP/AppData paths."""

    data_root = app_data_root()
    temporary = data_root / "temp"
    cache = data_root / "cache"
    models = data_root / "models"
    for directory in (temporary, cache, models):
        directory.mkdir(parents=True, exist_ok=True)

    # tempfile honours these variables, while assigning ``tempdir`` also
    # handles processes where another imported module already queried it.
    for name in ("TEMP", "TMP", "TMPDIR"):
        os.environ[name] = str(temporary)
    tempfile.tempdir = str(temporary)

    # Libraries used by Whisper/Hugging Face otherwise default to AppData or
    # the user profile on C:.  Keep all optional downloads on the install drive.
    os.environ["HF_HOME"] = str(cache / "huggingface")
    os.environ["HUGGINGFACE_HUB_CACHE"] = str(cache / "huggingface" / "hub")
    os.environ["XDG_CACHE_HOME"] = str(cache)
    os.environ["TORCH_HOME"] = str(cache / "torch")
    os.environ["SYNCVIDEO_MODEL_DIR"] = str(models)
    return data_root


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
