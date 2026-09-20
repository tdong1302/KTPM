# Benchmark

> **Trạng thái: đã đo S2. S1, S3, S4 chưa chạy.**
> Mọi con số trong tài liệu này đến từ một lần chạy thật trên Kaggle CPU; dữ liệu thô nằm trong
> [`benchmark/results/`](../benchmark/results/). Các ô còn ghi *(chưa đo)* là **chưa chạy**, không
> phải bỏ sót — và sẽ không được điền bằng số ước lượng.

## 1. Cấu hình phần cứng cố định

Theo yêu cầu của đề bài, mọi phép đo — cả BEFORE (Pha 1) và AFTER (Pha 2) — phải chạy trên **cùng
một cấu hình phần cứng**: **Kaggle CPU notebook**.

Thông tin dưới đây lấy từ [`benchmark/results/s2-environment.txt`](../benchmark/results/s2-environment.txt),
do [`benchmark/kaggle/run_baseline.py`](../benchmark/kaggle/run_baseline.py) tự động ghi lại mỗi lần chạy.

| Hạng mục | Giá trị |
|---|---|
| Nền tảng | Kaggle notebook, Accelerator = None (CPU) |
| CPU model | Intel(R) Xeon(R) CPU @ 2.20GHz |
| Số vCPU | 4 |
| RAM | 31 GiB (lúc chạy dùng ~898 MiB) |
| OS | Linux 6.12.90 x86_64, glibc 2.35 |
| Python | 3.12.13 |
| PostgreSQL | 16 (cài qua `apt-get` trong notebook) |
| App server | `uvicorn --workers 1` |
| `BCRYPT_ROUNDS` | 12 |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` | 5 / 10 (tối đa 15 kết nối) |
| Git commit | `73ca1ceca7d36e86846e82f58e42b77eea5f2c0c` |
| Ngày chạy | 2026-09-20 11:41 UTC |

## 2. Cách chạy

### Trên Kaggle (cấu hình chuẩn)

Kaggle là notebook, không có terminal: chạy trong ô code, thêm `!` phía trước.
Bật **Internet** trong Session options, rồi:

```python
!git clone https://github.com/tdong1302/KTPM.git /kaggle/working/ktpm
%cd /kaggle/working/ktpm
!pip install -q -e ".[bench]"
!python benchmark/kaggle/run_baseline.py --scenario s2
```

Script sẽ: cài và khởi động PostgreSQL → seed dữ liệu tất định → chạy uvicorn → chờ health →
warm-up 30 giây → chạy Locust headless → ghi CSV vào `benchmark/results/`.

### Trên máy cục bộ (để thử nghiệm, KHÔNG dùng làm số liệu chính thức)

```bash
docker compose up -d
python benchmark/seed_data.py --reset --events 500
locust -f benchmark/locustfile.py --headless --host http://localhost:8000 \
       --users 100 --spawn-rate 20 --run-time 5m --csv benchmark/results/s2-local
