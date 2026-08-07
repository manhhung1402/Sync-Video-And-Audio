# SyncVideo-Audio

Standalone Windows tool for synchronizing ordered images/videos with narration
audio and exporting an editable native CapCut project.

The implementation is intentionally split into a timeline-planning core and
independent render/export backends. CapCut is the primary editable output; an
FFmpeg renderer can consume the same timeline manifest.

## Development

```powershell
python -m pip install -e ".[dev]"
pytest
```

