# EventHub frontend MVP

## 1. Mục đích và phạm vi

Frontend MVP là giao diện tiếng Việt dành cho người dùng cuối của EventHub. Mục tiêu là trình diễn
trực quan các luồng REST API đã có: đăng ký, đăng nhập, khám phá sự kiện, tạo/phát hành sự kiện,
đặt vé và hủy vé. Frontend không bổ sung quy tắc nghiệp vụ hoặc endpoint mới.

Giao diện được phục vụ cùng nguồn với FastAPI tại:

```text
http://127.0.0.1:8000/app/
```

Không cần Node.js, npm, CDN hoặc bước build frontend.

## 2. Kiến trúc

```text
frontend/
├── index.html          Semantic HTML và các vùng giao diện
└── assets/
    ├── styles.css      Theme, responsive layout và accessibility states
    ├── api.js          Fetch client, error envelope và Authorization header
    ├── auth.js         Phiên đăng nhập và sessionStorage
    ├── ui.js           DOM helpers, formatter, badge, loading và toast
    └── app.js          Điều phối view và các workflow API
```

Frontend là presentation adapter. Mọi kiểm tra quyền, trạng thái sự kiện, giới hạn vé, tồn kho và
transaction vẫn do backend quyết định.

## 3. FastAPI phục vụ frontend

`app/main.py` mount duy nhất thư mục `frontend` bằng `StaticFiles` tại `/app`. Đường dẫn thư mục được
resolve từ vị trí source, không phụ thuộc thư mục hiện tại của terminal. Middleware cho phép GET và
HEAD dưới `/app`, trong khi chính sách xác thực của `/api/...` không thay đổi.

Static mount không xuất hiện trong OpenAPI; API có 15 operation nghiệp vụ. Không cần CORS vì
HTML, JavaScript và API cùng origin. Docker image copy đúng thư mục `frontend`, không chia sẻ phần
còn lại của repository.

## 4. Khởi động bằng Windows Command Prompt

Mở `cmd.exe`:

```cmd
cd /d E:\University\Semester_7\SA\KTPM
scripts\run-dev.cmd
```

Sau đó mở:

```text
Frontend: http://127.0.0.1:8000/app/
Swagger:  http://127.0.0.1:8000/docs
Health:   http://127.0.0.1:8000/health
```

Nhấn `Ctrl+C` để dừng Uvicorn. Dừng PostgreSQL nhưng giữ volume phát triển bằng:

```cmd
docker compose down
```

## 5. Workflow USER

1. Đăng ký với vai trò **Người tham dự** hoặc đăng nhập.
2. Tìm sự kiện theo từ khóa, thành phố, danh mục; chọn cách sắp xếp và chuyển trang.
3. Mở chi tiết sự kiện `PUBLISHED`, nhập số lượng 1–10 và đặt vé.
4. Quan sát số vé còn lại được làm mới từ API.
5. Mở **Vé của tôi**, xem chi tiết giá, số lượng, thời gian và trạng thái.
6. Hủy booking `CONFIRMED`; danh sách và tồn kho sự kiện được tải lại.

Frontend dùng validation HTML để phản hồi sớm, nhưng kết quả backend luôn là quyết định cuối cùng.

## 6. Workflow ORGANIZER

1. Đăng ký với vai trò **Nhà tổ chức** hoặc đăng nhập.
2. Tạo sự kiện; API trả về bản nháp `DRAFT`.
3. Bảng **Sự kiện của tôi** gọi `GET /api/events/mine` và hiển thị toàn bộ sự kiện thuộc tài khoản.
4. Lọc theo trạng thái, chuyển trang, làm mới hoặc mở chi tiết sự kiện.
5. Phát hành bản nháp đủ điều kiện, hủy sự kiện hợp lệ, hoặc xóa bản nháp hợp lệ; danh sách được
   tải lại sau mỗi thao tác.

Frontend không lưu danh sách event ID trong trình duyệt. Owner ID được backend lấy từ JWT, không lấy
từ query hoặc trạng thái phía client. Frontend vẫn không có chỉnh sửa sự kiện vì API không có
endpoint update.

## 7. Xác thực và token

