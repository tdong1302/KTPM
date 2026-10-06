"""Event lifecycle rules, exercised without a database or an HTTP server."""

from datetime import timedelta
from decimal import Decimal

import pytest

from app.application.event_service import CreateEventCommand, EventService, UpdateEventCommand
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


class TestUpdate:
    def test_partial_update_changes_only_supplied_fields_and_persists(self, service, uow, clock):
        event = make_event(uow, ORGANIZER_ID, status=EventStatus.DRAFT)

        updated = service.update(
            event.id,
            ORGANIZER_ID,
            UserRole.ORGANIZER,
            UpdateEventCommand(title="  Updated concert  ", price=Decimal("75.50")),
        )

        persisted = uow.events.get_by_id(event.id)
        assert updated.title == "Updated concert"
        assert updated.price == Decimal("75.50")
        assert updated.location == event.location
        assert persisted == updated
        assert updated.updated_at == clock.now()
        assert uow.commits == 1

    def test_update_locks_the_event_row(self, service, uow):
        event = make_event(uow, ORGANIZER_ID, status=EventStatus.DRAFT)

        service.update(
            event.id,
            ORGANIZER_ID,
            UserRole.ORGANIZER,
            UpdateEventCommand(title="Updated"),
        )

        assert uow.events.lock_calls == 1

    def test_capacity_update_resets_full_draft_inventory(self, service, uow):
        event = make_event(uow, ORGANIZER_ID, status=EventStatus.DRAFT, total_tickets=10)

        updated = service.update(
            event.id,
            ORGANIZER_ID,
            UserRole.ORGANIZER,
            UpdateEventCommand(total_tickets=25),
        )

        assert (updated.total_tickets, updated.available_tickets) == (25, 25)

    def test_capacity_update_rejects_inconsistent_reserved_draft(self, service, uow):
        event = make_event(
            uow,
            ORGANIZER_ID,
            status=EventStatus.DRAFT,
            total_tickets=10,
            available_tickets=8,
        )

        with pytest.raises(ConflictError):
            service.update(
                event.id,
                ORGANIZER_ID,
                UserRole.ORGANIZER,
                UpdateEventCommand(total_tickets=20),
            )

    def test_another_organizer_cannot_update(self, service, uow):
        event = make_event(uow, ORGANIZER_ID, status=EventStatus.DRAFT)

        with pytest.raises(ForbiddenError):
            service.update(
                event.id,
                OTHER_ORGANIZER_ID,
                UserRole.ORGANIZER,
                UpdateEventCommand(title="Stolen"),
            )

    def test_plain_user_cannot_update(self, service, uow):
        event = make_event(uow, ORGANIZER_ID, status=EventStatus.DRAFT)

        with pytest.raises(ForbiddenError):
            service.update(
                event.id,
                ORGANIZER_ID,
                UserRole.USER,
                UpdateEventCommand(title="Not allowed"),
            )

    def test_admin_follows_existing_owner_bypass_without_changing_owner(self, service, uow):
        event = make_event(uow, ORGANIZER_ID, status=EventStatus.DRAFT)

        updated = service.update(
            event.id,
            999,
            UserRole.ADMIN,
            UpdateEventCommand(title="Admin corrected title"),
        )

        assert updated.title == "Admin corrected title"
        assert updated.organizer_id == ORGANIZER_ID

    @pytest.mark.parametrize(
        "event_status",
        [EventStatus.PUBLISHED, EventStatus.CANCELLED, EventStatus.COMPLETED],
    )
    def test_non_draft_event_cannot_be_updated(self, service, uow, event_status):
        event = make_event(uow, ORGANIZER_ID, status=event_status)

        with pytest.raises(ConflictError):
            service.update(
                event.id,
                ORGANIZER_ID,
                UserRole.ORGANIZER,
                UpdateEventCommand(title="Too late"),
            )

    @pytest.mark.parametrize(
        "command",
        [
            UpdateEventCommand(title="   "),
            UpdateEventCommand(price=Decimal("-0.01")),
            UpdateEventCommand(total_tickets=0),
        ],
    )
    def test_invalid_title_price_and_capacity_are_rejected(self, service, uow, command):
        event = make_event(uow, ORGANIZER_ID, status=EventStatus.DRAFT)

        with pytest.raises(ValidationError):
            service.update(event.id, ORGANIZER_ID, UserRole.ORGANIZER, command)

    @pytest.mark.parametrize(
        "server_field",
        [{"organizer_id": 999}, {"status": EventStatus.PUBLISHED}],
    )
    def test_update_command_does_not_accept_owner_or_status(self, server_field):
        with pytest.raises(TypeError):
            UpdateEventCommand(**server_field)

    def test_failed_update_does_not_commit_or_persist_partial_changes(self, service, uow):
        event = make_event(uow, ORGANIZER_ID, status=EventStatus.DRAFT)

        with pytest.raises(ValidationError):
            service.update(
                event.id,
                ORGANIZER_ID,
                UserRole.ORGANIZER,
                UpdateEventCommand(title="Changed before failure", price=Decimal("-1.00")),
            )

        persisted = uow.events.get_by_id(event.id)
        assert persisted.title == event.title
        assert persisted.price == event.price
        assert uow.commits == 0

    def test_invalid_combined_time_order_is_rejected(self, service, uow):
        event = make_event(uow, ORGANIZER_ID, status=EventStatus.DRAFT)

        with pytest.raises(ValidationError):
            service.update(
                event.id,
                ORGANIZER_ID,
                UserRole.ORGANIZER,
                UpdateEventCommand(end_time=event.start_time - timedelta(hours=1)),
            )

    def test_empty_update_is_rejected_without_lock_or_commit(self, service, uow):
        event = make_event(uow, ORGANIZER_ID, status=EventStatus.DRAFT)

        with pytest.raises(ValidationError):
            service.update(
                event.id,
                ORGANIZER_ID,
                UserRole.ORGANIZER,
                UpdateEventCommand(),
            )

        assert uow.events.lock_calls == 0
        assert uow.commits == 0


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


