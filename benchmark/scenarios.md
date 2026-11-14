# Reproducible benchmark scenarios

These definitions are the Phase 2 BEFORE contract. An AFTER comparison must keep the commit,
machine, Docker/PostgreSQL configuration, worker/pool configuration, seed, warm-up, duration,
concurrency and repetition count visible. If the workload changes, run a new BEFORE baseline.

## Fixed conditions

| Condition | Phase 2 BEFORE value |
|---|---|
| Target | Local EventHub only; runner rejects non-local API/database targets |
| Database | Compose `postgres-test`, PostgreSQL 16, `eventhub_test_disposable` on port 5433 |
| Reset | Explicit disposable-name check + destructive acknowledgement; reset, Alembic, then seed |
| Dataset | Seed `20260920`, fixed clock `2030-01-01T12:00:00Z` |
| App | Uvicorn, one worker |
| Pool | size 5, max overflow 10, timeout 30 s |
| Security cost | `BCRYPT_ROUNDS=12` |
| Warm-up | Start after all users spawn; run 30 s; discard all ramp/setup/warm-up stats |
| Repetitions | 3 per measured configuration; report median and min/max spread |
| Resources | API parent + child processes sampled every second; 100% CPU = one logical core |
| Raw output | `artifacts/benchmarks/` (ignored); reviewed summary only under `docs/` |

Run from Command Prompt:

```cmd
cd /d E:\University\Semester_7\SA\KTPM
scripts\run-benchmark.cmd --scenario s1 --scenario s2 --scenario s3
scripts\run-benchmark.cmd --scenario s4
```

Safe smoke runs use two-second warm-up, five-second measurement, one repetition and S4 levels 1,2:

```cmd
scripts\run-benchmark.cmd --scenario s1 --scenario s4 --smoke
```

The CLI also exposes `--base-url`, `--warm-up`, `--repetitions`, `--duration`, `--concurrency`,
`--s4-levels`, `--output-dir` and repeatable `--scenario`. The API URL must resolve explicitly to
localhost. The database profile is intentionally fixed to the disposable Compose test database.

## S1 — normal read path

Purpose: measure catalogue queries without bcrypt or booking mutations.

| Parameter | Value |
|---|---:|
| Users / spawn rate | 50 / 10 per second |
| Measured duration | 180 s |
| Seed events | 500 |

`ReadPathBrowser` performs distinct groups for catalogue listing, city filtering,
search+category+price sort, and event detail. A separate 20-request `/health` diagnostic is kept
out of catalogue throughput and latency.

## S2 — sustained mixed load

Purpose: retain the original main comparison workload.

| Parameter | Value |
|---|---:|
| Users / mix | 100; catalogue/buyer weight 7:3 |
| Spawn rate / measured duration | 20 per second / 300 s |
| Seed events | 500 |

The catalogue and buyer task weights/wait times are unchanged. Measurement now begins only after
one-time register/login/setup and a 30-second full-load warm-up. Booking `201` and valid `409` are
separate groups; unexpected responses remain failures.

## S3 — single-row write contention

Purpose: retain the original scarce-event workload and prove the inventory invariant.

| Parameter | Value |
|---|---:|
| Users / mix | 100; catalogue/buyer weight 7:3 |
| Spawn rate / measured duration | 50 per second / 120 s |
| Seed events | 1 |

After each repetition the runner verifies
`available_tickets + confirmed_quantity == total_tickets`. A sold-out `409` is a correct business
outcome and is reported separately from genuine infrastructure/application errors.

## S4 — safe saturation search

Purpose: find evidence of a throughput plateau, disproportionate tail latency or errors without
forcing the workstation into an unsafe state.

| Parameter | Default |
|---|---|
| Concurrency ladder | `1,5,10,20,40,80` (configurable) |
| Spawn rate | up to 10 per second |
| Measured duration | 120 s per level |
| Repetitions | 3 per level |
| Workload / seed | S2 mixed workload / 500 events |

At every level the database is reset/migrated/seeded and warm-up stats are discarded. Saturation is
the first level with error rate over 1%, p95 over 1,000 ms, or two consecutive throughput-growth
steps below 10% accompanied by at least 50% p95 growth. The runner stops after evidenced
saturation. If no rule fires, report exactly: `Saturation point not reached within tested range`.

At very low levels Locust must round the 7:3 weights (u=1 is read-only; u=5 was 3:2). Use those
points for curve shape, not endpoint-mix comparisons. Levels 10, 20, 40 and 80 preserve 7:3 exactly.

## Measurement interpretation

- Locust quitting-hook JSON is authoritative because periodic CSV can lag the final request count.
- CSV/history/status/resource files remain raw evidence and must not be edited by hand.
- CPU/RSS belong to the Uvicorn process tree, not the whole machine.
- Connection-pool acquisition wait is `NOT YET MEASURED`; accurate values require narrowly scoped
  application instrumentation on `feature/observability-foundation`.
- S2/S3 workload behavior was not changed. Excluding ramp/setup traffic is an explicit measurement
  boundary correction; old historical CSV and new steady-state numbers are not interchangeable.