- JWT chỉ được lưu trong `sessionStorage`, không dùng `localStorage`.
- Token không xuất hiện trong URL, DOM, log hoặc thông báo.
- `Authorization: Bearer ...` chỉ được thêm cho request bảo vệ.
- Tải trang lại gọi `/api/auth/me` để khôi phục người dùng.
- Lỗi xác thực ở request bảo vệ sẽ xóa token, xóa UI bảo vệ và đưa người dùng về đăng nhập.
- Đăng xuất xóa token và dữ liệu giao diện gắn với tài khoản.
- Public registration chỉ hiển thị `USER` và `ORGANIZER`; không hiển thị `ADMIN`.

## 8. Xử lý lỗi

`api.js` chuẩn hóa lỗi mạng và các trạng thái `401`, `403`, `404`, `409`, `422`, `5xx`. Mã và mô tả
backend được chuyển thành thông báo tiếng Việt, đồng thời giữ phần chi tiết hữu ích. Form hiển thị
lỗi inline, tác vụ toàn cục dùng live-region toast. Nút submit bị khóa trong lúc request chạy để
tránh gửi trùng.

## 9. Accessibility và responsive

- Semantic landmarks, heading hierarchy, label hiển thị cho mọi input và skip link.
- Điều hướng, tab, form, dialog và action dùng button/link thật, hỗ trợ bàn phím.
- Focus state rõ ràng; loading/status/error có `aria-live` hoặc `aria-busy` phù hợp.
- Màu trạng thái luôn đi cùng nhãn chữ, không truyền ý nghĩa chỉ bằng màu.
- Layout chuyển từ ba cột sang hai/một cột trên màn hình nhỏ.
- Dùng system font và tôn trọng `prefers-reduced-motion`.
- Dữ liệu API được gắn bằng `textContent`/DOM node, không inject HTML không tin cậy.

## 10. Test

Chạy quality gate không PostgreSQL:

```cmd
cd /d E:\University\Semester_7\SA\KTPM
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen pytest -ra
```

Chạy toàn bộ suite và bắt buộc năm concurrency test trên database disposable:

```cmd
scripts\run-tests.cmd --with-db --junitxml=test-results.xml --cov=app --cov-report=term-missing --cov-report=xml --cov-fail-under=95
```

Test delivery kiểm tra HTML shell, MIME type của CSS/JavaScript, route API/docs, traversal, asset
404 và số operation OpenAPI.

## 11. Giới hạn do API hiện tại

- Không có endpoint chỉnh sửa sự kiện.
- Không có API chuyển sự kiện sang `COMPLETED`.
- Không có danh sách/search booking toàn hệ thống cho `ADMIN`.
- Danh mục chỉ trả sự kiện đã phát hành và chưa kết thúc; draft/cancelled không hiển thị công khai.
- API không khai báo đơn vị tiền tệ, nên giao diện hiển thị số tiền đúng dữ liệu mà không tự gắn mã
  tiền tệ.

## 12. Tính năng hoãn rõ ràng

Thanh toán, QR, thông báo, realtime/WebSocket, refresh token, HttpOnly cookie, upload ảnh, frontend
framework, Node build pipeline, async SQLAlchemy, cache/Redis và tối ưu Phase 2 đều nằm ngoài MVP.

## 13. Flow trình bày đề xuất

1. Mở `/app/`, thử tìm kiếm và responsive mobile width.
2. Đăng ký `ORGANIZER`, chỉ ra thông tin `/me` ở header.
3. Tạo draft và chỉ ra sự kiện tự xuất hiện trong **Sự kiện của tôi**, không cần nhập ID.
4. Lọc trạng thái `DRAFT`, phát hành sự kiện và quan sát dashboard tự làm mới.
5. Đăng xuất; đăng ký `USER` và xác nhận không có control tổ chức.
6. Mở event, đặt hai vé và chỉ ra inventory giảm.
7. Mở **Vé của tôi**, xem chi tiết và hủy; quay lại event để thấy inventory phục hồi.
8. Thử mật khẩu sai để minh họa lỗi inline; đăng xuất để xác nhận UI bảo vệ được xóa.
