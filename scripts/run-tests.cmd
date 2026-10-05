@echo off
setlocal

set "REPO_ROOT=%~dp0.."
pushd "%REPO_ROOT%" >nul || (
    echo ERROR: Cannot enter repository root: "%REPO_ROOT%"
    exit /b 1
)

where uv >nul 2>&1 || goto :missing_uv
set "PYTEST_ARGS="

if /I "%~1"=="--with-db" goto :with_db
if /I "%~1"=="/with-db" goto :with_db
goto :collect_args

:with_db
shift
where docker >nul 2>&1 || goto :missing_docker
docker info >nul 2>&1 || goto :docker_stopped
docker compose --profile test up -d postgres-test || goto :failed

echo Waiting for disposable PostgreSQL test database...
set /a attempts=0
:wait_test_postgres
docker compose exec -T postgres-test pg_isready -U eventhub_test -d eventhub_test_disposable >nul 2>&1
if not errorlevel 1 goto :test_postgres_ready
set /a attempts+=1
if %attempts% GEQ 60 (
    echo ERROR: Disposable PostgreSQL did not become ready within 60 seconds.
    goto :failed
)
ping -n 2 127.0.0.1 >nul
goto :wait_test_postgres

:test_postgres_ready
set "TEST_DATABASE_URL=postgresql+psycopg://eventhub_test:eventhub_test@127.0.0.1:5433/eventhub_test_disposable"
set "REQUIRE_POSTGRES_TESTS=1"
uv run --frozen python scripts\preflight.py --mode postgres-test || goto :failed
echo PostgreSQL concurrency tests are enabled against the disposable test database.

:collect_args
if "%~1"=="" goto :run_tests
set "PYTEST_ARGS=%PYTEST_ARGS% %1"
shift
goto :collect_args

:run_tests
uv run --frozen --extra dev python -m pytest %PYTEST_ARGS%
set "TEST_EXIT=%ERRORLEVEL%"
popd
exit /b %TEST_EXIT%

:missing_uv
echo ERROR: uv is not available on PATH.
goto :failed

:missing_docker
echo ERROR: Docker CLI is not available on PATH.
goto :failed

:docker_stopped
echo ERROR: Docker Desktop is installed but its daemon is not running.
echo Start Docker Desktop, wait until it reports Running, then retry.

:failed
popd
exit /b 1
