"""SQLAlchemy public-event instrumentation with precisely named timing semantics."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy import Engine, event

from app.observability.metrics import MetricsRegistry

_CHECKOUT_STARTED = "eventhub_checkout_started"
_QUERY_STARTED = "eventhub_query_started"


class SqlAlchemyMetrics:
    def __init__(self, engine: Engine, metrics: MetricsRegistry) -> None:
        self.engine = engine
        self.metrics = metrics
        self.clock = metrics.clock

    def do_connect(self, dialect: Any, connection_record: Any, cargs: Any, cparams: Any) -> Any:
        """Time the actual public dialect connect call without acquiring eagerly."""
        del connection_record
        started = self.clock()
        try:
            return dialect.connect(*cargs, **cparams)
        finally:
            self.metrics.observe(
                "eventhub_db_connection_creation_duration_seconds", self.clock() - started
            )

    def connection_created(self, dbapi_connection: Any, connection_record: Any) -> None:
        del dbapi_connection, connection_record
        self.metrics.increment("eventhub_db_connections_created_total")

    def checkout(self, dbapi_connection: Any, connection_record: Any, proxy: Any) -> None:
        del dbapi_connection, proxy
        connection_record.info[_CHECKOUT_STARTED] = self.clock()
        self.metrics.increment("eventhub_db_pool_checkouts_total")
        self.metrics.gauge_add("eventhub_db_pool_checked_out", amount=1)

    def checkin(self, dbapi_connection: Any, connection_record: Any) -> None:
        del dbapi_connection
        started = connection_record.info.pop(_CHECKOUT_STARTED, None)
        if started is not None:
            self.metrics.observe(
                "eventhub_db_connection_hold_duration_seconds", self.clock() - started
            )
            self.metrics.gauge_add("eventhub_db_pool_checked_out", amount=-1)

    def before_cursor_execute(
        self,
        connection: Any,
        cursor: Any,
        statement: Any,
        parameters: Any,
        context: Any,
        executemany: Any,
    ) -> None:
        del cursor, statement, parameters, context, executemany
        connection.info.setdefault(_QUERY_STARTED, []).append(self.clock())

    def after_cursor_execute(
        self,
        connection: Any,
        cursor: Any,
        statement: Any,
        parameters: Any,
        context: Any,
        executemany: Any,
    ) -> None:
        del cursor, statement, parameters, context, executemany
        self._finish_query(connection, "success")

    def handle_error(self, exception_context: Any) -> None:
        connection = exception_context.connection
        if connection is not None:
            self._finish_query(connection, "error")

    def _finish_query(self, connection: Any, outcome: str) -> None:
        starts = connection.info.get(_QUERY_STARTED, [])
        if not starts:
            return
        started = starts.pop()
        self.metrics.increment("eventhub_db_queries_total", (outcome,))
        self.metrics.observe(
            "eventhub_db_query_duration_seconds", self.clock() - started, (outcome,)
        )


def instrument_sqlalchemy(engine: Engine, metrics: MetricsRegistry) -> SqlAlchemyMetrics:
    """Attach public SQLAlchemy events without changing lazy acquisition or transactions."""
    observer = SqlAlchemyMetrics(engine, metrics)
    event.listen(engine.dialect, "do_connect", observer.do_connect, retval=True)
    event.listen(engine, "connect", observer.connection_created)
    event.listen(engine, "checkout", observer.checkout)
    event.listen(engine, "checkin", observer.checkin)
    event.listen(engine, "before_cursor_execute", observer.before_cursor_execute)
    event.listen(engine, "after_cursor_execute", observer.after_cursor_execute)
    event.listen(engine, "handle_error", observer.handle_error)

    pool = engine.pool
    checkedout: Callable[[], int] | None = getattr(pool, "checkedout", None)
    overflow: Callable[[], int] | None = getattr(pool, "overflow", None)

    def pool_snapshot() -> dict[str, float]:
        snapshot: dict[str, float] = {}
        if callable(checkedout):
            snapshot["eventhub_db_pool_checked_out"] = float(checkedout())
        if callable(overflow):
            snapshot["eventhub_db_pool_overflow_connections"] = float(max(0, overflow()))
        return snapshot

    metrics.set_pool_snapshot_provider(pool_snapshot)
    return observer
