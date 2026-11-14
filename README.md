# EventHub-KTPM

Dịch vụ REST API và frontend MVP cho nghiệp vụ **đặt vé sự kiện**, xây dựng làm **baseline (Pha 1)**
cho môn Kiến trúc/Kỹ thuật phần mềm.

> **Frontend MVP:** mở `/app/` để dùng giao diện người dùng cuối. Swagger UI tại `/docs` vẫn dành
> cho việc khám phá và kiểm thử API.

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
| Frontend | HTML/CSS/JavaScript thuần, được FastAPI phục vụ tại `/app/` |
| API docs | OpenAPI 3.1 / Swagger UI tại `/docs` |
| Đóng gói | Docker + docker compose |
| Test | pytest (unit, kiến trúc, integration, concurrency) |
| Load test | Locust, chạy được trên Kaggle CPU |

## 2. Phạm vi (scope)

### Chức năng của hệ thống

- Đăng ký, đăng nhập (JWT), xem tài khoản hiện tại.
- Tạo / chỉnh sửa bản nháp / phát hành / huỷ / xoá sự kiện; worker riêng tự động chuyển sự kiện
  đã kết thúc từ `PUBLISHED` sang `COMPLETED`.
- Tra cứu sự kiện công khai: tìm kiếm, lọc, phân trang, sắp xếp.
- Đặt vé (trừ tồn kho có khoá dòng), xem vé của mình, huỷ vé (hoàn tồn kho).

### Ngoài phạm vi Pha 1

Thanh toán, mã QR cho vé, thông báo, mua bán lại vé, upload ảnh, xác thực email, refresh token và
frontend framework/build pipeline đều nằm ngoài phạm vi.

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
| GET | `/ready` | – | PostgreSQL readiness |
| GET | `/metrics` | – | Operational Prometheus text metrics |
| POST | `/api/auth/register` | – | Đăng ký |
| POST | `/api/auth/login` | – | Đăng nhập, trả access token |
| GET | `/api/auth/me` | ✅ | **GET cần xác thực** |
| GET | `/api/events` | – | Danh sách sự kiện đã phát hành |
| GET | `/api/events/mine` | ✅ | Sự kiện thuộc ORGANIZER hiện tại |
| GET | `/api/events/{id}` | – | Chi tiết sự kiện |
| POST | `/api/events` | ✅ | **POST cần xác thực** (ORGANIZER/ADMIN) |
| PATCH | `/api/events/{id}` | ✅ | Chỉnh sửa một phần sự kiện `DRAFT` của chủ sở hữu |
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

Worker hoàn tất sự kiện chạy độc lập với tiến trình web. Mỗi transaction lấy một batch có giới hạn,
sắp xếp theo `end_time, id`, và PostgreSQL dùng `FOR UPDATE SKIP LOCKED` để nhiều worker chia việc
mà không chờ nhau. SQLite chỉ là fallback chức năng, không phải bằng chứng concurrency.

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

Trên Windows Command Prompt (`cmd.exe`), dùng các wrapper ngắn gọn sau:

```cmd
scripts\setup-local.cmd
scripts\verify-local.cmd
scripts\run-dev.cmd
scripts\run-demo.cmd
scripts\run-tests.cmd --with-db
scripts\run-completion-worker.cmd --once
scripts\quality-gate.cmd
```

Chạy worker liên tục bằng `scripts\run-completion-worker.cmd`; dừng an toàn bằng `Ctrl+C`. Hai biến
`EVENT_COMPLETION_POLL_SECONDS` (mặc định `60`) và `EVENT_COMPLETION_BATCH_SIZE` (mặc định `100`)
điều khiển polling và kích thước transaction. Worker không thêm endpoint; hai operational endpoint
`/ready` và `/metrics` nâng OpenAPI từ 16 operation nghiệp vụ lên tổng cộng 18 operation.

