# Auth & User Service — bản hoàn chỉnh Phần 1

Bản này chỉ gồm đăng nhập, đổi mật khẩu, đăng xuất và quản lý tài khoản.
Vai trò: ADMIN và LANDLORD. Không có API/giao diện quản lý nhà trọ, phòng, hợp đồng hoặc người thuê.
Chủ trọ có trang tài khoản cá nhân, đổi mật khẩu, đăng xuất. Chủ trọ không truy cập danh sách tài khoản.

## A. Bạn đã chạy được bản cũ: làm theo 6 bước

### 1. Dừng backend cũ

Trong PowerShell đang chạy Uvicorn, nhấn Ctrl + C.

### 2. Giải nén bản mới

Giải nén ZIP vào thư mục mới, ví dụ:

`C:\Users\Administrator\Downloads\auth-service-2-role\auth-service`

Sao chép **file .env đang dùng được** từ thư mục cũ sang thư mục mới này.
Không sao chép .venv cũ. Không tạo lại database và không xóa bảng đang có.

### 3. Cập nhật vai trò trong SQL Server

Mở SSMS → kết nối đúng máy/instance đang có `quan_ly_tro` → File → Open → File → chọn `sql\05_upgrade_auth.sql` trong bản mới → Execute hoặc F5.

Sau khi chạy thành công, **bảng role chỉ có đúng 2 dòng: ADMIN và LANDLORD (Chủ trọ)**.
Script chuyển tài khoản OWNER sang LANDLORD; giữ user_id, mật khẩu, email và dữ liệu nghiệp vụ.
Nếu đã có cả OWNER/LANDLORD, script dùng dòng LANDLORD đang có rồi xóa dòng OWNER không còn liên kết. TENANT và các vai trò khác chỉ bị xóa khi không còn tài khoản hoặc dữ liệu tham chiếu.
Script kiểm tra toàn bộ FK tới role trước khi xóa, kể cả FK CASCADE/disabled. Nếu còn tài khoản TENANT hoặc liên kết khác, script báo lỗi và hoàn tác toàn bộ; không tự xóa tài khoản hay cấp quyền Chủ trọ cho người thuê. Xem phần G để kiểm tra.
Phiên OWNER bị thu hồi khi cập nhật thành công; đăng nhập lại sau đó.
role_id có thể là 1 và 5; không cần đổi thành 1 và 2. Chương trình nhận diện theo role_name.

Kết quả cần thấy trong SSMS:

| role_name | description |
|---|---|
| ADMIN | Quản trị hệ thống |
| LANDLORD | Chủ trọ |

Chỉ giải nén file mới chưa làm thay đổi database. Bạn cần chạy script 05 trên database đang sử dụng.

Bản cũ của bạn đã có `auth_session`. Nếu chưa có, chạy `sql\03_auth_sessions.sql` trước script 05.
Không cần chạy lại script tạo database hoặc seed tài khoản trên database đã dùng được.

### 4. Tạo môi trường Python

Mở thư mục bản mới trong VS Code → Terminal → New Terminal. Chạy từng lệnh:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Nếu PowerShell chặn Activate.ps1, dùng trực tiếp Python của môi trường:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 5. Chạy backend

```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Đợi dòng `Application startup complete.` và giữ cửa sổ này mở.

### 6. Mở giao diện

Vào `http://127.0.0.1:8000/ui/`, nhấn Ctrl + F5 nếu trình duyệt còn giữ giao diện cũ.

Đăng nhập bằng tài khoản đã có. Với dữ liệu mẫu chưa đổi mật khẩu:

| Vai trò | Email | Mật khẩu mẫu |
|---|---|---|
| Admin | admin@troviet.example | Admin@2026! |
| Chủ trọ | chutro@troviet.example | ChuTro@2026! |

Tài khoản `owner01@troviet.example` bạn đã tạo vẫn giữ nguyên mật khẩu và ID; chỉ tên vai trò đổi thành LANDLORD.
SĐT chỉ đăng nhập được sau khi Admin đã nhập SĐT cho tài khoản. Bạn có thể thêm SĐT qua nút Sửa rồi đăng nhập bằng chính số đó.

