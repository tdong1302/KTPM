# Chạy load test trên Kaggle CPU

> **Kaggle không có terminal.** Kaggle là notebook, nên mọi lệnh shell phải chạy trong **ô code
> (cell)** với dấu `!` phía trước. `%cd` là lệnh magic để đổi thư mục (dùng `%` chứ không phải `!`,
> vì `!cd` chỉ đổi trong tiến trình con rồi mất tác dụng).

Đây là cấu hình phần cứng chuẩn của môn: **mọi số liệu BEFORE (Pha 1) và AFTER (Pha 2) đều phải đo
trên đây**, không được trộn với số đo từ máy cá nhân.

---

## Bước 1 — Tạo notebook

1. Vào <https://www.kaggle.com/code> → **New Notebook**
2. Panel bên phải → **Session options**:
   - **Accelerator**: `None` (CPU) — bắt buộc, đề bài yêu cầu CPU
   - **Internet**: **On** — bắt buộc, không có thì không `git clone` và `apt-get` được
   - **Language**: Python

> Bật Internet lần đầu Kaggle sẽ bắt xác minh số điện thoại. Làm trước cho đỡ mất thời gian.

## Bước 2 — Lấy code về

```python
!git clone https://github.com/tdong1302/KTPM.git /kaggle/working/ktpm
%cd /kaggle/working/ktpm
!git log --oneline -1
```

## Bước 3 — Cài dependency

```python
!pip install -q -e ".[bench]"
```

Mất khoảng 1–2 phút. Cảnh báo về version conflict với package có sẵn của Kaggle là bình thường,
cứ bỏ qua miễn là không có dòng `ERROR`.

## Bước 4 — Chạy benchmark

```python
!python benchmark/kaggle/run_baseline.py --scenario s2
```

Script tự động làm tuần tự: cài PostgreSQL bằng `apt-get` → khởi động → seed dữ liệu tất định →
chạy `uvicorn` nền → chờ `/health` → warm-up 30 giây → chạy Locust headless → ghi CSV.

Thời gian: lần đầu khoảng 8–10 phút (phần lớn là cài PostgreSQL). `s2` chạy 5 phút.

Các kịch bản khác — chạy **từng cái một**, mỗi cái một cell:

```python
!python benchmark/kaggle/run_baseline.py --scenario s1   # read-heavy, 50 user, 3 phút
!python benchmark/kaggle/run_baseline.py --scenario s3   # tranh chấp ghi, 100 user, 2 phút
```

Từ lần thứ hai trở đi thêm `--skip-install` để khỏi cài lại PostgreSQL:

```python
!python benchmark/kaggle/run_baseline.py --scenario s1 --skip-install
```

## Bước 5 — Xem và tải kết quả

```python
!ls -la benchmark/results/
```

In thẳng bảng tổng hợp ra màn hình cho dễ chép:

```python
import pandas as pd

df = pd.read_csv("benchmark/results/s2_stats.csv")
pd.set_option("display.width", 200)
print(
    df[
        [
            "Name",
            "Request Count",
            "Failure Count",
            "Median Response Time",
            "95%",
            "99%",
            "Requests/s",
        ]
    ].to_string(index=False)
)
```

Và thông tin phần cứng — **bắt buộc phải ghi lại** cùng số liệu:

```python
print(open("benchmark/results/s2-environment.txt").read())
```

Tải file về: các file trong `/kaggle/working/` xuất hiện ở tab **Output** bên phải, bấm tải xuống.
Nếu nhiều file, nén lại cho gọn:

```python
!cd /kaggle/working/ktpm && zip -r /kaggle/working/benchmark-results.zip benchmark/results/
```

## Bước 6 — Điền số vào `docs/benchmark.md`

Mở `docs/benchmark.md` trên máy, điền vào các ô đang để trống:

- Bảng **mục 1** — cấu hình phần cứng, lấy từ file `*-environment.txt` (CPU model, số core, RAM,
  Python version, git commit, ngày chạy).
- Bảng **mục 3** — số liệu từng kịch bản, lấy từ `*_stats.csv`.

Ánh xạ cột CSV của Locust sang bảng:

| Cột trong `_stats.csv` | Ô trong `docs/benchmark.md` |
|---|---|
| `Request Count` | Số request |
| `Requests/s` | Throughput (req/s) |
| `Median Response Time` | p50 (ms) |
| `95%` | p95 (ms) |
| `99%` | p99 (ms) |
| `Failure Count` / `Request Count` | Error rate |

Dòng `Aggregated` trong CSV chính là dòng **Tổng hợp**.

Nhớ commit cả file CSV thô trong `benchmark/results/` để có bằng chứng.

## Riêng với kịch bản S3 — kiểm tra bất biến

S3 đo cái giá của khoá chống bán vượt vé, nên ngoài độ trễ phải kiểm tra **tính đúng đắn**:

```python
!su postgres -c "psql -d eventhub_ktpm -c \"SELECT e.total_tickets, e.available_tickets, COALESCE(SUM(b.quantity) FILTER (WHERE b.status='CONFIRMED'),0) AS sold, (e.available_tickets + COALESCE(SUM(b.quantity) FILTER (WHERE b.status='CONFIRMED'),0) = e.total_tickets) AS invariant_holds FROM events e LEFT JOIN bookings b ON b.event_id=e.id GROUP BY e.id, e.total_tickets, e.available_tickets;\""
```

Cột `invariant_holds` phải là `t`. Nếu là `f` thì hệ thống đã bán vượt vé — đó là lỗi nghiêm trọng,
phải dừng lại và sửa chứ không phải một con số hiệu năng.

---

## Nguyên tắc bắt buộc

- **Không bịa số.** Chỉ điền số thực sự đọc được từ CSV của một lần chạy thật.
- **Ghi kèm git commit** của code lúc chạy. Số liệu không gắn với phiên bản code là vô nghĩa.
- **Giữ nguyên kịch bản và dữ liệu seed** giữa BEFORE và AFTER. Đổi một thứ là mất khả năng so sánh.
- **Chạy lặp lại 2–3 lần** rồi báo cáo cả độ dao động. Chênh lệch nhỏ hơn dao động giữa các lần chạy
  thì không được gọi là cải thiện.
- Session Kaggle bị ngắt khi đóng tab quá lâu. Chạy xong nên tải kết quả về ngay.

## Xử lý sự cố

| Triệu chứng | Nguyên nhân / cách xử lý |
|---|---|
| `git clone` treo hoặc lỗi mạng | Chưa bật **Internet** trong Session options |
| `apt-get` báo không tìm thấy package | Chưa bật Internet, hoặc cần `!apt-get update` trước |
| `the API did not become healthy in time` | Xem log, thường do PostgreSQL chưa lên. Chạy `!service postgresql status` |
| `psycopg.OperationalError: connection refused` | PostgreSQL chưa khởi động: `!service postgresql start` |
| Số liệu lần sau khác hẳn lần trước | Kaggle chia sẻ CPU nên có dao động. Chạy lại vài lần, báo cáo khoảng giá trị |
