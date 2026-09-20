# Benchmark

> **Trạng thái: CHƯA CÓ SỐ LIỆU.**
> Hạ tầng đo đã sẵn sàng nhưng chưa chạy lần nào trên phần cứng chuẩn.
> Mọi ô trong các bảng dưới đây được để trống và **chỉ được điền sau khi chạy thật**.
> Không điền số ước lượng, không chép số từ máy khác.

## 1. Cấu hình phần cứng cố định

Theo yêu cầu của đề bài, mọi phép đo — cả BEFORE (Pha 1) và AFTER (Pha 2) — phải chạy trên **cùng
một cấu hình phần cứng**: **Kaggle CPU notebook**.

Ghi lại các thông tin sau cho mỗi lần chạy (script
[`benchmark/kaggle/run_baseline.py`](../benchmark/kaggle/run_baseline.py) tự động ghi chúng vào
`benchmark/results/<tag>-environment.txt`):

| Hạng mục | Giá trị |
|---|---|
| CPU model | *(chưa đo)* |
| Số core | *(chưa đo)* |
| RAM | *(chưa đo)* |
| Python version | *(chưa đo)* |
| PostgreSQL version | *(chưa đo)* |
| Git commit | *(chưa đo)* |
| Ngày chạy | *(chưa đo)* |

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

| Endpoint | Số request | Throughput (req/s) | p50 (ms) | p95 (ms) | p99 (ms) | Error rate |
|---|---|---|---|---|---|---|
| `GET /api/events` | | | | | | |
| `GET /api/events?city` | | | | | | |
| `GET /api/events/{id}` | | | | | | |
| **Tổng hợp** | | | | | | |

### S2 — Mixed load (100 users, 5 phút) — điểm so sánh chính

| Endpoint | Số request | Throughput (req/s) | p50 (ms) | p95 (ms) | p99 (ms) | Error rate |
|---|---|---|---|---|---|---|
| `GET /api/events` | | | | | | |
| `GET /api/events/{id}` | | | | | | |
| `GET /api/bookings/me` (auth) | | | | | | |
| `POST /api/bookings` (auth) | | | | | | |
| `POST /api/auth/login` | | | | | | |
| **Tổng hợp** | | | | | | |

Tài nguyên tiến trình API:

| Chỉ số | Giá trị |
|---|---|
| CPU trung bình (%) | |
| CPU đỉnh (%) | |
| RSS trung bình (MB) | |
| RSS đỉnh (MB) | |

### S3 — Write contention trên sự kiện khan hiếm (100 users, 2 phút)

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

*(Để trống cho tới khi có dữ liệu thật. Phần này ghi lại điều đã quan sát được từ số liệu — endpoint
nào chậm nhất, tài nguyên nào bão hoà trước, hình dạng phân phối độ trễ — chứ không phải suy đoán
trước khi đo.)*

## 5. So sánh BEFORE / AFTER (Pha 2)

Bảng này sẽ được điền ở Pha 2, sau khi đã có cả số liệu baseline lẫn số liệu sau cải tiến, đo trên
**cùng một cấu hình Kaggle CPU** và cùng kịch bản.

| Chỉ số | BEFORE (Pha 1) | AFTER (Pha 2) | Thay đổi |
|---|---|---|---|
| Throughput S2 (req/s) | | | |
| p95 S2 (ms) | | | |
| p99 S2 (ms) | | | |
| Error rate S2 | | | |
| Throughput S3 (req/s) | | | |
| p95 S3 (ms) | | | |
| Sức chứa (S4) | | | |

Ứng viên cải tiến và lý do: [phase2.md](phase2.md).
