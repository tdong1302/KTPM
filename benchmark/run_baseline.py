"""Run the reproducible EventHub BEFORE benchmark against a disposable local PostgreSQL.

The script starts the Compose ``postgres-test`` service, resets only its explicitly disposable
database, migrates and seeds it, starts one Uvicorn worker, then executes Locust. Raw artifacts are
written under ``artifacts/benchmarks`` and are intentionally ignored by Git.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import platform
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import psutil
from sqlalchemy import create_engine, text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from benchmark.support import (  # noqa: E402
    aggregate_endpoints,
    aggregate_repetitions,
    file_sha256,
    median_summary,
    parse_locust_stats,
    safe_database_identity,
    saturation_conclusion,
    summarize_resource_samples,
    write_json,
)

LOCUSTFILE = PROJECT_ROOT / "benchmark" / "locustfile.py"
COMPOSE_TEST_DATABASE_URL = (
    "postgresql+psycopg://eventhub_test:eventhub_test@127.0.0.1:5433/eventhub_test_disposable"
)


@dataclass(frozen=True)
class Scenario:
    users: int
    spawn_rate: int
    duration_seconds: int
    events: int


SCENARIOS = {
    "s1": Scenario(users=50, spawn_rate=10, duration_seconds=180, events=500),
    "s2": Scenario(users=100, spawn_rate=20, duration_seconds=300, events=500),
    "s3": Scenario(users=100, spawn_rate=50, duration_seconds=120, events=1),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_checked(command: list[str], env: dict[str, str] | None = None) -> None:
    display = " ".join(command)
    if "postgresql" in display.lower():
        display = command[0] + " " + " ".join(command[1:3]) + " [arguments redacted]"
    print(f"> {display}", flush=True)
    subprocess.run(command, cwd=PROJECT_ROOT, env=env, check=True)


def git_output(*args: str) -> str:
    command = [
        "git",
        "-c",
        f"safe.directory={PROJECT_ROOT.as_posix()}",
        *args,
    ]
    return subprocess.run(
        command, cwd=PROJECT_ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()


def wait_for_postgres(timeout: int = 60) -> None:
    deadline = time.monotonic() + timeout
    command = [
        "docker",
        "compose",
        "--profile",
        "test",
        "exec",
        "-T",
        "postgres-test",
        "pg_isready",
        "-U",
        "eventhub_test",
        "-d",
        "eventhub_test_disposable",
    ]
    while time.monotonic() < deadline:
        result = subprocess.run(
            command, cwd=PROJECT_ROOT, capture_output=True, text=True, check=False
        )
        if result.returncode == 0:
            return
        time.sleep(1)
    raise RuntimeError("disposable benchmark PostgreSQL did not become ready")


def wait_for_api(base_url: str, timeout: int = 90) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{base_url}/health", timeout=2) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, OSError):
            time.sleep(0.5)
    raise RuntimeError("benchmark API did not become healthy")


def health_probe(base_url: str, requests: int = 20) -> dict[str, Any]:
    latencies: list[float] = []
    statuses: dict[str, int] = {}
    for _ in range(requests):
        started = time.perf_counter()
        with urllib.request.urlopen(f"{base_url}/health", timeout=5) as response:
            statuses[str(response.status)] = statuses.get(str(response.status), 0) + 1
        latencies.append((time.perf_counter() - started) * 1000)
    ordered = sorted(latencies)

    def percentile(value: float) -> float:
        index = max(0, math.ceil(value * len(ordered)) - 1)
        return ordered[index]

    return {
        "requests": requests,
        "status_counts": statuses,
        "p50_ms": percentile(0.50),
        "p95_ms": percentile(0.95),
        "p99_ms": percentile(0.99),
        "note": "Diagnostic only; excluded from catalogue throughput and latency.",
    }


class ResourceSampler:
    """Sample the Uvicorn parent and all child workers, not machine-wide usage."""

    def __init__(self, process_id: int, interval_seconds: float = 1.0) -> None:
        self.process_id = process_id
        self.interval_seconds = interval_seconds
        self.samples: list[dict[str, Any]] = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="benchmark-resource-sampler")
        self._process_cache: dict[int, psutil.Process] = {}

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=10)

    def _processes(self) -> list[psutil.Process]:
        try:
            parent = self._process_cache.setdefault(
                self.process_id, psutil.Process(self.process_id)
            )
            discovered = [parent, *parent.children(recursive=True)]
            for process in discovered:
                self._process_cache.setdefault(process.pid, process)
            return [self._process_cache[process.pid] for process in discovered]
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return []

    def _run(self) -> None:
        primed: set[int] = set()
        while not self._stop.is_set():
            processes = self._processes()
            cpu = 0.0
            rss = 0
            live_pids: list[int] = []
            for process in processes:
                try:
                    live_pids.append(process.pid)
                    if process.pid not in primed:
                        process.cpu_percent(interval=None)
                        primed.add(process.pid)
                    else:
                        cpu += process.cpu_percent(interval=None)
                    rss += process.memory_info().rss
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            self.samples.append(
                {
                    "timestamp_utc": utc_now(),
                    "cpu_percent": cpu,
                    "rss_mb": rss / (1024 * 1024),
                    "process_count": len(live_pids),
                    "pids": ";".join(str(pid) for pid in sorted(live_pids)),
                }
            )
            self._stop.wait(self.interval_seconds)

    def write_csv(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(self.samples[0]))
            writer.writeheader()
            writer.writerows(self.samples)


def benchmark_environment(database_url: str) -> dict[str, str]:
    return {
        **os.environ,
        "DATABASE_URL": database_url,
        "DB_AUTO_CREATE": "false",
        "DB_POOL_SIZE": "5",
        "DB_MAX_OVERFLOW": "10",
        "DB_POOL_TIMEOUT": "30",
        "BCRYPT_ROUNDS": "12",
        "JWT_SECRET": "benchmark-ephemeral-secret-at-least-32-characters",
        "ENVIRONMENT": "benchmark",
    }


def seed_database(events: int, env: dict[str, str]) -> None:
    run_checked(
        [
            sys.executable,
            str(PROJECT_ROOT / "benchmark" / "seed_data.py"),
            "--reset",
            "--allow-destructive-reset",
            "--events",
            str(events),
        ],
        env=env,
    )


def write_resource_csv(sampler: ResourceSampler, path: Path) -> None:
    if not sampler.samples:
        raise RuntimeError("resource sampler captured no API process samples")
    sampler.write_csv(path)


def stop_process(process: subprocess.Popen[Any]) -> None:
    if process.poll() is not None:
        return
    process.send_signal(signal.CTRL_BREAK_EVENT if os.name == "nt" else signal.SIGINT)
    try:
        process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


def check_s3_invariant(database_url: str) -> bool:
    engine = create_engine(database_url)
    statement = text(
        """
        SELECT COALESCE(bool_and(
            e.available_tickets + COALESCE(s.sold, 0) = e.total_tickets
        ), false)
        FROM events e
        LEFT JOIN (
            SELECT event_id, SUM(quantity) AS sold
            FROM bookings
            WHERE status = 'CONFIRMED'
            GROUP BY event_id
        ) s ON s.event_id = e.id
        """
    )
    try:
        with engine.connect() as connection:
            return bool(connection.execute(statement).scalar_one())
    finally:
        engine.dispose()


def run_once(
    *,
    scenario_name: str,
    users: int,
    spawn_rate: int,
    duration_seconds: int,
    warmup_seconds: int,
    events: int,
    repetition: int,
    output_dir: Path,
    base_url: str,
    database_url: str,
) -> dict[str, Any]:
    tag = f"{scenario_name}-u{users}-r{repetition}"
    run_dir = output_dir / tag
    run_dir.mkdir(parents=True, exist_ok=True)
    env = benchmark_environment(database_url)
    seed_database(events, env)

    parsed_url = urlsplit(base_url)
    port = parsed_url.port or 8000
    stdout_handle = (run_dir / "api.stdout.log").open("w", encoding="utf-8")
    stderr_handle = (run_dir / "api.stderr.log").open("w", encoding="utf-8")
    api = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--workers",
            "1",
            "--log-level",
            "warning",
        ],
        cwd=PROJECT_ROOT,
        env=env,
        stdout=stdout_handle,
        stderr=stderr_handle,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
    )
    sampler = ResourceSampler(api.pid)
    started_at = utc_now()
    try:
        wait_for_api(base_url)
        diagnostic_health = health_probe(base_url) if scenario_name == "s1" else None
        sampler.start()

        warmup_file = run_dir / "warmup.json"
        status_file = run_dir / "status.json"
        locust_env = {
            **env,
            "EVENTHUB_BENCHMARK_SCENARIO": scenario_name,
            "EVENTHUB_BENCHMARK_WARMUP_SECONDS": str(warmup_seconds),
            "EVENTHUB_BENCHMARK_WARMUP_FILE": str(warmup_file),
            "EVENTHUB_BENCHMARK_STATUS_FILE": str(status_file),
        }
        ramp_seconds = math.ceil(users / spawn_rate)
        total_runtime = ramp_seconds + warmup_seconds + duration_seconds
        csv_prefix = run_dir / "locust"
        locust_command = [
            sys.executable,
            "-m",
            "locust",
            "-f",
            str(LOCUSTFILE),
            "--headless",
            "--host",
            base_url,
            "--users",
            str(users),
            "--spawn-rate",
            str(spawn_rate),
            "--run-time",
            f"{total_runtime}s",
            "--stop-timeout",
            "10",
            "--csv",
            str(csv_prefix),
            "--csv-full-history",
            "--only-summary",
        ]
        run_checked(locust_command, env=locust_env)
    finally:
        if sampler._thread.is_alive():
            sampler.stop()
        stop_process(api)
        stdout_handle.close()
        stderr_handle.close()

    write_resource_csv(sampler, run_dir / "api-resource.csv")
    warmup = json.loads((run_dir / "warmup.json").read_text(encoding="utf-8"))
    status = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
    # Validate Locust's periodic CSV, but use the quitting-hook snapshot below for exact final
    # values. Locust's CSV writer can lag the final console count by one write interval.
    parse_locust_stats(run_dir / "locust_stats.csv")
    final_stats = status["final_stats"]
    if final_stats is None:
        raise RuntimeError("Locust did not produce a final statistics snapshot")
    aggregate = final_stats["aggregate"]
    status_total = sum(status["status_counts"].values())
    if status_total != aggregate["requests"]:
        raise RuntimeError(
            "HTTP status count does not match final Locust request count: "
            f"statuses={status_total} locust={aggregate['requests']}"
        )
    resources = summarize_resource_samples(sampler.samples, warmup["measured_from_utc"])
    result: dict[str, Any] = {
        "scenario": scenario_name,
        "concurrency": users,
        "spawn_rate": spawn_rate,
        "duration_seconds": duration_seconds,
        "warmup": warmup,
        "repetition": repetition,
        "started_at_utc": started_at,
        "finished_at_utc": utc_now(),
        "total_requests": aggregate["requests"],
        "successful_requests": aggregate["requests"] - aggregate["failures"],
        "failure_count": aggregate["failures"],
        "error_rate": aggregate["failures"] / aggregate["requests"],
        "requests_per_second": aggregate["rps"],
        "p50_ms": aggregate["p50_ms"],
        "p95_ms": aggregate["p95_ms"],
        "p99_ms": aggregate["p99_ms"],
        "status_counts": status["status_counts"],
        "endpoints": final_stats["endpoints"],
        "resources": resources,
        "health_probe": diagnostic_health,
        "artifact_directory": str(run_dir.relative_to(PROJECT_ROOT)),
    }
    if scenario_name == "s3":
        result["inventory_invariant_holds"] = check_s3_invariant(database_url)
        if not result["inventory_invariant_holds"]:
            raise RuntimeError("S3 inventory invariant failed")
    write_json(run_dir / "result.json", result)
    return result


def aggregate_scenario(runs: list[dict[str, Any]]) -> dict[str, Any]:
    aggregate = aggregate_repetitions(runs)
    aggregate["endpoints"] = aggregate_endpoints(runs)
    status_keys = sorted({key for run in runs for key in run["status_counts"]})
    aggregate["status_counts"] = {
        key: {
            "total": sum(run["status_counts"].get(key, 0) for run in runs),
            "median_per_repetition": median_summary(
                run["status_counts"].get(key, 0) for run in runs
            )["median"],
        }
        for key in status_keys
    }
    aggregate["resources"] = {
        metric: median_summary(run["resources"][metric] for run in runs)
        for metric in (
            "cpu_mean_percent",
            "cpu_peak_percent",
            "rss_mean_mb",
            "rss_peak_mb",
        )
    }
    return aggregate


def provenance(database_url: str, args: argparse.Namespace) -> dict[str, Any]:
    identity = safe_database_identity(database_url)
    status = git_output("status", "--short")
    docker_version = subprocess.run(
        ["docker", "version", "--format", "{{.Server.Version}}"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    postgres_version = subprocess.run(
        [
            "docker",
            "compose",
            "--profile",
            "test",
            "exec",
            "-T",
            "postgres-test",
            "postgres",
            "--version",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    changed_paths = [line[3:] for line in status.splitlines()]
    file_hashes = {
        path: file_sha256(PROJECT_ROOT / path)
        for path in changed_paths
        if (PROJECT_ROOT / path).is_file()
    }
    return {
        "git_commit": git_output("rev-parse", "HEAD"),
        "git_dirty": bool(status),
        "git_changed_paths": changed_paths,
        "working_tree_file_sha256": file_hashes,
        "operating_system": platform.platform(),
        "cpu_model": platform.processor() or platform.machine(),
        "logical_cpu_count": psutil.cpu_count(logical=True),
        "memory_gib": round(psutil.virtual_memory().total / (1024**3), 2),
        "python_version": platform.python_version(),
        "docker_server_version": docker_version or "unavailable",
        "postgresql_version": postgres_version or "unavailable",
        "application_workers": 1,
        "sqlalchemy_pool": {"pool_size": 5, "max_overflow": 10, "timeout_seconds": 30},
        "database": identity,
        "seed": {"random_seed": 20260920, "clock_utc": "2030-01-01T12:00:00+00:00"},
        "warmup_seconds": args.warm_up,
        "repetitions": args.repetitions,
    }


def write_markdown_summary(payload: dict[str, Any], path: Path) -> None:
    lines = [
        "# Generated benchmark summary",
        "",
        f"- Started (UTC): `{payload['started_at_utc']}`",
        f"- Finished (UTC): `{payload['finished_at_utc']}`",
        f"- Git commit: `{payload['provenance']['git_commit']}`",
        f"- Dirty worktree recorded: `{payload['provenance']['git_dirty']}`",
        "- Pool wait: `NOT YET MEASURED` (requires application-level instrumentation)",
        "",
        "| Scenario | Concurrency | Repetitions | Median req/s | Median p95 ms | Median error |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, result in payload["scenarios"].items():
        if name == "s4":
            for step in result["steps"]:
                aggregate = step["aggregate"]
                lines.append(
                    f"| S4 | {step['concurrency']} | {aggregate['repetition_count']} | "
                    f"{aggregate['requests_per_second']['median']:.2f} | "
                    f"{aggregate['p95_ms']['median']:.1f} | "
                    f"{aggregate['error_rate']['median']:.2%} |"
                )
        else:
            aggregate = result["aggregate"]
            lines.append(
                f"| {name.upper()} | {result['runs'][0]['concurrency']} | "
                f"{aggregate['repetition_count']} | "
                f"{aggregate['requests_per_second']['median']:.2f} | "
                f"{aggregate['p95_ms']['median']:.1f} | "
                f"{aggregate['error_rate']['median']:.2%} |"
            )
    if "s4" in payload["scenarios"]:
        conclusion = payload["scenarios"]["s4"]["saturation"]
        lines.extend(["", f"S4 conclusion: **{conclusion['reason']}**."])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_levels(value: str) -> list[int]:
    try:
        levels = [int(item.strip()) for item in value.split(",") if item.strip()]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("S4 levels must be comma-separated integers") from exc
    if not levels or any(level <= 0 for level in levels) or levels != sorted(set(levels)):
        raise argparse.ArgumentTypeError("S4 levels must be unique positive ascending integers")
    return levels


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario",
        action="append",
        choices=["s1", "s2", "s3", "s4"],
        help="repeat to select scenarios; default runs all",
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--warm-up", type=int, default=30)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--duration", type=int, help="override measured seconds for each run")
    parser.add_argument("--concurrency", type=int, help="override users for S1-S3")
    parser.add_argument("--s4-levels", type=parse_levels, default=parse_levels("1,5,10,20,40,80"))
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/benchmarks"))
    parser.add_argument("--smoke", action="store_true", help="2 s warm-up, 5 s runs, one repeat")
    parser.add_argument("--keep-postgres", action="store_true")
    args = parser.parse_args()

    if (
        args.warm_up < 0
        or args.repetitions < 1
        or (args.duration is not None and args.duration < 1)
    ):
        parser.error("warm-up must be non-negative; repetitions and duration must be positive")
    parsed_base = urlsplit(args.base_url)
    if parsed_base.hostname not in {"127.0.0.1", "localhost"}:
        parser.error("benchmark base URL must explicitly target localhost")

    if args.smoke:
        args.warm_up = 2
        args.repetitions = 1
        args.duration = 5
        args.s4_levels = [1, 2]

    database_url = COMPOSE_TEST_DATABASE_URL
    safe_database_identity(database_url)
    scenarios = args.scenario or ["s1", "s2", "s3", "s4"]
    started_at = utc_now()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = (PROJECT_ROOT / args.output_dir / run_id).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    run_checked(["docker", "compose", "--profile", "test", "up", "-d", "postgres-test"])
    wait_for_postgres()
    payload: dict[str, Any] = {
        "started_at_utc": started_at,
        "provenance": provenance(database_url, args),
        "scenarios": {},
    }
    try:
        for scenario_name in scenarios:
            if scenario_name != "s4":
                config = SCENARIOS[scenario_name]
                users = args.concurrency or config.users
                duration = args.duration or config.duration_seconds
                runs = [
                    run_once(
                        scenario_name=scenario_name,
                        users=users,
                        spawn_rate=min(config.spawn_rate, users),
                        duration_seconds=duration,
                        warmup_seconds=args.warm_up,
                        events=config.events,
                        repetition=repetition,
                        output_dir=output_dir,
                        base_url=args.base_url,
                        database_url=database_url,
                    )
                    for repetition in range(1, args.repetitions + 1)
                ]
                payload["scenarios"][scenario_name] = {
                    "runs": runs,
                    "aggregate": aggregate_scenario(runs),
                }
                continue

            steps: list[dict[str, Any]] = []
            for users in args.s4_levels:
                duration = args.duration or 120
                runs = [
                    run_once(
                        scenario_name="s4",
                        users=users,
                        spawn_rate=min(10, users),
                        duration_seconds=duration,
                        warmup_seconds=args.warm_up,
                        events=500,
                        repetition=repetition,
                        output_dir=output_dir,
                        base_url=args.base_url,
                        database_url=database_url,
                    )
                    for repetition in range(1, args.repetitions + 1)
                ]
                steps.append(
                    {"concurrency": users, "runs": runs, "aggregate": aggregate_scenario(runs)}
                )
                if saturation_conclusion(steps)["reached"]:
                    print(f"S4 safety stop after evidenced saturation at concurrency={users}")
                    break
            payload["scenarios"]["s4"] = {
                "steps": steps,
                "saturation": saturation_conclusion(steps),
            }
    finally:
        if not args.keep_postgres:
            subprocess.run(
                ["docker", "compose", "--profile", "test", "stop", "postgres-test"],
                cwd=PROJECT_ROOT,
                check=False,
            )

    payload["finished_at_utc"] = utc_now()
    write_json(output_dir / "baseline-summary.json", payload)
    write_markdown_summary(payload, output_dir / "baseline-summary.md")
    print(f"Benchmark complete. Artifacts: {output_dir.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