```

Hướng dẫn Kaggle từng bước: [benchmark/kaggle/README.md](../benchmark/kaggle/README.md).
Kịch bản chi tiết: [benchmark/scenarios.md](../benchmark/scenarios.md).

## 3. Kết quả BASELINE (Pha 1)

### S1 — Read-heavy (50 users, 3 phút)

*(chưa chạy)*

| Endpoint | Số request | Throughput (req/s) | p50 (ms) | p95 (ms) | p99 (ms) | Error rate |
|---|---|---|---|---|---|---|
| `GET /api/events` | | | | | | |
| `GET /api/events?city` | | | | | | |
| `GET /api/events/{id}` | | | | | | |
| **Tổng hợp** | | | | | | |

### S2 — Mixed load (100 users, 5 phút) — điểm so sánh chính

Nguồn: [`benchmark/results/s2_stats.csv`](../benchmark/results/s2_stats.csv) · thời lượng thực tế
298,9 s · 500 sự kiện đã seed.

| Endpoint | Số request | Throughput (req/s) | min (ms) | p50 (ms) | p95 (ms) | p99 (ms) | Error rate |
|---|---|---|---|---|---|---|---|
| `GET /api/events` | 18 890 | 63,20 | 14,6 | 230 | 400 | 570 | 0,00 % |
| `GET /api/events?city` | 11 281 | 37,74 | 20,3 | 230 | 400 | 590 | 0,00 % |
| `GET /api/events/{id}` | 7 533 | 25,20 | 22,8 | 230 | 430 | 600 | 0,00 % |
| `GET /api/bookings/me` (auth) | 4 831 | 16,16 | 74,5 | 250 | 440 | 570 | 0,00 % |
| `POST /api/bookings` (auth) | 3 694 | 12,36 | 101,4 | 300 | 510 | 630 | 0,00 % |
| `DELETE /api/bookings/{id}` (auth) | 1 223 | 4,09 | 143,0 | 320 | 500 | 600 | 0,00 % |
| `POST /api/auth/login` | 30 | 0,10 | 1 665,8 | 2 700 | 3 200 | 4 000 | 0,00 % |
| `POST /api/auth/register` | 30 | 0,10 | 1 031,6 | 3 100 | 3 900 | 4 000 | 0,00 % |
| **Tổng hợp** | **47 612** | **159,30** | 14,6 | **240** | **430** | **640** | **0,00 %** |

Phân bố tải: đọc công khai 79,2 % · đọc có xác thực 10,1 % · ghi (đặt + huỷ vé) 10,3 % ·
đăng ký/đăng nhập 0,1 %.

**Không có một lỗi nào** trên 47 612 request
([`s2_failures.csv`](../benchmark/results/s2_failures.csv) rỗng).

Tài nguyên tiến trình API:

| Chỉ số | Giá trị |
|---|---|
| CPU trung bình (%) | *(chưa đo)* |
| CPU đỉnh (%) | *(chưa đo)* |
| RSS trung bình (MB) | *(chưa đo)* |
| RSS đỉnh (MB) | *(chưa đo)* |

> `run_baseline.py` hiện **chưa lấy mẫu** CPU/RSS của tiến trình uvicorn. Cần bổ sung một sampler
> bằng `psutil` trước khi đo lại, nếu muốn so sánh mức tiêu thụ tài nguyên ở Pha 2.

### S3 — Write contention trên sự kiện khan hiếm (100 users, 2 phút)

*(chưa chạy — đây là kịch bản cô lập cái giá của khoá chống bán vượt vé, cần chạy để bổ sung cho
nhận định ở mục 4.4)*

| Chỉ số | Giá trị |
|---|---|
| Throughput `POST /api/bookings` (req/s) | |
| p50 / p95 / p99 (ms) | |
| Số đặt vé thành công (201) | |
| Số bị từ chối vì hết vé (409) | |
| Tỉ lệ lỗi thật (5xx) | |
| **Bất biến `đã_bán + còn_lại == tổng`** | |

Bất biến cuối cùng là tiêu chí *đúng/sai*, không phải chỉ số hiệu năng. Kiểm tra sau khi chạy:

```sql
SELECT e.total_tickets,
       e.available_tickets,
       COALESCE(SUM(b.quantity) FILTER (WHERE b.status = 'CONFIRMED'), 0) AS sold
