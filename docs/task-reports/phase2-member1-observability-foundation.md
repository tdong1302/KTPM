# Phase 2 Member 1 task report — observability foundation

## Scope and architecture

Implemented correlation ID, structured API/worker events, database readiness, low-cardinality
Prometheus text metrics, public-event SQLAlchemy timing and worker lifecycle observability. The
change stays in API/composition/infrastructure adapters; domain/application imports and all Unit of
Work, row-lock, transaction, pool-size and worker-batch semantics remain unchanged. No dependency,
migration, database constraint or frontend feature was added.

Initial safety state was branch `feature/observability-foundation`, HEAD `4d4d496`, clean worktree,
with merged benchmark baseline present.

## Contracts and semantics

- `X-Request-ID`: preserve conservative caller values up to 64 characters; otherwise generate a
  secure 32-hex ID; return it on success and errors; isolate/reset with `ContextVar`.
- API event fields: timezone timestamp, level, logger, event, correlation ID, method, route template,
  status and duration. No body, query string, Authorization, cookie, token, password, exception
  message or database URL is logged.
- `/health`: unchanged lightweight liveness. `/ready`: `SELECT 1`, `200 READY` or safe
  `503 NOT_READY`. `/metrics`: operational Prometheus text; production access must be network or
  reverse-proxy restricted.
- HTTP labels are bounded to normalized method, FastAPI route template and status class. Query
  labels are only `success`/`error`; IDs, email, claims and correlation IDs are never labels.
- Exact DB measurements: successful connection count, dialect connection creation duration,
  completed checkout count, current checked-out/overflow gauges, checkout-to-check-in hold duration,
  and cursor execution duration/outcome.
- Pool acquisition wait is **NOT YET MEASURED**. Checkout occurs after acquisition; hold duration is
  not renamed or presented as wait.
- Worker events cover start, batch ID/size/examined/completed/duration, safe failure type, shutdown
  request and stop. The poll interval remains 60 seconds; wait is sliced to at most 0.5 seconds so
  PID 1 can process SIGTERM within Docker's grace period without changing poll cadence.

OpenAPI intentionally changes from 16 business operations to 18 total operations by adding
`/ready` and `/metrics`.

## Files

Created `app/observability/`, `app/api/routers/operations.py`, focused observability tests, the
benchmark comparison and this report. Updated the API middleware/composition root, exception logs,
engine instrumentation hook, worker, one log-format setting, API/architecture/testing/setup/
benchmark documentation, README and `.env.example`.

## Verification evidence

- Frozen sync with `dev` + `bench`: passed, no lockfile change.
- Ruff check and format: passed.
- SQLite-backed suite during development: 275 passed, 7 expected PostgreSQL skips before the final
  worker shutdown test was added.
- Final quality gate: 284/284 passed, including 7/7 PostgreSQL concurrency tests; 97.68% coverage.
- Alembic repository/database: `e7b4a9c21d60 (head)`, exactly one head; no migration added.
- Compose validation, Docker image build, PostgreSQL smoke and SQLite demo: passed.
- Container endpoints `/health`, `/ready`, `/app/`, `/docs`, `/openapi.json`, `/metrics`: 200.
- Real DB failure: `/health` stayed 200 while `/ready` returned 503; readiness returned 200 after
  restart. Development volume was preserved.
- Worker one-shot: passed. Delayed Compose SIGTERM: shutdown request/stop logs present, exit code 0.
- Label/cardinality and redaction tests: passed; live metrics showed route templates, not IDs.

Post-benchmark `scripts\quality-gate.cmd` passed all eight steps: frozen sync, local preflight,
format, Ruff, Compose, development migration/current/10 constraints, full PostgreSQL coverage suite
and Git whitespace. Final status remains intentionally uncommitted and is reported at handoff.

## Benchmark overhead

See [`../benchmark-observability-overhead.md`](../benchmark-observability-overhead.md). The original
high-latency AFTER run was not reproducible. A controlled A-D matrix separately disabled completion
request logging, HTTP metrics and SQL cursor timing; no component reproduced or explained the
118.18% S4 p95 jump. Empty API log files also reject duplicate access-log or console-output I/O in
the runner. The most defensible cause is transient host-load contamination, although the external
process was not captured.

The smallest retained optimization changes histogram observation from updating every cumulative
bucket under the hot-path lock to one binary-search-selected bucket; cumulative Prometheus output is
computed when `/metrics` is rendered and is covered by a deterministic test. No metric was disabled
or sampled. The final full-observability run used three repetitions: S1 157.91 req/s and 26 ms p95;
S4 u=80 210.58 req/s and 63 ms p95; zero errors. Against BEFORE, throughput changed +1.37% and
−0.69%, while S4 p95 changed +14.55%, inside the preferred 15% bound. Saturation was not reached.

## Remaining risks

- Exact pool acquisition and threadpool wait are unavailable.
- `/metrics` needs deployment-layer restriction; no Prometheus/Grafana/OTel deployment is claimed.
- Performance evidence is local-host evidence, not a production capacity claim. Repeat on a quiet,
  dedicated runner before setting an SLO or capacity target.
