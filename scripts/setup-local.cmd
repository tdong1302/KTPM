@echo off
setlocal

set "REPO_ROOT=%~dp0.."
pushd "%REPO_ROOT%" >nul || (
    echo ERROR: Cannot enter repository root: "%REPO_ROOT%"
    exit /b 1
)

where git >nul 2>&1 || (
    echo ERROR: Git is not available on PATH.
    popd
    exit /b 1
)
where uv >nul 2>&1 || (
    echo ERROR: uv is not available on PATH.
    echo Install it from a new CMD window with: winget install --id=astral-sh.uv -e
    popd
    exit /b 1
)

echo Installing the locked development environment...
uv sync --frozen --extra dev || (
    echo ERROR: Frozen dependency installation failed.
    popd
    exit /b 1
)

if not exist ".env" (
    echo ERROR: .env is missing. Create it from .env.example and replace JWT_SECRET privately.
    popd
    exit /b 1
)

uv run --frozen python scripts\preflight.py --mode api-only || (
    echo ERROR: API-only preflight failed.
    popd
    exit /b 1
)

docker info >nul 2>&1
if errorlevel 1 (
    echo WARNING: Docker Desktop is not running. SQLite development and the demo are ready.
    echo Start Docker Desktop before PostgreSQL development or concurrency tests.
) else (
    echo Docker Desktop is running.
)

echo Setup complete.
echo Next: scripts\run-demo.cmd
echo Or, with Docker Desktop running: scripts\run-dev.cmd
popd
exit /b 0
