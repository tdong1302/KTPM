#!/usr/bin/env bash
# Run the test suite. Pass --with-db to also run the PostgreSQL concurrency tests.
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ "${1:-}" == "--with-db" ]]; then
  echo "starting postgres..."
  docker compose up -d postgres
  until docker compose exec -T postgres pg_isready -U eventhub -d eventhub_ktpm >/dev/null 2>&1; do
    sleep 1
  done
  export TEST_DATABASE_URL="postgresql+psycopg://eventhub:eventhub@localhost:5432/eventhub_ktpm"
  echo "TEST_DATABASE_URL is set; concurrency tests will run"
fi

pytest "${@:2}"
