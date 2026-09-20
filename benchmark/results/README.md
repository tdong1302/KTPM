# Raw benchmark results

Mỗi lần chạy sinh ra các file `<tag>_stats.csv`, `<tag>_failures.csv`,
`<tag>_exceptions.csv`, `<tag>_stats_history.csv` và `<tag>-environment.txt`.

Đây là **dữ liệu thô làm bằng chứng**. Số liệu đã được tổng hợp vào `docs/benchmark.md`.
Không sửa tay các file này.

| Tag | Kịch bản | Ngày chạy (UTC) | Phần cứng | Git commit |
|---|---|---|---|---|
| `s2` | S2 — mixed load, 100 user, 5 phút | 2026-09-20 11:41 | Kaggle CPU, Xeon @2.20GHz, 4 vCPU | `73ca1ce` |
| `s3` | S3 — write contention, 100 user, 2 phút, 1 sự kiện | 2026-09-20 12:01 | Kaggle CPU, Xeon @2.20GHz, 4 vCPU | `73ca1ce` |

Bộ file của S2 và S3 đã **đầy đủ** (mỗi lần chạy: `_stats.csv`, `_failures.csv`,
`_exceptions.csv`, `_stats_history.csv`, `-environment.txt`).

`_stats_history.csv` là file quan trọng nhất: nó cho phép tính lại số liệu **theo từng cửa sổ thời
gian**, nhờ đó phát hiện được rằng percentile toàn cuộc bị nhiễu bởi giai đoạn dồn tải
(xem `docs/benchmark.md` mục 4.5).