class TestListMine:
    def test_returns_only_events_owned_by_the_organizer_including_all_statuses(self, service, uow):
        owned = [
            make_event(uow, ORGANIZER_ID, status=EventStatus.DRAFT),
            make_event(uow, ORGANIZER_ID, status=EventStatus.PUBLISHED),
            make_event(uow, ORGANIZER_ID, status=EventStatus.CANCELLED),
            make_event(uow, ORGANIZER_ID, status=EventStatus.COMPLETED),
        ]
        make_event(uow, OTHER_ORGANIZER_ID, status=EventStatus.DRAFT)

        result = service.list_mine(ORGANIZER_ID, UserRole.ORGANIZER, page=1, size=20)

        assert {event.id for event in result.items} == {event.id for event in owned}
        assert result.total == 4

    def test_forwards_pagination_owner_and_newest_first_ordering(self, service, uow):
        for _ in range(3):
            make_event(uow, ORGANIZER_ID, status=EventStatus.DRAFT)

        result = service.list_mine(ORGANIZER_ID, UserRole.ORGANIZER, page=2, size=1)

        query, page, size = uow.events.search_calls[-1]
        assert (page, size) == (2, 1)
        assert query.organizer_id == ORGANIZER_ID
        assert query.sort_by == "created_at"
        assert query.sort_desc is True
        assert (result.page, result.size, result.total) == (2, 1, 3)

    def test_filters_by_status(self, service, uow):
        draft = make_event(uow, ORGANIZER_ID, status=EventStatus.DRAFT)
        make_event(uow, ORGANIZER_ID, status=EventStatus.PUBLISHED)

        result = service.list_mine(
            ORGANIZER_ID,
            UserRole.ORGANIZER,
            page=1,
            size=20,
            event_status=EventStatus.DRAFT,
        )

        assert [event.id for event in result.items] == [draft.id]
        assert uow.events.search_calls[-1][0].status == EventStatus.DRAFT

    def test_rejects_plain_user(self, service):
        with pytest.raises(ForbiddenError):
            service.list_mine(ORGANIZER_ID, UserRole.USER, page=1, size=20)

    def test_admin_lists_only_events_owned_by_that_admin(self, service, uow):
        owned = make_event(uow, 99, status=EventStatus.DRAFT)
        make_event(uow, ORGANIZER_ID, status=EventStatus.DRAFT)

        result = service.list_mine(99, UserRole.ADMIN, page=1, size=20)

        assert [event.id for event in result.items] == [owned.id]
