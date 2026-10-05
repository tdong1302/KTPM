# Mô tả hệ thống

EventHub-KTPM là dịch vụ backend REST API cho nghiệp vụ đặt vé sự kiện, viết bằng Python (FastAPI,
SQLAlchemy 2.0, PostgreSQL 16), phân tầng theo Ports & Adapters: `api` (router, DTO, middleware xác
thực) → `application` (nghiệp vụ, giao tiếp qua Protocol) → `infrastructure` (truy xuất dữ liệu,
JWT, bcrypt). Tầng `domain`/`application` không phụ thuộc framework web hay ORM; ràng buộc này được
kiểm chứng tự động bằng test quét AST.

Ba vai trò: **User** đăng ký/đăng nhập JWT, tra cứu sự kiện đã phát hành (tìm kiếm, lọc, phân
trang), đặt/xem/huỷ vé của mình. **Organizer** tạo, phát hành, huỷ sự kiện, xoá sự kiện nháp.
**Admin** quản lý toàn bộ sự kiện và có thể đọc/huỷ booking bất kỳ khi biết ID; baseline chưa có
API liệt kê booking của mọi user. Domain khai báo vòng đời
`DRAFT → PUBLISHED → CANCELLED/COMPLETED`, nhưng hiện chưa có use case chuyển sang `COMPLETED`.

Bất biến quan trọng nhất là số vé còn lại (`available_tickets`): trừ khi đặt vé, hoàn khi huỷ vé.
Thao tác đặt/huỷ khoá dòng sự kiện bằng `SELECT ... FOR UPDATE` trong cùng transaction, đảm bảo
không bán vượt số vé khi nhiều người đặt đồng thời — đã kiểm chứng bằng test tranh chấp ghi thật
trên PostgreSQL.

Xác thực JWT và kiểm tra route công khai/riêng tư nằm tập trung ở một middleware duy nhất, chạy
trước mọi handler; không endpoint nào lặp lại logic xác thực. Hệ thống đóng gói bằng Docker Compose,
có OpenAPI/Swagger, kèm test unit/kiến trúc/integration/concurrency và hạ tầng load test Locust. Đây
là baseline (Pha 1), giữ chủ ý nhỏ và đo được, làm đối tượng nghiên cứu cho cải tiến chất lượng ở
Pha 2.
