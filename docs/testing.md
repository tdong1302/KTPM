# Kiểm thử

## Cách chạy

```bash
uv run --frozen --extra dev pytest                      # toàn bộ
uv run --frozen --extra dev pytest tests/unit           # unit + kiến trúc
uv run --frozen --extra dev pytest tests/integration    # API + SQLite
uv run --frozen --extra dev pytest --cov=app            # kèm coverage
uv run --frozen --extra dev pytest -m concurrency       # cần PostgreSQL
```

Script tiện dụng: `scripts/run-tests.ps1` (Windows) hoặc `scripts/run-tests.sh` (Linux/macOS).

## Bốn tầng kiểm thử

| Tầng | Vị trí | Chạy trên | Kiểm chứng điều gì |
|---|---|---|---|
| Unit | `tests/unit/test_*_service.py` | Fake repo trong bộ nhớ | Quy tắc nghiệp vụ |
| Kiến trúc | `tests/unit/test_architecture.py` | Phân tích AST | Ràng buộc phân tầng của đề bài |
| Integration | `tests/integration/` | TestClient + SQLite | Hợp đồng HTTP, middleware, persistence |
| Concurrency | `tests/concurrency/` | **PostgreSQL thật** | Không bán vượt vé khi tranh chấp |

### Unit test

Dùng các test double trong [`tests/unit/fakes.py`](../tests/unit/fakes.py) để hiện thực các port:
`FakeUnitOfWork`, `FakeEventRepository`, `FakeClock`, `FakeHasher`, `FakeTokenService`. Không có
database, không HTTP server, không bcrypt — nên cả bộ chạy xong trong dưới một giây.

`FakeClock` cho phép test các quy tắc phụ thuộc thời gian (không đặt vé sau khi sự kiện đã bắt đầu)
một cách tất định, không cần `sleep`.

### Test kiến trúc

[`tests/unit/test_architecture.py`](../tests/unit/test_architecture.py) phân tích AST của mọi
module trong `app/domain` và `app/application`, rồi làm fail build nếu có import
`fastapi`, `sqlalchemy`, `pydantic`, `jwt`, `bcrypt`… hoặc import ngược lên `app.api` /
`app.infrastructure`.

Đây là cách biến yêu cầu *"tầng nghiệp vụ không import framework web hay thư viện DB"* từ một quy
ước thành một ràng buộc được máy kiểm tra ở mỗi lần chạy test.

### Integration test

Dựng app FastAPI thật, middleware thật, repository SQLAlchemy thật, JWT và bcrypt thật; chỉ engine
database là SQLite in-memory. Cost factor của bcrypt được hạ xuống 4 trong fixture để bộ test không
bị chi phối bởi thời gian băm mật khẩu.

Điểm đáng chú ý:
[`test_auth_and_middleware.py`](../tests/integration/test_auth_and_middleware.py) duyệt qua **toàn
bộ 9 route được bảo vệ** bằng `parametrize` và khẳng định cả trường hợp không token lẫn token rác
đều bị chặn ở middleware. Nếu ai đó thêm một endpoint mới mà quên bảo vệ, test này sẽ phát hiện.

### Test concurrency

[`tests/concurrency/test_no_overselling.py`](../tests/concurrency/test_no_overselling.py) bắn nhiều
request đặt vé song song bằng `ThreadPoolExecutor` và khẳng định bất biến
`đã_bán + còn_lại == tổng_số_vé`.

Test này **bị SKIP** khi không có biến `TEST_DATABASE_URL` trỏ tới PostgreSQL. Lý do: bảo đảm chống
bán vượt vé đến từ `SELECT ... FOR UPDATE`, mà SQLite vốn tuần tự hoá mọi writer — chạy trên SQLite
sẽ "pass" mà không chứng minh được gì. Skip trung thực hơn là pass giả.

Bật lên:

```bash
docker compose --profile test up -d postgres-test

# Windows PowerShell
$env:TEST_DATABASE_URL="postgresql+psycopg://eventhub_test:eventhub_test@localhost:5433/eventhub_test_disposable"
# Linux/macOS
export TEST_DATABASE_URL="postgresql+psycopg://eventhub_test:eventhub_test@localhost:5433/eventhub_test_disposable"

uv run --frozen --extra dev pytest tests/concurrency -v
```

Năm kịch bản: 20 người tranh 1 vé cuối; 40 người tranh 10 vé; đặt theo lô 3 vé trên 10 vé; huỷ nhiều
booking đồng thời; và 20 request cùng huỷ một booking nhưng chỉ được hoàn tồn kho đúng một lần.

#### Kiểm chứng rằng test này thực sự nhạy

Một test đồng thời "xanh" chưa chứng minh được điều gì — nó có thể xanh vì may mắn về thời điểm,
chứ không phải vì khoá hoạt động. Ngày 2026-09-20 đã chạy một phép thử đối chứng trên PostgreSQL 16
(20 luồng cùng tranh 1 vé cuối):

| Cấu hình | Số người mua được | Kết luận |
|---|---|---|
| `get_for_update` thật (`SELECT ... FOR UPDATE`) | **1** | Không bán vượt |
| Tạm thay `get_for_update` bằng đọc thường | **20** | Bán vượt 20 lần |

Nghĩa là khoá dòng chính là thứ tạo ra tính đúng đắn, và bộ test sẽ phát hiện ngay nếu ai đó gỡ nó
ra. Phép thử đối chứng này chạy ngoài repo (monkeypatch trong một script tạm), không sửa mã nguồn.

## Những gì hiện CHƯA có

- Đã có một lần chạy S2 và một lần chạy S3; S1/S4 và các lần chạy lặp chưa có. Xem
  [benchmark.md](benchmark.md) và [stabilization-report.md](stabilization-report.md).
- Chưa có kiểm thử trên PostgreSQL cho các luồng API thông thường (integration test dùng SQLite).
  Những phần bắt buộc kiểm tra riêng trên PostgreSQL gồm `SELECT ... FOR UPDATE` và Alembic DDL
  thêm check constraint; SQLite integration dùng `create_all()` nên không thay thế được hai kiểm tra này.
- GitHub Actions đã được cấu hình dùng PostgreSQL disposable, migration thật, constraint check,
  concurrency suite bắt buộc, coverage 95%, Ruff và container smoke. Workflow chưa được thực thi
  cho tới khi branch được push; xem [infrastructure-readiness-report.md](infrastructure-readiness-report.md).

> **Cảnh báo:** fixture concurrency gọi `drop_all()` trước và sau suite. Chỉ đặt
> `TEST_DATABASE_URL` tới database PostgreSQL dùng riêng cho test, không trỏ tới database local có
> dữ liệu cần giữ.
