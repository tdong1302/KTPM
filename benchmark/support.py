"""Pure helpers shared by the EventHub benchmark runners.

This module deliberately has no dependency on the application package.  Keeping parsing,
classification, aggregation and safety rules here makes them deterministic and unit-testable.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit, urlunsplit


class BenchmarkDataError(ValueError):
    """Raised when generated benchmark data is empty or malformed."""


@dataclass(frozen=True)
class LocustStats:
    total_requests: int
    failure_count: int
    requests_per_second: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    endpoints: tuple[dict[str, Any], ...]

    @property
    def error_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.failure_count / self.total_requests


def _number(row: dict[str, str], key: str, cast: type[int] | type[float]) -> int | float:
    value = row.get(key)
    if value is None or value.strip() == "":
        raise BenchmarkDataError(f"missing numeric field {key!r}")
    try:
        return cast(float(value)) if cast is int else cast(value)
    except ValueError as exc:
        raise BenchmarkDataError(f"invalid numeric field {key!r}: {value!r}") from exc


def parse_locust_stats(path: Path) -> LocustStats:
    """Parse Locust's final CSV and require one non-empty aggregate row."""

    if not path.is_file() or path.stat().st_size == 0:
        raise BenchmarkDataError(f"stats file is missing or empty: {path}")
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise BenchmarkDataError(f"stats file has no header: {path}")
        required = {
            "Name",
            "Request Count",
            "Failure Count",
            "Requests/s",
            "50%",
            "95%",
            "99%",
        }
        missing = required.difference(reader.fieldnames)
        if missing:
            raise BenchmarkDataError(f"stats file is missing columns: {sorted(missing)}")
        rows = list(reader)

    aggregate_rows = [row for row in rows if row.get("Name") == "Aggregated"]
    if len(aggregate_rows) != 1:
        raise BenchmarkDataError(f"expected exactly one aggregate row, found {len(aggregate_rows)}")
    aggregate = aggregate_rows[0]
    total = int(_number(aggregate, "Request Count", int))
    if total <= 0:
        raise BenchmarkDataError("aggregate request count must be positive")

    endpoints: list[dict[str, Any]] = []
    for row in rows:
        if row.get("Name") == "Aggregated":
            continue
        request_count = int(_number(row, "Request Count", int))
        if request_count == 0:
            continue
        endpoints.append(
            {
                "method": row.get("Type", ""),
                "name": row.get("Name", ""),
                "requests": request_count,
                "failures": int(_number(row, "Failure Count", int)),
                "rps": float(_number(row, "Requests/s", float)),
                "p50_ms": float(_number(row, "50%", float)),
                "p95_ms": float(_number(row, "95%", float)),
                "p99_ms": float(_number(row, "99%", float)),
            }
        )

    return LocustStats(
        total_requests=total,
        failure_count=int(_number(aggregate, "Failure Count", int)),
        requests_per_second=float(_number(aggregate, "Requests/s", float)),
        p50_ms=float(_number(aggregate, "50%", float)),
        p95_ms=float(_number(aggregate, "95%", float)),
        p99_ms=float(_number(aggregate, "99%", float)),
        endpoints=tuple(endpoints),
    )


def classify_http_result(status_code: int | None, exception: BaseException | str | None) -> str:
    """Return a stable result bucket without treating valid 409 outcomes as failures."""

    if exception is not None:
        message = str(exception).lower()
        return "timeout" if "timeout" in message or "timed out" in message else "transport_error"
    if status_code is None:
        return "transport_error"
    if status_code == 201:
        return "http_201_created"
    if status_code == 409:
        return "http_409_conflict"
    if 200 <= status_code < 300:
        return "http_2xx_other"
    if 400 <= status_code < 500:
        return "http_4xx_unexpected"
    if status_code >= 500:
        return "http_5xx"
    return f"http_{status_code}"


class HttpResultCounter:
    """Small mutable counter used by the Locust event hooks."""

    def __init__(self) -> None:
        self._counts: Counter[str] = Counter()

    def record(self, status_code: int | None, exception: BaseException | str | None = None) -> None:
        self._counts[classify_http_result(status_code, exception)] += 1

    def reset(self) -> None:
        self._counts.clear()

    def snapshot(self) -> dict[str, int]:
        return dict(sorted(self._counts.items()))


def median_summary(values: Iterable[float]) -> dict[str, float]:
    samples = [float(value) for value in values]
    if not samples:
        raise BenchmarkDataError("cannot aggregate an empty sample")
    return {
        "median": statistics.median(samples),
        "min": min(samples),
        "max": max(samples),
        "spread": max(samples) - min(samples),
    }


def aggregate_repetitions(repetitions: Iterable[dict[str, Any]]) -> dict[str, Any]:
    runs = list(repetitions)
    if not runs:
        raise BenchmarkDataError("cannot aggregate zero repetitions")
    metrics = ("requests_per_second", "p50_ms", "p95_ms", "p99_ms", "error_rate")
    result = {metric: median_summary(run[metric] for run in runs) for metric in metrics}
    result["repetition_count"] = len(runs)
    return result


