# Mô tả hệ thống

## Bản rút gọn (~200 từ) — dùng để nộp

**EventHub-KTPM — Dịch vụ đặt vé sự kiện.**

Hệ thống là một backend REST API cho nghiệp vụ bán và đặt vé sự kiện trực tuyến, với ba vai trò:
người dùng, ban tổ chức và quản trị viên.

Các chức năng chính gồm: (1) **Quản lý tài khoản và xác thực** — đăng ký, đăng nhập nhận JWT, xem
thông tin tài khoản hiện tại; xác thực được xử lý tập trung tại một middleware chạy trước mọi
endpoint và phân quyền theo vai trò. (2) **Quản lý sự kiện** — ban tổ chức tạo sự kiện (tiêu đề,
mô tả, danh mục, địa điểm, thời gian, tổng số vé, giá vé), phát hành, huỷ và xoá; sự kiện tuân theo
vòng đời DRAFT → PUBLISHED → CANCELLED/COMPLETED với điều kiện kiểm tra ở mỗi bước chuyển.
(3) **Tra cứu sự kiện công khai** — tìm kiếm theo từ khoá, thành phố, danh mục, có phân trang và
sắp xếp, chỉ hiển thị sự kiện đã phát hành và chưa kết thúc. (4) **Đặt vé** — người dùng đã đăng
nhập đặt vé cho một sự kiện; hệ thống kiểm tra điều kiện và trừ số vé còn lại trong cùng một giao
dịch có khoá dòng dữ liệu để không bán vượt số vé khi nhiều người đặt đồng thời. (5) **Quản lý vé
đã đặt** — xem danh sách vé của mình, xem chi tiết, huỷ vé và hoàn lại số vé cho sự kiện.

Thuộc tính chất lượng trọng tâm là tính đúng đắn khi tranh chấp đồng thời trên tồn kho vé và khả
năng đo được hiệu năng để so sánh trước/sau cải tiến ở Pha 2.

---

## Bản đầy đủ

**Tên hệ thống:** EventHub-KTPM — Dịch vụ đặt vé sự kiện (Event Ticket Booking Service)

Hệ thống là một backend REST API phục vụ nghiệp vụ bán và đặt vé sự kiện trực tuyến, với ba vai
trò: người dùng (USER), ban tổ chức (ORGANIZER) và quản trị viên (ADMIN).

**Các chức năng chính:**

1. **Quản lý tài khoản và xác thực.** Đăng ký tài khoản, đăng nhập và nhận về JWT access token,
   xem thông tin tài khoản đang đăng nhập. Việc xác thực được xử lý tập trung tại một middleware
   duy nhất chạy trước mọi endpoint, phân quyền theo vai trò.

2. **Quản lý sự kiện.** Ban tổ chức tạo sự kiện ở trạng thái nháp với tiêu đề, mô tả, danh mục,
   địa điểm, thời gian bắt đầu/kết thúc, tổng số vé và giá vé; sau đó phát hành, huỷ hoặc xoá sự
   kiện. Sự kiện tuân theo vòng đời DRAFT → PUBLISHED → CANCELLED/COMPLETED, mỗi bước chuyển đều
   được kiểm tra điều kiện hợp lệ.

3. **Tra cứu sự kiện công khai.** Tìm kiếm theo từ khoá, thành phố và danh mục, có phân trang và
   sắp xếp; chỉ hiển thị các sự kiện đã phát hành và chưa kết thúc.

4. **Đặt vé.** Người dùng đã đăng nhập đặt vé cho một sự kiện. Hệ thống kiểm tra điều kiện đặt vé
   và trừ số vé còn lại trong cùng một giao dịch có khoá dòng dữ liệu, nhằm bảo đảm không bán vượt
   số vé khi nhiều người đặt đồng thời.

5. **Quản lý vé đã đặt.** Xem danh sách vé của chính mình, xem chi tiết một vé, huỷ vé và hoàn lại
   số vé đã giữ cho sự kiện.

Thuộc tính chất lượng trọng tâm là **tính đúng đắn khi có tranh chấp đồng thời** trên tồn kho vé,
cùng với **khả năng đo được hiệu năng** (thời gian phản hồi, thông lượng, tỉ lệ lỗi) để so sánh
trước và sau cải tiến ở Pha 2.
