"""Ticket booking use cases.

This is the contended part of the system and the reason this domain was chosen for the
course: ``book`` reads the event under a row-level write lock, decrements the ticket
counter and writes the booking inside one transaction. Without that lock, two concurrent
requests for the last ticket both read ``available_tickets == 1`` and both succeed --
overselling. The lock is requested through ``EventRepository.get_for_update``, so the
business layer states the intent while the adapter picks the mechanism.
"""

from app.application.event_service import normalise_paging
from app.application.ports import Clock, UnitOfWork
from app.domain.enums import BookingStatus, EventStatus, UserRole
from app.domain.errors import ConflictError, ForbiddenError, NotFoundError
from app.domain.models import Booking, Page


class BookingService:
    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def book(self, actor_id: int, event_id: int, quantity: int) -> Booking:
        Booking.validate_quantity(quantity)
        now = self._clock.now()
        with self._uow as uow:
            event = uow.events.get_for_update(event_id)
            if event is None or event.status == EventStatus.DRAFT:
                raise NotFoundError("event not found")

            # Raises ConflictError when sold out, not published, or already started.
            event.reserve(quantity, now)
            uow.events.update(event)

            booking = uow.bookings.add(
                Booking(
                    user_id=actor_id,
                    event_id=event_id,
                    quantity=quantity,
                    unit_price=event.price,
                    event_title=event.title,
                    event_start_time=event.start_time,
                    status=BookingStatus.CONFIRMED,
                    created_at=now,
                )
            )
            uow.commit()
            return booking

    def list_mine(self, actor_id: int, page: int, size: int) -> Page[Booking]:
        page, size = normalise_paging(page, size)
        with self._uow as uow:
            items, total = uow.bookings.list_by_user(actor_id, page, size)
            return Page(items=items, total=total, page=page, size=size)

    def get(self, booking_id: int, actor_id: int, actor_role: UserRole) -> Booking:
        with self._uow as uow:
            booking = uow.bookings.get_by_id(booking_id)
            if booking is None:
                raise NotFoundError("booking not found")
            if not booking.is_owned_by(actor_id, actor_role):
                raise ForbiddenError("this booking belongs to another user")
            return booking

    def cancel(self, booking_id: int, actor_id: int, actor_role: UserRole) -> Booking:
        now = self._clock.now()
        with self._uow as uow:
            booking = uow.bookings.get_by_id(booking_id)
            if booking is None:
                raise NotFoundError("booking not found")
            if not booking.is_owned_by(actor_id, actor_role):
                raise ForbiddenError("this booking belongs to another user")

            # Lock the event first, then mutate, so that cancel and book serialise on
            # the same row and the ticket counter stays consistent.
            event = uow.events.get_for_update(booking.event_id)
            if event is not None and event.start_time <= now:
                raise ConflictError("event has already started; booking can no longer be cancelled")

            booking.cancel(now)
            if event is not None:
                event.release(booking.quantity, now)
                uow.events.update(event)
            updated = uow.bookings.update(booking)
            uow.commit()
            return updated
