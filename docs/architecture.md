# Kiến trúc baseline

## 1. Ràng buộc dẫn dắt thiết kế

Đề bài Pha 1 yêu cầu:

> Phân tầng rõ: API → Nghiệp vụ → Truy cập dữ liệu. **Tầng nghiệp vụ không import framework web
> hay thư viện DB.**

Đây là ràng buộc khó nhất. Cách viết thông thường với FastAPI (hoặc Spring) sẽ để `Session`,
`Depends`, kiểu phân trang của thư viện ORM, hay `HTTPException` rò rỉ thẳng vào tầng service — lúc
đó tầng nghiệp vụ không còn kiểm thử được nếu thiếu database và HTTP server, và việc đổi framework
sẽ kéo theo sửa toàn bộ logic nghiệp vụ.

Hệ thống chọn **Ports & Adapters (hexagonal)** để biến ràng buộc đó thành sự thật kiểm chứng được,
chứ không chỉ là quy ước.

## 2. Sơ đồ tầng

```
        HTTP request
             │
             ▼
┌────────────────────────────────────────────────┐
│ app/api                                        │
│  • routers/       Router FastAPI               │
│  • schemas/       DTO Pydantic (request/resp)  │
│  • middleware.py  Xác thực JWT tập trung       │
│  • deps.py        Composition root mỗi request │
│  • exception_handlers.py  DomainError → HTTP   │
└────────────────────────────────────────────────┘
             │ gọi xuống, truyền kiểu thuần (int, str, dataclass)
             ▼
┌────────────────────────────────────────────────┐
│ app/application    ← TẦNG NGHIỆP VỤ            │
│  • auth_service.py / event_service.py /        │
│    booking_service.py                          │
│  • ports.py   Protocol: Repository, UnitOfWork,│
│               PasswordHasher, TokenService,    │
│               Clock                            │
│  KHÔNG import fastapi / sqlalchemy / pydantic  │
└────────────────────────────────────────────────┘
             │ gọi qua Protocol
             ▼
┌────────────────────────────────────────────────┐
│ app/infrastructure                             │
│  • db/orm.py           Bảng SQLAlchemy         │
│  • db/mappers.py       ORM ↔ domain            │
│  • db/repositories.py  Adapter cho các port    │
│  • db/unit_of_work.py  Biên transaction        │
│  • security/           bcrypt, PyJWT           │
└────────────────────────────────────────────────┘
             │
             ▼
        PostgreSQL 16

┌────────────────────────────────────────────────┐
│ app/domain   Dataclass + Enum + invariant      │
│  Được cả application và infrastructure dùng.   │
│  Không phụ thuộc bất kỳ tầng nào khác.         │
└────────────────────────────────────────────────┘
```

Chiều phụ thuộc luôn hướng vào trong: `api → application → domain`, và
`infrastructure → application (ports) → domain`. Tầng nghiệp vụ không biết gì về tầng ngoài.

## 3. Ports & Adapters

[`app/application/ports.py`](../app/application/ports.py) khai báo toàn bộ giao diện ra bên ngoài
bằng `typing.Protocol`:

| Port | Adapter thật | Adapter test |
|---|---|---|
| `UserRepository` | `SqlAlchemyUserRepository` | `FakeUserRepository` |
| `EventRepository` | `SqlAlchemyEventRepository` | `FakeEventRepository` |
| `BookingRepository` | `SqlAlchemyBookingRepository` | `FakeBookingRepository` |
| `UnitOfWork` | `SqlAlchemyUnitOfWork` | `FakeUnitOfWork` |
| `PasswordHasher` | `BcryptPasswordHasher` | `FakeHasher` |
| `TokenService` | `JwtTokenService` | `FakeTokenService` |
| `Clock` | `SystemClock` | `FakeClock` |

Nhờ đó toàn bộ unit test nghiệp vụ chạy không cần database, không cần HTTP server, không cần
bcrypt — cả bộ hoàn thành trong dưới một giây.

### Một số quyết định cụ thể

**Không truyền principal vào tầng nghiệp vụ.** Service nhận `actor_id: int` và
`actor_role: UserRole` (kiểu của domain). Tầng nghiệp vụ không cần biết người dùng được xác thực
bằng JWT, session hay cơ chế nào khác — nhờ vậy đổi cơ chế xác thực không phải đụng vào logic
nghiệp vụ.

**Tự định nghĩa `Page`.** [`app/domain/models.py`](../app/domain/models.py) khai báo một dataclass
`Page[T]` thay vì dùng kiểu phân trang của thư viện persistence.

**Khoá dòng được diễn đạt bằng ý định.** Tầng nghiệp vụ gọi
`EventRepository.get_for_update(event_id)`. Nó nói *"tôi cần tuần tự hoá thao tác này"*; adapter mới
quyết định cơ chế (`SELECT ... FOR UPDATE` trên PostgreSQL, bỏ qua trên SQLite vì SQLite vốn đã
tuần tự hoá mọi writer).

**Quy tắc nghiệp vụ nằm trên aggregate.** `Event.reserve()`, `Event.transition_to()`,
`Booking.cancel()` chứa invariant. Service điều phối và quản lý transaction. Database còn có check
constraint cho các giới hạn dữ liệu cốt lõi; code ngoài application service vẫn không được coi là
đường ghi hợp lệ chỉ vì nó có thể gọi thẳng repository.

### Ràng buộc được kiểm chứng tự động

