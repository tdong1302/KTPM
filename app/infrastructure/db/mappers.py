"""Translation between persistence records and domain aggregates."""

from datetime import datetime, timezone

from app.domain.enums import BookingStatus, EventStatus, UserRole
from app.domain.models import Booking, Event, User
from app.infrastructure.db.orm import BookingRecord, EventRecord, UserRecord


def _as_utc(value: datetime | None) -> datetime | None:
    """Normalise to timezone-aware UTC.

    SQLite (used by the fast integration tests) drops timezone information, so rows can
    come back naive. The domain always compares aware datetimes, so attach UTC here at
    the boundary rather than making every business rule defensive.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def user_to_domain(record: UserRecord) -> User:
    return User(
        id=record.id,
        email=record.email,
        password_hash=record.password_hash,
        full_name=record.full_name,
        role=UserRole(record.role),
        created_at=_as_utc(record.created_at),
    )


def user_to_record(user: User) -> UserRecord:
    return UserRecord(
        id=user.id,
        email=user.email,
        password_hash=user.password_hash,
        full_name=user.full_name,
        role=user.role.value,
        created_at=user.created_at,
    )


def event_to_domain(record: EventRecord) -> Event:
    return Event(
        id=record.id,
        title=record.title,
        description=record.description,
        category=record.category,
        city=record.city,
        location=record.location,
        start_time=_as_utc(record.start_time),
        end_time=_as_utc(record.end_time),
        total_tickets=record.total_tickets,
        available_tickets=record.available_tickets,
        price=record.price,
        status=EventStatus(record.status),
        organizer_id=record.organizer_id,
        created_at=_as_utc(record.created_at),
        updated_at=_as_utc(record.updated_at),
    )


def event_to_record(event: Event) -> EventRecord:
    return EventRecord(
        id=event.id,
        title=event.title,
        description=event.description,
        category=event.category,
        city=event.city,
        location=event.location,
        start_time=event.start_time,
        end_time=event.end_time,
        total_tickets=event.total_tickets,
        available_tickets=event.available_tickets,
        price=event.price,
        status=event.status.value,
        organizer_id=event.organizer_id,
        created_at=event.created_at,
        updated_at=event.updated_at,
    )


def apply_event(record: EventRecord, event: Event) -> EventRecord:
    """Copy mutable domain state back onto an already-loaded record."""
    record.title = event.title
    record.description = event.description
    record.category = event.category
    record.city = event.city
    record.location = event.location
    record.start_time = event.start_time
    record.end_time = event.end_time
    record.total_tickets = event.total_tickets
    record.available_tickets = event.available_tickets
    record.price = event.price
    record.status = event.status.value
    record.updated_at = event.updated_at
    return record


def booking_to_domain(record: BookingRecord) -> Booking:
    return Booking(
        id=record.id,
        user_id=record.user_id,
        event_id=record.event_id,
        quantity=record.quantity,
        unit_price=record.unit_price,
        event_title=record.event_title,
        event_start_time=_as_utc(record.event_start_time),
        status=BookingStatus(record.status),
        created_at=_as_utc(record.created_at),
        cancelled_at=_as_utc(record.cancelled_at),
    )


def booking_to_record(booking: Booking) -> BookingRecord:
    return BookingRecord(
        id=booking.id,
        user_id=booking.user_id,
        event_id=booking.event_id,
        quantity=booking.quantity,
        unit_price=booking.unit_price,
        event_title=booking.event_title,
        event_start_time=booking.event_start_time,
        status=booking.status.value,
        created_at=booking.created_at,
        cancelled_at=booking.cancelled_at,
    )


def apply_booking(record: BookingRecord, booking: Booking) -> BookingRecord:
    record.quantity = booking.quantity
    record.status = booking.status.value
    record.cancelled_at = booking.cancelled_at
    return record
