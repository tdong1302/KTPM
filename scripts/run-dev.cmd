@echo off
setlocal

set "REPO_ROOT=%~dp0.."
pushd "%REPO_ROOT%" >nul || (
    echo ERROR: Cannot enter repository root: "%REPO_ROOT%"
    exit /b 1
)

where uv >nul 2>&1 || goto :missing_uv
where docker >nul 2>&1 || goto :missing_docker
if not exist ".env" goto :missing_env

docker info >nul 2>&1 || goto :docker_stopped
docker compose config --quiet || goto :failed
docker compose up -d postgres || goto :failed

echo Waiting for PostgreSQL...
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
uv run --frozen python -m alembic current || goto :failed

echo Starting EventHub at http://127.0.0.1:8000
echo Swagger UI: http://127.0.0.1:8000/docs
uv run --frozen python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
set "APP_EXIT=%ERRORLEVEL%"
popd
exit /b %APP_EXIT%

:missing_uv
echo ERROR: uv is not available on PATH.
goto :failed

:missing_docker
echo ERROR: Docker CLI is not available on PATH.
goto :failed

:missing_env
echo ERROR: .env is missing. Run scripts\setup-local.cmd after creating it safely.
goto :failed

:docker_stopped
echo ERROR: Docker Desktop is installed but its daemon is not running.
echo Start Docker Desktop, wait until it reports Running, then retry.

:failed
popd
exit /b 1
