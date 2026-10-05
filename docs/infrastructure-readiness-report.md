# Infrastructure readiness report

Ngày kiểm tra: **2026-10-05**.

## 1. Executive summary

**Kết quả: repository-ready-but-host-blocked.** Repository đã có dependency lock, preflight đa nền
tảng, Ruff, Docker Compose tách database phát triển/test, Alembic startup gate và GitHub Actions
dùng PostgreSQL thật. Các kiểm tra không cần Docker/PostgreSQL đều pass.

Host Windows hiện tại không có Docker CLI, Compose plugin, daemon hoặc PostgreSQL client/server;
WSL trả `Access is denied`. Vì vậy Docker Compose, migration online, container smoke và năm test
concurrency chưa thể chạy local. Workflow CI mới chỉ được cấu hình/static-review, chưa được thực thi
trên GitHub. Không tuyên bố full infrastructure verification cho tới khi migration và concurrency
suite pass trên PostgreSQL thật ở local hoặc CI.

Repository là **FastAPI REST API-only**, không có frontend người dùng cuối.

## 2. Initial environment state

| Thành phần | Kết quả quan sát |
|---|---|
| OS | Microsoft Windows NT `10.0.19045.0` |
| Shell | Windows PowerShell `5.1.19041.7725` |
| Python | `3.12.10` |
| uv | `0.12.13` |
| Git | `2.55.0.windows.5` |
| Docker CLI | Không có trên `PATH` |
| Docker Compose v2 | Không kiểm tra được vì thiếu Docker CLI |
| Docker daemon | Không kiểm tra được vì thiếu Docker CLI |
| `psql` / `pg_isready` | Không có trên `PATH` |
| `127.0.0.1:5432` | Không reachable |
| WSL | `wsl --status` và `wsl --list --verbose` trả `Access is denied` |
| `.env` | Không tồn tại |
| `.env.example` | Tồn tại; preflight xác nhận đủ tên setting bắt buộc |
| Environment variables | Không có `DATABASE_URL`, `TEST_DATABASE_URL`, `JWT_SECRET`, `ENVIRONMENT` |

Git khi bắt đầu task:

```text
branch: stabilization-infrastructure
HEAD: 5d6cb7083751b929c59f79e059f59eb741e8e415
status: clean
remote: https://github.com/tdong1302/KTPM.git
```

Commit `5d6cb70` chứa 23 file của stabilization pass trước; task này giữ nguyên các invariant và
locking fix đó.

## 3. Missing prerequisites

Các blocker host được xác định cụ thể:

- Thiếu executable `docker`, do đó chưa thể xác định tiếp Compose plugin hay daemon connectivity.
- Không có `psql` và `pg_isready`.
- Không có PostgreSQL nghe ở cổng local 5432.
- WSL command tồn tại nhưng không truy vấn được trạng thái vì Windows trả `Access is denied`;
  trạng thái distro integration và virtualization vì vậy chưa xác định được.
- Không có `.env`; điều này không chặn API-only test nhưng cần cho local development tùy chỉnh.

Không có privileged installation hay thay đổi host nào được thực hiện.

## 4. Repository infrastructure changes

- Tạo `uv.lock` từ `pyproject.toml`; runtime, `dev`, `bench` vẫn là ba nhóm logic riêng.
- Dev dependency chuyển từ legacy `httpx` sang `httpx2`, đúng dependency mà Starlette TestClient
  hiện ưu tiên; warning deprecation biến mất khi chạy test thật.
- Thêm Ruff lint/format; không bật ignore rộng. Migration khởi tạo sinh tự động được loại đúng file
  khỏi formatter để tránh diff lịch sử không liên quan.
- Không thêm Mypy: lần audit thực tế có 34 lỗi trong 5 file (nullable ORM mapping, Protocol/UoW và
  response typing). Việc làm xanh cần refactor type contract, không phù hợp với slice hạ tầng và
  không được che bằng `ignore_missing_imports` hoặc suppression rộng.
- Thêm preflight Python dùng chung và wrapper PowerShell/Bash.
- Tách PostgreSQL test destructive khỏi database phát triển.
- Docker API không còn `create_all()`; service `migrate` phải chạy Alembic thành công trước API.
- Thêm schema verifier và HTTP smoke runner không phụ thuộc package HTTP bên ngoài.
- Thêm GitHub Actions PostgreSQL CI.
- Cập nhật README, test docs và `.env.example` theo lệnh thực tế.

## 5. Preflight behavior

Files:

- `scripts/preflight.py`: logic chung, chỉ dùng standard library.
- `scripts/preflight.ps1`: wrapper Windows.
- `scripts/preflight.sh`: wrapper Bash/WSL.
- `tests/unit/test_preflight.py`: sáu test cho dotenv parsing, URL parsing, chống trùng/protected
  database và redaction credential.

Ba mode:

| Mode | Docker/PostgreSQL | Mục đích |
|---|---|---|
| `api-only` | WARN, không block | Unit/integration SQLite và quality checks |
| `development` | Bắt buộc | API local + PostgreSQL phát triển |
| `postgres-test` | Bắt buộc | Concurrency trên database có tên rõ là disposable |

Script kiểm tra Python ≥3.11, uv/version, file bắt buộc, cấu trúc `.env.example`, Docker
CLI/Compose/daemon, database reachability, cổng API 8000, production JWT requirement và safety của
`TEST_DATABASE_URL`. Output chỉ chứa host, port và database name; không in username, password,
token hoặc URL đầy đủ. Preflight không tạo/xóa schema hay database.

PowerShell `api-only` đã chạy thành công: `0 FAIL, 3 WARN` (`.env`, Docker và JWT local chưa set).
Mode `development` trả đúng non-zero với `2 FAIL, 3 WARN`: thiếu Docker CLI và PostgreSQL 5432
không reachable. Bash wrapper chưa chạy được vì host chuyển lệnh `bash` vào WSL và WSL trả
`Access is denied`.

## 6. Dependency-lock status

`uv lock` resolve thành công **78 package**. Frozen install:

```powershell
uv sync --frozen --extra dev
```

Kết quả: tạo `.venv`, build package local và cài **44 package** cho dev; lệnh
`uv sync --frozen --all-extras` sau đó cài thêm **32 package** benchmark từ cùng lockfile. Các phiên
bản chính được khóa gồm:

```text
Python local: 3.12.10
FastAPI:       0.142.2
Starlette:     1.7.0
SQLAlchemy:    2.1.3
Alembic:       1.20.0
psycopg:       3.3.6
pytest:        8.4.2
HTTPX2:        2.13.1
Ruff:          0.16.10
```

Cập nhật dependency có chủ đích:

```bash
# sửa constraint trong pyproject.toml
uv lock
uv sync --frozen --all-extras
```

Không sửa `uv.lock` thủ công.

## 7. Docker Compose design

### Development stack

- `postgres`: PostgreSQL 16, named volume `postgres-data`, health check bằng `pg_isready`, host
  port mặc định 5432.
- `migrate`: cùng image application, chờ PostgreSQL healthy rồi chạy `python -m alembic upgrade
  head`.
- `api`: chỉ bắt đầu sau khi `migrate` exit 0; `DB_AUTO_CREATE=false`; health check HTTP ở image.
- Local credential có thể override qua `.env`; không có production secret trong Compose.

### Destructive test database

- `postgres-test` nằm trong Compose profile `test`.
- Database `eventhub_test_disposable`, host port 5433.
- Dùng `tmpfs`, không dùng volume phát triển và mất dữ liệu khi container dừng.
- `run-tests.ps1 -WithDb` / `run-tests.sh --with-db` chỉ trỏ fixture `drop_all()` vào service này.
- `REQUIRE_POSTGRES_TESTS=1` làm collection fail nếu CI quên cung cấp PostgreSQL URL thay vì âm
  thầm skip.

Cleanup development volume là thao tác có chủ đích:

```bash
docker compose down             # giữ postgres-data
docker compose down -v          # xoá volume phát triển
docker compose --profile test down
```

`docker compose config/build/up` chưa chạy local vì thiếu Docker CLI.

## 8. CI workflow design

`.github/workflows/ci.yml` có quyền tối thiểu `contents: read`, timeout 20 phút và hủy run cũ cùng
branch. Job dùng Python 3.11, uv 0.12.13 và PostgreSQL 16 service với database
`eventhub_ci_disposable`.

Pipeline được cấu hình để:

1. `uv sync --frozen --extra dev`.
2. Chạy `postgres-test` preflight.
3. Ruff format/lint.
4. `docker compose config --quiet`.
5. Alembic migrate database rỗng tới head.
6. Kiểm tra đủ 10 check constraints bằng `scripts/verify_postgres_schema.py`.
7. Chạy riêng 19 architecture tests.
8. Chạy full pytest với PostgreSQL, JUnit, coverage XML và threshold 95%.
9. Bắt concurrency suite phải chạy bằng `REQUIRE_POSTGRES_TESTS=1`.
10. Build/start Compose trên database container riêng, rồi chạy HTTP smoke.
11. Upload JUnit, coverage và Compose log; cleanup volume/container kể cả khi fail.