## B. Các chức năng trên giao diện

### Admin

- Xem tổng tài khoản, số Admin, số Chủ trọ, số đang hoạt động/đã khóa.
- Tìm theo họ tên, email, SĐT; lọc vai trò, trạng thái; phân trang.
- Xem chi tiết tài khoản, ngày tạo, ngày cập nhật.
- Tạo tài khoản với họ tên, email, SĐT tùy chọn, mật khẩu và vai trò.
- Cập nhật họ tên, email, SĐT, vai trò, trạng thái.
- Khóa/mở khóa; đổi vai trò sẽ thu hồi các phiên của người dùng.
- Xóa có xác nhận: bị chặn nếu có dữ liệu nghiệp vụ tham chiếu; dùng Khóa để giữ lịch sử.
- Xem thông tin bản thân, đổi mật khẩu bản thân, đăng xuất.

### Chủ trọ (LANDLORD)

- Đăng nhập bằng email hoặc SĐT.
- Xem thông tin tài khoản của chính mình.
- Đổi mật khẩu của chính mình, đăng xuất.
- Mọi API quản lý tài khoản đều trả 403 khi gọi bằng phiên Chủ trọ.

## C. Quy tắc áp dụng

- Email bắt buộc, tối đa 255 ký tự ASCII, không phân biệt hoa/thường và duy nhất.
- Họ tên Unicode tối đa 100 ký tự; không được chỉ gồm khoảng trắng.
- SĐT không bắt buộc. Khi nhập: 8–15 chữ số, có thể bắt đầu bằng `+`, không trùng. Không tự chuyển `090…` thành `+8490…`; đăng nhập theo số đã lưu.
- Mật khẩu mới/tạo tài khoản: 10–128 ký tự; lưu Argon2id, không lưu mật khẩu rõ.
- Đổi mật khẩu kiểm tra mật khẩu hiện tại và xác nhận; mật khẩu mới phải khác mật khẩu cũ.
- Đổi mật khẩu thu hồi **mọi phiên**, kể cả phiên hiện tại; giao diện chuyển về đăng nhập.
- Tài khoản LOCKED bị chặn đăng nhập và mọi chức năng cần xác thực. Mở khóa không khôi phục token cũ.
- Chỉ ADMIN quản lý tài khoản. Không tự khóa, tự hạ quyền hoặc tự xóa tài khoản Admin đang đăng nhập. Phải giữ ít nhất một Admin hoạt động.
- Xóa tài khoản chỉ xóa tài khoản và các phiên xác thực kỹ thuật. Không tự xóa/cascade dữ liệu nghiệp vụ.
- Kiểm tra toàn bộ FK tham chiếu (kể cả FK CASCADE/disabled) trước xóa. Liên kết chuẩn `boarding_house.owner_id` cũng được kiểm tra khi bảng cũ thiếu FK.
- Module khác cần tạo FK cho mọi quan hệ tới `[user]`. Liên kết chỉ lưu trong dịch vụ/database khác cần được tích hợp API kiểm tra trước khi xóa; bản này kiểm tra các quan hệ trong cùng database SQL Server.
- Login kết nối SQL Server cần quyền `VIEW DEFINITION` trên database để nhận diện đủ FK. Windows Authentication đang dùng tài khoản quản trị thường đã có quyền. Nếu startup báo thiếu, người quản trị DB cấp: `GRANT VIEW DEFINITION TO [ten_database_user];`.
- Phiên Bearer tồn tại 8 giờ theo SESSION_HOURS, lưu digest trong auth_session; giao diện giữ token trong sessionStorage của tab và xóa khi đăng xuất.
- Giới hạn đăng nhập sai theo IP, 15 phút, trong một process. Môi trường nhiều worker cần kho rate limit chung.

## D. Máy mới chưa có database

Trong SSMS chạy lần lượt:

1. `sql/01_create_role_user.sql`
2. `sql/03_auth_sessions.sql`
3. `sql/05_upgrade_auth.sql`
4. `sql/04_seed_demo_accounts.sql` nếu cần tài khoản thực hành.

