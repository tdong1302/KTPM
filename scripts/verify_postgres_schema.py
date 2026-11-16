"""Verify that DATABASE_URL points to PostgreSQL with the invariant constraints."""

from sqlalchemy import inspect

from app.config import get_settings
from app.infrastructure.db.base import build_engine

EXPECTED_CHECKS = {
    "users": {"ck_users_role"},
    "events": {
        "ck_events_total_tickets_positive",
        "ck_events_available_nonnegative",
        "ck_events_available_within_total",
        "ck_events_price_nonnegative",
        "ck_events_time_order",
        "ck_events_status",
    },
    "bookings": {
        "ck_bookings_quantity",
        "ck_bookings_unit_price_nonnegative",
        "ck_bookings_status",
    },
    "reservations": {
        "ck_reservations_quantity",
        "ck_reservations_time_order",
        "ck_reservations_status",
        "ck_reservations_booking_status",
    },
}


def main() -> int:
    settings = get_settings()
    engine = build_engine(settings)
    try:
        if engine.dialect.name != "postgresql":
            print("FAIL: DATABASE_URL is not using PostgreSQL")
            return 1
        inspector = inspect(engine)
        missing: list[str] = []
        for table, expected in EXPECTED_CHECKS.items():
            actual = {item["name"] for item in inspector.get_check_constraints(table)}
            missing.extend(f"{table}.{name}" for name in sorted(expected - actual))
        if missing:
            print("FAIL: missing check constraints: " + ", ".join(missing))
            return 1
        count = sum(map(len, EXPECTED_CHECKS.values()))
        print(f"PASS: PostgreSQL has all {count} domain check constraints")
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
