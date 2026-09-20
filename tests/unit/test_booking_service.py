"""Booking rules: inventory arithmetic, ownership and cancellation."""

from datetime import timedelta
from decimal import Decimal

import pytest

from app.application.booking_service import BookingService
from app.domain.enums import BookingStatus, EventStatus, UserRole
from app.domain.errors import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.domain.models import MAX_TICKETS_PER_BOOKING
from tests.unit.fakes import FakeClock, FakeUnitOfWork, make_event

BUYER_ID = 10
OTHER_BUYER_ID = 11
ORGANIZER_ID = 1


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def uow() -> FakeUnitOfWork:
    return FakeUnitOfWork()


@pytest.fixture
def service(uow: FakeUnitOfWork, clock: FakeClock) -> BookingService:
    return BookingService(uow, clock)


class TestBook:
    def test_booking_decrements_inventory_and_snapshots_the_event(self, service, uow):
        event = make_event(uow, ORGANIZER_ID, total_tickets=100, price="50.00")

        booking = service.book(BUYER_ID, event.id, quantity=3)

        assert booking.status == BookingStatus.CONFIRMED
        assert booking.quantity == 3
        assert booking.unit_price == Decimal("50.00")
        assert booking.total_price == Decimal("150.00")
        assert booking.event_title == event.title
        assert uow.events.get_by_id(event.id).available_tickets == 97

    def test_booking_reads_the_event_under_a_write_lock(self, service, uow):
        """Overselling is prevented by serialising on the event row, not by luck."""
        event = make_event(uow, ORGANIZER_ID, total_tickets=10)

        service.book(BUYER_ID, event.id, quantity=1)

        assert uow.events.lock_calls == 1

    def test_booking_the_last_tickets_empties_the_inventory(self, service, uow):
        event = make_event(uow, ORGANIZER_ID, total_tickets=4, available_tickets=4)
        service.book(BUYER_ID, event.id, quantity=4)
        assert uow.events.get_by_id(event.id).available_tickets == 0

    def test_cannot_book_more_than_remaining(self, service, uow):
        event = make_event(uow, ORGANIZER_ID, total_tickets=10, available_tickets=2)
        with pytest.raises(ConflictError):
            service.book(BUYER_ID, event.id, quantity=3)
        assert uow.events.get_by_id(event.id).available_tickets == 2

    def test_sold_out_event_rejects_booking(self, service, uow):
        event = make_event(uow, ORGANIZER_ID, total_tickets=5, available_tickets=0)
        with pytest.raises(ConflictError):
            service.book(BUYER_ID, event.id, quantity=1)

    def test_draft_event_is_not_bookable(self, service, uow):
        event = make_event(uow, ORGANIZER_ID, status=EventStatus.DRAFT)
        with pytest.raises(NotFoundError):
            service.book(BUYER_ID, event.id, quantity=1)

    def test_cancelled_event_is_not_bookable(self, service, uow):
        event = make_event(uow, ORGANIZER_ID, status=EventStatus.CANCELLED)
        with pytest.raises(ConflictError):
            service.book(BUYER_ID, event.id, quantity=1)

    def test_started_event_is_not_bookable(self, service, uow, clock):
        past = clock.now() - timedelta(hours=1)
        event = make_event(uow, ORGANIZER_ID, start_time=past)
        with pytest.raises(ConflictError):
            service.book(BUYER_ID, event.id, quantity=1)

    def test_unknown_event_is_not_found(self, service):
        with pytest.raises(NotFoundError):
            service.book(BUYER_ID, 4242, quantity=1)

    @pytest.mark.parametrize("quantity", [0, -1, MAX_TICKETS_PER_BOOKING + 1])
    def test_invalid_quantity_is_rejected(self, service, uow, quantity):
        event = make_event(uow, ORGANIZER_ID, total_tickets=100)
        with pytest.raises(ValidationError):
            service.book(BUYER_ID, event.id, quantity=quantity)
        assert uow.events.get_by_id(event.id).available_tickets == 100

    def test_failed_booking_does_not_commit(self, service, uow):
        event = make_event(uow, ORGANIZER_ID, total_tickets=1, available_tickets=0)
        with pytest.raises(ConflictError):
            service.book(BUYER_ID, event.id, quantity=1)
        assert uow.commits == 0


