"""Deterministic dataset for load testing.

Every benchmark run must start from the same data, otherwise before/after comparisons in
Phase 2 are meaningless. The random seed is fixed, so running this twice against a fresh
database produces identical rows.

Usage:
    python benchmark/seed_data.py                    # default: 500 events
    python benchmark/seed_data.py --events 5000      # larger catalogue
    python benchmark/seed_data.py --reset            # drop and recreate the schema first
"""

import argparse
import random
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.domain.enums import EventStatus, UserRole  # noqa: E402
from app.domain.models import Event, User  # noqa: E402
from app.infrastructure.db import orm  # noqa: E402,F401
from app.infrastructure.db.base import Base, build_engine, build_session_factory  # noqa: E402
from app.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork  # noqa: E402
from app.infrastructure.security.bcrypt_hasher import BcryptPasswordHasher  # noqa: E402

SEED = 20260920
CITIES = ["Hanoi", "Da Nang", "Ho Chi Minh City", "Hue", "Can Tho"]
CATEGORIES = ["music", "sport", "conference", "workshop", "theatre"]

ORGANIZER_EMAIL = "bench-organizer@example.com"
BUYER_EMAIL = "bench-buyer@example.com"
BENCH_PASSWORD = "loadtest-password"


def seed(event_count: int, reset: bool) -> None:
    random.seed(SEED)
    settings = get_settings()
    engine = build_engine(settings)

    if reset:
        Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    session_factory = build_session_factory(engine)
    uow = SqlAlchemyUnitOfWork(session_factory)
    # Cost factor 4 keeps seeding fast; it does not affect the API under test, which
    # uses the configured BCRYPT_ROUNDS.
    hasher = BcryptPasswordHasher(rounds=4)
    now = datetime.now(timezone.utc)

    with uow:
        if uow.users.exists_by_email(ORGANIZER_EMAIL):
            print("database already seeded; pass --reset to rebuild it")
            return

        organizer = uow.users.add(
            User(
                email=ORGANIZER_EMAIL,
                password_hash=hasher.hash(BENCH_PASSWORD),
                full_name="Benchmark Organizer",
                role=UserRole.ORGANIZER,
            )
        )
        uow.users.add(
            User(
                email=BUYER_EMAIL,
                password_hash=hasher.hash(BENCH_PASSWORD),
                full_name="Benchmark Buyer",
                role=UserRole.USER,
            )
        )

        for index in range(event_count):
            start = now + timedelta(days=random.randint(3, 180), hours=random.randint(0, 23))
            uow.events.add(
                Event(
                    title=f"Benchmark Event {index:05d}",
                    description=f"Seeded event number {index} for load testing.",
                    category=random.choice(CATEGORIES),
                    city=random.choice(CITIES),
                    location=f"Venue {index % 50}",
                    start_time=start,
                    end_time=start + timedelta(hours=3),
                    # Large inventory so a run measures throughput rather than
                    # immediately exhausting every event.
                    total_tickets=random.choice([500, 1000, 2000]),
                    price=Decimal(random.choice(["10.00", "25.50", "49.99", "120.00"])),
                    organizer_id=organizer.id,
                    status=EventStatus.PUBLISHED,
                )
            )
        uow.commit()

    safe_database_url = engine.url.render_as_string(hide_password=True)
    print(f"seeded {event_count} published events into {safe_database_url}")
    engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=int, default=500, help="number of published events")
    parser.add_argument(
        "--reset", action="store_true", help="drop and recreate the schema before seeding"
    )
    args = parser.parse_args()
    seed(args.events, args.reset)


if __name__ == "__main__":
    main()
