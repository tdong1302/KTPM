# Tổng kết mục tiêu và định hướng phát triển EventHub

> **Mục đích:** Chốt phạm vi và hướng phát triển tiếp theo sau baseline Pha 1. Tài liệu này phân
> biệt rõ phần **đã có**, phần **đã hoàn thành thiết kế** và phần **sẽ triển khai**, tránh trình bày
> kế hoạch tương lai như chức năng đã tồn tại.

## 1. Mục tiêu chung của dự án

EventHub hướng tới một hệ thống đặt vé sự kiện có khả năng:

- Quản lý người dùng, nhà tổ chức và vòng đời sự kiện.
- Cho phép tìm kiếm sự kiện và đặt vé qua giao diện web/API.
- Không bán vượt số vé khi nhiều người đặt đồng thời.
- Hỗ trợ giữ chỗ có thời hạn, thanh toán và phát hành vé.
- Hoạt động ổn định trước request lặp, bot hoặc lỗi từ dịch vụ bên ngoài.
- Có số liệu kiểm thử và benchmark để chứng minh cải tiến thay vì tối ưu theo phỏng đoán.

Mục tiêu gần nhất không phải xây một hệ thống quy mô toàn cầu hoặc chuyển sang microservices. Mục
tiêu là phát triển baseline hiện tại thành một **modular monolith đúng đắn, đo được và dễ mở rộng**.

## 2. Trạng thái hiện tại

### Đã triển khai trong Pha 1

- Kiến trúc Ports & Adapters với chiều phụ thuộc hướng vào application/domain.
- Repository, Unit of Work, Data Mapper và Dependency Injection.
- JWT authentication, RBAC với các vai trò `USER`, `ORGANIZER`, `ADMIN`.
- Quản lý và tra cứu sự kiện; dashboard nhà tổ chức; frontend MVP tại `/app/`.
- Đặt và hủy vé trong một transaction.
- Chống overselling bằng PostgreSQL row lock và constraint ở database.
- State machine cho vòng đời sự kiện.
- Worker tự động chuyển sự kiện đã kết thúc sang `COMPLETED`.
- Alembic migration, Docker Compose, CI và các lớp test unit/integration/concurrency.
- Baseline benchmark S2/S3; quality gate được ghi nhận 257 test và coverage 97,56%.

### Đã hoàn thành ở mức phân tích và thiết kế

- Đánh giá khoảng cách giữa baseline và hệ thống ticketing hoàn chỉnh.
- Chọn modular monolith làm hướng phát triển, chưa tách microservices.
- Thiết kế kiến trúc mục tiêu Pha 2 và các luồng reservation/payment/expiry.
- Chọn ba hướng bổ sung chính: **Rate Limiting, Circuit Breaker và CQRS-lite**.
- Xác định PostgreSQL tiếp tục là nguồn dữ liệu chuẩn; Redis chỉ là adapter tùy chọn.
- Xây dựng lộ trình triển khai theo vertical slice và tiêu chí kiểm chứng cho từng giai đoạn.

Chi tiết kiến trúc: [phase2-target-architecture.md](phase2-target-architecture.md).

## 3. Nguyên tắc kiến trúc được chốt

### 3.1. Giữ modular monolith

Kiến trúc Pha 1 không cần viết lại. Các module mới vẫn chạy trong cùng hệ thống nhưng được phân chia
trách nhiệm rõ ràng:

```text
API / Middleware
├── Command services: Event, Reservation, Payment, Ticket
├── Query services: Catalogue, Booking history, Organizer dashboard
├── Domain: trạng thái và bất biến nghiệp vụ
└── Ports
    ├── Repositories / Unit of Work
    ├── RateLimiter
    └── PaymentGateway
```

Lựa chọn này giữ được transaction giữa tồn kho và booking, giảm lỗi mạng và chi phí vận hành. Chỉ
xem xét microservices khi có nhu cầu triển khai độc lập, nhiều nhóm phát triển hoặc benchmark chứng
minh một module cần scale độc lập.

### 3.2. PostgreSQL là nguồn dữ liệu chuẩn

- Quyết định bán vé phải được xác nhận trong transaction PostgreSQL.
- Cache hoặc Redis không được quyết định số vé cuối cùng.
- Tồn kho, reservation và order phải cập nhật đồng bộ hoặc rollback cùng nhau.
- Mọi thay đổi cơ chế khóa phải chạy lại PostgreSQL concurrency test.

### 3.3. Đo trước khi tối ưu

Mọi tuyên bố cải thiện phải có số liệu BEFORE/AFTER trên cùng cấu hình, dữ liệu và kịch bản. Không
thêm Redis, async I/O hoặc tăng connection pool chỉ vì đó là công nghệ phổ biến.

## 4. Ba hướng thiết kế bổ sung chính

### 4.1. Rate Limiting

**Mục tiêu:** bảo vệ điểm vào của hệ thống khỏi brute-force, bot và request đột biến.

