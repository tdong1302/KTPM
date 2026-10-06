"""PostgreSQL proves completion workers divide batches with SKIP LOCKED."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from threading import Event as ThreadEvent

import pytest

from app.application.event_completion_service import EventCompletionService
from app.config import Settings
from app.domain.enums import EventStatus, UserRole
from app.domain.models import Event, User
from app.infrastructure.db.base import Base, build_engine, build_session_factory
from app.infrastructure.db.orm import EventRecord
from app.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork
from tests.unit.fakes import FakeClock

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "")
REQUIRE_POSTGRES_TESTS = os.getenv("REQUIRE_POSTGRES_TESTS", "") == "1"

if REQUIRE_POSTGRES_TESTS and not TEST_DATABASE_URL.startswith("postgresql"):
    raise RuntimeError("REQUIRE_POSTGRES_TESTS=1 but TEST_DATABASE_URL is not PostgreSQL")

pytestmark = [
    pytest.mark.concurrency,
    pytest.mark.skipif(
        not TEST_DATABASE_URL.startswith("postgresql"),
        reason="needs a real PostgreSQL database; set TEST_DATABASE_URL to run",
    ),
]


@pytest.fixture
def session_factory():
    engine = build_engine(
        Settings(database_url=TEST_DATABASE_URL, db_pool_size=10, db_max_overflow=10)
    )
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    factory = build_session_factory(engine)
    yield factory
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


class PausingCompletionUnitOfWork(SqlAlchemyUnitOfWork):
    def __init__(self, session_factory, acquired: ThreadEvent, release: ThreadEvent):
        super().__init__(session_factory)
        self._acquired = acquired
        self._release = release

    def __enter__(self):
        uow = super().__enter__()
        claim = self.events.list_expired_published_for_update

        def claim_and_pause(*, now, limit):
            events = claim(now=now, limit=limit)
            self._acquired.set()
            if not self._release.wait(timeout=5):
                raise RuntimeError("timed out waiting to release completion locks")
            return events

        self.events.list_expired_published_for_update = claim_and_pause
        return uow


def _seed_expired_events(session_factory, clock, count=4):
    uow = SqlAlchemyUnitOfWork(session_factory)
    with uow:
        organizer = uow.users.add(
            User(
                email="completion-concurrency@example.com",
                password_hash="x",
                full_name="Completion Concurrency",
                role=UserRole.ORGANIZER,
            )
        )
        ids = []
        for index in range(count):
            end = clock.now() - timedelta(hours=count - index)
            event = uow.events.add(
                Event(
                    title=f"Expired {index}",
                    description="Concurrent completion fixture",
                    category="music",
                    city="Hanoi",
                    location="Main Hall",
                    start_time=end - timedelta(hours=2),
                    end_time=end,
                    total_tickets=10,
                    price=Decimal("10.00"),
                    organizer_id=organizer.id,
                    status=EventStatus.PUBLISHED,
                )
            )
            ids.append(event.id)
        uow.commit()
    return ids


def test_two_workers_skip_locked_rows_without_duplicate_updates_or_loss(session_factory):
    clock = FakeClock()
    event_ids = _seed_expired_events(session_factory, clock)
    acquired = ThreadEvent()
    release = ThreadEvent()
    first_service = EventCompletionService(
        PausingCompletionUnitOfWork(session_factory, acquired, release), clock
    )
    second_service = EventCompletionService(SqlAlchemyUnitOfWork(session_factory), clock)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(first_service.complete_batch, 2)
        assert acquired.wait(timeout=5), "first worker must acquire its batch deterministically"
        second = pool.submit(second_service.complete_batch, 4)
        try:
            second_result = second.result(timeout=5)
        finally:
            release.set()
        first_result = first.result(timeout=5)

    assert first_result.completed == 2
    assert second_result.completed == 2
    with session_factory() as session:
        statuses = {
            row.id: row.status
            for row in session.query(EventRecord).filter(EventRecord.id.in_(event_ids)).all()
        }
    assert statuses == {event_id: EventStatus.COMPLETED.value for event_id in event_ids}
    assert (
        EventCompletionService(SqlAlchemyUnitOfWork(session_factory), clock)
        .complete_batch()
        .selected
        == 0
    )
