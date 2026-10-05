# EventHub-KTPM

Dịch vụ backend REST API cho nghiệp vụ **đặt vé sự kiện**, xây dựng làm **baseline (Pha 1)** cho
môn Kiến trúc/Kỹ thuật phần mềm.

> **Trạng thái giao diện:** dự án hiện là **REST API-only**. Swagger UI tại `/docs` là giao diện
> khám phá API, không phải frontend dành cho người dùng cuối.

> Mô tả hệ thống ngắn gọn: [docs/mo-ta-he-thong.md](docs/mo-ta-he-thong.md)

---

## 1. Tổng quan

| Hạng mục | Nội dung |
|---|---|
| Domain | Đặt vé sự kiện (event ticket booking) |
| Vai trò | `USER`, `ORGANIZER`, `ADMIN` |
| Kiến trúc | Ports & Adapters: `api` → `application` → `infrastructure` → PostgreSQL |
| Ngôn ngữ | Python 3.11+ |
| Framework | FastAPI + Uvicorn |
| ORM | SQLAlchemy 2.0 (data mapper), Alembic migration |
| Database | PostgreSQL 16 |
| Auth | JWT (HS256, PyJWT) + bcrypt, xác thực tại **middleware** |
| API docs | OpenAPI 3.1 / Swagger UI tại `/docs` |
| Đóng gói | Docker + docker compose |
| Test | pytest (unit, kiến trúc, integration, concurrency) |
| Load test | Locust, chạy được trên Kaggle CPU |

## 2. Phạm vi (scope)

### Chức năng của hệ thống

- Đăng ký, đăng nhập (JWT), xem tài khoản hiện tại.
- Tạo / phát hành / huỷ / xoá sự kiện. Domain có trạng thái `COMPLETED`, nhưng baseline hiện chưa
  có endpoint hoặc background job chuyển sự kiện sang trạng thái này.
- Tra cứu sự kiện công khai: tìm kiếm, lọc, phân trang, sắp xếp.
- Đặt vé (trừ tồn kho có khoá dòng), xem vé của mình, huỷ vé (hoàn tồn kho).

### Ngoài phạm vi Pha 1

Thanh toán, mã QR cho vé, thông báo, mua bán lại vé, upload ảnh, xác thực email, refresh token và
giao diện người dùng đều nằm ngoài phạm vi.

