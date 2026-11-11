"""Reserve, confirm, cancel and reclaim temporary holds."""

from datetime import timedelta

from app.application.ports import Clock, UnitOfWork
from app.domain.enums import EventStatus, ReservationStatus
from app.domain.errors import ForbiddenError, NotFoundError
from app.domain.models import Booking, Event
from app.domain.reservation import Reservation

RESERVATION_DURATION = timedelta(minutes=10)


class ReservationService:
    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def reserve(self, actor_id: int, event_id: int, quantity: int) -> Reservation:
        Booking.validate_quantity(quantity)
        with self._uow as uow:
            event = uow.events.get_for_update(event_id)
            if event is None or event.status == EventStatus.DRAFT:
                raise NotFoundError("event not found")
            now = self._clock.now()
            event.reserve(quantity, now)
            uow.events.update(event)
            reservation = uow.reservations.add(
                Reservation(
                    user_id=actor_id,
                    event_id=event_id,
                    quantity=quantity,
                    expires_at=min(now + RESERVATION_DURATION, event.start_time),
                    created_at=now,
                )
            )
            uow.commit()
            return reservation

    def get(self, reservation_id: int, actor_id: int) -> Reservation:
        with self._uow as uow:
            return self._require_owned(uow.reservations.get_by_id(reservation_id), actor_id)

    def confirm(self, reservation_id: int, actor_id: int) -> Reservation:
        with self._uow as uow:
            event, reservation = self._lock_owned(uow, reservation_id, actor_id)
            if reservation.status == ReservationStatus.CONFIRMED:
                return reservation

            now = self._clock.now()
            reservation.require_active(now)
            # The tickets are already held, so only check whether sales are still open.
            event.ensure_bookable(0, now)
            booking = uow.bookings.add(
                Booking(
                    user_id=reservation.user_id,
                    event_id=reservation.event_id,
                    quantity=reservation.quantity,
                    unit_price=event.price,
                    event_title=event.title,
                    event_start_time=event.start_time,
                    created_at=now,
                )
            )
            reservation.status = ReservationStatus.CONFIRMED
            reservation.booking_id = booking.id
            updated = uow.reservations.update(reservation)
            uow.commit()
            return updated

    def cancel(self, reservation_id: int, actor_id: int) -> Reservation:
        with self._uow as uow:
            event, reservation = self._lock_owned(uow, reservation_id, actor_id)
            now = self._clock.now()
            reservation.require_active(now)
            event.release(reservation.quantity, now)
            reservation.status = ReservationStatus.CANCELLED
            uow.events.update(event)
            updated = uow.reservations.update(reservation)
            uow.commit()
            return updated

    def expire_batch(self, limit: int = 100) -> int:
        with self._uow as uow:
            ids = uow.reservations.list_due_ids(self._clock.now(), limit)

        # Each release owns one transaction and locks a single event before its hold.
        return sum(self._expire_one(reservation_id) for reservation_id in ids)

    def _expire_one(self, reservation_id: int) -> bool:
        with self._uow as uow:
            candidate = uow.reservations.get_by_id(reservation_id)
            if candidate is None:
                return False
            event = uow.events.get_for_update(candidate.event_id)
            reservation = uow.reservations.get_for_update(reservation_id)
            now = self._clock.now()
            if event is None or reservation is None or not reservation.is_due(now):
                return False
            event.release(reservation.quantity, now)
            reservation.status = ReservationStatus.EXPIRED
            uow.events.update(event)
            uow.reservations.update(reservation)
            uow.commit()
            return True

    def _lock_owned(
        self, uow: UnitOfWork, reservation_id: int, actor_id: int
    ) -> tuple[Event, Reservation]:
        candidate = self._require_owned(uow.reservations.get_by_id(reservation_id), actor_id)
        event = uow.events.get_for_update(candidate.event_id)
        reservation = self._require_owned(uow.reservations.get_for_update(reservation_id), actor_id)
        if event is None:
            raise NotFoundError("event not found")
        return event, reservation

    @staticmethod
    def _require_owned(reservation: Reservation | None, actor_id: int) -> Reservation:
        if reservation is None:
            raise NotFoundError("reservation not found")
        if reservation.user_id != actor_id:
            raise ForbiddenError("this reservation belongs to another user")
        return reservation
