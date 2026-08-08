import json
from pathlib import Path

from syncvideo_audio.probe import FfprobeMediaProbe


def test_probe_uses_audio_stream_duration_when_format_duration_is_missing(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "voice.wav"
    source.write_bytes(b"fixture")
    payload = {
        "format": {"filename": str(source)},
        "streams": [
            {
                "codec_type": "audio",
                "codec_name": "pcm_s24le",
                "duration": "3.25",
            }
        ],
    }

    class Result:
        stdout = json.dumps(payload)
        stderr = ""

    monkeypatch.setattr("syncvideo_audio.probe.subprocess.run", lambda *args, **kwargs: Result())

    info = FfprobeMediaProbe().probe(source)

    assert info.duration_us == 3_250_000