def aggregate_endpoints(repetitions: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate like-named endpoint snapshots without requiring every optional status group."""

    runs = list(repetitions)
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for run in runs:
        for endpoint in run.get("endpoints", []):
            key = (str(endpoint["method"]), str(endpoint["name"]))
            grouped.setdefault(key, []).append(endpoint)

    aggregated: list[dict[str, Any]] = []
    for (method, name), samples in sorted(grouped.items()):
        aggregated.append(
            {
                "method": method,
                "name": name,
                "observed_repetitions": len(samples),
                "requests": median_summary(sample["requests"] for sample in samples),
                "failures": sum(int(sample["failures"]) for sample in samples),
                "rps": median_summary(sample["rps"] for sample in samples),
                "p50_ms": median_summary(sample["p50_ms"] for sample in samples),
                "p95_ms": median_summary(sample["p95_ms"] for sample in samples),
                "p99_ms": median_summary(sample["p99_ms"] for sample in samples),
            }
        )
    return aggregated


def parse_utc_timestamp(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise BenchmarkDataError(f"timestamp lacks timezone: {value!r}")
    return parsed


def summarize_resource_samples(
    samples: Iterable[dict[str, Any]], measured_from_utc: str
) -> dict[str, float | int]:
    threshold = parse_utc_timestamp(measured_from_utc)
    measured = [
        sample
        for sample in samples
        if parse_utc_timestamp(str(sample["timestamp_utc"])) >= threshold
    ]
    if not measured:
        raise BenchmarkDataError("no CPU/RSS samples fall inside the measured interval")
    cpu = [float(sample["cpu_percent"]) for sample in measured]
    rss = [float(sample["rss_mb"]) for sample in measured]
    return {
        "sample_count": len(measured),
        "cpu_mean_percent": statistics.fmean(cpu),
        "cpu_peak_percent": max(cpu),
        "rss_mean_mb": statistics.fmean(rss),
        "rss_peak_mb": max(rss),
    }


def safe_database_identity(database_url: str) -> dict[str, str]:
    """Validate that a destructive benchmark target is explicit and clearly disposable."""

    parsed = urlsplit(database_url)
    database = parsed.path.lstrip("/")
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"postgresql", "postgresql+psycopg"}:
        raise ValueError("benchmark reset requires PostgreSQL")
    if host not in {"127.0.0.1", "localhost"}:
        raise ValueError("benchmark reset only permits an explicit local PostgreSQL host")
    lowered = database.lower()
    if not database or not any(marker in lowered for marker in ("benchmark", "disposable")):
        raise ValueError(
            "benchmark reset requires a database name containing 'benchmark' or 'disposable'"
        )
    return {"engine": "PostgreSQL", "host": host, "database": database}


def redact_url(value: str) -> str:
    """Remove URL credentials while preserving useful non-sensitive provenance."""

    parsed = urlsplit(value)
    if not parsed.scheme or not parsed.netloc:
        return value
    hostname = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    netloc = f"{hostname}{port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def saturation_conclusion(steps: list[dict[str, Any]]) -> dict[str, Any]:
    """Identify the first evidenced saturation level, without inventing one.

    Saturation requires an error breach, a p95 breach, or two consecutive steps whose median
    throughput grows by less than 10% while p95 grows by at least 50% from the preceding step.
    """

    if not steps:
        raise BenchmarkDataError("S4 has no step results")
    weak_growth_streak = 0
    previous: dict[str, Any] | None = None
    for step in steps:
        p95 = float(step["aggregate"]["p95_ms"]["median"])
        error_rate = float(step["aggregate"]["error_rate"]["median"])
        if error_rate > 0.01:
            return {"reached": True, "concurrency": step["concurrency"], "reason": "error_rate"}
        if p95 > 1000:
            return {"reached": True, "concurrency": step["concurrency"], "reason": "p95"}
        if previous is not None:
            old_rps = float(previous["aggregate"]["requests_per_second"]["median"])
            growth = (
                math.inf
                if old_rps <= 0
                else (float(step["aggregate"]["requests_per_second"]["median"]) / old_rps - 1)
            )
            old_p95 = float(previous["aggregate"]["p95_ms"]["median"])
            p95_growth = math.inf if old_p95 <= 0 else p95 / old_p95 - 1
            weak_growth_streak = weak_growth_streak + 1 if growth < 0.10 else 0
            if weak_growth_streak >= 2 and p95_growth >= 0.50:
                return {
                    "reached": True,
                    "concurrency": step["concurrency"],
                    "reason": "throughput_plateau_and_latency_growth",
                }
        previous = step
    return {
        "reached": False,
        "concurrency": None,
        "reason": "Saturation point not reached within tested range",
    }
