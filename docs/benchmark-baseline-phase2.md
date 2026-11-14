# Phase 2 BEFORE benchmark baseline

Status: **measured locally on 2026-11-14; no application optimization applied**.

This is the comparison baseline for later Phase 2 changes. Historical Kaggle S2/S3 files remain
useful evidence, but they use a different machine and include ramp/auth setup in their percentiles;
they must not be compared numerically with this steady-state baseline.

## Provenance and method

| Item | Recorded value |
|---|---|
| Application commit | `e592db3228863b05fe08073a76e5442cfbbb9d83` |
| Worktree | Dirty because benchmark harness/docs were uncommitted; changed-path SHA-256 manifest is in raw summary |
| OS | Windows `10.0.26300` |
| CPU | AMD64 Family 25 Model 117; 16 logical CPUs |
| RAM | 31.31 GiB |
| Python / Docker | 3.11.16 / Engine 29.8.2 |
| PostgreSQL | 16.15, disposable Compose test database |
| App | One Uvicorn worker; synchronous Phase 1 application unchanged |
| SQLAlchemy pool | size 5, max overflow 10, timeout 30 s |
| Seed | `20260920`; fixed clock `2030-01-01T12:00:00Z` |
| Dataset | 500 events for S1/S2/S4; 1 event for S3 |
| Warm-up | Ramp completes, then 30 s full-load warm-up; counters/resources before marker excluded |
| Repetitions | 3 for every scenario and S4 level; median reported with observed range |
| CPU semantics | API process tree only; 100% means one logical CPU, not the whole machine |
| Raw evidence | `artifacts/benchmarks/20261114T084247Z` and `20261114T091902Z` (Git-ignored) |

Every repetition reset only `eventhub_test_disposable`, ran all Alembic revisions, seeded fixed
data, started a fresh API process and stopped it afterward. The development database/volume was not
reset. Locust's quitting-hook snapshot is authoritative; periodic CSV was retained as raw evidence
but can lag the last write interval.

## Scenario definitions

- **S1:** 50 read-only users, spawn 10/s, 180 s measured. Catalogue list, city filter,
  search+category+price sort and detail are separate groups. Health is a separate 20-request
  diagnostic and is excluded from catalogue numbers.
- **S2:** original 7:3 catalogue/buyer mix, 100 users, spawn 20/s, 300 s measured, 500 events.
- **S3:** original 7:3 mix, 100 users, spawn 50/s, 120 s measured, one event; inventory invariant
  checked after every repetition.
- **S4:** S2 mix, levels `1,5,10,20,40,80`, spawn up to 10/s, 120 s measured and three
  repetitions per level. Low levels round the 7:3 weights; levels 10+ preserve them exactly.

S2/S3 tasks and wait times were not changed. Excluding one-time register/login and ramp traffic is
an explicit measurement-boundary correction, so the new percentiles describe steady state.

## Results

### S1 — read path

Across three repetitions, **84,085 measured requests** completed with no failures. The discarded
ramp/warm-up counts were 5,019 / 5,022 / 5,026.

| Group | Median req/s | p50 | p95 | p99 |
|---|---:|---:|---:|---:|
| `GET /api/events` | 65.13 | 14 ms | 37 ms | 79 ms |
| `GET /api/events?city` | 38.52 | 15 ms | 39 ms | 81 ms |
| `GET /api/events?search-filter-sort` | 25.96 | 15 ms | 40 ms | 79 ms |
| `GET /api/events/{id}` | 26.09 | 12 ms | 40 ms | 79 ms |
| **Aggregate** | **155.78** | **14 ms** | **39 ms** | **81 ms** |

Aggregate variation: throughput 155.56–155.91 req/s; p95 36–41 ms; p99 72–86 ms. API CPU
median was 68.93% mean / 90.9% peak; RSS median was 96.46 MB mean / 96.71 MB peak.

The separate health probe used 20 sequential requests per repetition. Its median-of-repetitions was
approximately p50 1.71 ms, p95 26.37 ms and p99 27.11 ms. These values are diagnostic only and are
not presented as catalogue-query performance.

### S2 — sustained mixed workload

Across three repetitions, **202,398 measured requests** completed with no unexpected failure,
5xx or timeout.

| Metric | Median | Observed range |
|---|---:|---:|
| Throughput | 226.12 req/s | 220.24–226.72 |
| p50 | 75 ms | 75–89 |
| p95 | 180 ms | 180–200 |
| p99 | 240 ms | 240–250 |
| Error rate | 0.00% | 0.00–0.00% |
| Booking `201` | 4,821/run | 4,638–4,826 |
| Booking valid `409` | 0/run | 0–0 |

CPU median was 131.30% mean / 160.6% peak (about 1.31 / 1.61 logical cores). RSS median was
105.28 MB mean / 106.23 MB peak. Warm-up discarded 7,155–7,393 requests per repetition.

### S3 — single-event contention

Across three repetitions, **87,097 measured requests** completed with no unexpected failure, 5xx
or timeout. Every inventory invariant check passed.

| Metric | Median | Observed range |
|---|---:|---:|
| Throughput | 240.82 req/s | 237.79–243.06 |
| p50 | 48 ms | 44–52 |
| p95 | 140 ms | 140–150 |
| p99 | 190 ms | 190–220 |
| Booking `201` | 1,022/run | 968–1,029 |
| Valid sold-out `409` | 1,013/run | 982–1,058 |
| Real errors | 0 | 0–0 |

