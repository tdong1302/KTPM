# Stabilization report

> **Historical snapshot:** báo cáo này ghi kết quả của stabilization pass tại commit `5d6cb70`.
> Sau infrastructure pass, trạng thái hiện tại là 164 collected / 159 passed / 5 PostgreSQL-only
> skipped; xem [infrastructure-readiness-report.md](infrastructure-readiness-report.md).

Ngày kiểm tra: **2026-10-05**. Báo cáo này ghi lại đợt ổn định chức năng trước Pha 2. Không có
thay đổi async, cache, Redis, microservice, CQRS, locking strategy hay benchmark workload.

**Kết quả tổng thể: partially stable.** Application và toàn bộ test không phụ thuộc PostgreSQL đã
pass; acceptance criteria về clean PostgreSQL migration và row-lock concurrency còn bị chặn bởi
môi trường audit không có Docker/PostgreSQL.

## 1. Repository and Git state

- Repository: `https://github.com/tdong1302/KTPM.git`.
- Branch: `main`.
- Commit nền khi bắt đầu: `245af74a07aa582c9dbd2358ee4b49d1e116bb97`.
- Không có `AGENTS.md`.
- Working tree sạch khi bắt đầu; không có file untracked.
- Không commit hoặc push trong đợt ổn định này.
- Dự án là **REST API-only**. Không có frontend, template hoặc static web application. `/docs` là
  Swagger UI dành cho khám phá API, không phải giao diện người dùng hoàn chỉnh.

## 2. Initial failures and gaps

Baseline trước thay đổi:

```text
142 tests collected
138 passed
4 skipped (PostgreSQL concurrency)
0 failed
```

Các gap xác định từ code và test:

1. `BookingService.cancel()` đọc booking trước khi chờ khóa Event nhưng không đọc lại booking sau
   khi lấy khóa. Hai request cùng hủy một booking có thể cùng dùng snapshot `CONFIRMED` và hoàn vé
   hai lần nếu vẫn còn booking khác trên event.
2. Publish/cancel/delete Event dùng read thường, vì vậy các transition đồng thời có thể cùng nhìn
   thấy state cũ và ghi đè kết quả của nhau.
3. Database schema chưa có check constraint cho ticket bounds, giá, role/status, quantity hoặc thứ
   tự thời gian. Domain có kiểm tra nhưng SQL/repository trực tiếp có thể bypass.
4. Production có thể khởi động với JWT secret phát triển mặc định.
5. `seed_data.py` in đầy đủ database URL, có thể làm lộ password trong log.
6. Tài liệu mâu thuẫn về S3, số test, quyền ADMIN, `COMPLETED` và trạng thái frontend.
7. Docker CLI, PostgreSQL client/server và port 5432 không có trên máy kiểm tra; vì vậy không thể
   thực chạy migration/concurrency test trên PostgreSQL.

Các lệnh tái hiện blocker:

```powershell
docker compose config
# docker: command not found

$env:DATABASE_URL="postgresql+psycopg://eventhub@127.0.0.1:5432/eventhub_ktpm?connect_timeout=2"
python -m alembic upgrade head
# sqlalchemy.exc.OperationalError / psycopg.errors.ConnectionTimeout
```

## 3. Changes implemented

### Concurrency and transactions

- Thêm `BookingRepository.get_for_update()` và SQLAlchemy adapter dùng `SELECT ... FOR UPDATE`.
- Khi hủy booking: xác thực caller, khóa Event, sau đó đọc lại/khóa Booking trước khi chuyển state
  và hoàn inventory. Booking chỉ được hoàn đúng một lần.
- Event publish/cancel/delete đọc Event bằng `get_for_update()` để serialize state transition.
- Thêm PostgreSQL concurrency regression test: 20 request cùng hủy một booking, chỉ một request
  được thành công và invariant inventory phải còn đúng.
- Thêm integration test chứng minh exception rollback write chưa commit.

### Database invariants

- ORM và Alembic revision `c4d2f3a1b890` thêm check constraints cho:
  - user role;
  - Event status, positive capacity, non-negative/within-capacity availability, non-negative price,
    `start_time < end_time`;
  - Booking status, quantity 1–10 và non-negative unit price.
- Thêm integration test để chứng minh database từ chối inventory âm khi dùng `create_all()`.

### Configuration and secret safety

- `Settings` kiểm tra pool size/overflow/timeout, JWT expiry và bcrypt rounds.
- `ENVIRONMENT=production|prod` từ chối JWT secret mặc định hoặc secret ngắn hơn 32 ký tự.
- `.env.example` bổ sung `DB_ECHO=false` và giải thích quy tắc JWT production.
- Seed output dùng URL đã che password.

### Documentation

- README nói rõ API-only, sửa trạng thái S2/S3, số test và giới hạn `COMPLETED`.
- API docs mô tả đúng quyền ADMIN đối với booking theo ID.
- Testing docs bỏ thông tin “chưa load test”, thêm cảnh báo concurrency fixture xóa schema.
- Benchmark docs ghi rõ commit artifact không còn trong Git, PostgreSQL version chưa được capture,
  và S2 booking chỉ phân tán trên tối đa 100 event IDs.
- Architecture/Phase 2 docs không còn nói repository không thể bị bypass hoặc async chỉ thay adapter.

## 4. Verified user journeys

Một Uvicorn process thật được chạy ở `127.0.0.1:8765` với SQLite file tạm và
`DB_AUTO_CREATE=true`. Kết quả smoke HTTP:

