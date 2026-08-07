# Third-party notices

The SyncVideo-Audio source code and project-created logo assets are released under the MIT License in [LICENSE](LICENSE). The following components are distributed separately or included in the full Windows build and remain under their own licenses.

## FFmpeg and FFprobe

The bundled `ffmpeg.exe` and `ffprobe.exe` are FFmpeg project binaries. FFmpeg is generally licensed under LGPL-2.1-or-later; builds containing optional GPL components may be subject to GPL-2.0-or-later obligations. See the official guidance:

- <https://ffmpeg.org/legal.html>
- <https://ffmpeg.org/doxygen/trunk/md_LICENSE.html>

The exact binary build configuration should be recorded with each public release.

## Noto Sans CJK

`assets/fonts/NotoSansCJK-Regular.ttc` is from the Noto CJK project and is distributed under the SIL Open Font License 1.1:

- <https://github.com/notofonts/noto-cjk>
- <https://openfontlicense.org/>

## faster-whisper and CTranslate2

Transcript mode uses the `faster-whisper` Python package and its CTranslate2 runtime when installed or bundled:

- <https://github.com/SYSTRAN/faster-whisper>
- <https://github.com/OpenNMT/CTranslate2>

Both upstream projects provide their own license files. Their dependencies may have additional notices.

## Whisper small model

The optional/bundled `assets/models/small` directory is a CTranslate2 conversion of `openai/whisper-small`. The model card identifies it as MIT-licensed and links to the original model:

- <https://huggingface.co/Systran/faster-whisper-small>
- <https://huggingface.co/openai/whisper-small>

Check the upstream model card before redistributing a modified model or a different model size.

## CapCut

CapCut and its trademarks are owned by their respective rights holders. SyncVideo-Audio is an independent interoperability tool and is not affiliated with or endorsed by CapCut or ByteDance. The native draft format used by the exporter is private and undocumented.