Nếu one-shot trả exit code khác `0`, kiểm tra kết nối database và migration rồi chạy lại; log chỉ
ghi loại lỗi, không ghi URL kết nối. Continuous mode chờ đúng poll interval sau lỗi nên không tạo
retry loop nóng. Trạng thái trên UI có eventual-consistency tối đa bằng poll interval và hiện chỉ
cập nhật khi người dùng refresh theo hành vi sẵn có; slice này không thêm refund/realtime policy.

Hướng dẫn đầy đủ và cảnh báo database test: [docs/local-machine-setup.md](docs/local-machine-setup.md).

Quy tắc branch/commit/PR và Definition of Done: [CONTRIBUTING.md](CONTRIBUTING.md). Kế hoạch chia
việc ba thành viên và thứ tự merge Pha 2: [docs/phase2-team-plan.md](docs/phase2-team-plan.md).

Các quality command chuẩn:

```bash
uv run --frozen --extra dev ruff format --check app tests alembic scripts
uv run --frozen --extra dev ruff check app tests alembic scripts
uv run --frozen --extra dev pytest
uv run --frozen --extra dev pytest --cov=app --cov-report=term-missing --cov-fail-under=95
```

Mở frontend tại http://localhost:8000/app/ và Swagger tại http://localhost:8000/docs. Hướng dẫn sử
dụng, giới hạn MVP và kịch bản trình bày: [docs/frontend-mvp.md](docs/frontend-mvp.md).

### Functional demo không cần Docker

Trên Windows PowerShell, lệnh sau tạo database SQLite demo riêng, khởi động API, chạy các luồng
auth/event/booking chính, dừng server và sinh báo cáo đã loại token/password:

```powershell
.\scripts\run-demo.ps1
```

Từ Windows Command Prompt, chạy `scripts\run-demo.cmd`.

Kết quả nằm tại `artifacts/demo/latest-demo-report.md` và `.json`. Trên Bash/WSL:

```bash
bash scripts/run-demo.sh
```

Demo SQLite dùng để trình diễn chức năng, không thay thế bằng chứng PostgreSQL concurrency hoặc
benchmark. Hướng dẫn thao tác qua frontend/Swagger và chạy demo bằng Docker:
[docs/demo-guide.md](docs/demo-guide.md).

## 8. Chạy bằng Docker

```cmd
docker compose up -d --build
curl http://localhost:8000/health
curl http://localhost:8000/ready
curl http://localhost:8000/metrics
```

Lệnh này dựng PostgreSQL 16 (cổng 5432), chạy Alembic tới `head`, rồi mới khởi động API ở cổng
8000 và worker nền không mở cổng. API và worker dùng cùng image/cấu hình database;
`DB_AUTO_CREATE=false`; lỗi migration làm cả hai không khởi động.

Dừng: `docker compose down` (thêm `-v` để xoá luôn dữ liệu).

## 9. Chạy test

```cmd
scripts\run-tests.cmd
uv run --frozen pytest tests\unit
uv run --frozen pytest --cov=app
```

Bật test chống bán vượt vé trên database disposable riêng (cổng 5433):

```cmd
scripts\run-tests.cmd --with-db tests\concurrency -v
```

Wrapper tự cấu hình database test disposable mà không yêu cầu in connection URL. Nó không bao giờ
trỏ fixture phá schema vào database phát triển.

Chi tiết: [docs/testing.md](docs/testing.md).

## 10. Observability

Mọi HTTP response có `X-Request-ID`: ID an toàn từ client được giữ, giá trị thiếu/sai được thay bằng
ID ngẫu nhiên. Completion log là JSON mặc định và chỉ chứa timestamp, level, logger, event,
correlation ID, method, route template, status và duration; không ghi body, query string,
Authorization hay cookie. Đặt `OBSERVABILITY_LOG_FORMAT=text` nếu cần log local dễ đọc hơn.

