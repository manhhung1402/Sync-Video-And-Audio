import os
import tempfile
from pathlib import Path

from syncvideo_audio.runtime import (
    app_data_root,
    configure_runtime_storage,
    runtime_temp_dir,
)
from syncvideo_audio.transcription import _whisper_cache_dir


def test_runtime_storage_stays_under_explicit_app_data_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    data_root = tmp_path / "installed-on-d" / "data"
    monkeypatch.setenv("SYNCVIDEO_DATA_DIR", str(data_root))
    previous_tempdir = tempfile.tempdir
    managed_variables = (
        "TEMP",
        "TMP",
        "TMPDIR",
        "HF_HOME",
        "HUGGINGFACE_HUB_CACHE",
        "XDG_CACHE_HOME",
        "TORCH_HOME",
        "SYNCVIDEO_MODEL_DIR",
    )
    previous_environment = {name: os.environ.get(name) for name in managed_variables}
    try:
        configured = configure_runtime_storage()

        assert configured == data_root.resolve()
        assert app_data_root() == data_root.resolve()
        assert runtime_temp_dir() == data_root.resolve() / "temp"
        assert _whisper_cache_dir() == data_root.resolve() / "models"
        assert Path(tempfile.gettempdir()) == data_root.resolve() / "temp"
        for variable in ("TEMP", "TMP", "TMPDIR"):
            assert Path(os.environ[variable]) == data_root.resolve() / "temp"
        assert Path(os.environ["HF_HOME"]).is_relative_to(data_root.resolve())
        assert Path(os.environ["HUGGINGFACE_HUB_CACHE"]).is_relative_to(data_root.resolve())
        assert Path(os.environ["TORCH_HOME"]).is_relative_to(data_root.resolve())
    finally:
        tempfile.tempdir = previous_tempdir
        for name, value in previous_environment.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def test_source_runtime_default_is_inside_repository(monkeypatch) -> None:
    monkeypatch.delenv("SYNCVIDEO_DATA_DIR", raising=False)

    root = app_data_root()

    assert root.name == ".runtime"
    assert (root.parent / "pyproject.toml").is_file()
