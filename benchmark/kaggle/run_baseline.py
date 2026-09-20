"""Run the whole benchmark inside a Kaggle CPU notebook.

Kaggle gives a Python runtime with root access and no Docker, so PostgreSQL is installed
with apt and started directly. Enable "Internet" in the notebook settings first.

Kaggle has no terminal: run these in a notebook cell, with a leading "!".

    !git clone https://github.com/tdong1302/KTPM.git /kaggle/working/ktpm
    %cd /kaggle/working/ktpm
    !pip install -q -e ".[bench]"
    !python benchmark/kaggle/run_baseline.py --scenario s2

Then download whatever landed in ``benchmark/results/``.

Step by step guide, including how to read the CSV into docs/benchmark.md:
benchmark/kaggle/README.md

This script only produces measurements; it never writes conclusions. Interpretation
belongs in docs/benchmark.md, written by a human after reading the numbers.
"""

import argparse
import os
import platform
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = PROJECT_ROOT / "benchmark" / "results"

PG_USER = "eventhub"
PG_PASSWORD = "eventhub"
PG_DB = "eventhub_ktpm"
DATABASE_URL = f"postgresql+psycopg://{PG_USER}:{PG_PASSWORD}@localhost:5432/{PG_DB}"
BASE_URL = "http://127.0.0.1:8000"

SCENARIOS = {
    "s1": {"users": 50, "spawn_rate": 10, "run_time": "3m", "events": 500},
    "s2": {"users": 100, "spawn_rate": 20, "run_time": "5m", "events": 500},
    "s3": {"users": 100, "spawn_rate": 50, "run_time": "2m", "events": 1},
}


def run(command: str, check: bool = True) -> int:
    print(f"$ {command}", flush=True)
    return subprocess.run(command, shell=True, check=check).returncode


def install_postgres() -> None:
    if shutil.which("pg_ctlcluster") or Path("/usr/lib/postgresql").exists():
        print("postgresql already present")
        return
    run("apt-get update -qq")
    run("DEBIAN_FRONTEND=noninteractive apt-get install -y -qq postgresql postgresql-contrib")


def start_postgres() -> None:
    run("service postgresql start", check=False)
    time.sleep(5)
    # Idempotent: re-running the notebook must not fail on an existing role/database.
    run(
        f"""su postgres -c "psql -tc \\"SELECT 1 FROM pg_roles WHERE rolname='{PG_USER}'\\" """
        f"""| grep -q 1 || psql -c \\"CREATE USER {PG_USER} WITH SUPERUSER PASSWORD '{PG_PASSWORD}'\\" " """,
        check=False,
    )
    run(
        f"""su postgres -c "psql -tc \\"SELECT 1 FROM pg_database WHERE datname='{PG_DB}'\\" """
        f"""| grep -q 1 || createdb -O {PG_USER} {PG_DB}" """,
        check=False,
    )


def wait_for_health(timeout: int = 90) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{BASE_URL}/health", timeout=2) as response:
                if response.status == 200:
                    print("api is up")
                    return
        except (urllib.error.URLError, OSError):
            time.sleep(1)
    raise RuntimeError("the API did not become healthy in time")


def record_environment(tag: str) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    target = RESULTS_DIR / f"{tag}-environment.txt"
    lines = [
        f"timestamp_utc: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}",
        f"python: {platform.python_version()}",
        f"platform: {platform.platform()}",
        f"cpu_count: {os.cpu_count()}",
    ]
    for label, command in (
        ("git_commit", "git rev-parse HEAD"),
        ("cpu_model", "lscpu | grep -m1 'Model name'"),
        ("memory", "free -h | head -2 | tail -1"),
    ):
        try:
            output = subprocess.run(
                command, shell=True, capture_output=True, text=True, timeout=20
            ).stdout.strip()
            lines.append(f"{label}: {output}")
        except Exception as exc:  # noqa: BLE001 - environment capture must never abort a run
            lines.append(f"{label}: unavailable ({exc})")
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {target}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), default="s2")
    parser.add_argument("--tag", default=None, help="result file prefix, default <scenario>")
    parser.add_argument("--workers", type=int, default=1, help="uvicorn worker processes")
    parser.add_argument("--skip-install", action="store_true")
    args = parser.parse_args()

    scenario = SCENARIOS[args.scenario]
    tag = args.tag or args.scenario
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    if not args.skip_install:
        install_postgres()
    start_postgres()

    env = {**os.environ, "DATABASE_URL": DATABASE_URL, "BCRYPT_ROUNDS": "12"}

    print(f"seeding {scenario['events']} events")
    subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "benchmark" / "seed_data.py"),
            "--reset",
            "--events",
            str(scenario["events"]),
        ],
        cwd=PROJECT_ROOT,
        env=env,
        check=True,
    )

    api = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
            "--workers",
            str(args.workers),
            "--log-level",
            "warning",
        ],
        cwd=PROJECT_ROOT,
        env=env,
    )

    try:
        wait_for_health()
        record_environment(tag)

        print("warming up for 30s")
        warmup_deadline = time.time() + 30
        while time.time() < warmup_deadline:
            try:
                urllib.request.urlopen(f"{BASE_URL}/api/events?size=20", timeout=5).read()
            except (urllib.error.URLError, OSError):
                pass

        subprocess.run(
            [
                sys.executable,
                "-m",
                "locust",
                "-f",
                str(PROJECT_ROOT / "benchmark" / "locustfile.py"),
                "--headless",
                "--host",
                BASE_URL,
                "--users",
                str(scenario["users"]),
                "--spawn-rate",
                str(scenario["spawn_rate"]),
                "--run-time",
                scenario["run_time"],
                "--csv",
                str(RESULTS_DIR / tag),
                "--csv-full-history",
            ],
            cwd=PROJECT_ROOT,
            env=env,
            check=True,
        )
    finally:
        api.send_signal(signal.SIGINT)
        try:
            api.wait(timeout=20)
        except subprocess.TimeoutExpired:
            api.kill()

    print(f"\nresults written to {RESULTS_DIR}")
    for path in sorted(RESULTS_DIR.glob(f"{tag}*")):
        print(f"  {path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
