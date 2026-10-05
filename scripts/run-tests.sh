#!/usr/bin/env bash
# Run the test suite. Pass --with-db to also run the PostgreSQL concurrency tests.
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ "${1:-}" == "--with-db" ]]; then
  echo "starting disposable test postgres..."
  docker compose --profile test up -d postgres-test
  until docker compose exec -T postgres-test pg_isready -U eventhub_test -d eventhub_test_disposable >/dev/null 2>&1; do
    sleep 1
  done
  export TEST_DATABASE_URL="postgresql+psycopg://eventhub_test:eventhub_test@localhost:5433/eventhub_test_disposable"
  export REQUIRE_POSTGRES_TESTS=1
  echo "TEST_DATABASE_URL is set; concurrency tests will run"
  shift
fi

uv run --frozen --extra dev python -m pytest "$@"
