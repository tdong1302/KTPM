"""Small structured-event layer built on the Python standard logging package."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Literal

from app.observability.context import get_correlation_id

LogFormat = Literal["json", "text"]


def configure_eventhub_logging() -> None:
    """Allow EventHub INFO events through an existing Uvicorn/root logging setup."""
    logging.getLogger("eventhub").setLevel(logging.INFO)


def emit_event(
    logger: logging.Logger,
    level: int,
    event: str,
    *,
    log_format: LogFormat = "json",
    correlation_id: str | None = None,
    **fields: Any,
) -> None:
    """Emit only explicitly supplied, non-sensitive fields.

    Exception messages and request data are deliberately not accepted implicitly. Callers
    supply bounded classifications such as ``exception_type`` instead.
    """
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": logging.getLevelName(level),
        "logger": logger.name,
        "event": event,
        "correlation_id": correlation_id or get_correlation_id() or "none",
        **fields,
    }
    if log_format == "text":
        message = " ".join(f"{key}={value}" for key, value in payload.items())
    else:
        message = json.dumps(payload, separators=(",", ":"), sort_keys=True, default=str)
    logger.log(level, message, extra={"event_name": event, "event_fields": payload})
