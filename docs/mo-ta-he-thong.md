# Mô tả hệ thống

**EventHub-KTPM — Hệ thống đặt vé sự kiện.**

User: đăng ký/đăng nhập, xem danh sách sự kiện, chọn sự kiện và đặt vé, xem vé đã đặt, hủy vé.
Organizer: tạo sự kiện (tiêu đề, thời gian, địa điểm, tổng số vé, giá vé), phát hành hoặc hủy sự
kiện, xóa sự kiện nháp. Admin: quản lý toàn bộ sự kiện và vé của mọi user.

Sự kiện có vòng đời DRAFT → PUBLISHED → CANCELLED/COMPLETED. Số vé còn lại (available_tickets) bị
trừ khi đặt vé và hoàn lại khi hủy vé, đảm bảo không bán vượt số vé khi nhiều người đặt đồng thời.
