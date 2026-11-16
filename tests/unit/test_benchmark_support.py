import csv
from pathlib import Path

import pytest

from benchmark.support import (
    BenchmarkDataError,
    HttpResultCounter,
    aggregate_endpoints,
    aggregate_repetitions,
    classify_http_result,
    parse_locust_stats,
    redact_url,
    safe_database_identity,
    saturation_conclusion,
    summarize_resource_samples,
)


def write_stats(path: Path, rows: list[dict[str, object]]) -> None:
    fieldnames = [
        "Type",
        "Name",
        "Request Count",
        "Failure Count",
        "Requests/s",
        "50%",
        "95%",
        "99%",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def test_parse_locust_stats_extracts_aggregate_and_endpoints(tmp_path: Path) -> None:
    path = tmp_path / "stats.csv"
    write_stats(
        path,
        [
            {
                "Type": "GET",
                "Name": "SETUP /api/events",
                "Request Count": 0,
                "Failure Count": 0,
                "Requests/s": 0,
                "50%": "N/A",
                "95%": "N/A",
                "99%": "N/A",
            },
            {
                "Type": "GET",
                "Name": "GET /api/events",
                "Request Count": 90,
                "Failure Count": 0,
                "Requests/s": 9,
                "50%": 10,
                "95%": 20,
                "99%": 30,
            },
            {
                "Type": "",
                "Name": "Aggregated",
                "Request Count": 100,
                "Failure Count": 2,
                "Requests/s": 10,
                "50%": 11,
                "95%": 21,
                "99%": 31,
            },
        ],
    )

    result = parse_locust_stats(path)

    assert result.total_requests == 100
    assert result.error_rate == pytest.approx(0.02)
    assert result.p99_ms == 31
    assert len(result.endpoints) == 1
    assert result.endpoints[0]["name"] == "GET /api/events"


@pytest.mark.parametrize("contents", ["", "Name,Request Count\nAggregated,1\n"])
def test_parse_locust_stats_rejects_empty_or_malformed_data(tmp_path: Path, contents: str) -> None:
    path = tmp_path / "stats.csv"
    path.write_text(contents, encoding="utf-8")

    with pytest.raises(BenchmarkDataError):
        parse_locust_stats(path)


def test_http_classification_separates_created_conflict_and_real_errors() -> None:
    assert classify_http_result(201, None) == "http_201_created"
    assert classify_http_result(409, None) == "http_409_conflict"
    assert classify_http_result(422, None) == "http_4xx_unexpected"
    assert classify_http_result(503, None) == "http_5xx"
    assert classify_http_result(None, "read timed out") == "timeout"

    counter = HttpResultCounter()
    counter.record(201)
    counter.record(409)
    counter.record(409)
    assert counter.snapshot() == {"http_201_created": 1, "http_409_conflict": 2}
    counter.reset()
    assert counter.snapshot() == {}


def test_repetition_aggregation_reports_median_and_variation() -> None:
    runs = [
        {
            "requests_per_second": rps,
            "p50_ms": p50,
            "p95_ms": p50 * 2,
            "p99_ms": p50 * 3,
            "error_rate": error,
        }
        for rps, p50, error in [(90, 10, 0.0), (110, 12, 0.01), (100, 11, 0.0)]
    ]

    result = aggregate_repetitions(runs)

    assert result["repetition_count"] == 3
    assert result["requests_per_second"] == {
        "median": 100,
        "min": 90,
        "max": 110,
        "spread": 20,
    }
    assert result["p50_ms"]["median"] == 11


def test_endpoint_aggregation_handles_optional_status_groups() -> None:
    runs = [
        {
            "endpoints": [
                {
                    "method": "POST",
                    "name": "booking 201",
                    "requests": 10,
                    "failures": 0,
                    "rps": 1,
                    "p50_ms": 20,
                    "p95_ms": 40,
                    "p99_ms": 50,
                }
            ]
        },
        {
            "endpoints": [
                {
                    "method": "POST",
                    "name": "booking 201",
                    "requests": 12,
                    "failures": 0,
                    "rps": 1.2,
                    "p50_ms": 22,
                    "p95_ms": 42,
                    "p99_ms": 52,
                },
                {
                    "method": "POST",
                    "name": "booking 409",
                    "requests": 2,
                    "failures": 0,
                    "rps": 0.2,
                    "p50_ms": 15,
                    "p95_ms": 25,
                    "p99_ms": 30,
                },
            ]
        },
    ]

    result = aggregate_endpoints(runs)

    created = next(endpoint for endpoint in result if endpoint["name"] == "booking 201")
    conflict = next(endpoint for endpoint in result if endpoint["name"] == "booking 409")
    assert created["observed_repetitions"] == 2
    assert created["requests"]["median"] == 11
    assert conflict["observed_repetitions"] == 1
    assert conflict["p95_ms"]["median"] == 25


def test_resource_summary_excludes_warmup_samples() -> None:
    samples = [
        {"timestamp_utc": "2026-01-01T00:00:00Z", "cpu_percent": 99, "rss_mb": 999},
        {"timestamp_utc": "2026-01-01T00:00:01Z", "cpu_percent": 20, "rss_mb": 100},
        {"timestamp_utc": "2026-01-01T00:00:02+00:00", "cpu_percent": 40, "rss_mb": 120},
    ]

    result = summarize_resource_samples(samples, "2026-01-01T00:00:01+00:00")

    assert result["sample_count"] == 2
    assert result["cpu_mean_percent"] == 30
    assert result["cpu_peak_percent"] == 40
    assert result["rss_mean_mb"] == 110


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://user:secret@example.com/eventhub_benchmark_disposable",
        "postgresql+psycopg://user:secret@localhost/eventhub",
        "sqlite:///eventhub_benchmark_disposable.db",
    ],
)
def test_destructive_target_safety_rejects_remote_valuable_or_non_postgres(url: str) -> None:
    with pytest.raises(ValueError):
        safe_database_identity(url)


def test_destructive_target_safety_accepts_explicit_local_disposable_database() -> None:
    identity = safe_database_identity(
        "postgresql+psycopg://user:secret@127.0.0.1:5433/eventhub_test_disposable"
    )
    assert identity == {
        "engine": "PostgreSQL",
        "host": "127.0.0.1",
        "database": "eventhub_test_disposable",
    }


def test_redaction_removes_credentials_but_keeps_non_secret_provenance() -> None:
    redacted = redact_url(
        "postgresql+psycopg://eventhub:top-secret@localhost:5433/eventhub_disposable"
    )
    assert "top-secret" not in redacted
    assert "eventhub@" not in redacted
    assert redacted == "postgresql+psycopg://localhost:5433/eventhub_disposable"


def test_saturation_is_not_invented_and_detects_threshold_breach() -> None:
    safe_steps = [
        {
            "concurrency": 1,
            "aggregate": {
                "requests_per_second": {"median": 10},
                "p95_ms": {"median": 20},
                "error_rate": {"median": 0},
            },
        },
        {
            "concurrency": 5,
            "aggregate": {
                "requests_per_second": {"median": 40},
                "p95_ms": {"median": 40},
                "error_rate": {"median": 0},
            },
        },
    ]
    assert saturation_conclusion(safe_steps)["reached"] is False

    breached = [
        *safe_steps,
        {
            "concurrency": 10,
            "aggregate": {
                "requests_per_second": {"median": 45},
                "p95_ms": {"median": 1100},
                "error_rate": {"median": 0},
            },
        },
    ]
    assert saturation_conclusion(breached) == {
        "reached": True,
        "concurrency": 10,
        "reason": "p95",
    }
