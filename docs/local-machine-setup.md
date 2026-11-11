# Local Windows machine setup

This repository supports local development on Windows through **Command Prompt (`cmd.exe`)**.
The end-user frontend is served at `/app/`; Swagger at `/docs` remains developer documentation.

## Supported setup and verified versions

The supported baseline is Windows 10 or 11 with WSL2 optional. The current repository/host audit
verified:

| Tool | Verified version |
|---|---|
| Git for Windows | 2.45.1.windows.1 |
| uv | 0.12.13 |
| Python managed by uv | 3.11.16 |
| Docker Engine CLI | 29.8.2; 29.4.0 or compatible is supported |
| Docker Compose v2 | 5.5.1; 5.1.1 or compatible is supported |
| PostgreSQL | 16.15 in the current `postgres:16-alpine` container |
| WSL2 | Optional; not required for the normal CMD workflow |

`.python-version` selects the Python 3.11 line; the current uv-managed project interpreter is
3.11.16. `Dockerfile` pins uv 0.12.13, while Compose intentionally pins PostgreSQL major version 16
through `postgres:16-alpine`. Existing global Python installations do not need to be removed or
changed.

Important versions locked by `uv.lock`:

| Package | Locked version |
|---|---:|
| FastAPI | 0.142.2 |
| Uvicorn | 0.54.0 |
| SQLAlchemy | 2.1.3 |
| Alembic | 1.20.0 |
| Pydantic | 2.13.5 |
| pydantic-settings | 2.15.0 |
| Psycopg | 3.3.6 |
| PyJWT | 2.15.1 |
| bcrypt | 4.3.0 |
| pytest | 8.4.2 |
| pytest-cov | 6.3.0 |
| Ruff | 0.16.10 |

`pyproject.toml` and `uv.lock` are canonical. Do not manually maintain `requirements.txt` or
silently upgrade these packages.

## Initial setup

Open **Command Prompt**, then run the complete first-time sequence:

```cmd
cd /d E:\University\Semester_7\SA\KTPM
copy .env.example .env
uv sync --frozen --extra dev
scripts\verify-local.cmd
docker compose up -d postgres
uv run --frozen python -m alembic upgrade head
scripts\run-tests.cmd --with-db
scripts\run-dev.cmd
```

`scripts\run-dev.cmd` remains attached to the foreground Uvicorn process. Open a second CMD window
for tests or the worker. For subsequent setup checks, the idempotent wrapper is:

```cmd
cd /d E:\University\Semester_7\SA\KTPM
scripts\setup-local.cmd
```

The setup wrapper checks Git and uv, synchronizes the frozen development environment, validates
`.env` structurally without displaying values and reports Docker availability. It does not install
or modify machine-wide Git, Python, Docker or PostgreSQL.

If uv is missing and `winget` is available, install the official package from a new CMD window:

```cmd
winget install --id=astral-sh.uv -e
uv python install 3.11
```

If `winget` is unavailable, use the official uv installer documented at
`https://docs.astral.sh/uv/getting-started/installation/`, then reopen CMD so PATH is refreshed.

## Local `.env`

`.env` is ignored by Git and must never be committed. It contains local PostgreSQL connection
settings, pool settings, token lifetime, bcrypt cost, and a private JWT signing secret. The local
file should use `ENVIRONMENT=local`, PostgreSQL on port 5432, and `DB_AUTO_CREATE=false`; Alembic
owns the PostgreSQL schema. Never paste its JWT secret, password, or full database URL into logs or
reports.

To confirm only that the file is ignored:

```cmd
git check-ignore .env
```

## SQLite functional demo

Docker is not required:

```cmd
cd /d E:\University\Semester_7\SA\KTPM
scripts\run-demo.cmd
```

The wrapper delegates to the existing reproducible demo runner. It uses a separate SQLite file,
starts Uvicorn on port 8765, runs the API journey, writes redacted reports under `artifacts\demo`,
and stops its temporary server.

## PostgreSQL and Alembic

Start Docker Desktop and wait until it reports that the engine is running. Then:

```cmd
cd /d E:\University\Semester_7\SA\KTPM
docker compose config
docker compose up -d postgres
uv run --frozen python -m alembic upgrade head
uv run --frozen python -m alembic current
```

The expected migration head is `8d2fe144b7c0`. `scripts\run-dev.cmd` performs these startup and
migration checks automatically before starting Uvicorn.

## Start the API

```cmd
cd /d E:\University\Semester_7\SA\KTPM
scripts\run-dev.cmd
```

Open:

