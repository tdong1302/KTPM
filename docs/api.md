# Đặc tả API

Base URL mặc định: `http://localhost:8000`
Swagger UI: `/docs` · ReDoc: `/redoc` · OpenAPI JSON: `/openapi.json`

Mọi request/response đều dùng JSON.

## Xác thực

Gọi `POST /api/auth/login` để lấy `access_token`, rồi gửi kèm mọi request được bảo vệ:

```
Authorization: Bearer <access_token>
```

Trong Swagger UI, bấm **Authorize** rồi dán token.

## Hình dạng lỗi

Mọi lỗi đều trả về cùng cấu trúc:

```json
{ "code": "CONFLICT", "message": "not enough tickets available" }
```

| HTTP | `code` | Khi nào |
|---|---|---|
| 400 | `VALIDATION_ERROR` | Vi phạm quy tắc nghiệp vụ (ví dụ thời gian bắt đầu ở quá khứ) |
| 401 | `UNAUTHENTICATED` | Route được bảo vệ nhưng không có token |
| 401 | `TOKEN_INVALID` / `TOKEN_EXPIRED` | Token sai chữ ký hoặc hết hạn |
| 401 | `INVALID_CREDENTIALS` | Sai email hoặc mật khẩu |
| 403 | `FORBIDDEN` | Đã đăng nhập nhưng không đủ quyền |
| 404 | `NOT_FOUND` | Không tồn tại, hoặc bị ẩn với người gọi |
| 409 | `CONFLICT` | Xung đột trạng thái (hết vé, đã huỷ, chuyển trạng thái không hợp lệ) |
| 422 | `REQUEST_VALIDATION_ERROR` | Payload sai kiểu/thiếu trường |

## Phân trang

Endpoint danh sách trả về:

```json
{ "items": [ ... ], "total": 42, "page": 1, "size": 20, "total_pages": 3 }
```

---

## Health

### `GET /health` — công khai

```json
{ "status": "UP", "service": "eventhub-ktpm" }
```

---

## Auth

### `POST /api/auth/register` — công khai → `201`

```json
{
  "email": "alice@example.com",
  "password": "password123",
  "full_name": "Alice Nguyen",
  "role": "USER"
}
```

`role` nhận `USER` hoặc `ORGANIZER`. `ADMIN` không được phép tự đăng ký (trả `422`).
`password` tối thiểu 8 ký tự. Email được chuẩn hoá về chữ thường.

Trả về `UserResponse` (không bao giờ chứa mật khẩu hay hash).

**Lỗi:** `409` email đã tồn tại · `422` payload không hợp lệ

### `POST /api/auth/login` — công khai → `200`

```json
{ "email": "alice@example.com", "password": "password123" }
```

```json
{
  "access_token": "eyJhbGciOi...",
  "token_type": "bearer",
  "expires_in": 86400,
  "user": { "id": 1, "email": "alice@example.com", "full_name": "Alice Nguyen",
            "role": "USER", "created_at": "2026-09-20T10:00:00Z" }
}
```

**Lỗi:** `401 INVALID_CREDENTIALS` — cố ý trả cùng một lỗi cho email không tồn tại và mật khẩu sai,
để không lộ danh sách email đã đăng ký.

### `GET /api/auth/me` — 🔒 **cần xác thực** → `200`

Trả về `UserResponse` của tài khoản đang đăng nhập.

---

## Events

### `GET /api/events` — công khai → `200`

Chỉ trả về sự kiện **đã phát hành và chưa kết thúc**.

| Query param | Mặc định | Ghi chú |
|---|---|---|
| `q` | – | Tìm trong tiêu đề và mô tả |
| `city` | – | Khớp chính xác, không phân biệt hoa thường |
| `category` | – | Khớp chính xác, không phân biệt hoa thường |
| `page` | `1` | ≥ 1 |
| `size` | `20` | 1–100 |
| `sort_by` | `start_time` | `start_time` \| `price` \| `created_at` |
| `sort_dir` | `asc` | `asc` \| `desc` |

`sort_by` ngoài danh sách cho phép sẽ bị từ chối ở `422` — tên cột không bao giờ đi thẳng xuống
tầng dữ liệu.

### `GET /api/events/mine` — 🔒 **ORGANIZER** → `200`

Trả về toàn bộ sự kiện thuộc tài khoản organizer trong token, gồm `DRAFT`, `PUBLISHED`,
`CANCELLED` và `COMPLETED`. Organizer ID luôn được lấy từ JWT đã xác thực; endpoint không nhận owner
ID từ client.

| Query param | Mặc định | Ghi chú |
|---|---|---|
| `page` | `1` | ≥ 1 |
| `size` | `20` | 1–100 |
| `status` | – | Tuỳ chọn: `DRAFT` \| `PUBLISHED` \| `CANCELLED` \| `COMPLETED` |

Kết quả dùng envelope phân trang chuẩn và được sắp xếp theo `created_at` mới nhất trước, với ID làm
điểm phân định ổn định. `ADMIN` giữ chính sách tổ chức hiện có nhưng cũng chỉ nhận sự kiện mang ID
của chính tài khoản admin; `USER` trả `403`, không có token trả `401`.

### `GET /api/events/{id}` — công khai → `200`

Sự kiện `DRAFT` hoặc `CANCELLED` chỉ hiển thị với chủ sở hữu và `ADMIN`; với người khác trả `404`
(chứ không phải `403`) để không tiết lộ sự tồn tại của nó.

### `POST /api/events` — 🔒 **cần xác thực**, ORGANIZER/ADMIN → `201`

