# BENCH-01 — Member 1 baseline benchmark report

Outcome: **COMPLETE** for benchmark implementation/execution; no optimization or observability
feature was added.

## Scope

- Added S1 read-only and S4 configurable step-load execution to the existing Locust framework.
- Preserved S2/S3 tasks and wait times; moved measurement start after ramp/setup and 30 s warm-up.
- Added exact final Locust snapshot, `201`/valid `409` classification, repetitions/median/range,
  API-process CPU/RSS sampling, deterministic seed clock and destructive-target safety.
- Ran S1–S4 against the disposable PostgreSQL test database and reviewed the evidence.
- Documented evidence-based hypotheses and the next observability-only scope.

## Files

Created:

- `benchmark/run_baseline.py`
- `benchmark/support.py`
- `scripts/run-benchmark.cmd`
- `tests/unit/test_benchmark_support.py`
- `docs/benchmark-baseline-phase2.md`
- `docs/task-reports/phase2-member1-baseline-benchmark.md`

Modified:

- `.gitignore`
- `benchmark/locustfile.py`
- `benchmark/seed_data.py`
- `benchmark/scenarios.md`
- `benchmark/kaggle/run_baseline.py`
- `benchmark/results/README.md`
- `docs/benchmark.md`
- `docs/testing.md`
- `README.md`

No `app/`, Alembic revision, database constraint, API contract, auth/RBAC, frontend, pool size,
runtime dependency or lockfile changed. OpenAPI behavior is unchanged.

## Verification and measured result

Commands executed from Command Prompt:

```cmd
uv sync --frozen --extra dev --extra bench
uv run --frozen ruff check benchmark tests\unit\test_benchmark_support.py
uv run --frozen pytest tests\unit\test_benchmark_support.py -q
scripts\run-benchmark.cmd --scenario s1 --scenario s4 --smoke
scripts\quality-gate.cmd
scripts\run-benchmark.cmd --scenario s1 --scenario s2 --scenario s3
scripts\run-benchmark.cmd --scenario s4
```

Results available at handoff:

- Benchmark helper tests: 13 passed after endpoint aggregation test was added.
- Pre-baseline quality gate: 269 passed, 7 PostgreSQL concurrency tests, 97.81% coverage.
- Final post-documentation quality gate: 270 passed, 7 PostgreSQL concurrency tests, 97.81%
  coverage.
- S1 median: 155.78 req/s, p95 39 ms, no error.
- S2 median: 226.12 req/s, p95 180 ms, no error.
- S3 median: 240.82 req/s, p95 140 ms; totals 3,019 `201`, 3,053 valid `409`, zero real
  errors; invariant passed every repetition.
- S4 median at u=80: 212.05 req/s, p95 55 ms, p99 100 ms, no error.
- Saturation point not reached within tested range.
- Pool acquisition wait: `NOT YET MEASURED`.

Final Git diff/status is recorded in the chat handoff because it must reflect the complete working
tree after this report is written.

## Risks and next branch

The baseline is local-machine evidence, not a production capacity claim. The actual saturation
point is above the tested safe ladder or depends on a different workload. S3 aggregate numbers are
confounded by the one-event catalogue, so row-lock cost needs a matched workload before tuning.

Proposed `feature/observability-foundation` scope:

1. Correlation ID and structured request logs.
2. Route-template request duration/status metrics.
3. PostgreSQL readiness separate from liveness.
4. SQLAlchemy pool acquisition/checkout/hold timing.
5. Minimal DB/query timing needed to separate pool, execution and threadpool waiting.

Do not change pool sizes, convert to async, add caching or replace the row lock based on the current
hypotheses alone.
