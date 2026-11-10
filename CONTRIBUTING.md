# Contributing to EventHub

EventHub is developed as a modular monolith. Keep changes small, measurable and reviewable; one
branch and one pull request should have one acceptance goal.

## Initial setup on Windows

Open Command Prompt and run:

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

Replace the local JWT placeholder privately before using the environment outside local development.
Do not print or commit `.env`. See [docs/local-machine-setup.md](docs/local-machine-setup.md) for
tool versions, troubleshooting, worker and shutdown instructions.

## Branches and commits

Create a new branch from updated `main` for every task:

```cmd
git switch main
git pull --ff-only origin main
git switch -c feature/example-slice
```

Allowed prefixes:

- `feature/` for a user-visible or business capability.
- `fix/` for a defect.
- `refactor/` for behavior-preserving restructuring.
- `test/` for test-only work.
- `docs/` for documentation-only work.
- `chore/` for tooling, CI and repository maintenance.

Use concise Conventional Commit messages, for example:

```text
feat: add expiring reservation
fix: prevent duplicate inventory release
test: cover concurrent reservation expiry
docs: document Phase 2 setup
chore: standardize local verification
```

Never push directly to `main`, force-push a branch used by another member, or mix unrelated changes
in one pull request.

## Pull request process

1. Update the branch from the latest `main` before final verification.
2. Review `git status --short`, `git diff` and `git diff --check`.
3. Run the checks appropriate to the change; inventory/concurrency work requires PostgreSQL tests
   with zero relevant skips.
4. Update documentation and API contracts in the same pull request.
5. Complete every applicable section of the pull request template and include reproducible evidence.
6. Request at least one review. Member 1 performs the final integration review for Phase 2.

Prefer a small pull request that can be reverted independently. Do not share one feature branch
between members.

## Required checks

The standard local quality gate is:

```cmd
scripts\quality-gate.cmd
```

Equivalent individual commands are:

```cmd
uv sync --frozen --extra dev
uv run --frozen ruff format --check .
uv run --frozen ruff check .
docker compose config --quiet
scripts\run-tests.cmd --with-db
uv run --frozen python -m alembic heads
uv run --frozen python -m alembic current
git diff --check
```

Coverage must remain at or above 95%. New tests may increase the historical count, so do not assert
that the suite must remain exactly 257 tests.

## Alembic migration coordination

- Member 2 is the sole migration owner during the immediate Phase 2 cycle.
- Update from the latest `main` immediately before generating or writing a revision.
- Keep exactly one Alembic head. Never rewrite an applied/shared revision to remove a conflict.
- Verify both repository and database state:

```cmd
uv run --frozen python -m alembic heads
uv run --frozen python -m alembic current
```

- Test `upgrade head` from an empty disposable PostgreSQL database.
- Never point destructive fixtures at a shared or valuable database.

## Shared files

Coordinate before changing:

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

When two tasks need the same shared contract, agree on the interface first and merge the foundational
change before finalizing the dependent branch.

## Documentation rules

- API changes update `docs/api.md` and relevant request/response examples.
- Architectural decisions update `docs/architecture.md` or the approved Phase 2 document.
- Test strategy or commands update `docs/testing.md`.
- Setup, environment or script changes update `docs/local-machine-setup.md` and README links.
- Frontend behavior changes include workflow tests, accessible/responsive verification and screenshot
  or demo evidence.

## Definition of done

A task is complete only when its acceptance criteria are met, existing tests pass, appropriate new
tests exist, Ruff/format checks pass, migrations are verified where relevant, documentation is
current, no secret or local artifact is tracked, the branch is current with `main`, and the pull
request includes reproducible evidence. Temporary servers, disposable test containers and generated
artifacts must be stopped or cleaned safely.

