#!/usr/bin/env bash
# Start PostgreSQL in Docker and run the API locally with reload.
set -euo pipefail
cd "$(dirname "$0")/.."

docker compose up -d postgres
until docker compose exec -T postgres pg_isready -U eventhub -d eventhub_ktpm >/dev/null 2>&1; do
  sleep 1
done

export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg://eventhub:eventhub-local-only@localhost:5432/eventhub_ktpm}"
uv run --frozen python -m alembic upgrade head
exec uv run --frozen python -m uvicorn app.main:app --reload --port 8000