```json
{
  "title": "Rock Night",
  "description": "An evening of live rock music",
  "category": "music",
  "city": "Hanoi",
  "location": "Main Hall",
  "start_time": "2026-12-01T19:00:00Z",
  "end_time": "2026-12-01T22:00:00Z",
  "total_tickets": 100,
  "price": "49.99"
}
```

Sự kiện luôn được tạo ở trạng thái `DRAFT` với `available_tickets = total_tickets`.

**Lỗi:** `403` vai trò `USER` · `400` `start_time` trong quá khứ hoặc `start_time >= end_time` ·
`422` `total_tickets <= 0`, giá âm, trường bắt buộc rỗng

### `PATCH /api/events/{id}` — 🔒 chủ sở hữu/ADMIN, chỉ `DRAFT` → `200`

Cập nhật một phần sự kiện. Chỉ gửi những trường cần đổi:

```json
{
  "title": "Rock Night — Main Stage",
  "location": "Grand Hall",
  "total_tickets": 150
}
```

Các trường được phép: `title`, `description`, `category`, `city`, `location`, `start_time`,
`end_time`, `total_tickets`, `price`. Payload rỗng, giá trị `null`, trường lạ và trường do server
quản lý (`id`, `organizer_id`, `status`, `available_tickets`, timestamps) đều bị từ chối ở `422`.
Giá trị bỏ qua được giữ nguyên. Chuỗi được trim và toàn bộ invariant hiện có vẫn được kiểm tra:
tiêu đề/danh mục/thành phố/địa điểm không rỗng, giá không âm, sức chứa dương, thời gian bắt đầu ở
tương lai và trước thời gian kết thúc.

Endpoint lấy actor từ JWT và khoá dòng sự kiện trước khi kiểm tra owner/trạng thái rồi cập nhật trong
cùng transaction. `ADMIN` giữ owner-bypass đã dùng bởi các mutation khác nhưng không thay đổi
`organizer_id`. Vì API không cho đặt vé khi event còn `DRAFT`, đổi `total_tickets` đặt lại
`available_tickets` bằng sức chứa mới; một draft bất thường đã có vé giữ chỗ sẽ bị từ chối.

**Lỗi:** `403` vai trò không được tổ chức hoặc organizer khác · `404` không tồn tại · `409` không
còn là `DRAFT` hoặc draft có reservation bất thường · `400` vi phạm invariant kết hợp · `422`
payload không hợp lệ

### `PATCH /api/events/{id}/publish` — 🔒 chủ sở hữu/ADMIN → `200`

`DRAFT → PUBLISHED`. Kiểm tra bổ sung khi phát hành: mô tả không rỗng, `start_time` ở tương lai.

**Lỗi:** `403` không phải chủ sở hữu · `409` trạng thái hiện tại không cho phép chuyển ·
`400` chưa đủ điều kiện phát hành

### `PATCH /api/events/{id}/cancel` — 🔒 chủ sở hữu/ADMIN → `200`

`DRAFT → CANCELLED` hoặc `PUBLISHED → CANCELLED`. `CANCELLED` và `COMPLETED` là trạng thái kết thúc.
Baseline hiện chưa có endpoint hoặc background job chuyển một sự kiện sang `COMPLETED`; sự kiện đã
qua `end_time` chỉ bị loại khỏi danh mục công khai và vẫn giữ status đã lưu.

### `DELETE /api/events/{id}` — 🔒 chủ sở hữu/ADMIN → `204`

Chỉ xoá được sự kiện `DRAFT` và **chưa có vé nào được giữ**.

**Lỗi:** `409` sự kiện đã phát hành hoặc đã có đặt chỗ · `403` không phải chủ sở hữu

---

## Bookings

Mọi endpoint dưới đây đều 🔒 **cần xác thực**.

### `POST /api/bookings` → `201`

```json
{ "event_id": 1, "quantity": 2 }
```

```json
{
  "id": 7, "user_id": 3, "event_id": 1,
  "event_title": "Rock Night", "event_start_time": "2026-12-01T19:00:00Z",
  "quantity": 2, "unit_price": "49.99", "total_price": "99.98",
  "status": "CONFIRMED", "created_at": "2026-09-20T10:05:00Z", "cancelled_at": null
}
```

Tối đa 10 vé mỗi lần đặt. Thao tác này đọc dòng sự kiện dưới khoá ghi rồi trừ tồn kho trong cùng
một transaction, nên không thể bán vượt số vé.

**Lỗi:** `404` sự kiện không tồn tại hoặc còn là `DRAFT` · `409` hết vé, sự kiện đã huỷ, hoặc đã
bắt đầu · `422` số lượng ≤ 0 hoặc > 10

### `GET /api/bookings/me` → `200`

Danh sách vé của chính người gọi, mới nhất trước. Nhận `page`, `size`.

### `GET /api/bookings/{id}` → `200`

Chủ booking hoặc `ADMIN` có thể đọc. Không có endpoint để `ADMIN` liệt kê toàn bộ booking.

**Lỗi:** `403` vé của người khác đối với caller không phải `ADMIN` · `404` không tồn tại

### `DELETE /api/bookings/{id}` → `200`

Huỷ vé và **hoàn lại tồn kho** cho sự kiện. Trả về booking đã cập nhật với
`status = "CANCELLED"`.

Đây là huỷ theo nghiệp vụ, không xoá dòng dữ liệu — lịch sử đặt vé được giữ lại.

Chủ booking hoặc `ADMIN` có thể huỷ. Booking được khoá lại trong cùng transaction trước khi hoàn vé
để hai request đồng thời không thể hoàn tồn kho hai lần.

**Lỗi:** `403` vé của người khác đối với caller không phải `ADMIN` · `409` đã huỷ rồi, hoặc sự kiện
đã bắt đầu · `404` không tồn tại
