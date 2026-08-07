# SyncVideo-Audio

Công cụ Windows độc lập để xếp ảnh/video theo audio thuyết minh, tạo bản xem
trước MP4 và bàn giao một project CapCut native vẫn chỉnh sửa được.

Khác với phần CapCut export hiện có của `Agions/vynaro` (mới chỉ sinh một
`draft_info.json` mô phỏng), project này tạo đầy đủ `draft_content.json`,
`draft_meta_info.json`, timeline mirror, asset cục bộ và registry entry theo
schema quan sát từ **CapCut International 9.1.0**.

## Chức năng

- Tự xếp file có prefix `img-001`, `vid-002`, ...; file không có số đứng sau.
- Cho phép đổi thứ tự thủ công trong GUI.
- Căn đều theo độ dài audio hoặc nhận `mapping.json` có timestamp từng cảnh.
- Ảnh dài tự tách thành các shot (mặc định 6 giây).
- Video tự trim, đổi speed hoặc lặp bằng các segment vẫn chỉnh được.
- Sáu preset keyframe CapCut nhẹ: zoom in/out, pan ngang/dọc hai chiều.
- Ba mode output: `mp4`, `capcut`, `both`.
- Luôn lưu `*.timeline.json` làm hợp đồng hand-off có thể export lại.
- Copy asset vào project CapCut để tránh mất link khi di chuyển source.
- Tự dò Draft root và đăng ký project vào CapCut bằng ghi file atomic.

## Yêu cầu

- Windows 10/11, Python 3.10 trở lên.
- `ffmpeg` và `ffprobe` có trong `PATH`.
- CapCut International 9.1 được khuyến nghị cho native draft.

## Cài và chạy GUI

```powershell
cd G:\GitHub\SyncVideo-Audio
python -m pip install -e .
syncvideo-audio-gui
```

Trong GUI:

1. Chọn audio và thư mục ảnh/video.
2. Kiểm tra danh sách, dùng **Lên/Xuống** nếu cần đổi thứ tự.
3. Chọn `both` để nhận cả MP4 và CapCut project.
4. Đóng project đang mở trong CapCut rồi bấm **Tạo hand-off**.

## CLI

Tạo mới từ audio và thư mục media:

```powershell
syncvideo-audio build `
  --audio "D:\Job\voice.wav" `
  --media-dir "D:\Job\media" `
  --name "Video 001" `
  --mode both `
  --output-dir "D:\Job\output"
```

Nếu không truyền `--draft-root`, tool tự dò CapCut. Có thể chỉ định rõ:

```powershell
--draft-root "D:\Capcut Draft\CapCut Drafts"
```

Export lại từ timeline manifest đã chỉnh:

```powershell
syncvideo-audio export "D:\Job\output\Video 001.timeline.json" `
  --mode capcut `
  --output-dir "D:\Job\output" `
  --draft-root "D:\Capcut Draft\CapCut Drafts"
```

Các option hữu ích:

- `--mapping scenes.json`: dùng scene map thay vì chia đều.
- `--width`, `--height`, `--fps`: cấu hình canvas.
- `--image-duration 6`: số giây tối đa mỗi shot ảnh.
- `--no-motion`: không tạo motion/keyframe.
- `--no-register`: tạo folder draft nhưng không sửa registry CapCut.
- `--overwrite-mp4`: cho phép ghi đè bản MP4.

## Scene mapping

Timestamp thủ công dùng giây:

```json
[
  {
    "clip": "img-001.png",
    "audio_start": 0.0,
    "audio_end": 4.2,
    "text": "Câu thứ nhất"
  },
  {
    "clip": "vid-002.mp4",
    "audio_start": 4.2,
    "audio_end": 9.8,
    "text": "Câu thứ hai"
  }
]
```

Nếu bỏ toàn bộ `audio_start`/`audio_end`, thời lượng sẽ được phân theo số từ
trong `text`/`sourceText`. Không được trộn scene có timestamp với scene không có.

## Output hand-off

Mode `both` tạo:

```text
output/
├── Video 001.timeline.json   # nguồn sự thật để export lại
└── Video 001.mp4             # bản xem trước

CapCut Drafts/
└── Video 001/
    ├── draft_content.json
    ├── draft_meta_info.json
    ├── timeline_layout.json
    ├── Timelines/
    │   ├── project.json
    │   └── <timeline-id>/draft_content.json
    └── Resources/syncvideo_media/  # asset đã copy
```

Chi tiết quy trình bàn giao và rollback xem [docs/HANDOFF.md](docs/HANDOFF.md).

## Build file EXE Windows

```powershell
python -m pip install pyinstaller
powershell -ExecutionPolicy Bypass -File .\packaging\build_windows.ps1
```

Artifact nằm tại `dist\SyncVideo-Audio.exe`. FFmpeg không được nhúng vào EXE;
máy nhận bàn giao vẫn cần `ffmpeg`/`ffprobe` trong `PATH`.

## Phát triển và kiểm tra

```powershell
python -m pip install -e ".[dev]"
python -m pytest
python -m pip wheel . --no-deps --wheel-dir dist-wheel
```

Định dạng CapCut là private/undocumented. Exporter cố ý tách riêng schema adapter
để có thể cập nhật khi CapCut đổi version. Không chỉnh tay draft đang mở trong
CapCut; luôn giữ `timeline.json` và source media để tái tạo project.
