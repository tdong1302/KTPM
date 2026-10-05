#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

port="${1:-8765}"
demo_dir="$PWD/artifacts/demo"
database_path="$demo_dir/eventhub-demo.sqlite3"
mkdir -p "$demo_dir"

uv sync --frozen --extra dev
rm -f -- "$database_path"

export DATABASE_URL="sqlite+pysqlite:///$database_path"
export DB_AUTO_CREATE=true
export JWT_SECRET="local-functional-demo-secret-at-least-32-characters"
export BCRYPT_ROUNDS=4
export ENVIRONMENT=demo
export APP_NAME="EventHub-KTPM Functional Demo"

uv run --frozen python -m uvicorn app.main:app \
  --host 127.0.0.1 --port "$port" \
  >"$demo_dir/server.stdout.log" 2>"$demo_dir/server.stderr.log" &
server_pid=$!
trap 'kill "$server_pid" >/dev/null 2>&1 || true' EXIT

uv run --frozen python scripts/demo_api.py \
  --base-url "http://127.0.0.1:$port" \
  --output-dir "$demo_dir" \
  --storage-label "SQLite local functional demo (not PostgreSQL concurrency evidence)"

echo "Demo completed. Open artifacts/demo/latest-demo-report.md"
