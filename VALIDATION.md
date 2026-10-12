# Kiểm tra bản 2.0.1 — Phần 1 Auth & User

## Kết quả

- 59 kiểm tra API/ORM/cấu hình chạy qua bằng pytest trên bản sửa hai vai trò.
- Kiểm tra mới xác nhận backend từ chối database có thiếu hoặc thừa vai trò (kể cả đủ ADMIN/LANDLORD nhưng vẫn còn OWNER/TENANT), chấp nhận hai vai trò không phụ thuộc thứ tự/ID, và CHECK của ORM chặn thêm OWNER/TENANT.
- Cấu hình ODBC mặc định đã sửa thành Driver 17; bộ kiểm tra kết nối xác nhận dùng Driver 17.
- Giao diện giữ nguyên bản 2.0. Kiểm tra trình duyệt Chromium của bản 2.0 với API thật và database thử nghiệm SQLite đã chạy qua:
  - Đăng nhập Admin bằng email; Chủ trọ bằng SĐT.
  - Hiển thị 20 tài khoản/trang, chuyển trang, tìm kiếm.
  - Tạo, xem chi tiết, cập nhật thông tin và đổi vai trò.
  - Khóa/mở khóa tài khoản.
  - Xóa tài khoản chưa tham chiếu; từ chối xóa khi có bảng lịch sử tham chiếu.
  - Chủ trọ chỉ có trang cá nhân; gọi /users trả 403.
  - Đổi mật khẩu: sai mật khẩu hiện tại bị từ chối; thành công thu hồi phiên và đăng nhập bằng mật khẩu mới.
  - Đăng xuất.
  - Không có lỗi JavaScript trong các luồng trên.
- Đã xem ảnh chụp giao diện desktop 1440×1000 và mobile 390×844. Bảng trên điện thoại cuộn ngang, trang không tràn ngang.
- JavaScript qua `node --check`.
- Bộ kiểm tra bao gồm giữ BIGINT chính xác, duy nhất email/SĐT, chống phản chiếu mật khẩu trong lỗi, kiểm tra quyền, khóa/mở khóa, FK có/không CASCADE, phiên bị thu hồi.

## Giới hạn cần xác minh trên máy triển khai

- Môi trường kiểm tra không kết nối trực tiếp SQL Server/Windows Authentication trên máy bạn.
- Script SQL migration đã sửa và rà soát, chưa chạy trên SQL Server trong môi trường kiểm tra này. Cần chạy trong SSMS trên instance đúng để xác minh với database thực tế. Khi thành công chỉ còn ADMIN/LANDLORD; nếu còn tài khoản TENANT hoặc FK tham chiếu vai trò cũ thì báo lỗi và hoàn tác.
- Khóa XLOCK/UPDLOCK/HOLDLOCK, quyền VIEW DEFINITION, kiểm tra sys.foreign_key_columns và hành vi đồng thời của SQL Server cần được xác minh trên SQL Server thật. SQLite không mô phỏng các khóa này.
- Liên kết nghiệp vụ chuẩn và FK trong cùng database được kiểm tra trước xóa. Dữ liệu nằm ở dịch vụ/database khác cần API tích hợp, chưa thuộc bản này.
- Boarding House Service không được triển khai. Dữ liệu lịch sử được dùng trong kiểm tra xóa tài khoản, không cung cấp chức năng quản lý nhà trọ.

## Chạy lại kiểm tra API

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Các trường hợp kiểm tra nằm trong `tests/`. Các hướng dẫn tự kiểm tra SQL Server và giao diện có trong `HUONG_DAN.md`.
