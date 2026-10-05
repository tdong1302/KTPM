"""Event lifecycle rules, exercised without a database or an HTTP server."""

from datetime import timedelta
from decimal import Decimal

import pytest

from app.application.event_service import CreateEventCommand, EventService
from app.application.ports import EventQuery
from app.domain.enums import EventStatus, UserRole
from app.domain.errors import ConflictError, ForbiddenError, NotFoundError, ValidationError
from tests.unit.fakes import FakeClock, FakeUnitOfWork, make_event

ORGANIZER_ID = 1
OTHER_ORGANIZER_ID = 2


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def uow() -> FakeUnitOfWork:
    return FakeUnitOfWork()


@pytest.fixture
def service(uow: FakeUnitOfWork, clock: FakeClock) -> EventService:
    return EventService(uow, clock)


def a_command(clock: FakeClock, **overrides) -> CreateEventCommand:
    start = clock.now() + timedelta(days=30)
    defaults = dict(
        title="Concert",
        description="A live concert",
        category="music",
        city="Hanoi",
        location="Main Hall",
        start_time=start,
        end_time=start + timedelta(hours=3),
        total_tickets=100,
        price=Decimal("50.00"),
    )
    defaults.update(overrides)
    return CreateEventCommand(**defaults)


class TestCreate:
    def test_organizer_creates_a_draft_with_full_inventory(self, service, clock):
        event = service.create(ORGANIZER_ID, UserRole.ORGANIZER, a_command(clock))

        assert event.id is not None
        assert event.status == EventStatus.DRAFT
        assert event.available_tickets == 100
        assert event.organizer_id == ORGANIZER_ID

    def test_admin_may_also_create(self, service, clock):
        event = service.create(99, UserRole.ADMIN, a_command(clock))
        assert event.status == EventStatus.DRAFT

    def test_plain_user_cannot_create(self, service, clock):
        with pytest.raises(ForbiddenError):
            service.create(ORGANIZER_ID, UserRole.USER, a_command(clock))

    def test_rejects_start_time_in_the_past(self, service, clock):
        past = clock.now() - timedelta(days=1)
        command = a_command(clock, start_time=past, end_time=past + timedelta(hours=2))
        with pytest.raises(ValidationError):
            service.create(ORGANIZER_ID, UserRole.ORGANIZER, command)

    def test_rejects_end_before_start(self, service, clock):
        start = clock.now() + timedelta(days=10)
        command = a_command(clock, start_time=start, end_time=start - timedelta(hours=1))
        with pytest.raises(ValidationError):
            service.create(ORGANIZER_ID, UserRole.ORGANIZER, command)

    def test_rejects_zero_tickets(self, service, clock):
        with pytest.raises(ValidationError):
            service.create(ORGANIZER_ID, UserRole.ORGANIZER, a_command(clock, total_tickets=0))

    def test_rejects_blank_title(self, service, clock):
        with pytest.raises(ValidationError):
            service.create(ORGANIZER_ID, UserRole.ORGANIZER, a_command(clock, title="   "))

    def test_commits_exactly_once(self, service, uow, clock):
        service.create(ORGANIZER_ID, UserRole.ORGANIZER, a_command(clock))
        assert uow.commits == 1


class TestTransitions:
    def test_publish_moves_draft_to_published(self, service, uow):
        event = make_event(uow, ORGANIZER_ID, status=EventStatus.DRAFT)
        published = service.publish(event.id, ORGANIZER_ID, UserRole.ORGANIZER)
        assert published.status == EventStatus.PUBLISHED

    def test_transition_locks_the_event_row(self, service, uow):
        event = make_event(uow, ORGANIZER_ID, status=EventStatus.DRAFT)

        service.publish(event.id, ORGANIZER_ID, UserRole.ORGANIZER)

        assert uow.events.lock_calls == 1

    def test_publishing_twice_conflicts(self, service, uow):
        event = make_event(uow, ORGANIZER_ID, status=EventStatus.DRAFT)
        service.publish(event.id, ORGANIZER_ID, UserRole.ORGANIZER)
        with pytest.raises(ConflictError):
            service.publish(event.id, ORGANIZER_ID, UserRole.ORGANIZER)

    def test_cannot_publish_an_event_that_already_started(self, service, uow, clock):
        past = clock.now() - timedelta(hours=1)
        event = make_event(uow, ORGANIZER_ID, status=EventStatus.DRAFT, start_time=past)
        with pytest.raises(ValidationError):
            service.publish(event.id, ORGANIZER_ID, UserRole.ORGANIZER)

    def test_cancelled_event_is_terminal(self, service, uow):
        event = make_event(uow, ORGANIZER_ID, status=EventStatus.DRAFT)
        service.cancel(event.id, ORGANIZER_ID, UserRole.ORGANIZER)
        with pytest.raises(ConflictError):
            service.publish(event.id, ORGANIZER_ID, UserRole.ORGANIZER)

    def test_another_organizer_cannot_publish(self, service, uow):
        event = make_event(uow, ORGANIZER_ID, status=EventStatus.DRAFT)
        with pytest.raises(ForbiddenError):
            service.publish(event.id, OTHER_ORGANIZER_ID, UserRole.ORGANIZER)

    def test_admin_may_publish_any_event(self, service, uow):
        event = make_event(uow, ORGANIZER_ID, status=EventStatus.DRAFT)
        assert service.publish(event.id, 999, UserRole.ADMIN).status == EventStatus.PUBLISHED

    def test_unknown_event_is_not_found(self, service):
        with pytest.raises(NotFoundError):
            service.publish(4242, ORGANIZER_ID, UserRole.ORGANIZER)


