# Phase 2 team plan

## 1. Scope and working agreement

The immediate cycle prepares a measured, reliable foundation and delivers expiring Reservation,
Rate Limiting, CQRS-lite and the dependent reservation UI. EventHub remains a modular monolith and
PostgreSQL remains the inventory source of truth.

Payment, Circuit Breaker, GA/assigned-seat expansion and electronic tickets stay in the backlog for
this cycle. Do not introduce microservices, Event Sourcing, Kafka, a separate read database,
distributed inventory locks or Redis as inventory authority.

Neutral owner labels:

- **Member 1 — Integration and Platform**
- **Member 2 — Reservation and Persistence**
- **Member 3 — API Protection, Query and Frontend**

Use one branch and pull request per task. Member 1 owns final integration review; every pull request
requires at least one other member's review.

## 2. Immediate task matrix

| ID | Owner | Branch | Depends on | Expected files/modules | Acceptance criteria | Size |
|---|---|---|---|---|---|:---:|
| SETUP-01 | Member 1 | `chore/phase2-team-setup` | None | `AGENTS.md`, `CONTRIBUTING.md`, setup docs/scripts, GitHub collaboration files | Three machines can follow the same CMD onboarding; Phase 1 quality gate remains green | M |
| BENCH-01 | Member 1 | `chore/baseline-benchmark` | SETUP-01 | `benchmark/`, `docs/benchmark.md`, benchmark scripts/results | S1 and S4 are repeatable; warm-up stats reset; `201`/`409` separated; CPU/RSS and pool-wait evidence recorded; 2–3 comparable runs | L |
| OBS-01 | Member 1 | `feature/observability-foundation` | BENCH-01 contract/metrics agreed | API middleware, logging/config adapters, health/readiness, tests/docs | Correlation ID, secret-safe structured logs, PostgreSQL readiness and roadmap metrics hooks are tested | M |
| RES-01 | Member 2 | `feature/expiring-reservation` | SETUP-01; migration ownership reserved | Domain/application ports and services, ORM/repositories/UoW, Alembic, worker, API/tests/docs | `RESERVED/CONFIRMED/EXPIRED/CANCELLED`, `expires_at`, separate expiry worker, inventory restored at most once, unit/integration/PostgreSQL concurrency tests pass | XL |
| RATE-01 | Member 3 | `feature/rate-limiting` | RES-01 API entry contract approved | RateLimiter port, in-memory adapter, middleware/dependencies, config, tests/docs | Policies protect auth/search/reservation entry; `429` and `Retry-After`; no Redis; row-lock protection unchanged | M |
| CQRS-01 | Member 3 | `refactor/cqrs-lite-queries` | RES-01 contracts stable | Application query services/read DTOs, query adapters, routers/tests/docs | Catalogue, booking history and organizer dashboard queries are separated from commands while using the same PostgreSQL database; behavior preserved | L |
| UI-01 | Member 3 | `feature/reservation-ui` | RES-01 merged; RATE-01 response contract stable | `frontend/`, frontend delivery/workflow tests, frontend docs | Expiry is visible; loading/success/expiry/conflict/rate-limit states work; responsive and accessible behavior preserved | L |

Relative sizes are planning aids: `M` is a focused pull request, `L` needs contract coordination,
and `XL` should still be delivered as one vertical slice but may require review checkpoints.

## 3. Detailed ownership

### Member 1 — Integration and Platform

- Integrate approved branches into `main` and review cross-cutting changes.
- Maintain CI, setup documentation and development wrappers.
- Complete S1/S4, resource sampling, pool-wait measurement, warm-up reset, response-code split and
  repeated comparable runs.
- Add correlation IDs, secret-safe structured logging, PostgreSQL readiness and minimum metrics
  hooks in a separate branch from benchmark work.
- Do not combine BENCH-01 and OBS-01 in one pull request.

### Member 2 — Reservation and Persistence

- Own the only active Alembic migration chain for the immediate cycle.
- Implement the complete expiring Reservation vertical slice: domain invariant, application service,
  port, repository, Unit of Work integration, API contract and separate expiry worker.
- Preserve PostgreSQL transaction/row-lock correctness and restore inventory at most once.
- Add unit, integration and real PostgreSQL concurrency evidence.
- Update API, architecture and testing documentation.

### Member 3 — API Protection, Query and Frontend

- Deliver Rate Limiting, CQRS-lite and reservation UI as three separate branches and pull requests.
- Rate Limiting starts with an in-memory adapter for the current single-instance environment; do not
  add Redis in this cycle.
- CQRS-lite separates application command/query responsibilities but retains the same PostgreSQL
  database; do not add Event Sourcing, a broker or a second database.
- Start UI-01 only after the reservation API is approved. Cover expiry, conflict and rate-limit
  states with workflow tests and evidence.

## 4. Dependencies and merge order

Required merge order:

1. `chore/phase2-team-setup`
2. `chore/baseline-benchmark`
3. `feature/observability-foundation`
4. `feature/expiring-reservation`
5. `feature/rate-limiting`
6. `refactor/cqrs-lite-queries`
7. `feature/reservation-ui`

Preparation may happen in parallel only when tasks do not modify the same contract or shared file.
Before final verification, update every branch from the latest `main`. A dependent branch must not
merge before its prerequisite contract is stable.

## 5. Shared-file coordination

Coordinate ownership of:

- `app/config.py`
- `app/main.py`
- `app/application/ports.py`
- `app/infrastructure/db/orm.py`
- `app/infrastructure/db/repositories.py`
- `tests/unit/fakes.py`
- `docker-compose.yml`
- `pyproject.toml` and `uv.lock`
- `alembic/versions/`
- OpenAPI and architecture documentation

Only one member actively changes a shared file for the same milestone. When two tasks need it,
define the smallest interface first, merge the foundational change, then update the dependent branch.

## 6. Review and definition of done

Every task must meet its listed acceptance criteria and the repository definition of done in
`CONTRIBUTING.md`. Pull requests must include reproducible commands/results, migration and API
impact, security considerations, documentation updates and frontend evidence when applicable.

Inventory, Reservation, cancellation or expiry concurrency changes require PostgreSQL tests with
zero relevant skips. Temporary servers and disposable test containers must be stopped or removed
safely after verification.

## 7. Backlog after the immediate cycle

Do not schedule these until the merge sequence above is accepted and stable:

- Payment integration and idempotent webhook handling.
- Circuit Breaker around the external payment adapter.
- GA ticket types and assigned seats.
- Electronic ticket/QR issuance.
- Redis-backed distributed Rate Limiting or Virtual Queue, unless later benchmark evidence justifies
  them.

