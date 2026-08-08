"""Start the GUI without allowing Python to use the system TEMP directory."""

from pathlib import Path
import os
import sys
import tempfile


def _bootstrap_storage() -> None:
    root = Path(sys.executable).resolve().parent / "data"
    temporary = root / "temp"
    cache = root / "cache"
    models = root / "models"
    for directory in (temporary, cache, models):
        directory.mkdir(parents=True, exist_ok=True)
    for name in ("TEMP", "TMP", "TMPDIR"):
        os.environ[name] = str(temporary)
    os.environ["HF_HOME"] = str(cache / "huggingface")
    os.environ["HUGGINGFACE_HUB_CACHE"] = str(cache / "huggingface" / "hub")
    os.environ["XDG_CACHE_HOME"] = str(cache)
    os.environ["TORCH_HOME"] = str(cache / "torch")
    os.environ["SYNCVIDEO_DATA_DIR"] = str(root)
    os.environ["SYNCVIDEO_MODEL_DIR"] = str(models)
    tempfile.tempdir = str(temporary)


_bootstrap_storage()

from syncvideo_audio.gui import launch  # noqa: E402


if __name__ == "__main__":
    launch()
