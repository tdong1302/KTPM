# Start PostgreSQL in Docker and run the API locally with reload.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

docker compose up -d postgres
do {
    Start-Sleep -Seconds 1
    docker compose exec -T postgres pg_isready -U eventhub -d eventhub_ktpm *> $null
} until ($LASTEXITCODE -eq 0)

if (-not $env:DATABASE_URL) {
    $env:DATABASE_URL = "postgresql+psycopg://eventhub:eventhub@localhost:5432/eventhub_ktpm"
}
python -m alembic upgrade head
python -m uvicorn app.main:app --reload --port 8000
