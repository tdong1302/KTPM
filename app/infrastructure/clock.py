"""Clock adapter. Injected so business rules that depend on time stay testable."""

from datetime import datetime, timezone


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)
