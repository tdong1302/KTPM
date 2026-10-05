# Local Windows machine setup

This repository supports local development on Windows through **Command Prompt (`cmd.exe`)**.
The application is a FastAPI REST API; Swagger at `/docs` is developer documentation, not an
end-user frontend.

## Supported setup and verified versions

Verified on Windows 10 build `10.0.26200.9457` with:

| Tool | Verified version |
|---|---|
| Git for Windows | 2.45.1.windows.1 |
| uv | 0.12.13 |
| Python managed by uv | 3.11.16 |
| Docker Engine CLI | 29.4.0 |
| Docker Compose v2 | 5.1.1 |
| PostgreSQL image | 16 Alpine |
| WSL | WSL2; Ubuntu 22.04 is present |

Python 3.11 is selected by `.python-version`. The existing global Python installations do not need
to be removed or changed. Dependencies are installed from `uv.lock` without re-locking.

## Initial setup

Open **Command Prompt**, then run:

```cmd
cd /d E:\University\Semester_7\SA\KTPM
scripts\setup-local.cmd
```

The setup wrapper checks Git and uv, runs `uv sync --frozen --extra dev`, validates `.env` without
printing values, and reports whether Docker Desktop is running.

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

The expected migration head is `c4d2f3a1b890`. `scripts\run-dev.cmd` performs these startup and
migration checks automatically before starting Uvicorn.

## Start the API

```cmd
cd /d E:\University\Semester_7\SA\KTPM
scripts\run-dev.cmd
```

Open:

- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/openapi.json`

Press `Ctrl+C` in the CMD window to stop Uvicorn.

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
- **Migration fails:** run `docker compose ps` and `docker compose logs postgres`, confirm the
  development database is healthy, then rerun Alembic.
- **Concurrency tests skip:** use `scripts\run-tests.cmd --with-db`; it sets both the disposable
  test URL and `REQUIRE_POSTGRES_TESTS=1`.

## Verification status and remaining blockers

This host is **READY**. Docker Desktop started without UAC or restart, PostgreSQL 16 became healthy,
an empty development database migrated to `c4d2f3a1b890`, and the PostgreSQL-backed API served
health, OpenAPI, and Swagger successfully. The complete suite collected and passed 164 tests,
including all five PostgreSQL concurrency tests, with 97.63% measured coverage (98% rounded).

There are no remaining setup blockers. No Windows optional feature, BIOS setting, global Python
default, or application architecture was changed. If Docker Desktop is not configured to start
automatically, starting it after a reboot is the only manual host step.
