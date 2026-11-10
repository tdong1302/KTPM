# EventHub repository instructions

These instructions apply to the entire repository.

## Architecture

- Keep EventHub a modular monolith using Ports and Adapters.
- Dependency direction is `api -> application -> domain`; infrastructure implements application
  ports. `app/domain` and `app/application` must not import FastAPI, Pydantic, SQLAlchemy, Alembic,
  Psycopg, JWT or bcrypt implementations.
- PostgreSQL is the source of truth for inventory and transactional state. A cache, Redis adapter or
  frontend value must never make the final inventory decision.
- Keep one transaction per write use case through the Unit of Work. Preserve row-lock and database
  constraint guarantees unless a measured replacement proves the same invariants.
- Implement one vertical slice per task. Do not introduce microservices, Event Sourcing, Kafka, a
  separate read database or distributed inventory locks without an explicitly approved task.

## Local commands

- User-facing Windows instructions must use Command Prompt (`cmd.exe`). Do not give PowerShell
  commands unless an existing repository wrapper invokes PowerShell internally.
- Run commands from `E:\University\Semester_7\SA\KTPM` or use the repository CMD wrappers.
- Do not read, print or paste `.env`, secrets, JWTs, passwords or complete connection URLs.

## Dependencies and migrations

- `pyproject.toml` and `uv.lock` are canonical. Normally install with
  `uv sync --frozen --extra dev`; do not hand-maintain `requirements.txt`.
- Do not upgrade or add dependencies unless the task requires it. If dependencies change, update
  both `pyproject.toml` and `uv.lock` intentionally and explain why.
- Only one task may own the Alembic chain at a time. Never edit or delete a shared/applied migration
  to resolve a conflict.
- Before creating a migration, update from current `main`. Afterward verify `alembic heads`, migrate
  an empty disposable PostgreSQL database and keep exactly one head.
- Concurrency fixtures may only target a clearly disposable PostgreSQL database; never point them
  at development, shared, staging or production data.

## Git and safety

- Inspect `git status --short` before editing. Preserve unrelated and user-authored work; do not
  delete, overwrite, stash or revert it.
- Use one branch and one acceptance goal per task. Follow the prefixes `feature/`, `fix/`,
  `refactor/`, `test/`, `docs/` and `chore/`.
- Do not commit, push, merge, force-push or open a pull request unless explicitly requested.
- Coordinate changes to shared files listed in `CONTRIBUTING.md`, especially ports, ORM records,
  repositories, configuration, lockfiles and the Alembic chain.

## Required verification

Use the narrowest relevant checks during development and the complete gate before handoff:

```cmd
uv sync --frozen --extra dev
uv run --frozen ruff format --check .
uv run --frozen ruff check .
scripts\run-tests.cmd --with-db
uv run --frozen python -m alembic heads
uv run --frozen python -m alembic current
git diff --check
```

Also run Docker Compose validation, container smoke, frontend workflow or migration-from-empty checks
when the task touches those areas. PostgreSQL concurrency tests must have zero relevant skips for
inventory, reservation, cancellation or worker concurrency changes.

## Documentation and task reports

- Update API, architecture, testing and local setup documentation when their contracts change.
- Never claim a planned Phase 2 feature is implemented without code and reproducible verification.
- For substantial tasks, leave a concise Markdown report containing: scope, files changed,
  architectural/migration/API impact, commands and results, remaining risks, and final Git status.

