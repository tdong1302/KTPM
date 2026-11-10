@echo off
setlocal EnableExtensions

set "REPO_ROOT=%~dp0.."
set "RESULT=0"

pushd "%REPO_ROOT%" >nul || (
    echo ERROR: Cannot enter repository root: "%REPO_ROOT%"
    exit /b 1
)

echo [1/8] Synchronizing locked development dependencies...
where uv >nul 2>&1 || (
    echo ERROR: uv is not available on PATH.
    goto :failed
)
uv sync --frozen --extra dev || goto :failed
call scripts\verify-local.cmd || goto :failed

echo [2/8] Checking formatting...
uv run --frozen ruff format --check . || goto :failed

echo [3/8] Running Ruff...
uv run --frozen ruff check . || goto :failed

echo [4/8] Validating Docker Compose...
docker compose config --quiet || goto :failed

echo [5/8] Starting development PostgreSQL and applying migrations...
docker compose up -d postgres || goto :failed
set /a attempts=0
:wait_postgres
docker compose exec -T postgres pg_isready -U eventhub -d eventhub_ktpm >nul 2>&1
if not errorlevel 1 goto :postgres_ready
set /a attempts+=1
if %attempts% GEQ 60 (
    echo ERROR: PostgreSQL did not become ready within 60 seconds.
    goto :failed
)
ping -n 2 127.0.0.1 >nul
goto :wait_postgres

:postgres_ready
uv run --frozen python scripts\preflight.py --mode development || goto :failed
uv run --frozen python -m alembic upgrade head || goto :failed
uv run --frozen python -m alembic heads || goto :failed
uv run --frozen python -m alembic current || goto :failed
uv run --frozen python scripts\verify_postgres_schema.py || goto :failed

echo [6/8] Running the full PostgreSQL suite with coverage...
call scripts\run-tests.cmd --with-db --junitxml=test-results.xml --cov=app --cov-report=term-missing --cov-report=xml --cov-fail-under=95 || goto :failed

echo [7/8] Checking Git whitespace...
git diff --check || goto :failed

echo [8/8] Quality gate passed.
goto :cleanup

:failed
set "RESULT=1"
echo ERROR: Quality gate failed. Review the first failing command above.

:cleanup
docker compose --profile test stop postgres-test >nul 2>&1
popd
exit /b %RESULT%