Pha 1 chủ ý giữ lõi nghiệp vụ đủ nhỏ để kiểm thử và đo đạc được, vì chính hệ thống này sẽ là đối
tượng nghiên cứu ở Pha 2. Lý do của từng quyết định phạm vi ghi trong
[docs/architecture.md](docs/architecture.md#5-quyết-định-phạm-vi).

## 3. Kiến trúc

```
┌──────────────────────────────────────────────────────────┐
│ app/api           Router, DTO (Pydantic), middleware JWT,│
│                   exception handler                      │
├──────────────────────────────────────────────────────────┤
│ app/application   Service nghiệp vụ + Port (Protocol)    │
│                   ❗ chỉ import stdlib và app.domain      │
├──────────────────────────────────────────────────────────┤
│ app/domain        Dataclass + Enum + quy tắc nghiệp vụ   │
│                   ❗ thuần Python, không annotation ORM   │
├──────────────────────────────────────────────────────────┤
│ app/infrastructure  SQLAlchemy, repository adapter,      │
│                     UnitOfWork, bcrypt, PyJWT            │
└──────────────────────────────────────────────────────────┘
                          ↓
                    PostgreSQL 16
```

Yêu cầu khó nhất của đề bài là *"Tầng nghiệp vụ không import framework web hay thư viện DB"*.
Ở đây `app/domain` và `app/application` chỉ giao tiếp với bên ngoài qua các `Protocol` khai báo
trong [`app/application/ports.py`](app/application/ports.py). Ràng buộc này **được kiểm chứng tự
động** bởi [`tests/unit/test_architecture.py`](tests/unit/test_architecture.py): test phân tích AST
từng module trong hai tầng đó và làm fail build nếu có import `fastapi`, `sqlalchemy`, `pydantic`,
`jwt`, `bcrypt`...

Chi tiết: [docs/architecture.md](docs/architecture.md).

## 4. API

Đặc tả đầy đủ: [docs/api.md](docs/api.md). Swagger UI: `http://localhost:8000/docs`.

| Method | Path | Auth | Mô tả |
|---|---|:---:|---|
| GET | `/health` | – | Liveness |
| POST | `/api/auth/register` | – | Đăng ký |
| POST | `/api/auth/login` | – | Đăng nhập, trả access token |
| GET | `/api/auth/me` | ✅ | **GET cần xác thực** |
| GET | `/api/events` | – | Danh sách sự kiện đã phát hành |
| GET | `/api/events/{id}` | – | Chi tiết sự kiện |
| POST | `/api/events` | ✅ | **POST cần xác thực** (ORGANIZER/ADMIN) |
| PATCH | `/api/events/{id}/publish` | ✅ | Phát hành sự kiện |
| PATCH | `/api/events/{id}/cancel` | ✅ | Huỷ sự kiện |
| DELETE | `/api/events/{id}` | ✅ | **DELETE** – xoá sự kiện nháp |
| POST | `/api/bookings` | ✅ | Đặt vé |
| GET | `/api/bookings/me` | ✅ | Vé của tôi |
| GET | `/api/bookings/{id}` | ✅ | Chi tiết vé |
| DELETE | `/api/bookings/{id}` | ✅ | Huỷ vé, hoàn tồn kho |

Đáp ứng yêu cầu Pha 1: có đủ `POST`/`GET`/`DELETE`, ≥1 `GET` và ≥1 `POST` yêu cầu xác thực.

## 5. Authentication

Toàn bộ việc xác thực nằm ở **một middleware duy nhất**
([`app/api/middleware.py`](app/api/middleware.py)), chạy trước mọi route handler:

1. Đọc header `Authorization: Bearer <token>`, xác minh chữ ký, gắn principal vào `request.state`.
2. Đối chiếu bảng policy khai báo `PUBLIC_ROUTES`. Route không công khai mà không có token hợp lệ
   → trả `401` ngay, handler **không chạy**.
3. Handler chỉ *đọc* kết quả qua dependency mỏng `current_principal`. Không endpoint nào lặp lại
   logic xác thực.
4. Phân quyền theo nghiệp vụ (chủ sở hữu sự kiện, vai trò ORGANIZER) nằm ở tầng business và trả
   `403`.

## 6. Database

Ba bảng: `users`, `events`, `bookings`. Xem
[`app/infrastructure/db/orm.py`](app/infrastructure/db/orm.py) và migration khởi tạo trong
[`alembic/versions/`](alembic/versions/).

Tồn kho vé dùng một biến đếm `events.available_tickets`. Thao tác đặt/huỷ vé đọc dòng sự kiện bằng
`SELECT ... FOR UPDATE` trong cùng một transaction, nên **không thể bán vượt số vé** khi nhiều
người đặt đồng thời.

## 7. Development environment

Yêu cầu: Python 3.11+, [uv](https://docs.astral.sh/uv/) và Docker Desktop/Compose v2 khi cần
PostgreSQL. Dependency graph được khóa trong `uv.lock`.

```bash
uv sync --frozen --extra dev --extra bench

# Windows PowerShell
Copy-Item .env.example .env
.\scripts\preflight.ps1 -Mode api-only

# Bash/WSL
cp .env.example .env
bash scripts/preflight.sh api-only
```

Sau khi Docker/PostgreSQL đã khởi động, dùng mode `development` hoặc `postgres-test` để kiểm tra
đầy đủ. Preflight không tạo/xóa database và không in secret hay URL đầy đủ. Hướng dẫn Windows/WSL2
và troubleshooting: [docs/infrastructure-readiness-report.md](docs/infrastructure-readiness-report.md).

Chạy API local:

```bash
docker compose up -d postgres
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

Hoặc dùng `scripts/run-dev.ps1` / `scripts/run-dev.sh`. Để cập nhật dependency có chủ đích, sửa
`pyproject.toml`, chạy `uv lock`, rồi xác nhận lại bằng `uv sync --frozen --all-extras`.

Các quality command chuẩn:

```bash
uv run --frozen --extra dev ruff format --check app tests alembic scripts
uv run --frozen --extra dev ruff check app tests alembic scripts
uv run --frozen --extra dev pytest
uv run --frozen --extra dev pytest --cov=app --cov-report=term-missing --cov-fail-under=95
```

Mở http://localhost:8000/docs

### Functional demo không cần Docker

Trên Windows PowerShell, lệnh sau tạo database SQLite demo riêng, khởi động API, chạy các luồng
auth/event/booking chính, dừng server và sinh báo cáo đã loại token/password:

```powershell
.\scripts\run-demo.ps1
```

Kết quả nằm tại `artifacts/demo/latest-demo-report.md` và `.json`. Trên Bash/WSL:

```bash
bash scripts/run-demo.sh
```

Demo SQLite dùng để trình diễn chức năng, không thay thế bằng chứng PostgreSQL concurrency hoặc
benchmark. Hướng dẫn tự thao tác qua Swagger và chạy demo bằng Docker:
[docs/demo-guide.md](docs/demo-guide.md).

## 8. Chạy bằng Docker

```bash
docker compose up -d --build
curl http://localhost:8000/health
```

Lệnh này dựng PostgreSQL 16 (cổng 5432), chạy Alembic tới `head`, rồi mới khởi động API ở cổng
8000. `DB_AUTO_CREATE=false`; lỗi migration làm API không khởi động.

Dừng: `docker compose down` (thêm `-v` để xoá luôn dữ liệu).

## 9. Chạy test

```bash
uv run pytest                    # toàn bộ; concurrency SKIP nếu thiếu TEST_DATABASE_URL
uv run pytest tests/unit         # unit + kiến trúc
uv run pytest --cov=app          # coverage
```

Bật test chống bán vượt vé trên database disposable riêng (cổng 5433):

```bash
docker compose --profile test up -d postgres-test
# Windows PowerShell:
$env:TEST_DATABASE_URL="postgresql+psycopg://eventhub_test:eventhub_test@localhost:5433/eventhub_test_disposable"
# Linux/macOS:
export TEST_DATABASE_URL="postgresql+psycopg://eventhub_test:eventhub_test@localhost:5433/eventhub_test_disposable"

uv run pytest tests/concurrency -v
```

Hoặc dùng `scripts/run-tests.ps1 -WithDb` / `scripts/run-tests.sh --with-db`. Các script không bao
giờ trỏ fixture phá schema vào database phát triển.

Chi tiết: [docs/testing.md](docs/testing.md).

## 10. Benchmark

Đã đo các kịch bản **S2 và S3** trên Kaggle CPU (Xeon @2.20GHz, 4 vCPU). S2 ghi nhận
**47 612 request, 0 lỗi,
159,30 req/s, p50 240 ms, p95 430 ms**. Số liệu đầy đủ và phần phân tích ở
[docs/benchmark.md](docs/benchmark.md); dữ liệu thô ở [benchmark/results/](benchmark/results/).
S1 và S4 chưa chạy. Các giới hạn về provenance và khả năng lặp lại được ghi trong
[`docs/stabilization-report.md`](docs/stabilization-report.md).

```bash
python benchmark/seed_data.py --reset --events 500
locust -f benchmark/locustfile.py --headless --host http://localhost:8000 \
       --users 100 --spawn-rate 20 --run-time 5m --csv benchmark/results/s2-baseline
```

Trên Kaggle CPU (cấu hình chuẩn của môn): xem hướng dẫn từng bước ở
[benchmark/kaggle/README.md](benchmark/kaggle/README.md). Kaggle là notebook nên chạy trong
ô code: `!python benchmark/kaggle/run_baseline.py --scenario s2`.

Kịch bản cố định: [benchmark/scenarios.md](benchmark/scenarios.md).
Bảng ghi kết quả: [docs/benchmark.md](docs/benchmark.md).

## 11. Trạng thái hiện tại

Pha 1 có kiến trúc phân tầng với ràng buộc business layer không import framework/DB được kiểm chứng
tự động bằng AST, 14 endpoint REST (đủ GET/POST/DELETE, có route yêu cầu xác thực qua middleware),
Swagger và đóng gói Docker. Lần kiểm tra hạ tầng gần nhất thu được **164 test collected: 159 pass,
5 PostgreSQL concurrency test skip** khi máy kiểm tra không có PostgreSQL. Git history ghi nhận một
lần chạy cũ trên PostgreSQL, nhưng không có raw test log kèm theo để tái lập. Đã chạy load test thật
trên Kaggle CPU cho hai kịch bản S2 (baseline throughput) và S3 (tranh chấp ghi) — số liệu và phân
tích ở [docs/benchmark.md](docs/benchmark.md).

Còn thiếu: kịch bản benchmark S1 và S4 chưa chạy — S4 quan trọng nhất vì nó xác định nút thắt hiệu
năng thực sự (CPU/connection pool/threadpool), cần có trước khi bắt đầu Pha 2. Pha 2 (cải tiến chất
lượng) chưa bắt đầu; danh sách ứng viên quality attribute và cách đo được ghi ở
[docs/phase2.md](docs/phase2.md), chưa có kết luận nào được viết ra trước khi có số đo thật.

## 12. Cấu trúc thư mục

```
app/
├── domain/          Dataclass, enum, quy tắc nghiệp vụ (thuần Python)
├── application/     Service + Port (Protocol) — tầng nghiệp vụ
├── infrastructure/  SQLAlchemy, repository, UnitOfWork, bcrypt, JWT
└── api/             Router, schema, middleware, exception handler
alembic/             Migration
tests/
├── unit/            Nghiệp vụ với fake repo + test ràng buộc kiến trúc
├── integration/     API thật qua TestClient + SQLite
└── concurrency/     Chống bán vượt vé (cần PostgreSQL)
benchmark/           Locust, seed dữ liệu, script Kaggle
docs/                Tài liệu kiến trúc, API, test, benchmark, Pha 2
```
