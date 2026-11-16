"""Request-local correlation identifiers."""

from __future__ import annotations

import re
import secrets
from contextvars import ContextVar, Token

MAX_CORRELATION_ID_LENGTH = 64
_VALID_CORRELATION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")
_correlation_id: ContextVar[str | None] = ContextVar("eventhub_correlation_id", default=None)


def is_valid_correlation_id(value: str | None) -> bool:
    """Accept a conservative printable identifier and reject control characters."""
    return bool(value and _VALID_CORRELATION_ID.fullmatch(value))


def effective_correlation_id(value: str | None) -> str:
    """Return a caller-provided safe ID, or a cryptographically random replacement."""
    if is_valid_correlation_id(value):
        return value
    return secrets.token_hex(16)


def set_correlation_id(value: str) -> Token[str | None]:
    return _correlation_id.set(value)


def reset_correlation_id(token: Token[str | None]) -> None:
    _correlation_id.reset(token)


def get_correlation_id() -> str | None:
    return _correlation_id.get()
