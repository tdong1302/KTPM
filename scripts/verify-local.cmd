@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "REPO_ROOT=%~dp0.."
set /a FAILURES=0

pushd "%REPO_ROOT%" >nul || (
    echo ERROR: Cannot enter repository root: "%REPO_ROOT%"
    exit /b 1
)

echo EventHub local environment verification
echo Repository: %CD%
echo.

where git >nul 2>&1
if errorlevel 1 (
    echo [FAIL] Git is not available on PATH.
    echo        Install Git for Windows 2.45.1 or a compatible newer version.
    set /a FAILURES+=1
) else (
    for /f "delims=" %%V in ('git --version') do echo [PASS] %%V
)

where uv >nul 2>&1
if errorlevel 1 (
    echo [FAIL] uv is not available on PATH.
    echo        Install uv 0.12.13 or a compatible version, then reopen CMD.
    set /a FAILURES+=1
) else (
    for /f "delims=" %%V in ('uv --version') do echo [PASS] %%V
)

if exist ".venv\Scripts\python.exe" (
    for /f "delims=" %%V in ('.venv\Scripts\python.exe --version') do echo [PASS] Project %%V
) else (
    echo [FAIL] Project virtual environment is missing.
    echo        Run: uv sync --frozen --extra dev
    set /a FAILURES+=1
)

where docker >nul 2>&1
if errorlevel 1 (
    echo [FAIL] Docker CLI is not available on PATH.
    echo        Install or repair Docker Desktop, then reopen CMD.
    set /a FAILURES+=1
) else (
    for /f "delims=" %%V in ('docker --version') do echo [PASS] %%V
    docker compose version >nul 2>&1
    if errorlevel 1 (
        echo [FAIL] Docker Compose v2 plugin is unavailable.
        set /a FAILURES+=1
    ) else (
        for /f "delims=" %%V in ('docker compose version') do echo [PASS] %%V
    )
    docker info >nul 2>&1
    if errorlevel 1 (
        echo [FAIL] Docker daemon is unreachable.
        echo        Start Docker Desktop, wait for Running, then retry.
        set /a FAILURES+=1
    ) else (
        echo [PASS] Docker daemon is reachable.
    )
)

for %%F in (pyproject.toml uv.lock .python-version .env.example docker-compose.yml alembic.ini) do (
    if not exist "%%F" (
        echo [FAIL] Required repository file is missing: %%F
        set /a FAILURES+=1
    )
)

if not exist ".env" (
    echo [FAIL] .env is missing.
    echo        Create it with: copy .env.example .env
    set /a FAILURES+=1
) else (
    git check-ignore --quiet .env
    if errorlevel 1 (
        echo [FAIL] .env exists but is not ignored by Git.
        set /a FAILURES+=1
    ) else (
        echo [PASS] .env exists and is ignored. Its contents were not read.
    )
)

if !FAILURES! EQU 0 (
    docker compose config --quiet
    if errorlevel 1 (
        echo [FAIL] Docker Compose configuration is invalid.
        set /a FAILURES+=1
    ) else (
        echo [PASS] Docker Compose configuration is valid.
    )
)

echo.
if !FAILURES! EQU 0 (
    echo READY: local prerequisites are available.
    popd
    exit /b 0
)

echo NOT READY: !FAILURES! check(s) failed. Follow the action shown for each failure.
popd
exit /b 1