Totals across repetitions were 3,019 successful booking creations and 3,053 valid sold-out
conflicts. CPU median was 125.18% mean / 155.3% peak; RSS median was 102.90 MB mean / 103.35 MB
peak. Do not infer that contention improves the system from S3 aggregate throughput: its catalogue
contains one row instead of 500, so read queries are cheaper. Booking `201` p95 was about 200 ms
versus 230 ms in S2; accurate row-lock wait is not measured, so the current run does not isolate
lock cost.

### S4 — saturation search

| Users | Median req/s (range) | p50 | p95 | p99 | Error | CPU mean | RSS mean |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 3.06 (3.05–3.29) | 11 ms | 15 ms | 16 ms | 0% | 1.73% | 86.74 MB |
| 5 | 12.63 (12.52–12.75) | 11 ms | 16 ms | 18 ms | 0% | 6.07% | 88.35 MB |
| 10 | 26.91 (26.85–27.20) | 11 ms | 16 ms | 19 ms | 0% | 12.28% | 90.14 MB |
| 20 | 53.99 (53.95–54.04) | 10 ms | 16 ms | 20 ms | 0% | 21.67% | 91.26 MB |
| 40 | 108.53 (107.98–108.98) | 10 ms | 18 ms | 42 ms | 0% | 39.15% | 94.04 MB |
| 80 | 212.05 (212.03–213.01) | 14 ms | 55 ms | 100 ms | 0% | 80.37% | 99.12 MB |

At u=80 median peak CPU was 106.0% and median peak RSS was 100.05 MB. Throughput still grew about
95% from u=40 to u=80, while p95 remained far below 1,000 ms and no errors occurred. Therefore:

> **Saturation point not reached within tested range.**

The p95/p99 rise at u=80 is a real early queueing signal, but it is not a throughput plateau or
instability. The safe ladder is not extended beyond 80 on this branch.

## Evidence-based bottleneck assessment

| Area | Status and evidence | Confidence | Alternative explanation | Smallest confirming measurement |
|---|---|---|---|---|
| CPU saturation | **Observed:** u=80 mean 80.37%, peak 106% of one core on 16 logical CPUs; throughput still rises. **Inference:** no CPU saturation in tested range. | High | Short CPU bursts may be hidden by 1 s sampling. | Retain sampler at next safe level or shorten sampling interval only if justified. |
| RSS growth | **Observed:** 86.74→99.12 MB as users rise; repetitions at each level are stable. **Inference:** bounded load-related growth, no leak evidence. | Medium | A 120 s step cannot reveal a slow leak. | One longer u=80 soak with RSS slope. |
| PostgreSQL/query latency | **Observed:** S1 query groups have p95 37–40 ms; S4 p95 rises to 55 ms at u=80. **Hypothesis:** query/DB waiting may contribute to the tail, but is not isolated. | Low | Thread scheduling, client queueing or pool acquisition can produce the same shape. | Per-request DB/query duration plus slow-query/`EXPLAIN ANALYZE` evidence. |
| Connection-pool contention | **NOT YET MEASURED.** Pool max is 15, but u=80 has no plateau/errors and p95 55 ms. | Low | Threadpool or database service time may dominate instead. | Time SQLAlchemy checkout acquisition separately from connection hold time. |
| Sync/threadpool waiting | Sync endpoints are known; near-linear S4 throughput through u=80 does not show exhaustion. | Low | Queueing may begin only above the tested range. | Request queue/threadpool wait and active-worker metrics. |
| Row-lock contention | S3 produces valid 409s, zero real errors and preserves inventory. Cross-scenario aggregate latency is confounded by 1 vs 500 events. | Medium for correctness; low for cost | Cheaper one-row catalogue masks lock waiting. | Write-only matched-dataset scenario plus PostgreSQL lock-wait timing. |
| Deep OFFSET | S1 uses pages 1–3 on 500 rows. **Unverified hypothesis; not exercised.** | None | Current pages are too shallow to show degradation. | Add a separate deep-page diagnostic on a larger deterministic catalogue; do not redefine S1. |
| Sold-out vs failures | **Observed:** S3 totals 3,019 `201`, 3,053 valid `409`, zero unexpected failures. | High | None for classification; response semantics are explicit. | Keep the same counters in AFTER runs. |
| Warm-up distortion | **Observed:** thousands of ramp/setup requests were discarded; measured stats contain no setup groups. | High | Machine background load can still affect repetitions. | Keep marker/count evidence and three repetitions. |
| Measurement variance | S1 throughput spread 0.35 req/s; S2 6.48; S3 5.27; S4 u=80 0.98. | High | Background OS activity explains some tail spread. | Compare AFTER medians and ranges on the same machine; do not claim changes inside the spread. |

## Scope for `feature/observability-foundation`

The next branch should close measurement gaps, not tune performance:

1. Correlation ID propagated into structured request logs.
2. Request duration and status metrics grouped by route template.
3. PostgreSQL readiness distinct from liveness.
4. SQLAlchemy pool acquisition wait, checkout count and connection-hold duration.
5. Minimal DB/query timing sufficient to separate pool wait from execution time.

No pool-size change, async conversion, cache or lock-strategy change is justified by this baseline.

## Limitations

- Results are local Windows measurements, not portable capacity claims for production/Kaggle.
- Baseline was run before committing as required; HEAD plus changed-path SHA-256 manifest records
  provenance. The reviewed harness/docs should be committed before an AFTER run.
- S4 stopped at the preconfigured safe maximum 80, so the actual saturation point is unknown.
- Pool, threadpool, query and lock-wait durations were not instrumented.
- S4 u=1/u=5 round workload weights; use u=10+ for like-for-like mixed-load interpretation.
- The seed is deterministic, but OS scheduling and Docker Desktop introduce normal local variance.
