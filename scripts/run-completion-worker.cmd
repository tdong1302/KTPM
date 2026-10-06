@echo off
setlocal

set "REPO_ROOT=%~dp0.."
pushd "%REPO_ROOT%" >nul || (
    echo ERROR: Cannot enter repository root: "%REPO_ROOT%"
    exit /b 1
)

where uv >nul 2>&1 || (
    echo ERROR: uv is not available on PATH.
    popd
    exit /b 1
)

if /I "%~1"=="--once" (
    echo Running EventHub completion worker in one-shot mode...
) else (
    echo Starting EventHub completion worker. Press Ctrl+C to stop.
)
uv run --frozen python -m app.workers.event_completion %*
set "WORKER_EXIT=%ERRORLEVEL%"
popd
exit /b %WORKER_EXIT%
