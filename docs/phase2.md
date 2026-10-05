# Pha 2 — Cải tiến thuộc tính chất lượng

> **Trạng thái: CHƯA BẮT ĐẦU.**
> Tài liệu này chỉ liệt kê các **ứng viên** cải tiến và cách đo chúng. Chưa có cải tiến nào được
> triển khai.
> Đã có số liệu baseline cho kịch bản S2 và S3 ([benchmark.md](benchmark.md)); S1 và S4 chưa chạy.
> Thứ tự ưu tiên chỉ được chốt sau khi có S4, vì đó mới là kịch bản chỉ ra nút thắt.

## Quy trình bắt buộc

```
1. Chạy baseline trên Kaggle CPU  →  ghi số liệu BEFORE
2. Đọc số liệu, xác định nút thắt THẬT (không đoán)
3. Chọn 1–2 thuộc tính chất lượng để cải tiến, nêu rõ lý do dựa trên số liệu
4. Triển khai cải tiến
5. Chạy lại ĐÚNG kịch bản cũ trên ĐÚNG cấu hình cũ  →  ghi số liệu AFTER
6. So sánh và giải thích
```

Bước 2 là bước không được bỏ qua. Chọn cải tiến trước khi đo là làm ngược, và sẽ không trả lời được
câu hỏi "tại sao lại cải tiến chỗ này".

## Các ứng viên

Dưới đây là những điểm đã biết là **có thể** trở thành nút thắt, kèm cách xác nhận bằng số liệu.
Đây không phải kế hoạch — đây là danh sách giả thuyết cần kiểm chứng.

### A. Thông lượng — chuyển sang async I/O