- `http://127.0.0.1:8000/app/`
- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/openapi.json`

Press `Ctrl+C` in the CMD window to stop Uvicorn.

## Automatic completion worker

Run all currently due events and exit:

```cmd
scripts\run-completion-worker.cmd --once
```

Run continuously at the configured interval, then stop gracefully with `Ctrl+C`:

```cmd
scripts\run-completion-worker.cmd
```

The defaults are `EVENT_COMPLETION_POLL_SECONDS=60` and
`EVENT_COMPLETION_BATCH_SIZE=100`. With Compose, `docker compose up -d api worker` starts both
processes from the same image; `docker compose stop worker` leaves API and PostgreSQL running.

## Tests and quality checks

Run the normal SQLite-backed suite:

```cmd
scripts\run-tests.cmd
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen pytest --junitxml=test-results.xml --cov=app --cov-report=term-missing --cov-report=xml --cov-fail-under=95
```

Run the full suite including all PostgreSQL concurrency tests:

```cmd
scripts\run-tests.cmd --with-db
```

Run the complete local quality gate used before a pull request:

```cmd
scripts\quality-gate.cmd
```

It synchronizes locked dependencies, runs Ruff and formatting, validates Compose, migrates the
development database, verifies the Alembic state/constraints, runs the full PostgreSQL suite with
coverage and checks Git whitespace. It stops the disposable test database afterward but preserves
the development PostgreSQL volume.

**Safety warning:** the concurrency fixture calls `drop_all()`. The CMD wrapper deliberately uses
only the Compose database `eventhub_test_disposable` on port 5433. Never set `TEST_DATABASE_URL` to
the development database, a shared database, staging, production, or any database with valuable
data.

## Stop services

Keep development PostgreSQL data while stopping containers:

```cmd
docker compose down
docker compose --profile test down
```

Do not add `-v` unless the development volume has been positively identified as disposable;
`docker compose down -v` deletes it.

## Resume after reboot

1. Start Docker Desktop and wait for the engine to be ready.
2. Open CMD.
3. Run `cd /d E:\University\Semester_7\SA\KTPM`.
4. Run `scripts\run-dev.cmd` for PostgreSQL development, `scripts\run-demo.cmd` for the isolated
   SQLite demo, or `scripts\run-tests.cmd --with-db` for the complete test suite.

## Troubleshooting

- **`docker info` cannot connect:** Docker Desktop is installed but stopped. Start it, wait for the
  engine, then retry. WSL2 and the Docker Desktop WSL distro must be available.
- **Port 5432 is occupied:** stop the conflicting local service or set a coordinated alternative
  `POSTGRES_PORT` and matching `DATABASE_URL` in `.env`.
- **Port 8000 is occupied:** stop the other process before `run-dev.cmd`.
- **Port 8765 is occupied:** run `scripts\run-demo.cmd -Port 8877`.
- **Frozen sync fails:** do not regenerate `uv.lock` casually. Confirm Python 3.11 and uv 0.12.13,
  then retry `uv sync --frozen --extra dev`.
- **Stale or wrong virtual environment:** remove only the project `.venv` after confirming its
  absolute path is inside this repository, then rerun `uv sync --frozen --extra dev`. Do not alter
  the global Python installation.
- **Migration fails:** run `docker compose ps` and `docker compose logs postgres`, confirm the
  development database is healthy, then rerun Alembic.
- **Concurrency tests skip:** use `scripts\run-tests.cmd --with-db`; it sets both the disposable
  test URL and `REQUIRE_POSTGRES_TESTS=1`.
- **Worker one-shot exits nonzero:** confirm PostgreSQL is healthy and Alembic is at head, then run
  it again. Continuous mode logs an exception type and waits for the next poll instead of spinning.

## Verification status and remaining blockers

This host is **READY**. Docker Desktop started without UAC or restart, PostgreSQL 16 became healthy,
a development database migrated to `e7b4a9c21d60`, and the PostgreSQL-backed API and completion
worker started independently. The complete suite collected and passed 257 tests, including all
seven PostgreSQL concurrency tests, with 97.56% measured coverage.

There are no remaining setup blockers. No Windows optional feature, BIOS setting, global Python
default, or application architecture was changed. If Docker Desktop is not configured to start
automatically, starting it after a reboot is the only manual host step.

## Reservation expiry worker

After applying `uv run --frozen python -m alembic upgrade head`, run the expiry worker
from a separate Command Prompt for local development.

```cmd
uv run --frozen python -m app.workers.reservation_expiry
```

Use `--once` to reclaim currently due holds and exit. The continuous worker polls every
five seconds when idle and can be stopped with Ctrl+C. Docker Compose starts the
`reservation-expiry` service after migrations succeed. View its logs with
`docker compose logs reservation-expiry`. Before downgrading the reservation revision,
stop reservation traffic and let the worker reclaim all holds.
