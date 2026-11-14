# Phase 2 observability overhead: controlled recheck

## Decision

The observability slice is **READY** on the measured performance gate. The final three-repetition
run had zero errors, S1 throughput was 1.37% above BEFORE, and S4 u=80 throughput was 0.69% below
BEFORE. S4 p95 was 63 ms, 14.55% above BEFORE and inside the preferred 15% bound.

The earlier S4 result of 197.66 req/s and 120 ms p95 was not reproducible. Controlled ablations do
not identify request logging, HTTP metrics or SQL query timing as a source of that magnitude. The
most defensible diagnosis is a contaminated/outlier benchmark run caused by transient host load;
the exact external load source was not captured, so this is evidence-backed but not process-level
attribution.

## Comparable protocol

BEFORE, the recheck, every ablation and the final run used the same Windows host, disposable
PostgreSQL database, deterministic 500-event seed, one Uvicorn worker, SQLAlchemy pool `5 + 10`,
30-second post-ramp warm-up and the existing Locust workloads. S1 used 50 users for 180 measured
seconds. S4 used 80 users for 120 measured seconds. A-D used two repetitions; the final result used
three.

- BEFORE source: [`benchmark-baseline-phase2.md`](benchmark-baseline-phase2.md).
- Original anomalous AFTER evidence (Git-ignored): `artifacts\benchmarks\20261114T134327Z`.
- A-D evidence (Git-ignored): `artifacts\benchmarks\ablation\...`.
- Final evidence (Git-ignored):
  `artifacts\benchmarks\observability-final\20261114T200356Z`.
- Commit provenance: `4d4d496`; dirty worktree is expected because this task is intentionally
  uncommitted.
- Pool acquisition wait: **NOT YET MEASURED**. Checkout-to-check-in hold time is measured but is
  not acquisition wait.

The runner starts Uvicorn with `--log-level warning`. Both original AFTER API log files were empty,
so access-log duplication and console I/O are rejected for these benchmark runs. Structured event
construction still executes, but no handler writes the completion records in this runner.

## Hypotheses and ablations

| Variant | Change from A | S1 req/s / p95 / p99 | S1 CPU mean / peak | S4 req/s / p95 / p99 | S4 CPU mean / peak | Result |
|---|---|---:|---:|---:|---:|---|
| A full | None | 157.30 / 27.5 / 71.5 ms | 57.14% / 83.95% | 211.37 / 63 / 105 ms | 83.63% / 106.10% | Recheck; zero errors |
| B no completion request log | Request completion event disabled | 157.55 / 25 / 64 ms | 56.86% / 76.35% | 211.01 / 65 / 110 ms | 84.05% / 106.10% | No material improvement; logging rejected as primary cause |
| C no HTTP metrics | Per-request HTTP counters/gauges/histogram disabled | 157.59 / 27 / 71.5 ms | 56.76% / 80.80% | 211.94 / 58.5 / 100 ms | 81.85% / 104.65% | Small S4 signal, but throughput unchanged and two-run ranges are insufficient for causal attribution |
| D no query timing | SQL cursor count/duration/error hooks disabled | 157.94 / 25 / 64 ms | 56.56% / 75.60% | 211.75 / 62 / 105 ms | 83.41% / 106.85% | No material improvement; query timing rejected as primary cause |

RSS means stayed tightly bounded: S1 95.43-95.98 MB and S4 99.07-99.65 MB across A-D. All valid
A-D repetitions had zero errors and no S4 saturation. A failed B attempt was excluded: an orphaned
API from an interrupted tool session held port 8000, the replacement could not bind, and Locust
subsequently lost the old process. B was rerun from a verified clean port and completed normally.

Other common-path work (route-template resolution, correlation `ContextVar` and pool lifecycle
metrics) remained enabled in all variants. Operational endpoints were not part of the measured
Locust groups. These facts, plus the near-identical A-D throughput, make them implausible causes of
the original 118% p95 jump, although this matrix was not designed to measure each one separately.

## Small mitigation

The HTTP duration histogram previously incremented every matching cumulative bucket while holding
the registry lock. It now uses binary search and increments only one non-cumulative bucket during
request processing; cumulative Prometheus buckets are produced during the much less frequent
`/metrics` render. A deterministic test verifies boundary, cumulative and `+Inf` behavior.

This reduces hot-path work without sampling, disabling or changing any metric contract. The final
benchmark does not show a material end-to-end gain over A, so this report treats it as a bounded
algorithmic improvement, not as the explanation for the anomalous run.

## Final result

| Scenario | BEFORE req/s → final | Δ req/s | BEFORE p95 → final | Δ p95 | BEFORE p99 → final | Final range req/s / p95 | Errors |
|---|---:|---:|---:|---:|---:|---:|---:|
| S1 u=50 | 155.78 → 157.91 | +1.37% | 39 → 26 ms | −33.33% | 81 → 66 ms | 157.82-158.23 / 25-26 ms | 0 |
| S4 u=80 | 212.05 → 210.58 | −0.69% | 55 → 63 ms | +14.55% | 100 → 110 ms | 210.06-212.36 / 63-65 ms | 0 |

Final resource medians were S1 CPU 58.19%, peak 81.60%, RSS mean 95.67 MB, peak 96.16 MB; S4 CPU
83.90%, peak 107.70%, RSS mean 99.44 MB, peak 100.02 MB. S4 saturation was not reached.

The original AFTER numbers remain historical evidence but are superseded for the merge decision by
the controlled recheck, component ablations and final three-repetition confirmation. No application,
pool, query, transaction, migration or business behavior was tuned to obtain this result.