Phạm vi đề xuất:

| Luồng | Khóa giới hạn |
|---|---|
| Đăng nhập/đăng ký | IP kết hợp email |
| Tạo booking/reservation | User ID kết hợp Event ID |
| Khởi tạo payment | User ID kết hợp Order ID |
| Tìm kiếm sự kiện | IP hoặc API client |

Thiết kế đặt `RateLimiter` sau reverse proxy và trước application service. Một API worker có thể
dùng in-memory adapter; nhiều worker sử dụng Redis adapter. Khi vượt ngưỡng, API trả `429` cùng
`Retry-After`.

Rate Limiting chỉ kiểm soát lưu lượng, không thay thế transaction hoặc row lock chống overselling.

### 4.2. Circuit Breaker

**Mục tiêu:** ngăn lỗi hoặc timeout của dịch vụ bên ngoài lan sang toàn bộ EventHub.

Circuit Breaker được đặt trong outbound adapter, trước hết là payment provider:

```text
PaymentService → PaymentGateway port → Circuit Breaker → VNPay/MoMo/Stripe
```

Ba trạng thái vận hành:

- `CLOSED`: gọi dịch vụ bình thường và theo dõi lỗi.
- `OPEN`: tạm dừng gọi, trả lỗi nhanh để không giữ thread/connection.
- `HALF_OPEN`: gửi một số request thử trước khi khôi phục hoàn toàn.

Circuit Breaker chỉ có ý nghĩa khi đã tích hợp dịch vụ mạng bên ngoài. Không áp dụng máy móc cho
các lời gọi nội bộ hoặc dùng nó để che lỗi lập trình.

### 4.3. CQRS-lite

**Mục tiêu:** tách code thay đổi trạng thái khỏi code truy vấn phục vụ giao diện.

```text
Command side                         Query side
-------------                        ----------
CreateReservation                    EventCatalogueQuery
CancelReservation                    BookingHistoryQuery
ConfirmPayment                       OrganizerDashboardQuery
IssueTicket                          EventDetailQuery
       │                                     │
Domain + Unit of Work                Read DTO / projection
       └──────────── PostgreSQL ──────────────┘
```

Command side tiếp tục dùng domain, Repository và Unit of Work để bảo vệ bất biến. Query side trả DTO
phù hợp với frontend, có thể tối ưu join, keyset pagination hoặc cache mà không làm command service
phức tạp.

Pha 2 chỉ áp dụng CQRS-lite với cùng PostgreSQL. Không triển khai Event Sourcing, message broker hay
read database riêng khi chưa có nhu cầu đo được.

## 5. Các chức năng cần bổ sung

### 5.1. Reservation có thời hạn

Chuyển từ mô hình “đặt là xác nhận ngay” sang:

```text
AVAILABLE → RESERVED → CONFIRMED
                   ├→ EXPIRED
                   └→ CANCELLED
```

Cần có `expires_at`, worker thu hồi reservation hết hạn và quy tắc bảo đảm mỗi reservation chỉ hoàn
tồn kho một lần. Worker này độc lập với event-completion worker hiện có.

### 5.2. Order và thanh toán

- Tạo order từ reservation còn hiệu lực.
- Tích hợp payment provider qua `PaymentGateway` port.
- Xác minh chữ ký webhook.
- Dùng idempotency key để tránh tạo hoặc xác nhận payment lặp.
- Ghi lịch sử mọi lần thử thanh toán/hoàn tiền để đối soát.
- Xử lý late payment: không cấp trùng vé; ghi nhận và đưa vào quy trình refund.

### 5.3. Hai dạng vé

- Vé khu vực/GA: quản lý bằng quota tổng.
- Vé ghế chỉ định: quản lý theo từng mã ghế.
- Giữ nguyên một quy trình reservation chung nhưng dùng cơ chế phân bổ phù hợp với từng loại.

### 5.4. Vé điện tử

- Chỉ phát hành sau khi payment được xác nhận.
- Mỗi vé có mã định danh hoặc QR token không đoán được.
- Có trạng thái hợp lệ, đã sử dụng, bị hủy hoặc được hoàn tiền.
- Không lưu dữ liệu thẻ thanh toán trong EventHub.

## 6. Những điểm cần tối ưu và cách xác nhận

