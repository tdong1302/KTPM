"""Domain aggregates.

Plain dataclasses. No ORM mapping, no validation framework, no web types: an instance
can be constructed and exercised in a unit test without a database or an HTTP server.

Business invariants live here as methods so that the rules are testable in isolation and
cannot be bypassed by a caller that forgets to check them.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Generic, TypeVar

from app.domain.enums import EVENT_TRANSITIONS, BookingStatus, EventStatus, UserRole
from app.domain.errors import ConflictError, ValidationError

T = TypeVar("T")

MAX_TICKETS_PER_BOOKING = 10


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Page(Generic[T]):
    """Our own pagination envelope.

    Deliberately not Spring-Data-style ``Page``/``Pageable`` from a persistence library:
    the business layer must not depend on one. See docs/architecture.md.
    """

    items: list[T]
    total: int
    page: int
    size: int

    @property
    def total_pages(self) -> int:
        if self.size <= 0:
            return 0
        return (self.total + self.size - 1) // self.size


@dataclass
class User:
    email: str
    password_hash: str
    full_name: str
    role: UserRole = UserRole.USER
    id: int | None = None
    created_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        self.email = self.email.strip().lower()


@dataclass
class Event:
    title: str
    description: str
    category: str
    city: str
    location: str
    start_time: datetime
    end_time: datetime
    total_tickets: int
    price: Decimal
    organizer_id: int
    available_tickets: int | None = None
    status: EventStatus = EventStatus.DRAFT
    id: int | None = None
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        if self.available_tickets is None:
            self.available_tickets = self.total_tickets

    @property
    def reserved_tickets(self) -> int:
        return self.total_tickets - (self.available_tickets or 0)

    def validate_basics(self) -> None:
        """Rules every event must satisfy, even as a draft."""
        for name in ("title", "category", "city", "location"):
            if not str(getattr(self, name) or "").strip():
                raise ValidationError(f"{name} must not be blank")
        if self.total_tickets <= 0:
            raise ValidationError("total_tickets must be greater than 0")
        if self.price < 0:
            raise ValidationError("price must not be negative")
        if self.start_time >= self.end_time:
            raise ValidationError("start_time must be before end_time")
        if not 0 <= (self.available_tickets or 0) <= self.total_tickets:
            raise ValidationError("available_tickets must be between 0 and total_tickets")

    def validate_publishable(self, now: datetime) -> None:
        """Extra rules that only apply when the event becomes publicly visible."""
        self.validate_basics()
        if not str(self.description or "").strip():
            raise ValidationError("description must not be blank when publishing")
        if self.start_time <= now:
            raise ValidationError("start_time must be in the future when publishing")

    def transition_to(self, target: EventStatus, now: datetime) -> None:
        if target == self.status:
            raise ConflictError(f"event is already {target.value}")
        if target not in EVENT_TRANSITIONS[self.status]:
            raise ConflictError(
                f"cannot transition event from {self.status.value} to {target.value}"
            )
        if target == EventStatus.PUBLISHED:
            self.validate_publishable(now)
        self.status = target
        self.updated_at = now

    def ensure_deletable(self) -> None:
        if self.status != EventStatus.DRAFT:
            raise ConflictError("only DRAFT events can be deleted")
        if self.reserved_tickets > 0:
            raise ConflictError("event has ticket reservations and cannot be deleted")

    def ensure_bookable(self, quantity: int, now: datetime) -> None:
        if self.status != EventStatus.PUBLISHED:
            raise ConflictError("event is not open for booking")
        if self.start_time <= now:
            raise ConflictError("event has already started")
        if (self.available_tickets or 0) < quantity:
            raise ConflictError("not enough tickets available")

    def reserve(self, quantity: int, now: datetime) -> None:
        self.ensure_bookable(quantity, now)
        self.available_tickets = (self.available_tickets or 0) - quantity
        self.updated_at = now

    def release(self, quantity: int, now: datetime) -> None:
        restored = (self.available_tickets or 0) + quantity
        if restored > self.total_tickets:
            raise ConflictError("available_tickets cannot exceed total_tickets")
        self.available_tickets = restored
        self.updated_at = now

    def is_visible_to(self, actor_id: int | None, actor_role: UserRole | None) -> bool:
        """Drafts and cancelled events are only visible to their organizer and admins."""
        if self.status in (EventStatus.PUBLISHED, EventStatus.COMPLETED):
            return True
        if actor_role == UserRole.ADMIN:
            return True
        return actor_id is not None and actor_id == self.organizer_id


@dataclass
class Booking:
    user_id: int
    event_id: int
    quantity: int
    unit_price: Decimal
    # Denormalised snapshot so a booking stays readable if the event later changes.
    event_title: str = ""
    event_start_time: datetime | None = None
    status: BookingStatus = BookingStatus.CONFIRMED
    id: int | None = None
    created_at: datetime = field(default_factory=utcnow)
    cancelled_at: datetime | None = None

    @property
    def total_price(self) -> Decimal:
        return self.unit_price * self.quantity

    @staticmethod
    def validate_quantity(quantity: int) -> None:
        if quantity <= 0:
            raise ValidationError("quantity must be greater than 0")
        if quantity > MAX_TICKETS_PER_BOOKING:
            raise ValidationError(
                f"quantity must not exceed {MAX_TICKETS_PER_BOOKING} tickets per booking"
            )

    def cancel(self, now: datetime) -> None:
        if self.status == BookingStatus.CANCELLED:
            raise ConflictError("booking is already cancelled")
        self.status = BookingStatus.CANCELLED
        self.cancelled_at = now

    def is_owned_by(self, actor_id: int, actor_role: UserRole) -> bool:
        return actor_role == UserRole.ADMIN or self.user_id == actor_id