[`tests/unit/test_architecture.py`](../tests/unit/test_architecture.py) phân tích AST của mọi module
trong `app/domain` và `app/application`, rồi fail build nếu phát hiện:

- import `fastapi`, `starlette`, `sqlalchemy`, `alembic`, `psycopg`, `pydantic`, `jwt`, `bcrypt`,
  `httpx`, `requests`;
- import `app.api` hoặc `app.infrastructure`;
- `app.domain` import `app.application`.

Đây là bằng chứng trực tiếp, có thể chạy lại được, cho tiêu chí chấm điểm về phân tầng.

## 4. Xác thực và phân quyền

| Mối quan tâm | Nơi xử lý | Mã trả về |
|---|---|---|
| Token hợp lệ? Route này có cần đăng nhập không? | `app/api/middleware.py` | 401 |
| Vai trò có được phép thực hiện hành động? | tầng `application` | 403 |
| Người gọi có sở hữu tài nguyên? | tầng `application` | 403 |
| Tài nguyên ẩn với người gọi? | tầng `domain` (`Event.is_visible_to`) | 404 |

`AuthenticationMiddleware` giữ một bảng `PUBLIC_ROUTES` khai báo — tương đương
`SecurityConfig.requestMatchers(...).permitAll()` của Spring. Mặc định là **đóng**: route nào không
nằm trong bảng đều yêu cầu token. Không endpoint nào tự viết lại logic xác thực.

Một chi tiết có chủ ý: token hỏng gửi tới route công khai **không** gây lỗi, người gọi chỉ đơn giản
là ẩn danh; còn gửi tới route được bảo vệ thì trả 401 kèm mã lỗi cụ thể (`TOKEN_EXPIRED` /
`TOKEN_INVALID`). Hành vi này được test trong
[`tests/integration/test_auth_and_middleware.py`](../tests/integration/test_auth_and_middleware.py).

## 5. Quyết định phạm vi

Phạm vi Pha 1 được giữ hẹp một cách có chủ ý. Mỗi chức năng đưa vào đều phải phục vụ một yêu cầu
của đề bài; chức năng nào chỉ làm hệ thống to ra mà không thêm giá trị kiểm chứng thì để lại.

| Ngoài phạm vi | Lý do |
|---|---|
| Thanh toán | Không có cổng thanh toán thật; một module giả lập chỉ thêm mã nguồn mà không thêm nghiệp vụ nào kiểm chứng được |
| Mã QR cho vé | Thêm dependency và làm phình kích thước dòng dữ liệu, gây nhiễu cho số liệu đo |
| Mua bán lại vé | Là một bounded context thứ hai với vòng đời sở hữu riêng; vượt xa yêu cầu Pha 1 |
| Thông báo + message queue | Chỉ ghi thêm vài dòng dữ liệu, nhưng kéo theo cả một hạ tầng hàng đợi |
| Service discovery + API gateway | Chỉ có ý nghĩa với kiến trúc nhiều dịch vụ; Pha 1 là một tiến trình duy nhất |
| Upload ảnh | I/O ra hệ thống ngoài, làm nhiễu số liệu benchmark |
| Xác thực email, quên mật khẩu, refresh token | Vượt phạm vi yêu cầu "hỗ trợ đăng nhập" |
| Giao diện người dùng | Không phục vụ trực tiếp yêu cầu nào của Pha 1 |

Hai nguyên tắc thiết kế được áp dụng xuyên suốt và đáng nêu vì chúng ảnh hưởng tới số liệu đo:

1. **Chỉ khai báo trạng thái thực sự được dùng.** `BookingStatus` chỉ có `CONFIRMED` và `CANCELLED`.
   Trạng thái khai báo nhưng không bao giờ đạt tới chỉ gây hiểu nhầm khi đọc mã nguồn.
2. **Không ghi trên đường đọc.** Không có tác vụ dọn dẹp hay cập nhật trạng thái nào được gọi bên
   trong request đọc. Việc đó thuộc về một job nền, nếu sau này cần.

## 6. Hai quyết định có chủ ý, để dành cho Pha 2

**Đồng bộ (sync), không async.** Toàn bộ tầng dữ liệu dùng SQLAlchemy đồng bộ và endpoint khai báo
bằng `def`, nên FastAPI chạy chúng trong threadpool. Đây là lựa chọn có cân nhắc: baseline đơn giản,
dễ đọc, dễ suy luận — và việc chuyển sang async + `asyncpg` trở thành một cải tiến Pha 2 **đo được**
với số liệu trước/sau rõ ràng.

**Khoá bi quan (pessimistic lock), không phải bug cố ý.** Baseline chọn phương án *đúng đắn*:
`SELECT ... FOR UPDATE`. Nó bảo đảm không bao giờ bán vượt vé, nhưng đồng thời tạo ra một điểm tuần
tự hoá — và đó chính là một đánh đổi giữa *tính đúng đắn* và *thông lượng* rất đáng đo ở Pha 2.

Cả hai điểm này được ghi chi tiết trong [phase2.md](phase2.md).

## 7. Xử lý lỗi

Tầng nghiệp vụ ném `DomainError` mang mã ổn định (`VALIDATION_ERROR`, `NOT_FOUND`, `CONFLICT`,
`FORBIDDEN`, `UNAUTHORIZED`). [`app/api/exception_handlers.py`](../app/api/exception_handlers.py)
ánh xạ chúng sang HTTP một lần cho toàn bộ ứng dụng. Mọi lỗi đều trả về cùng một hình dạng JSON:

```json
{ "code": "CONFLICT", "message": "not enough tickets available" }
```
