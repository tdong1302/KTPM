# Raw benchmark results

Mỗi lần chạy sinh ra các file `<tag>_stats.csv`, `<tag>_failures.csv`,
`<tag>_exceptions.csv`, `<tag>_stats_history.csv` và `<tag>-environment.txt`.

Đây là **dữ liệu thô làm bằng chứng**. Số liệu đã được tổng hợp vào `docs/benchmark.md`.
Không sửa tay các file này.

| Tag | Kịch bản | Ngày chạy (UTC) | Phần cứng | Git commit |
|---|---|---|---|---|
| `s2` | S2 — mixed load, 100 user, 5 phút | 2026-09-20 11:41 | Kaggle CPU, Xeon @2.20GHz, 4 vCPU | `73ca1ce` |
| `s3` | S3 — write contention, 100 user, 2 phút, 1 sự kiện | 2026-09-20 12:01 | Kaggle CPU, Xeon @2.20GHz, 4 vCPU | `73ca1ce` |

**Còn thiếu, cần tải về từ Kaggle:**

- `s2`: `s2_stats_history.csv`, `s2_exceptions.csv`
- `s3`: toàn bộ CSV gốc. Hiện mới chỉ có `s3-environment.txt` (nguyên văn) và
  `s3_stats_excerpt.txt` — bảng pandas chép lại, **không phải** file CSV gốc.