Sao chép `.env.example` thành `.env`, sửa đúng server/instance, database và ODBC driver đã cài.

Cấu hình máy bạn trước đây:

```dotenv
DB_AUTH=windows
DB_SERVER=localhost
DB_DATABASE=quan_ly_tro
DB_DRIVER=ODBC Driver 17 for SQL Server
DB_INSTANCE=
DB_PORT=1433
DB_USER=
DB_PASSWORD=
DB_ENCRYPT=true
DB_TRUST_SERVER_CERTIFICATE=true
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
SESSION_HOURS=8
LOGIN_LIMIT=10
```

Nếu bạn đã đổi cổng để chạy được, giữ cổng của **file .env đang hoạt động**, không tự thay về 1433.

## E. API

Swagger: `http://127.0.0.1:8000/docs`. Authorize: chỉ dán token, không nhập thêm Bearer.

| API | Quyền / chức năng |
|---|---|
| POST /auth/login | `{identifier: email hoặc SĐT, password}`; vẫn chấp nhận `{email, password}` cho client cũ |
| GET /auth/me | Tài khoản hiện tại |
| POST /auth/change-password | `{current_password, new_password, confirm_password}`; 204; thu hồi mọi phiên |
| POST /auth/logout | 204; thu hồi phiên hiện tại |
| GET /roles | ADMIN; hai vai trò hỗ trợ |
| GET /users/overview | ADMIN; thống kê toàn bộ tài khoản hỗ trợ |
| GET /users | ADMIN; search, role_name, status, page, limit |
| GET /users/{id} | ADMIN; chi tiết |
| POST /users | ADMIN; tạo |
| PATCH /users/{id} | ADMIN; cập nhật |
| PATCH /users/{id}/status | ADMIN; ACTIVE/LOCKED |
| PATCH /users/{id}/role | ADMIN; ADMIN/LANDLORD |
| DELETE /users/{id} | ADMIN; 204 hoặc 409 nếu có tham chiếu |
| GET /health | Kiểm tra kết nối database |

## F. Tự kiểm tra trên máy bạn

1. Admin đăng nhập bằng email → bảng tài khoản hiện.
2. Tạo Chủ trọ có SĐT; thử trùng email/SĐT → bị từ chối.
3. Sửa thông tin; xem chi tiết; lọc và chuyển trang.
4. Chủ trọ đăng nhập bằng SĐT → chỉ có trang cá nhân; gọi /users → 403.
5. Đổi mật khẩu với mật khẩu cũ sai/xác nhận sai → bị từ chối; nhập đúng → đăng nhập lại bằng mật khẩu mới.
6. Admin khóa Chủ trọ → phiên cũ và đăng nhập mới đều bị chặn; mở khóa → đăng nhập lại được.
7. Xóa tài khoản chưa có dữ liệu liên quan → thành công; tài khoản đang được nhà trọ hoặc bảng lịch sử tham chiếu → 409, dữ liệu giữ nguyên.

Kiểm tra tự động: `python -m pip install -r requirements-dev.txt` rồi `python -m pytest -q`.
Xem `VALIDATION.md` để biết phạm vi đã kiểm tra và giới hạn.

## G. Nếu script báo còn tài khoản TENANT hoặc dữ liệu tham chiếu

Script chưa thay đổi database khi báo lỗi. Chạy truy vấn sau trong SSMS để xem các tài khoản cần xử lý:

```sql
USE [quan_ly_tro];
GO
SELECT u.user_id, u.full_name, u.email, r.role_name, u.status
FROM dbo.[user] u
JOIN dbo.[role] r ON r.role_id = u.role_id
WHERE r.role_name NOT IN ('ADMIN', 'LANDLORD', 'OWNER');
```

Tài khoản người thuê cũ cần được xử lý theo dữ liệu thực tế trước khi bỏ vai trò TENANT; không đổi hàng loạt sang LANDLORD.
Nếu lỗi nêu một bảng/FK khác, giữ liên kết đó và xử lý trước khi chạy lại. Gửi thông báo lỗi và kết quả truy vấn để xác định cách chuyển dữ liệu phù hợp.
