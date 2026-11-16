"""Deterministic tests for correlation, metrics and SQL timing semantics."""

import asyncio
import logging

from app.api.middleware import ObservabilityMiddleware
from app.observability.context import (
    MAX_CORRELATION_ID_LENGTH,
    effective_correlation_id,
    get_correlation_id,
)
from app.observability.metrics import MetricsRegistry
from app.observability.sqlalchemy_metrics import SqlAlchemyMetrics


def test_correlation_id_validation_preserves_only_conservative_values() -> None:
    assert effective_correlation_id("client-request_123") == "client-request_123"
    for invalid in (None, "", "has space", "line\nbreak", "x" * (MAX_CORRELATION_ID_LENGTH + 1)):
        replacement = effective_correlation_id(invalid)
        assert replacement != invalid
        assert len(replacement) == 32


def test_concurrent_request_contexts_are_isolated_and_cleaned() -> None:
    seen: list[tuple[str | None, str | None]] = []
    metrics = MetricsRegistry(lambda: 1.0)

    async def downstream(scope, receive, send):
        before = get_correlation_id()
        await asyncio.sleep(0)
        seen.append((before, get_correlation_id()))
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    middleware = ObservabilityMiddleware(
        downstream, metrics=metrics, routes_provider=lambda: [], log_format="json"
    )

    async def invoke(request_id: str) -> None:
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "headers": [(b"x-request-id", request_id.encode())],
        }

        async def send(message) -> None:
            del message

        await middleware(scope, lambda: None, send)

    async def run_concurrently() -> None:
        await asyncio.gather(invoke("request-a"), invoke("request-b"))

    asyncio.run(run_concurrently())

    assert set(seen) == {("request-a", "request-a"), ("request-b", "request-b")}
    assert get_correlation_id() is None


def test_unhandled_error_is_safe_and_cleans_inflight(caplog) -> None:
    secret = "authorization-secret-must-not-appear"
    messages = []
    ticks = iter([1.0, 1.25])
    metrics = MetricsRegistry(lambda: next(ticks))

    async def failing(scope, receive, send):
        raise RuntimeError(secret)

    async def send(message):
        messages.append(message)

    middleware = ObservabilityMiddleware(
        failing, metrics=metrics, routes_provider=lambda: [], log_format="json"
    )
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/failure/123",
        "headers": [(b"authorization", secret.encode())],
    }
    with caplog.at_level(logging.INFO, logger="eventhub.api"):
        asyncio.run(middleware(scope, lambda: None, send))

    start = next(message for message in messages if message["type"] == "http.response.start")
    headers = dict(start["headers"])
    rendered = metrics.render_prometheus()
    assert start["status"] == 500
    assert b"x-request-id" in headers
    assert 'eventhub_http_requests_in_flight{method="GET",route="unmatched"} 0' in rendered
    assert "eventhub_http_unhandled_exceptions_total" in rendered
    assert secret not in caplog.text
    assert get_correlation_id() is None


class _InfoOwner:
    def __init__(self) -> None:
        self.info = {}


def test_sqlalchemy_metrics_distinguish_creation_hold_and_query_time() -> None:
    ticks = iter([1.0, 1.4, 2.0, 2.5, 3.0, 3.2])
    metrics = MetricsRegistry(lambda: next(ticks))
    observer = SqlAlchemyMetrics(object(), metrics)
    record = _InfoOwner()
    connection = _InfoOwner()

    class Dialect:
        @staticmethod
        def connect(*args, **kwargs):
            return "connection"

    assert observer.do_connect(Dialect(), record, (), {}) == "connection"
    observer.connection_created(None, record)
    observer.checkout(None, record, None)
    observer.checkin(None, record)
    observer.before_cursor_execute(connection, None, None, None, None, None)
    observer.after_cursor_execute(connection, None, None, None, None, None)

    rendered = metrics.render_prometheus()
    assert "eventhub_db_connections_created_total 1" in rendered
    assert "eventhub_db_connection_creation_duration_seconds_sum 0.400000000" in rendered
    assert "eventhub_db_connection_hold_duration_seconds_sum 0.500000000" in rendered
    assert 'eventhub_db_queries_total{outcome="success"} 1' in rendered
    assert 'eventhub_db_query_duration_seconds_sum{outcome="success"} 0.200000000' in rendered
    assert "acquisition" not in rendered
    assert "wait" not in rendered


def test_histogram_buckets_remain_cumulative_at_render_time() -> None:
    metrics = MetricsRegistry(lambda: 1.0)
    labels = ("GET", "/test")
    metrics.observe("eventhub_http_request_duration_seconds", 0.004, labels)
    metrics.observe("eventhub_http_request_duration_seconds", 0.007, labels)
    metrics.observe("eventhub_http_request_duration_seconds", 12.0, labels)

    rendered = metrics.render_prometheus()

    assert (
        'eventhub_http_request_duration_seconds_bucket{method="GET",route="/test",le="0.005"} 1'
        in rendered
    )
    assert (
        'eventhub_http_request_duration_seconds_bucket{method="GET",route="/test",le="0.01"} 2'
        in rendered
    )
    assert (
        'eventhub_http_request_duration_seconds_bucket{method="GET",route="/test",le="10"} 2'
        in rendered
    )
    assert (
        'eventhub_http_request_duration_seconds_bucket{method="GET",route="/test",le="+Inf"} 3'
        in rendered
    )