class TestCancel:
    def test_cancelling_returns_the_tickets(self, service, uow):
        event = make_event(uow, ORGANIZER_ID, total_tickets=10)
        booking = service.book(BUYER_ID, event.id, quantity=4)
        assert uow.events.get_by_id(event.id).available_tickets == 6

        cancelled = service.cancel(booking.id, BUYER_ID, UserRole.USER)

        assert cancelled.status == BookingStatus.CANCELLED
        assert cancelled.cancelled_at is not None
        assert uow.events.get_by_id(event.id).available_tickets == 10

    def test_cancelling_twice_conflicts(self, service, uow):
        event = make_event(uow, ORGANIZER_ID, total_tickets=10)
        booking = service.book(BUYER_ID, event.id, quantity=1)
        service.cancel(booking.id, BUYER_ID, UserRole.USER)
        with pytest.raises(ConflictError):
            service.cancel(booking.id, BUYER_ID, UserRole.USER)

    def test_inventory_never_exceeds_capacity_after_cancelling(self, service, uow):
        event = make_event(uow, ORGANIZER_ID, total_tickets=10)
        booking = service.book(BUYER_ID, event.id, quantity=5)
        service.cancel(booking.id, BUYER_ID, UserRole.USER)
        stored = uow.events.get_by_id(event.id)
        assert stored.available_tickets == stored.total_tickets

    def test_another_user_cannot_cancel_my_booking(self, service, uow):
        event = make_event(uow, ORGANIZER_ID, total_tickets=10)
        booking = service.book(BUYER_ID, event.id, quantity=1)
        with pytest.raises(ForbiddenError):
            service.cancel(booking.id, OTHER_BUYER_ID, UserRole.USER)

    def test_admin_may_cancel_any_booking(self, service, uow):
        event = make_event(uow, ORGANIZER_ID, total_tickets=10)
        booking = service.book(BUYER_ID, event.id, quantity=1)
        assert service.cancel(booking.id, 999, UserRole.ADMIN).status == BookingStatus.CANCELLED

    def test_cannot_cancel_after_the_event_started(self, service, uow, clock):
        event = make_event(uow, ORGANIZER_ID, total_tickets=10)
        booking = service.book(BUYER_ID, event.id, quantity=1)
        clock.advance(days=365)
        with pytest.raises(ConflictError):
            service.cancel(booking.id, BUYER_ID, UserRole.USER)

    def test_unknown_booking_is_not_found(self, service):
        with pytest.raises(NotFoundError):
            service.cancel(4242, BUYER_ID, UserRole.USER)


class TestRead:
    def test_list_mine_returns_only_my_bookings(self, service, uow):
        event = make_event(uow, ORGANIZER_ID, total_tickets=50)
        service.book(BUYER_ID, event.id, quantity=1)
        service.book(BUYER_ID, event.id, quantity=2)
        service.book(OTHER_BUYER_ID, event.id, quantity=1)

        page = service.list_mine(BUYER_ID, page=1, size=10)

        assert page.total == 2
        assert {b.user_id for b in page.items} == {BUYER_ID}

    def test_list_mine_reports_total_pages(self, service, uow):
        event = make_event(uow, ORGANIZER_ID, total_tickets=50)
        for _ in range(5):
            service.book(BUYER_ID, event.id, quantity=1)

        page = service.list_mine(BUYER_ID, page=1, size=2)

        assert (page.total, page.total_pages, len(page.items)) == (5, 3, 2)

    def test_owner_can_read_a_booking(self, service, uow):
        event = make_event(uow, ORGANIZER_ID, total_tickets=10)
        booking = service.book(BUYER_ID, event.id, quantity=1)
        assert service.get(booking.id, BUYER_ID, UserRole.USER).id == booking.id

    def test_stranger_cannot_read_a_booking(self, service, uow):
        event = make_event(uow, ORGANIZER_ID, total_tickets=10)
        booking = service.book(BUYER_ID, event.id, quantity=1)
        with pytest.raises(ForbiddenError):
            service.get(booking.id, OTHER_BUYER_ID, UserRole.USER)
