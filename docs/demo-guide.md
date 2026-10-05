# Functional demo guide

Hướng dẫn này tạo bằng chứng ban đầu cho các chức năng đã có của EventHub-KTPM. Nó không thêm chức
năng sản phẩm và không phải benchmark.

## 1. Cách nhanh nhất trên Windows

Yêu cầu: Python 3.11+ và `uv`. Không cần Docker/PostgreSQL.

Từ thư mục repository:

```cmd
scripts\run-demo.cmd
```

Wrapper CMD gọi runner PowerShell hiện có và giữ nguyên exit code. Nếu đang dùng PowerShell trực
tiếp, lệnh tương đương là:

```powershell
.\scripts\run-demo.ps1
```

Script sẽ:

1. Cài đúng dependency từ `uv.lock` bằng `uv sync --frozen --extra dev`.
2. Tạo/reset `artifacts/demo/eventhub-demo.sqlite3`.
3. Khởi động Uvicorn ẩn tại `http://127.0.0.1:8765`.
4. Chạy các request demo.
5. Sinh báo cáo Markdown và JSON đã loại secret.
6. Dừng Uvicorn kể cả khi demo fail.

Mở báo cáo:

```powershell
Get-Content artifacts\demo\latest-demo-report.md
```

Hoặc mở file `artifacts/demo/latest-demo-report.md` trực tiếp trong IDE. Log server nằm ở:

```text
artifacts/demo/server.stdout.log
artifacts/demo/server.stderr.log
```

Nếu cổng 8765 đang được dùng:

```powershell
.\scripts\run-demo.ps1 -Port 8877
```

Mặc định database demo được reset để kết quả có thể lặp lại. Muốn giữ dữ liệu lần trước:

```powershell
.\scripts\run-demo.ps1 -KeepData
```

## 2. Bash/WSL

```bash
bash scripts/run-demo.sh
```

Chọn cổng khác bằng argument đầu tiên:

```bash
bash scripts/run-demo.sh 8877
```

Nếu Windows trả `Access is denied` khi gọi `bash`/`wsl`, dùng PowerShell demo ở mục 1 hoặc khắc
phục WSL2 theo [infrastructure-readiness-report.md](infrastructure-readiness-report.md).

## 3. Chức năng được demo

| Nhóm | Bằng chứng tự động |
|---|---|
| Health/API docs | `/health`, Swagger UI, OpenAPI 3 |
| Authentication | Đăng ký ORGANIZER/USER, login, `/me`, login sai trả 401 |
| Route protection | Booking route không token trả 401 |
| Event management | Create DRAFT, publish, cancel, delete draft |
| Event visibility | Draft không public; published event tìm được qua search/filter |
| Authorization | USER không publish event; ORGANIZER không đọc booking của USER |
| Booking | Đặt 2 vé, xem danh sách booking, hủy booking |
| Inventory | 5 → 3 khi đặt 2 vé; 3 → 5 khi hủy |

Mỗi bước ghi method, path, HTTP status kỳ vọng/thực tế, thời gian và kết quả PASS/FAIL. Token,
password và database URL không được ghi vào report.

## 4. Tự thao tác qua Swagger

Nếu muốn trình bày trực tiếp thay vì chạy tự động, mở một PowerShell mới:

```powershell
uv sync --frozen --extra dev
New-Item -ItemType Directory -Path artifacts\demo -Force | Out-Null
$env:DATABASE_URL="sqlite+pysqlite:///./artifacts/demo/manual-demo.sqlite3"
$env:DB_AUTO_CREATE="true"
$env:JWT_SECRET="local-manual-demo-secret-at-least-32-characters"
$env:BCRYPT_ROUNDS="4"
$env:ENVIRONMENT="demo"
uv run --frozen python -m uvicorn app.main:app --reload --port 8000
```

Sau đó mở `http://127.0.0.1:8000/docs` và thao tác theo thứ tự:

1. `POST /api/auth/register`: tạo một `ORGANIZER`.
2. `POST /api/auth/login`: copy `access_token`.
3. Bấm **Authorize**, dán token.
4. `POST /api/events`: tạo event với `start_time` trong tương lai và `total_tickets=5`.
5. `PATCH /api/events/{id}/publish`.
6. Đăng ký/login một `USER`, Authorize lại bằng token USER.
7. `GET /api/events` để tìm event đã publish.
8. `POST /api/bookings` với `quantity=2`.
9. `GET /api/bookings/me` và `GET /api/bookings/{id}`.
10. `DELETE /api/bookings/{id}` rồi xem inventory event đã phục hồi.

Đóng terminal/server sau demo. Các biến trên chỉ là giá trị local trong process hiện tại.

## 5. Demo với PostgreSQL/Docker

Khi Docker đã sẵn sàng:

```powershell
docker compose config
docker compose up -d --build api
uv run --frozen python scripts/demo_api.py `
  --base-url http://127.0.0.1:8000 `
  --output-dir artifacts/demo `
  --storage-label "PostgreSQL 16 via Docker Compose"
```

Kiểm tra log và dừng stack:

```powershell
docker compose logs --no-color api migrate postgres
docker compose down
```

Không thêm `-v` nếu muốn giữ development volume. Chỉ dùng `docker compose down -v` khi đã xác nhận
dữ liệu trong volume có thể xóa.

## 6. Cách đọc báo cáo

- `PASS`: toàn bộ HTTP contract và invariant chức năng trong bảng đều đúng.
- `FAIL`: xem step đầu tiên fail và `server.stderr.log`.
- Thời gian `ms` chỉ dùng chẩn đoán demo; không được báo cáo như benchmark.
- Demo SQLite không chứng minh `SELECT ... FOR UPDATE` hoặc chống overselling dưới concurrency.
- Bằng chứng concurrency chỉ hợp lệ khi năm test PostgreSQL trong `tests/concurrency/` thực sự chạy
  và pass.
