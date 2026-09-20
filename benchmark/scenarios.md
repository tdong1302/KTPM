# Load test scenarios

These scenarios are fixed so that Phase 1 (BEFORE) and Phase 2 (AFTER) measure the same
thing. Do not change them between runs. If a scenario must change, record why and re-run
the baseline.

## Fixed conditions

Every run must hold these constant and record them next to the results:

| Condition | Value |
|---|---|
| Hardware | Kaggle CPU notebook (record the exact CPU model and core count from `lscpu`) |
| Database | PostgreSQL 16, local to the runner |
| Dataset | `python benchmark/seed_data.py --reset --events 500` (fixed random seed `20260920`) |
| App server | `uvicorn app.main:app --workers 1` unless the scenario says otherwise |
| `BCRYPT_ROUNDS` | 12 |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` | 5 / 10 |
| Warm-up | 30 s discarded before measurement |

Record the git commit hash of the code under test with every result.

## Workload mix

`benchmark/locustfile.py` defines two user classes, weighted 7:3:

- **CatalogueBrowser** (weight 7) - anonymous reads: event listing, filtered listing,
  event detail.
- **TicketBuyer** (weight 3) - registers, logs in, then reads `/api/bookings/me` and
  performs contended `POST /api/bookings` with occasional cancellations.

A `409 Conflict` on booking means "sold out", which is a correct business outcome under
contention. The locustfile marks it as a success on purpose; counting it as an error
would make the error rate meaningless.

## Scenarios

### S1 - Read-heavy baseline
Purpose: establish latency and throughput of the public catalogue.

| Parameter | Value |
|---|---|
| Users | 50 |
| Spawn rate | 10 /s |
| Duration | 3 min |

```
locust -f benchmark/locustfile.py --headless --host http://localhost:8000 \
       --users 50 --spawn-rate 10 --run-time 3m --csv benchmark/results/s1-baseline
```

### S2 - Sustained mixed load
Purpose: the main before/after comparison point.

| Parameter | Value |
|---|---|
| Users | 100 |
| Spawn rate | 20 /s |
| Duration | 5 min |

```
locust -f benchmark/locustfile.py --headless --host http://localhost:8000 \
       --users 100 --spawn-rate 20 --run-time 5m --csv benchmark/results/s2-baseline
```

### S3 - Write contention on a scarce event
Purpose: measure the cost of the row lock that prevents overselling.

Seed a single event with a small inventory and point the buyers at it:

```
python benchmark/seed_data.py --reset --events 1
locust -f benchmark/locustfile.py --headless --host http://localhost:8000 \
       --users 100 --spawn-rate 50 --run-time 2m --csv benchmark/results/s3-baseline
```

Alongside latency, assert the correctness invariant after the run:
`tickets_sold + available_tickets == total_tickets`.

### S4 - Saturation search
Purpose: find the point where p95 latency exceeds 1 s or the error rate exceeds 1 %.

Step the user count: 25, 50, 100, 200, 400. Two minutes per step. Record the last step
that stayed within the thresholds; that number is the baseline capacity.

## Metrics to record

| Metric | Source |
|---|---|
| Throughput (req/s) | locust `*_stats.csv`, aggregated row |
| p50 / p95 / p99 latency | locust `*_stats.csv` per endpoint |
| Error rate | locust `*_failures.csv` |
| CPU and RSS of the API process | `psutil` sampler, or `top -b` during the run |
| Correctness invariant (S3) | SQL query after the run |

Write the numbers into `docs/benchmark.md` only after an actual run, and keep the raw
CSV files under `benchmark/results/`.
