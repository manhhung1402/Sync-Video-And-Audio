# Quy trình hand-off

Mục tiêu của hand-off là người nhận có thể xem nhanh bằng MP4, sau đó mở CapCut
để chỉnh timing, crop, âm lượng và keyframe mà không phải dựng lại timeline.

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

Các segment video giữ `sourceStartUs`, `sourceDurationUs`, `speed`; ảnh giữ
`motion`. Vì vậy người nhận vẫn có thể điều chỉnh các giá trị này trong CapCut.

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
- [ ] Keyframe scale/position xuất hiện trên các ảnh có motion.
- [ ] Asset không báo offline sau khi đổi tên/di chuyển source ban đầu.
- [ ] Timeline mirror và root `draft_content.json` giống nhau.