`/health` chỉ chứng minh process sống; `/ready` chạy `SELECT 1` qua pool hiện hữu để chứng minh
PostgreSQL sẵn sàng. `/metrics` xuất request/status/duration/in-flight/error cùng connection
creation, checkout, checked-out, overflow, hold và query timing. Label chỉ dùng method, route
template, status class và outcome hữu hạn. Production phải chặn `/metrics` ở reverse proxy/network,
không coi endpoint công khai ở tầng app là quyền truy cập Internet mặc định.

Pool acquisition wait vẫn là **NOT YET MEASURED**: SQLAlchemy `checkout` event chỉ chạy sau khi đã
lấy được connection, nên không được đổi tên hold time thành wait time.

## 11. Benchmark

Phase 2 BEFORE đã đo đủ **S1–S4**, ba lần cho mỗi cấu hình, trên cùng máy/config. S1 đạt median
155,78 req/s (p95 39 ms); S2 đạt 226,12 req/s (p95 180 ms); S3 tách đúng `201`/valid `409`, không
có lỗi thật và giữ invariant tồn kho. S4 tăng tới 80 user với median 212,05 req/s, p95 55 ms,
không lỗi; saturation chưa đạt trong dải an toàn đã thử.

```cmd
scripts\run-benchmark.cmd --scenario s1 --scenario s2 --scenario s3
scripts\run-benchmark.cmd --scenario s4
scripts\run-benchmark.cmd --scenario s1 --scenario s4 --smoke
```

Trên Kaggle CPU (cấu hình chuẩn của môn): xem hướng dẫn từng bước ở
[benchmark/kaggle/README.md](benchmark/kaggle/README.md). Kaggle là notebook nên chạy trong
ô code: `!python benchmark/kaggle/run_baseline.py --scenario s2`.

Kịch bản cố định: [benchmark/scenarios.md](benchmark/scenarios.md). Baseline hiện hành, provenance,
CPU/RSS, variation và phân tích bottleneck:
[docs/benchmark-baseline-phase2.md](docs/benchmark-baseline-phase2.md). Raw output mới ở
`artifacts/benchmarks/` và bị Git ignore; `benchmark/results/` giữ evidence Kaggle lịch sử.

## 12. Trạng thái hiện tại

Pha 1 có kiến trúc phân tầng với ràng buộc business layer không import framework/DB được kiểm chứng
tự động bằng AST, 16 operation nghiệp vụ cùng 2 operation vận hành (đủ GET/POST/DELETE, có route yêu cầu xác thực qua middleware),
frontend MVP tại `/app/`, Swagger và đóng gói Docker. Quality gate automatic-completion thu được
**283/283 test pass**, gồm **7/7 PostgreSQL concurrency test**, với coverage **97,67%**. Benchmark
Phase 2 BEFORE S1–S4 đã hoàn tất; S4 chưa đạt saturation trong dải 1–80. Observability foundation
đã đo query execution và connection hold; acquisition wait và threadpool wait vẫn chưa đo chính
xác. Xem [docs/benchmark-baseline-phase2.md](docs/benchmark-baseline-phase2.md).

## 13. Cấu trúc thư mục

```
app/
├── domain/          Dataclass, enum, quy tắc nghiệp vụ (thuần Python)
├── application/     Service + Port (Protocol) — tầng nghiệp vụ
├── infrastructure/  SQLAlchemy, repository, UnitOfWork, bcrypt, JWT
├── observability/   Correlation context, structured events, metrics, SQL timing
├── workers/         Tiến trình nền độc lập, không import FastAPI
└── api/             Router, schema, middleware, exception handler
alembic/             Migration
frontend/            Giao diện MVP tĩnh, không có build step
tests/
├── unit/            Nghiệp vụ với fake repo + test ràng buộc kiến trúc
├── integration/     API thật qua TestClient + SQLite
└── concurrency/     Chống bán vượt vé (cần PostgreSQL)
benchmark/           Locust, seed dữ liệu, script Kaggle
docs/                Tài liệu kiến trúc, API, test, benchmark, Pha 2
```
