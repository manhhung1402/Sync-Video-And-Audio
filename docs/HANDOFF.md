# Quy trình hand-off

Mục tiêu của hand-off là người nhận có thể xem nhanh bằng MP4, sau đó mở CapCut
để chỉnh timing, crop, âm lượng và keyframe mà không phải dựng lại timeline.

## Chọn chế độ đồng bộ

- `Chia đều theo audio`: chia duration audio cho media theo thứ tự đã sắp xếp.
- `Căn chuẩn theo transcript`: nhận thêm TXT/SRT/JSON, chạy Whisper local để
  lấy timestamp từ voice, rồi ghép câu 1 với media 001, câu 2 với
  media 002, v.v. Số câu phải bằng số media.

GUI nhận cả text dán trực tiếp và file transcript. Câu được tách theo
`. ! ? … 。！？`, không tách theo xuống dòng. Quy tắc này hỗ trợ tiếng Nhật,
Hàn và Trung, kể cả chuỗi CJK không có khoảng trắng.

Whisper chỉ xác định timing của transcript. Tool không phân tích nội dung ảnh/video
và không tự thay đổi thứ tự media.

Nếu bật `Burn caption vào MP4 preview`, caption được render cố định vào file MP4;
các mốc caption vẫn nằm trong manifest để tiếp tục căn/chỉnh khi dựng trong CapCut.
Draft native hiện chưa tự tạo text track CapCut. Nếu tên project đã tồn tại, hand-off
mới tự dùng hậu tố `(2)`, `(3)`... để không ghi đè output/draft cũ.

## Người tạo project

1. Đóng project CapCut đang mở.
2. Chạy mode `both`.
3. Xác nhận MP4 có đúng tổng duration của audio và đúng thứ tự cảnh.
4. Giữ cùng nhau:
   - file `*.timeline.json`;
   - folder CapCut project;
   - MP4 preview.
5. Mở CapCut, kiểm tra project mới xuất hiện và các track có thể chọn/chỉnh.

Asset được copy vào `Resources/syncvideo_media`, nên folder project là một đơn
vị bàn giao tự chứa. Không xoá `Resources` sau khi đã mở project.

## Người nhận

Nếu project đã nằm trong Draft root của máy hiện tại, chỉ cần mở CapCut. Nếu
nhận folder từ máy khác:

1. Đóng CapCut.
2. Copy nguyên folder vào CapCut Draft root.
3. Chạy lại lệnh `syncvideo-audio export` từ timeline manifest trên máy nhận để
   tạo và đăng ký project mới; đây là cách an toàn nhất vì đường dẫn asset sẽ
   được viết lại theo máy nhận.
4. Mở CapCut và chỉnh sửa bình thường.

## Hợp đồng dữ liệu

`timeline.json` dùng microsecond nguyên và là nguồn sự thật trung gian. Cả MP4
và CapCut draft đều được tạo từ cùng manifest, nên khác biệt output không được
khắc phục bằng cách sửa riêng backend. Hãy sửa manifest/mapping rồi export lại.

Các segment video giữ `sourceStartUs`, `sourceDurationUs`, `speed`; cả ảnh và video
giữ `motion`. Vì vậy người nhận vẫn có thể điều chỉnh timing, speed và
keyframe trực tiếp trong CapCut.

## Rollback và xử lý lỗi

- Tool không ghi đè folder CapCut đã tồn tại.
- MP4 chỉ bị ghi đè khi dùng `--overwrite-mp4`.
- Draft được dựng trong staging folder và rename sau khi toàn bộ reference hợp
  lệ; lỗi giữa chừng không để lại một project nửa vời.
- Registry CapCut được ghi atomic. Dùng `--no-register` nếu chỉ muốn kiểm tra
  folder draft mà không thay đổi danh sách project của CapCut.
- Nếu CapCut version mới không mở draft, giữ nguyên manifest và export lại sau
  khi schema adapter được cập nhật.

## Acceptance checklist

- [ ] MP4 mở được và duration khớp audio.
- [ ] Thứ tự ảnh/video đúng.
- [ ] CapCut hiển thị một video track và một audio track.
- [ ] Mỗi ảnh là segment riêng, không phải video đã flatten.
- [ ] Keyframe scale/position xuất hiện trên cả ảnh và video có motion.
- [ ] Với transcript mode, số caption/cảnh bằng số media và thứ tự 001 → 002 → 003 được giữ nguyên.
- [ ] Asset không báo offline sau khi đổi tên/di chuyển source ban đầu.
- [ ] Timeline mirror và root `draft_content.json` giống nhau.
