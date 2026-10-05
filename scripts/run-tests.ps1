# Run the test suite. Pass -WithDb to also run the PostgreSQL concurrency tests.
param([switch]$WithDb)

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

if ($WithDb) {
    Write-Host "starting disposable test postgres..."
    docker compose --profile test up -d postgres-test
    do {
        Start-Sleep -Seconds 1
        docker compose exec -T postgres-test pg_isready -U eventhub_test -d eventhub_test_disposable *> $null
    } until ($LASTEXITCODE -eq 0)
    $env:TEST_DATABASE_URL = "postgresql+psycopg://eventhub_test:eventhub_test@localhost:5433/eventhub_test_disposable"
    $env:REQUIRE_POSTGRES_TESTS = "1"
    Write-Host "TEST_DATABASE_URL is set; concurrency tests will run"
}

uv run --frozen --extra dev python -m pytest @args