| Hạng mục | Hiện trạng/giả thuyết | Hành động trước khi tối ưu |
|---|---|---|
| Điểm bão hòa | Chưa có S4 | Chạy S4 với nhiều mức user |
| Đường đọc | Có dấu hiệu chờ pool/thread | Chạy S1, đo CPU/RSS và pool wait |
| Row lock booking | Đúng nhưng tuần tự khi tranh chấp | Đo lại S3 nhiều lần trước khi đổi |
| Connection pool | Có thể nhỏ dưới tải cao | Đo thời gian chờ connection |
| Threadpool/sync I/O | Có thể là nút thắt | Chỉ cân nhắc async sau khi có metrics |
| Truy vấn trang sâu | `OFFSET` suy giảm theo dữ liệu | `EXPLAIN ANALYZE`, sau đó cân nhắc keyset |
| Danh mục sự kiện | Có thể cache | Chỉ cache đường đọc, định nghĩa TTL/staleness |
| Bcrypt | Chậm có chủ ý | Không giảm rounds chỉ để làm benchmark đẹp |
| Dồn tải đầu benchmark | Làm nhiễu percentile | Reset stats sau warm-up |

Các việc cần hoàn thiện cho bộ đo:

1. Chạy S1 và S4.
2. Thêm CPU/RSS sampler.
3. Tách kết quả booking `201` và sold-out `409`.
4. Reset thống kê sau warm-up.
5. Chạy lặp 2–3 lần để xác định độ dao động.

## 7. Quan sát và vận hành

Pha 2 cần bổ sung khả năng quan sát song song với chức năng mới:

- Correlation ID xuyên suốt API, worker và payment callback.
- Structured logging không chứa password, JWT, secret hoặc dữ liệu thẻ.
- Readiness check cho PostgreSQL và dependency bên ngoài.
- Metrics tối thiểu: request rate, p95/p99, `429`, booking conflict, active reservation, expiry lag,
  payment timeout, trạng thái Circuit Breaker và connection-pool wait.
- Cảnh báo khi reservation hết hạn không được xử lý hoặc payment provider lỗi kéo dài.

## 8. Lộ trình ưu tiên

| Thứ tự | Giai đoạn | Kết quả chính |
|---:|---|---|
| 1 | Hoàn thiện baseline | S1/S4 và metrics tài nguyên đáng tin cậy |
| 2 | Reservation | Giữ chỗ có hạn và hoàn kho đúng một lần |
| 3 | Rate Limiting | Bảo vệ auth và booking khỏi spam/bot |
| 4 | CQRS-lite | Tách command/query, tối ưu catalogue/dashboard |
| 5 | Payment | Payment port, webhook, idempotency và transaction history |
| 6 | Circuit Breaker | Cô lập lỗi payment provider |
| 7 | Ticket expansion | Vé GA, ghế chỉ định và vé điện tử |
| 8 | Tối ưu theo số đo | Cache, Redis, async hoặc virtual queue nếu thật sự cần |

Mỗi giai đoạn phải có unit test, integration test và concurrency test tương ứng; không triển khai
toàn bộ lộ trình trong một lần thay đổi.

## 9. Tiêu chí hoàn thành Pha 2

Pha 2 được xem là đạt mục tiêu khi:

- Không oversell dưới tải đồng thời.
- Reservation hết hạn được hoàn kho đúng một lần.
- Request hoặc webhook lặp không tạo booking/payment/ticket lặp.
- Rate Limiting trả `429` đúng policy và không chặn nhầm luồng nội bộ cần thiết.
- Circuit Breaker fail fast khi payment provider lỗi và tự phục hồi qua `HALF_OPEN`.
- Command/query được tách rõ nhưng vẫn giữ transaction cho đường ghi.
- Test coverage không thấp hơn quality gate đã thống nhất.
- Có báo cáo benchmark BEFORE/AFTER và giải thích được nguyên nhân thay đổi.
- Tài liệu API, kiến trúc, migration và hướng dẫn vận hành được cập nhật.

## 10. Những việc chưa ưu tiên

- Chuyển sang microservices.
- Full CQRS với read database riêng.
- Event Sourcing.
- Kafka hoặc service discovery.
- Distributed lock thay PostgreSQL transaction.
- Redis làm nguồn dữ liệu chuẩn của tồn kho.
- Virtual Queue khi chưa có benchmark flash-sale chứng minh nhu cầu.

Các nội dung trên có thể trở thành hướng nghiên cứu sau này, nhưng không thuộc mục tiêu gần nhất.

## 11. Tóm tắt dùng trong báo cáo

> EventHub đã hoàn thành baseline Pha 1 với kiến trúc Ports & Adapters, frontend MVP, JWT/RBAC,
> quản lý sự kiện và cơ chế đặt vé không oversell bằng PostgreSQL transaction. Hướng phát triển được
> chốt cho Pha 2 là tiếp tục dưới dạng modular monolith, bổ sung reservation có thời hạn, thanh toán
> và vé điện tử. Ba cải tiến kiến trúc chính là Rate Limiting để bảo vệ đầu vào, CQRS-lite để tách
> command khỏi query và Circuit Breaker để cô lập lỗi của payment provider. Mọi tối ưu hiệu năng
> chỉ được thực hiện sau khi hoàn thiện benchmark S1/S4 và phải có so sánh BEFORE/AFTER, bảo đảm hệ
> thống mở rộng mà không đánh đổi tính đúng đắn của tồn kho.