**Baseline:** SQLAlchemy đồng bộ, endpoint khai báo bằng `def`, FastAPI chạy chúng trong threadpool
mặc định (~40 thread). Đây là lựa chọn có chủ ý, không phải thiếu sót — xem
[architecture.md](architecture.md#6-hai-quyết-định-có-chủ-ý-để-dành-cho-pha-2).

**Giả thuyết:** với tải đọc cao, threadpool trở thành giới hạn trước khi CPU hoặc database bão hoà.

**Cách xác nhận:** trong S4, nếu throughput đi ngang trong khi CPU chưa tới hạn và độ trễ database
vẫn thấp, giả thuyết được củng cố.

**Cải tiến có thể khảo sát sau:** `asyncpg` + `AsyncSession` + endpoint `async def`. Các port và
service hiện là đồng bộ, nên true async sẽ cần thay đổi signature/transaction orchestration xuyên
qua application boundary, không chỉ thay adapter. Chỉ thực hiện sau khi số đo chứng minh threadpool
là nút thắt.

### B. Độ trễ đọc — cache danh mục sự kiện

**Baseline:** mỗi lần gọi `GET /api/events` đều truy vấn database, kể cả khi danh mục gần như không
đổi.

**Cách xác nhận:** tỉ trọng request đọc trong S2, và p95 của `GET /api/events` so với các endpoint
khác.

**Cải tiến:** cache trong tiến trình có TTL, hoặc Redis nếu cần chia sẻ giữa nhiều worker.
**Đánh đổi phải nêu rõ:** dữ liệu cũ (stale) — số vé còn lại hiển thị có thể lệch. Cần quyết định
và ghi lại TTL chấp nhận được.

### C. Thông lượng ghi — giảm chi phí tuần tự hoá

**Baseline:** `SELECT ... FOR UPDATE` trên dòng sự kiện. Đúng đắn tuyệt đối, nhưng mọi thao tác đặt
vé cho **cùng một sự kiện** đều bị xếp hàng.

**Đã đo.** So sánh S3 (một sự kiện khan hiếm) với S2 (500 sự kiện), chuẩn hoá theo độ trễ đọc
trong cùng lần chạy: đường đặt vé đi từ 1,30× lên 1,79× một request đọc, thông lượng giảm 7,6 %.
Phần đuôi chịu ảnh hưởng nặng hơn trung vị (p99 cửa sổ xấu nhất 720 ms → 1 300 ms), nhưng **không
lan sang các endpoint đọc**. Chi tiết ở [benchmark.md](benchmark.md) mục 4.4 và 4.5.

**Hệ quả:** cái giá của khoá khiêm tốn hơn dự đoán ban đầu. Cần cân nhắc kỹ trước khi thay nó —
và mức giảm 7,6 % vẫn có thể nằm trong biên nhiễu, phải chạy lặp mới khẳng định được.

**Các phương án, đều phải giữ bất biến không bán vượt vé:**

1. Khoá lạc quan (optimistic) bằng cột version + retry — tốt khi tranh chấp thấp, tệ khi cao.
2. `UPDATE events SET available_tickets = available_tickets - :q WHERE id = :id AND
   available_tickets >= :q` — một câu lệnh nguyên tử, không cần `SELECT` trước.
3. Chia tồn kho thành nhiều "xô" (bucket) để giảm tranh chấp trên một dòng.

Đây là ứng viên thú vị nhất về mặt học thuật vì nó thể hiện rõ đánh đổi giữa **tính đúng đắn** và
**thông lượng** — và bất biến phải được kiểm chứng lại sau mỗi phương án bằng
`tests/concurrency/`.

### D. Chỉ mục và hình dạng truy vấn

**Baseline:** đã có `ix_events_status_start_time`, `ix_bookings_user_id_created_at`,
`ix_bookings_event_id_status`. Phân trang dùng `OFFSET`, vốn suy giảm tuyến tính ở trang sâu.

**Cách xác nhận:** `EXPLAIN ANALYZE` trên truy vấn danh mục ở kích thước dữ liệu thật; đo p95 của
trang 1 so với trang 100.

**Cải tiến:** phân trang theo con trỏ (keyset), hoặc chỉ mục phù hợp hơn với bộ lọc thực tế.

### E. Pool kết nối và số worker

**Baseline:** `DB_POOL_SIZE=5`, `DB_MAX_OVERFLOW=10`, `uvicorn --workers 1`.

**Cách xác nhận:** nếu độ trễ tăng vọt nhưng CPU và database đều nhàn rỗi, nhiều khả năng request
đang chờ lấy kết nối từ pool.

**Cải tiến:** tăng pool, tăng số worker uvicorn. Rẻ và dễ đo — nhưng phải đo, vì tăng quá tay sẽ
đẩy nút thắt sang database.

### F. Chi phí bcrypt trên đường đăng nhập

**Baseline:** `BCRYPT_ROUNDS=12`. Đây là chi phí CPU **có chủ ý** vì lý do bảo mật.

**Cách xác nhận:** p95 của `POST /api/auth/login` so với các endpoint khác.

**Lưu ý quan trọng:** nếu có thay đổi tham số này, phải ghi rõ và coi đó là một đánh đổi **bảo mật**,
không được trình bày như một "tối ưu hiệu năng" thuần tuý.

## Ba tính chất của baseline cần giữ khi cải tiến

Baseline hiện có ba tính chất khiến nó dễ đo và dễ suy luận. Bất kỳ cải tiến nào ở Pha 2 làm mất
một trong số đó đều phải nêu rõ cái giá phải trả:

1. **Không ghi trên đường đọc.** Không request đọc nào kích hoạt một thao tác ghi ẩn. Nhờ vậy độ
   trễ đọc đo được là độ trễ đọc thật.

2. **Không gọi liên tiến trình trên đường phục vụ request.** Toàn bộ xử lý nằm trong một tiến
   trình và một database, nên không có độ trễ mạng nào lẫn vào số liệu.

3. **Một transaction cho một thao tác nghiệp vụ.** Đặt vé trừ tồn kho và ghi booking trong cùng một
   transaction, nên thao tác thất bại không để lại trạng thái dở dang. Nếu Pha 2 tách thành nhiều
   dịch vụ với nhiều database, tính chất này mất đi và phải thay bằng saga có bù trừ — **cái giá
   đó phải được nêu rõ trong phần đánh đổi**, không được coi là miễn phí.

## Điều không được làm

- Không đặt mục tiêu bằng số trước khi có baseline.
- Không so sánh số đo trên máy cá nhân với số đo trên Kaggle.
- Không thay đổi kịch bản hoặc dữ liệu seed giữa BEFORE và AFTER.
- Không tuyên bố cải thiện nếu chênh lệch nằm trong dao động giữa các lần chạy — hãy chạy lặp lại
  và báo cáo độ biến thiên.
- Không thêm microservices, message queue hay service discovery chỉ vì "kiến trúc cho có". Mỗi
  thành phần thêm vào phải giải quyết một vấn đề đã được số liệu chỉ ra.
