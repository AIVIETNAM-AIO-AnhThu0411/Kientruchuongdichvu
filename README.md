# Trọ Việt — Auth & User Service 2.0.1

FastAPI + SQLAlchemy + SQL Server, kèm giao diện HTML/CSS/JavaScript chạy cùng backend.

**Bắt đầu tại [HUONG_DAN.md](HUONG_DAN.md).** Nếu đã chạy bản cũ, làm phần A để giữ database và cấu hình hiện tại.

Phạm vi: ADMIN/LANDLORD; đăng nhập email/SĐT, đổi mật khẩu, đăng xuất, Admin xem/tạo/sửa/phân quyền/khóa/mở/xóa tài khoản có kiểm tra tham chiếu. Không triển khai Boarding House Service.

Bản sửa này yêu cầu bảng `role` có đúng 2 dòng: `ADMIN` và `LANDLORD` (Chủ trọ).
Database đã có OWNER/TENANT: dừng API, chạy `sql/05_upgrade_auth.sql` trong SSMS rồi khởi động lại.
Script giữ tài khoản Chủ trọ và dữ liệu liên quan; chỉ xóa vai trò cũ không còn liên kết. Nếu còn tài khoản TENANT hoặc tham chiếu khác, script báo rõ và hoàn tác.
ODBC mặc định là Driver 17, phù hợp máy đang dùng của bạn; giữ file `.env` đang kết nối được.

Chạy: `python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000`.
Giao diện: http://127.0.0.1:8000/ui/ · Swagger: http://127.0.0.1:8000/docs.
