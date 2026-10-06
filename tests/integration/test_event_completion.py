"""SQLite repository fallback and HTTP reflection of worker-completed events."""

from datetime import timedelta
from decimal import Decimal

from app.application.event_completion_service import EventCompletionService
from app.domain.enums import EventStatus, UserRole
from app.domain.models import Event, User
from app.infrastructure.db.orm import EventRecord
from app.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork
from tests.conftest import create_published_event, register_and_login
from tests.unit.fakes import FakeClock


def _add_event(uow, organizer_id, clock, *, title, end_offset, status):
    end = clock.now() + end_offset
    return uow.events.add(
        Event(
            title=title,
            description="Completion integration fixture",
            category="music",
            city="Hanoi",
            location="Main Hall",
            start_time=end - timedelta(hours=2),
            end_time=end,
            total_tickets=10,
            price=Decimal("10.00"),
            organizer_id=organizer_id,
            status=status,
        )
    )


def test_sqlite_repository_filters_orders_and_limits_claimed_rows(client):
    uow = SqlAlchemyUnitOfWork(client.app.state.session_factory)
    clock = FakeClock()
    with uow:
        organizer = uow.users.add(
            User(
                email="repository@example.com",
                password_hash="x",
                full_name="Repository Organizer",
                role=UserRole.ORGANIZER,
            )
        )
        later = _add_event(
            uow,
            organizer.id,
            clock,
            title="Later",
            end_offset=timedelta(minutes=-1),
            status=EventStatus.PUBLISHED,
        )
        earliest = _add_event(
            uow,
            organizer.id,
            clock,
            title="Earliest",
            end_offset=timedelta(hours=-3),
            status=EventStatus.PUBLISHED,
        )
        same_time = _add_event(
            uow,
            organizer.id,
            clock,
            title="Same time",
            end_offset=timedelta(hours=-3),
            status=EventStatus.PUBLISHED,
        )
        _add_event(
            uow,
            organizer.id,
            clock,
            title="Future",
            end_offset=timedelta(hours=1),
            status=EventStatus.PUBLISHED,
        )
        _add_event(
            uow,
            organizer.id,
            clock,
            title="Cancelled",
            end_offset=timedelta(hours=-4),
            status=EventStatus.CANCELLED,
        )
        _add_event(
            uow,
            organizer.id,
            clock,
            title="Draft",
            end_offset=timedelta(hours=-5),
            status=EventStatus.DRAFT,
        )
        _add_event(
            uow,
            organizer.id,
            clock,
            title="Completed",
            end_offset=timedelta(hours=-6),
            status=EventStatus.COMPLETED,
        )
        uow.commit()

    with uow:
        claimed = uow.events.list_expired_published_for_update(now=clock.now(), limit=2)

    assert [event.id for event in claimed] == [earliest.id, same_time.id]
    assert later.id not in [event.id for event in claimed]


def test_sqlite_completion_persists_and_is_idempotent(client):
    uow = SqlAlchemyUnitOfWork(client.app.state.session_factory)
    clock = FakeClock()
    with uow:
        organizer = uow.users.add(
            User(
                email="worker@example.com",
                password_hash="x",
                full_name="Worker Organizer",
                role=UserRole.ORGANIZER,
            )
        )
        event = _add_event(
            uow,
            organizer.id,
            clock,
            title="Ended event",
            end_offset=timedelta(seconds=0),
            status=EventStatus.PUBLISHED,
        )
        uow.commit()

    service = EventCompletionService(uow, clock)
    assert service.complete_batch().completed == 1
    assert service.complete_batch().completed == 0
    with client.app.state.session_factory() as session:
        assert session.get(EventRecord, event.id).status == EventStatus.COMPLETED.value


def test_completed_event_is_reflected_consistently_across_existing_api(client, organizer):
    buyer = register_and_login(client, "completion-buyer@example.com")
    event = create_published_event(organizer, total_tickets=10)
    booking = client.post(
        "/api/bookings",
        json={"event_id": event["id"], "quantity": 1},
        headers=buyer.headers,
    ).json()
    clock = FakeClock()

    with client.app.state.session_factory() as session:
        record = session.get(EventRecord, event["id"])
        record.start_time = clock.now() - timedelta(hours=2)
        record.end_time = clock.now() - timedelta(hours=1)
        session.commit()

    result = EventCompletionService(
        SqlAlchemyUnitOfWork(client.app.state.session_factory), clock
    ).complete_batch()

    assert result.completed == 1
    assert client.get(f"/api/events/{event['id']}").json()["status"] == "COMPLETED"
    assert client.get("/api/events").json()["total"] == 0
    mine = client.get(
        "/api/events/mine",
        params={"status": "COMPLETED"},
        headers=organizer.headers,
    ).json()
    assert mine["total"] == 1
    assert mine["items"][0]["id"] == event["id"]
    assert (
        client.patch(
            f"/api/events/{event['id']}",
            json={"title": "Too late"},
            headers=organizer.headers,
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/api/bookings",
            json={"event_id": event["id"], "quantity": 1},
            headers=buyer.headers,
        ).status_code
        == 409
    )
    assert client.get("/api/bookings/me", headers=buyer.headers).json()["total"] == 1
    assert client.get(f"/api/bookings/{booking['id']}", headers=buyer.headers).status_code == 200
    assert client.delete(f"/api/bookings/{booking['id']}", headers=buyer.headers).status_code == 409