```text
GET  /health                         200, status=UP
GET  /docs                           200
GET  /openapi.json                   200, 14 operations
POST /api/auth/register              201 (ORGANIZER và USER)
POST /api/auth/login                 200
GET  /api/auth/me                    200, role=USER
POST /api/events                     201, DRAFT
PATCH /api/events/{id}/publish       200, PUBLISHED
GET  /api/events                     200, total=1
POST /api/bookings                   201, CONFIRMED
GET  /api/bookings/me                200, total=1
DELETE /api/bookings/{id}            200, CANCELLED
POST /api/auth/login (sai password)  401
```

Các suite integration hiện có còn xác minh invalid/expired token, password hash không xuất hiện,
draft visibility, ownership, pagination/filter/sort, sold-out, invalid transition và cancellation.

## 5. Test and validation results

Lệnh full suite:

```powershell
uv run --isolated --no-project --no-env-file --with ".[dev]" python -m pytest -ra
```

Kết quả sau thay đổi:

```text
158 collected
153 passed
5 skipped
0 failed
0 deselected
2 warnings
1.54 s
```

Năm test skip đều thuộc `tests/concurrency/test_no_overselling.py` và cần PostgreSQL thật.

Coverage:

```powershell
uv run --isolated --no-project --no-env-file --with ".[dev]" `
  python -m pytest -ra --cov=app --cov-report=term-missing
```

```text
153 passed, 5 skipped, 2 warnings in 2.96 s
TOTAL: 1011 statements, 26 missing, 97%
```

Architecture tests: 19/19 pass. Domain/application không import framework hoặc ORM.

Alembic revision chain:

```text
<base> -> a9ddd8888f24 -> c4d2f3a1b890 (head)
```

`python -m alembic upgrade head --sql` sinh thành công PostgreSQL transactional DDL, gồm toàn bộ
table/index và 10 check constraints mới. Đây là kiểm tra offline; migration chưa được execute trên
PostgreSQL thật trong môi trường này.

Warnings còn lại:

- Starlette cảnh báo TestClient với HTTPX hiện tại đã deprecated.
- Test forged JWT cố ý dùng key ngắn và tạo `InsecureKeyLengthWarning`.

Không có lint/format/type-check tool được cấu hình, nên không có command tương ứng để chạy.

## 6. Exact reproduction commands

### Local development

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev,bench]"
Copy-Item .env.example .env
# Thay DATABASE_URL/JWT_SECRET trong .env; không commit file này.

docker compose up -d postgres
python -m alembic upgrade head
python -m uvicorn app.main:app --reload --port 8000
```

Hoặc:

```powershell
.\scripts\run-dev.ps1
```

### Full tests without PostgreSQL concurrency

```powershell
python -m pytest -ra
```

### Full tests with PostgreSQL

Chỉ dùng database disposable; fixture gọi `drop_all()`:

```powershell
docker compose up -d postgres
$env:TEST_DATABASE_URL="<dedicated disposable PostgreSQL DSN>"
python -m pytest -ra
```

### Migration verification

```powershell
docker compose up -d postgres
python -m alembic upgrade head
python -m alembic current
```

## 7. Current UI status

**API-only.** Dự án có FastAPI REST API, OpenAPI JSON, Swagger UI và ReDoc. Không có server-rendered
UI hoặc frontend riêng. Việc thêm một frontend tối thiểu là development slice riêng, không thuộc
đợt stabilization này.

## 8. Remaining limitations

- PostgreSQL migration và 5 concurrency tests chưa chạy được trên máy audit vì Docker/PostgreSQL
  không được cài và `127.0.0.1:5432` không reachable.
- Docker Compose startup/config validation chưa thể chạy vì không có Docker CLI.
- `benchmark/seed_data.py` đã được kiểm tra và output DSN đã được che password, nhưng seed chưa được
  thực thi vì nó cần PostgreSQL đang chạy.
- Integration API thông thường vẫn dùng SQLite; PostgreSQL coverage chỉ nằm ở concurrency suite.
- Không có dependency lockfile hoặc CI.
- `COMPLETED` chưa có application use case/API/job.
- Không có Event update endpoint; không bổ sung trong stabilization vì scope hiện được code/test hỗ trợ
  chỉ gồm create, publish, cancel và delete draft.
- ADMIN có thể get/cancel booking theo ID nhưng chưa thể list/search tất cả booking.
- Không có frontend.
- Benchmark artifact cũ tham chiếu commit không còn tồn tại; S1/S4 và repetition còn thiếu.

## 9. Recommended next development slice

Trên máy có Docker:

1. `docker compose config`.
2. Khởi động PostgreSQL disposable.
3. Chạy migration từ database rỗng tới `c4d2f3a1b890`.
4. Chạy đủ 158 tests và yêu cầu 158 pass, không skip.
5. Chạy smoke flow với API container.
6. Lưu console log và tạo một baseline tag có thể truy xuất.

Sau đó mới quyết định development slice sản phẩm: hoặc hoàn thiện semantics `COMPLETED`, hoặc bổ
sung ADMIN booking search/list; không nên làm cả hai cùng với thay đổi kiến trúc.

## 10. Deliberately deferred to Phase 2

- Async SQLAlchemy/asyncpg.
- Cache hoặc Redis.
- Tuning workers/connection pool.
- Atomic inventory update thay pessimistic lock.
- Index/keyset pagination optimization.
- Microservices, queue, CQRS, Kubernetes.
- Benchmark/load-test optimization và BEFORE/AFTER comparison.

Các hạng mục này chỉ được chọn sau khi PostgreSQL correctness baseline và benchmark có thể tái lập.
