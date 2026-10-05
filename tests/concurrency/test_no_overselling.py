"""Concurrency safety of ticket reservation.

This is the correctness property that motivated choosing this domain for the course: when
many people race for the last tickets, the system must never sell more than it has.

It only runs against a real PostgreSQL database, because the guarantee comes from
``SELECT ... FOR UPDATE`` row locking. SQLite serialises all writers anyway, so passing
there would prove nothing. Set TEST_DATABASE_URL to enable it, for example:

    TEST_DATABASE_URL=postgresql+psycopg://eventhub:eventhub@localhost:5432/eventhub_ktpm

Without that variable the test is SKIPPED, not silently passed.
"""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.application.booking_service import BookingService
from app.config import Settings
from app.domain.enums import BookingStatus, EventStatus, UserRole
from app.domain.errors import DomainError
from app.domain.models import Event, User
from app.infrastructure.clock import SystemClock
from app.infrastructure.db.base import Base, build_engine, build_session_factory
from app.infrastructure.db.orm import BookingRecord, EventRecord, UserRecord
from app.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "")

pytestmark = [
    pytest.mark.concurrency,
    pytest.mark.skipif(
        not TEST_DATABASE_URL.startswith("postgresql"),
        reason="needs a real PostgreSQL database; set TEST_DATABASE_URL to run",
    ),
]


@pytest.fixture
def session_factory():
    settings = Settings(database_url=TEST_DATABASE_URL, db_pool_size=20, db_max_overflow=20)
    engine = build_engine(settings)
    # Start from a clean schema so repeated runs stay independent.
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    factory = build_session_factory(engine)
    yield factory
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def _seed(session_factory, total_tickets: int) -> tuple[int, list[int]]:
    """Create one published event plus enough buyers, and return their ids."""
    uow = SqlAlchemyUnitOfWork(session_factory)
    start = datetime.now(timezone.utc) + timedelta(days=30)
    with uow:
        organizer = uow.users.add(
            User(
                email="organizer@example.com",
                password_hash="x",
                full_name="Organizer",
                role=UserRole.ORGANIZER,
            )
        )
        buyer_ids = [
            uow.users.add(
                User(
                    email=f"buyer{i}@example.com",
                    password_hash="x",
                    full_name=f"Buyer {i}",
                    role=UserRole.USER,
                )
            ).id
            for i in range(40)
        ]
        event = uow.events.add(
            Event(
                title="Sold Out Show",
                description="One night only",
                category="music",
                city="Hanoi",
                location="Main Hall",
                start_time=start,
                end_time=start + timedelta(hours=3),
                total_tickets=total_tickets,
                price=Decimal("10.00"),
                organizer_id=organizer.id,
                status=EventStatus.PUBLISHED,
            )
        )
        uow.commit()
    return event.id, buyer_ids


def _book_once(session_factory, event_id: int, buyer_id: int, quantity: int) -> bool:
    """Attempt one booking in its own transaction. True if it succeeded."""
    service = BookingService(SqlAlchemyUnitOfWork(session_factory), SystemClock())
    try:
        service.book(buyer_id, event_id, quantity)
        return True
    except DomainError:
        return False


def _run_concurrently(session_factory, event_id, buyer_ids, quantity, workers) -> int:
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(
            pool.map(
                lambda buyer_id: _book_once(session_factory, event_id, buyer_id, quantity),
                buyer_ids,
            )
        )
    return sum(results)


def _read_state(session_factory, event_id: int) -> tuple[int, int]:
    """Return (available_tickets, confirmed_tickets_sold) straight from the database."""
    with session_factory() as session:
        event = session.get(EventRecord, event_id)
        sold = sum(
            row.quantity
            for row in session.query(BookingRecord)
            .filter(
                BookingRecord.event_id == event_id,
                BookingRecord.status == BookingStatus.CONFIRMED.value,
            )
            .all()
        )
        return event.available_tickets, sold


def test_only_one_buyer_gets_the_last_ticket(session_factory):
    event_id, buyer_ids = _seed(session_factory, total_tickets=1)

    successes = _run_concurrently(session_factory, event_id, buyer_ids[:20], quantity=1, workers=20)

    available, sold = _read_state(session_factory, event_id)
    assert successes == 1, "exactly one of 20 concurrent buyers may win the last ticket"
    assert sold == 1
    assert available == 0


def test_inventory_is_never_oversold_under_contention(session_factory):
    total = 10
    event_id, buyer_ids = _seed(session_factory, total_tickets=total)

    successes = _run_concurrently(session_factory, event_id, buyer_ids, quantity=1, workers=40)

    available, sold = _read_state(session_factory, event_id)
    assert successes == total
    assert sold == total
    assert available == 0
    assert sold + available == total, "tickets must be conserved"


def test_multi_ticket_bookings_do_not_oversell(session_factory):
    total = 10
    event_id, buyer_ids = _seed(session_factory, total_tickets=total)

    successes = _run_concurrently(session_factory, event_id, buyer_ids, quantity=3, workers=40)

    available, sold = _read_state(session_factory, event_id)
    assert successes == 3, "10 tickets in batches of 3 means 3 winners and 1 ticket left"
    assert sold == 9
    assert available == 1
    assert sold + available == total


def test_concurrent_cancellations_restore_exactly_what_was_taken(session_factory):
    total = 20
    event_id, buyer_ids = _seed(session_factory, total_tickets=total)
    _run_concurrently(session_factory, event_id, buyer_ids[:20], quantity=1, workers=20)

    uow = SqlAlchemyUnitOfWork(session_factory)
    with uow:
        booking_ids = [row.id for row in uow.session.query(BookingRecord).all()]
    service_factory = lambda: BookingService(  # noqa: E731
        SqlAlchemyUnitOfWork(session_factory), SystemClock()
    )

    def cancel(booking_id: int) -> bool:
        try:
            service_factory().cancel(booking_id, 0, UserRole.ADMIN)
            return True
        except DomainError:
            return False

    with ThreadPoolExecutor(max_workers=20) as pool:
        cancelled = sum(pool.map(cancel, booking_ids))

    available, sold = _read_state(session_factory, event_id)
    assert cancelled == len(booking_ids)
    assert sold == 0
    assert available == total, "every released ticket must come back, exactly once"


def test_same_booking_can_only_be_cancelled_once_concurrently(session_factory):
    total = 20
    event_id, buyer_ids = _seed(session_factory, total_tickets=total)
    assert _run_concurrently(
        session_factory, event_id, buyer_ids[:2], quantity=1, workers=2
    ) == 2

    with session_factory() as session:
        booking_id = session.query(BookingRecord.id).order_by(BookingRecord.id).first()[0]

    def cancel_once(_: int) -> bool:
        service = BookingService(SqlAlchemyUnitOfWork(session_factory), SystemClock())
        try:
            service.cancel(booking_id, 0, UserRole.ADMIN)
            return True
        except DomainError:
            return False

    with ThreadPoolExecutor(max_workers=20) as pool:
        successes = sum(pool.map(cancel_once, range(20)))

    available, sold = _read_state(session_factory, event_id)
    assert successes == 1
    assert sold == 1
    assert available == total - sold