Tại thời điểm báo cáo readiness được tạo, workflow **chưa được thực thi** vì thay đổi chưa được
commit/push. YAML và command đã được đọc/static review; trạng thái run sau handoff phải được kiểm
tra trên GitHub Actions. Compose semantics chỉ được xác nhận khi CI hoặc host có Docker chạy
workflow.

## 9. Exact commands executed

Audit host:

```powershell
python --version
uv --version
git --version
docker --version
docker compose version
psql --version
pg_isready --version
Test-NetConnection 127.0.0.1 -Port 5432
wsl --status
wsl --list --verbose
```

Dependencies và quality:

```powershell
uv lock
uv lock --check
uv sync --frozen --extra dev
uv sync --frozen --all-extras
uv run --frozen ruff check app tests alembic scripts
uv run --frozen ruff format --check app tests alembic scripts
uv run --isolated --no-project --no-env-file --with ".[dev]" --with "mypy==1.18.2" mypy app
```

Preflight, test và migration:

```powershell
.\scripts\preflight.ps1 -Mode api-only
bash scripts/preflight.sh api-only
uv run --frozen python -m pytest -W default -ra
python -m pytest -p no:cacheprovider --basetemp .pytest-final-tmp -W error -ra `
  --cov=app --cov-report=term-missing --cov-report=xml --cov-fail-under=95
uv run --frozen pytest tests/unit/test_architecture.py -ra
uv run --frozen python -m pytest -ra --cov=app --cov-report=term-missing `
  --cov-report=xml --cov-fail-under=95
uv run --frozen python -m alembic heads
uv run --frozen python -m alembic history
uv run --frozen python -m alembic upgrade head --sql
```

