# RES-01 — Báo cáo bàn giao

## Phạm vi

- Giữ chỗ tối đa 10 phút và giới hạn đến giờ bắt đầu sự kiện. Bốn endpoint tạo, xem, xác nhận và hủy được ghi trong [hợp đồng API](api.md#reservations--giữ-chỗ-có-thời-hạn).
- Xác nhận tạo booking trong cùng transaction. Gửi lại xác nhận trả cùng booking. API đặt vé trực tiếp vẫn dùng được và dùng chung tồn kho PostgreSQL với giữ chỗ.
- Worker `reservation-expiry` kiểm tra giữ chỗ đến hạn và hoàn vé. Khi rảnh worker kiểm tra lại sau 5 giây, nên GET có thể còn trả `RESERVED` sau `expires_at` cho đến khi worker cập nhật.

## Thay đổi

- Domain, service, ports và adapter Unit of Work triển khai trạng thái giữ chỗ. Mọi thao tác có thể hoàn vé khóa sự kiện trước rồi đọc lại giữ chỗ dưới khóa.
- Migration `8d2fe144b7c0` thêm bảng `reservations`, khóa ngoại, ràng buộc trạng thái và chỉ mục tìm giữ chỗ hết hạn. Cần dừng traffic giữ chỗ và thu hồi hết giữ chỗ trước khi downgrade.
- Router, schema và Compose nối API xác thực và worker độc lập. Bộ test bao phủ quyền sở hữu, thời hạn, booking, tranh vé cuối và hoàn vé đồng thời.

## Xác minh

- Sau khi tích hợp `main` tại `40544f2`, chạy `uv run --frozen python -m pytest -q --cov=app --cov-fail-under=95` với PostgreSQL disposable. **303 test pass**, gồm **11 test concurrency PostgreSQL**, **0 skip**, coverage **96,66%**.
- `alembic upgrade head` chạy từ PostgreSQL rỗng. `alembic heads` và `alembic current` cùng trả về `8d2fe144b7c0`. Script kiểm tra đủ 14 ràng buộc CHECK.
- Docker Compose build và khởi động API và worker trên project kiểm thử riêng. `/health` trả `UP`, `/ready` xác nhận PostgreSQL, request có correlation ID. Luồng giữ vé, hủy và xác nhận lặp đạt. `docker compose exec -T reservation-expiry python -m app.workers.reservation_expiry --once` thành công.
- Ruff, Docker Compose config và `git diff --check` đạt.

## Tích hợp

- Nhánh `feature/expiring-reservation` đã tích hợp `main` tại `40544f2`. OpenAPI đăng ký cả endpoint giữ chỗ và endpoint vận hành. Test dashboard kiểm soát thời gian tạo sự kiện để kiểm tra thứ tự và phân trang ổn định.
- Member 3 có thể dùng hợp đồng API để chuẩn bị rate limiting và giao diện. Khi mở PR, đặt base là `main`, mời Huy Anh review và giữ thứ tự merge trong [kế hoạch Pha 2](phase2-team-plan.md).