FROM events e LEFT JOIN bookings b ON b.event_id = e.id
GROUP BY e.id, e.total_tickets, e.available_tickets;
```

### S4 — Điểm bão hoà

*(chưa chạy)*

Ngưỡng: p95 ≤ 1000 ms **và** tỉ lệ lỗi ≤ 1 %.

| Số user | Throughput (req/s) | p95 (ms) | Error rate | Đạt ngưỡng? |
|---|---|---|---|---|
| 25 | | | | |
| 50 | | | | |
| 100 | | | | |
| 200 | | | | |
| 400 | | | | |

**Sức chứa baseline:** *(chưa đo)*

## 4. Quan sát

Tất cả nhận định dưới đây rút ra từ số liệu S2 ở mục 3. Những chỗ dữ liệu chưa đủ để kết luận đều
được nói rõ là chưa đủ.

### 4.1. Baseline ổn định, không lỗi

47 612 request, 0 thất bại, p95 tổng hợp 430 ms. Baseline chịu được 100 người dùng đồng thời mà
không suy sụp. Đây là tiền đề cần thiết: nếu baseline đã lỗi thì mọi so sánh ở Pha 2 đều vô nghĩa.

### 4.2. Độ trễ đồng đều một cách đáng ngờ → dấu hiệu xếp hàng, không phải chi phí truy vấn

Đây là quan sát quan trọng nhất. Ba endpoint đọc có chi phí truy vấn **rất khác nhau** —
`GET /api/events` là truy vấn lọc + đếm + phân trang trên 500 dòng, còn `GET /api/events/{id}` chỉ
là một `SELECT` theo khoá chính — nhưng cả hai đều có p50 đúng **230 ms**.

Khoảng cách giữa `min` và `p50` mới là chỗ lộ nguyên nhân:

| Endpoint | min | p50 | p50 / min |
|---|---|---|---|
| `GET /api/events` | 14,6 ms | 230 ms | **15,8×** |
| `GET /api/events?city` | 20,3 ms | 230 ms | 11,3× |
| `GET /api/events/{id}` | 22,8 ms | 230 ms | 10,1× |

Khi không có tranh chấp, truy vấn chỉ mất 14–23 ms. Dưới tải, nó mất 230 ms. Nghĩa là **phần lớn
thời gian phản hồi là thời gian chờ, không phải thời gian làm việc**. Ứng viên gây chờ:

1. **Pool kết nối**: cấu hình tối đa 15 kết nối, trong khi có 100 người dùng đồng thời.
2. **Threadpool của FastAPI**: baseline dùng SQLAlchemy đồng bộ với endpoint `def`, nên mỗi request
   chiếm một thread trong threadpool mặc định.
3. **CPU**: chỉ có 4 vCPU.

Số liệu S2 **chưa đủ** để tách ba nguyên nhân này. Cần chạy S4 (quét điểm bão hoà) và bổ sung lấy
mẫu CPU/RSS thì mới chỉ đích danh được. Đây là việc phải làm trước khi chọn cải tiến cho Pha 2 —
xem [phase2.md](phase2.md), mục A và E.

### 4.3. Đăng nhập / đăng ký chậm hơn một bậc, và đó là có chủ ý

| Endpoint | p50 | So với `GET /api/events` |
|---|---|---|
| `POST /api/auth/login` | 2 700 ms | **11,7× chậm hơn** |
| `POST /api/auth/register` | 3 100 ms | **13,5× chậm hơn** |

Nguyên nhân là bcrypt với cost factor 12 — một chi phí CPU **cố ý** vì lý do bảo mật, trên CPU
2,2 GHz. Chú ý `min` của login đã là 1 666 ms: ngay cả khi không tranh chấp, băm mật khẩu vẫn tốn
chừng đó.

Ảnh hưởng tới tổng thể là nhỏ (60 request, 0,1 % tải) vì mỗi người dùng chỉ đăng nhập một lần. Nhưng
với hệ thống bán vé thật — nơi hàng nghìn người đăng nhập cùng lúc ngay trước giờ mở bán — đây sẽ là
nút thắt đầu tiên.

**Cảnh báo cho Pha 2:** hạ `BCRYPT_ROUNDS` sẽ làm con số đẹp lên ngay, nhưng đó là **đánh đổi bảo
mật**, không phải tối ưu hiệu năng. Nếu có thay đổi thì phải trình bày đúng bản chất như vậy.

### 4.4. Đường ghi chưa phải nút thắt ở kịch bản này

`POST /api/bookings` có p50 300 ms, chỉ chậm hơn đọc (230 ms) khoảng 30 %, dù nó phải mở transaction
và giữ khoá `SELECT ... FOR UPDATE`. Sàn chi phí của nó cao hơn thật (min 101 ms so với 14,6 ms của
đọc), nhưng dưới tải thì phần chờ chung mới là chủ đạo.

Lý do khoá chưa lộ ra: 500 sự kiện đã seed, mà Locust chọn ngẫu nhiên, nên hầu như không có hai
request nào tranh cùng một dòng. **S2 vì vậy không đo được cái giá của khoá.** Đó đúng là lý do tồn
tại của kịch bản S3 — dồn toàn bộ người mua vào một sự kiện duy nhất. Chưa chạy S3 thì chưa được
kết luận gì về chi phí của khoá.

### 4.5. Chưa thể kết luận về sức chứa

Throughput tổng hợp 159,3 req/s **không phải** giới hạn của hệ thống. Locust chạy theo mô hình vòng
kín có thời gian nghĩ (0,1–1,0 s), nên thông lượng bị chặn bởi chính số người dùng và thời gian
nghĩ, chứ chưa chắc bởi server. Với độ trễ trung bình 262 ms cộng thời gian nghĩ trung bình khoảng
0,4 s, con số 159 req/s đúng bằng kỳ vọng của workload — tức là nó **chưa** chứng minh server đã
bão hoà.

Muốn biết sức chứa thật phải chạy S4, tăng dần số người dùng tới khi p95 vượt 1 s hoặc tỉ lệ lỗi
vượt 1 %.

### 4.6. Việc cần làm tiếp

1. Chạy **S3** — cô lập cái giá của khoá chống bán vượt vé, và kiểm tra lại bất biến tồn kho.
2. Chạy **S4** — tìm điểm bão hoà thật, phân biệt giữa giới hạn pool, threadpool và CPU.
3. Bổ sung **sampler CPU/RSS** vào `run_baseline.py` trước khi đo lại.
4. Chạy lặp **2–3 lần** mỗi kịch bản để biết độ dao động; Kaggle dùng CPU chia sẻ nên số liệu có
   nhiễu. Chưa biết biên độ nhiễu thì chưa thể nói cải tiến ở Pha 2 là thật hay chỉ là dao động.

## 5. So sánh BEFORE / AFTER (Pha 2)

Bảng này sẽ được điền ở Pha 2, sau khi đã có cả số liệu baseline lẫn số liệu sau cải tiến, đo trên
**cùng một cấu hình Kaggle CPU** và cùng kịch bản.

| Chỉ số | BEFORE (Pha 1) | AFTER (Pha 2) | Thay đổi |
|---|---|---|---|
| Throughput S2 (req/s) | 159,30 | | |
| p95 S2 (ms) | 430 | | |
| p99 S2 (ms) | 640 | | |
| Error rate S2 | 0,00 % | | |
| Throughput S3 (req/s) | *(chưa đo)* | | |
| p95 S3 (ms) | *(chưa đo)* | | |
| Sức chứa (S4) | *(chưa đo)* | | |

Ứng viên cải tiến và lý do: [phase2.md](phase2.md).