HTTP smoke local dùng Uvicorn thật, SQLite file tạm, `DB_AUTO_CREATE=true`, port 8766:

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8766
uv run --frozen python scripts/smoke_api.py --base-url http://127.0.0.1:8766
```

Hai lần chạy `-W error` trong sandbox bị dừng bởi `PermissionError` khi pytest truy cập cache/tmp
do chính nó tạo. Cùng lệnh chạy ngoài filesystem sandbox với cacheprovider tắt đã pass. Đây là lỗi
quyền của harness audit, không phải assertion failure. File database, pytest tmp, coverage và uv
cache tạm đã được xóa sau kiểm tra; Uvicorn đã shutdown sạch.

## 10. Exact results

```text
Ruff lint:         All checks passed
Ruff format:       59 files already formatted (migration lịch sử được exclude có chủ đích)
Full pytest:       164 collected, 159 passed, 5 skipped, 0 failed, 0 deselected, 3.13 s
Warnings:          0 khi chạy với -W default
Architecture:      19 passed in 0.06 s
Coverage:          1011 statements, 26 missing, 97.43% (threshold 95% passed)
Alembic head:      c4d2f3a1b890
Alembic offline:   PostgreSQL transactional DDL generated successfully
PowerShell check:  api-only 0 FAIL/3 WARN; development 2 FAIL/3 WARN
PS syntax parse:   PASS
YAML parse/assert: Compose PASS; GitHub Actions PASS (static only)
HTTP smoke:        PASS
```

Smoke xác nhận health, register/login, create/publish event, create/cancel booking và OpenAPI.

Mypy audit: **34 errors in 5 files**; không cấu hình Mypy và không suppress lỗi. Đây là debt được
defer có chủ đích.

## 11. PostgreSQL migration result

Local online migration: **BLOCKED / not executed**. Không có Docker/PostgreSQL và port 5432 đóng.

Offline PostgreSQL SQL generation: **PASS**. Chain:

```text
<base> -> a9ddd8888f24 -> c4d2f3a1b890 (head)
```

Generated SQL chứa 3 table, indexes và đủ 10 check constraints. CI đã được cấu hình chạy online
migration từ database rỗng và inspector xác nhận constraint, nhưng run CI chưa tồn tại.

## 12. Concurrency-test result

Local: **5 skipped**, đúng vì `TEST_DATABASE_URL` không có. Không có bằng chứng PostgreSQL mới trong
task này.

CI/repository safety:

- Database test có tên và service riêng, không persistent.
- Nếu `REQUIRE_POSTGRES_TESTS=1` mà URL thiếu/không phải PostgreSQL, collection fail.
- Năm scenario bao gồm last-ticket, overselling, multi-ticket, multi-booking cancellation và cùng
  một booking bị hủy 20 lần nhưng chỉ hoàn inventory một lần.

Full verification chỉ đạt khi CI hoặc local trả về năm test concurrency pass, không skip.

## 13. Remaining blockers

- Cài/bật Docker Desktop + Compose v2 và xác nhận daemon connectivity.
- Khắc phục WSL `Access is denied`; chưa biết distro/virtualization/integration hiện tại.
- Chạy Compose config/build/up thật.
- Chạy Alembic online từ PostgreSQL rỗng và schema verifier.
- Chạy năm concurrency tests thật.
- Chạy containerized API smoke.
- Push branch để GitHub Actions chạy; workflow hiện chỉ configured, chưa executed.
- Mypy cần một slice riêng để sửa type contract thay vì suppress.

## 14. Host setup: Windows + WSL2

### Windows với Docker Desktop

1. Trong PowerShell Administrator, kiểm tra/bật WSL2 theo chính sách máy:

   ```powershell
   wsl --install
   wsl --update
   wsl --set-default-version 2
   ```

   Reboot nếu Windows yêu cầu. Nếu `Access is denied` tiếp diễn, kiểm tra quyền chạy WSL, Windows
   Subsystem for Linux/Virtual Machine Platform và virtualization trong BIOS/UEFI với quản trị viên
   máy; không tự thay đổi các mục này trong task.

2. Cài Docker Desktop chính thức, chọn WSL2 backend và bật integration cho distro cần dùng.
3. Mở terminal mới và xác nhận:

   ```powershell
   wsl --status
   docker version
   docker compose version
   docker info
   ```

4. Trong repository:

   ```powershell
   uv sync --frozen --extra dev
   Copy-Item .env.example .env
   docker compose up -d postgres
   .\scripts\preflight.ps1 -Mode development
   uv run alembic upgrade head
   ```

5. Verification destructive riêng:

   ```powershell
   .\scripts\run-tests.ps1 -WithDb
   ```

### Trong WSL2

Nên clone repository vào filesystem Linux của distro để tránh I/O và permission edge cases trên
mount Windows. Cài Python 3.11+ và uv theo hướng dẫn chính thức, sau đó:

```bash
uv sync --frozen --extra dev
cp .env.example .env
docker compose up -d postgres
bash scripts/preflight.sh development
uv run alembic upgrade head
bash scripts/run-tests.sh --with-db
```

Không đặt `TEST_DATABASE_URL` tới database phát triển, staging hoặc production. Fixture
concurrency gọi `drop_all()`.

## 15. Recommended next development slice

1. Hoàn tất host setup hoặc push branch để CI chạy.
2. Yêu cầu `docker compose config` và build pass.
3. Yêu cầu migration online + 10 constraint checks pass trên database rỗng.
4. Yêu cầu full suite không skip concurrency và coverage ≥95%.
5. Yêu cầu container smoke pass và lưu artifacts.
6. Chỉ sau đó mới tạo baseline/tag hạ tầng và bắt đầu frontend hoặc một slice product riêng.

Không bắt đầu async, cache, benchmark tuning hoặc đổi locking strategy trước bằng chứng PostgreSQL
trên.

## 16. Git status and changed files

Báo cáo này được tạo trước commit bàn giao; commit/push chỉ được thực hiện sau đó khi người dùng yêu
cầu rõ ràng và kết quả cuối phải đối chiếu bằng Git history. Nhóm thay đổi:

- Dependency/quality: `pyproject.toml`, `uv.lock`.
- Preflight/verification: `scripts/preflight.*`, `scripts/verify_postgres_schema.py`,
  `scripts/smoke_api.py`, `tests/unit/test_preflight.py`.
- Docker: `Dockerfile`, `.dockerignore`, `docker-compose.yml`, `.env.example`, run scripts.
- CI: `.github/workflows/ci.yml`.
- Warning/quality cleanup: test JWT key, import/format changes hữu hạn.
- Repository hygiene: `.gitignore` cho cache/artifact sinh cục bộ.
- Docs: `README.md`, `docs/testing.md`, ghi chú snapshot trong `docs/stabilization-report.md` và
  report này.

`git status --short` chính xác tại bàn giao nằm trong final response; chạy lại trước khi commit vì
status có thể thay đổi trong quá trình review.