class TestDelete:
    def test_draft_without_reservations_is_deleted(self, service, uow):
        event = make_event(uow, ORGANIZER_ID, status=EventStatus.DRAFT)
        service.delete(event.id, ORGANIZER_ID, UserRole.ORGANIZER)
        assert uow.events.get_by_id(event.id) is None

    def test_delete_locks_the_event_row(self, service, uow):
        event = make_event(uow, ORGANIZER_ID, status=EventStatus.DRAFT)

        service.delete(event.id, ORGANIZER_ID, UserRole.ORGANIZER)

        assert uow.events.lock_calls == 1

    def test_published_event_cannot_be_deleted(self, service, uow):
        event = make_event(uow, ORGANIZER_ID, status=EventStatus.PUBLISHED)
        with pytest.raises(ConflictError):
            service.delete(event.id, ORGANIZER_ID, UserRole.ORGANIZER)

    def test_draft_with_reservations_cannot_be_deleted(self, service, uow):
        event = make_event(
            uow, ORGANIZER_ID, status=EventStatus.DRAFT, total_tickets=10, available_tickets=7
        )
        with pytest.raises(ConflictError):
            service.delete(event.id, ORGANIZER_ID, UserRole.ORGANIZER)

    def test_other_organizer_cannot_delete(self, service, uow):
        event = make_event(uow, ORGANIZER_ID, status=EventStatus.DRAFT)
        with pytest.raises(ForbiddenError):
            service.delete(event.id, OTHER_ORGANIZER_ID, UserRole.ORGANIZER)


class TestVisibilityAndSearch:
    def test_draft_is_hidden_from_strangers(self, service, uow):
        event = make_event(uow, ORGANIZER_ID, status=EventStatus.DRAFT)
        with pytest.raises(NotFoundError):
            service.get(event.id, actor_id=OTHER_ORGANIZER_ID, actor_role=UserRole.USER)

    def test_draft_is_visible_to_its_organizer(self, service, uow):
        event = make_event(uow, ORGANIZER_ID, status=EventStatus.DRAFT)
        assert service.get(event.id, ORGANIZER_ID, UserRole.ORGANIZER).id == event.id

    def test_draft_is_visible_to_admin(self, service, uow):
        event = make_event(uow, ORGANIZER_ID, status=EventStatus.DRAFT)
        assert service.get(event.id, 999, UserRole.ADMIN).id == event.id

    def test_published_event_is_visible_anonymously(self, service, uow):
        event = make_event(uow, ORGANIZER_ID, status=EventStatus.PUBLISHED)
        assert service.get(event.id).id == event.id

    def test_public_search_only_returns_published_events(self, service, uow):
        make_event(uow, ORGANIZER_ID, status=EventStatus.DRAFT)
        published = make_event(uow, ORGANIZER_ID, status=EventStatus.PUBLISHED)

        result = service.search_public(EventQuery(), page=1, size=10)

        assert [e.id for e in result.items] == [published.id]
        assert result.total == 1

    def test_search_clamps_page_size(self, service, uow):
        make_event(uow, ORGANIZER_ID, status=EventStatus.PUBLISHED)
        result = service.search_public(EventQuery(), page=1, size=5000)
        assert result.size == 100

    def test_unknown_sort_field_falls_back_to_default(self, service, uow):
        """An unknown sort key must never reach the persistence layer."""
        make_event(uow, ORGANIZER_ID, status=EventStatus.PUBLISHED)
        result = service.search_public(EventQuery(sort_by="password_hash"), page=1, size=10)
        assert result.total == 1
