# EventHub-KTPM

Dịch vụ backend REST API cho nghiệp vụ **đặt vé sự kiện**, xây dựng làm **baseline (Pha 1)** cho
môn Kiến trúc/Kỹ thuật phần mềm.

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
- Tạo / phát hành / huỷ / xoá sự kiện, theo vòng đời `DRAFT → PUBLISHED → CANCELLED|COMPLETED`.
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

## 7. Chạy local

Yêu cầu: Python 3.11+ và một PostgreSQL đang chạy (hoặc dùng `docker compose up -d postgres`).

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

pip install -e ".[dev,bench]"
cp .env.example .env          # rồi sửa DATABASE_URL nếu cần

# Tạo schema (chọn 1 trong 2):
alembic upgrade head          # cách chuẩn
# hoặc đặt DB_AUTO_CREATE=true trong .env để app tự tạo bảng lúc khởi động

uvicorn app.main:app --reload
```

Mở http://localhost:8000/docs

## 8. Chạy bằng Docker

```bash
docker compose up -d --build
curl http://localhost:8000/health
```

Lệnh này dựng PostgreSQL 16 (cổng 5432) và API (cổng 8000). API chờ database healthy rồi mới khởi
động, và tự tạo schema vì `DB_AUTO_CREATE=true` trong compose.

Dừng: `docker compose down` (thêm `-v` để xoá luôn dữ liệu).

## 9. Chạy test

```bash
pytest                    # toàn bộ; test concurrency sẽ SKIP nếu chưa có PostgreSQL
pytest tests/unit         # chỉ unit + test kiến trúc, rất nhanh
pytest --cov=app          # kèm coverage
```

Bật test chống bán vượt vé (cần PostgreSQL thật, vì nó phụ thuộc row lock):

```bash
docker compose up -d postgres
# Windows PowerShell:
$env:TEST_DATABASE_URL="postgresql+psycopg://eventhub:eventhub@localhost:5432/eventhub_ktpm"
# Linux/macOS:
export TEST_DATABASE_URL="postgresql+psycopg://eventhub:eventhub@localhost:5432/eventhub_ktpm"

pytest tests/concurrency -v
```

Hoặc dùng script: `scripts/run-tests.ps1` (Windows) / `scripts/run-tests.sh` (Linux/macOS).

Chi tiết: [docs/testing.md](docs/testing.md).

## 10. Benchmark

Đã đo kịch bản **S2** trên Kaggle CPU (Xeon @2.20GHz, 4 vCPU): **47 612 request, 0 lỗi,
159,30 req/s, p50 240 ms, p95 430 ms**. Số liệu đầy đủ và phần phân tích ở
[docs/benchmark.md](docs/benchmark.md); dữ liệu thô ở [benchmark/results/](benchmark/results/).
S1, S3, S4 chưa chạy.

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

Pha 1 (baseline) đã hoàn chỉnh và được verify bằng chạy thật: kiến trúc phân tầng với ràng buộc
business layer không import framework/DB kiểm chứng tự động bằng AST, 14 endpoint REST (đủ
GET/POST/DELETE, có route yêu cầu xác thực qua middleware), Swagger, đóng gói Docker, 142 test pass
trên PostgreSQL (bao gồm test chống bán vượt vé). Đã đẩy lên GitHub public và chạy load test thật
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
