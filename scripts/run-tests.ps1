# Run the test suite. Pass -WithDb to also run the PostgreSQL concurrency tests.
param([switch]$WithDb)

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

if ($WithDb) {
    Write-Host "starting postgres..."
    docker compose up -d postgres
    do {
        Start-Sleep -Seconds 1
        docker compose exec -T postgres pg_isready -U eventhub -d eventhub_ktpm *> $null
    } until ($LASTEXITCODE -eq 0)
    $env:TEST_DATABASE_URL = "postgresql+psycopg://eventhub:eventhub@localhost:5432/eventhub_ktpm"
    Write-Host "TEST_DATABASE_URL is set; concurrency tests will run"
}

python -m pytest
