"""Ports: the only way the business layer talks to the outside world.

Everything here is a ``typing.Protocol`` or a plain dataclass. Concrete adapters live in
``app.infrastructure`` and are injected by ``app.api.deps``. This is what keeps the
business layer free of web-framework and database imports, as required by the course
brief ("Tầng nghiệp vụ không import framework web hay thư viện DB").
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from app.domain.enums import BookingStatus, EventStatus, UserRole
from app.domain.models import Booking, Event, User


@dataclass(frozen=True)
class TokenClaims:
    """What a verified access token asserts. Deliberately not a security-library type."""

    user_id: int
    email: str
    role: UserRole


@dataclass(frozen=True)
class EventQuery:
    """Search criteria for the event listing, expressed in domain terms."""

    q: str | None = None
    city: str | None = None
    category: str | None = None
    status: EventStatus | None = None
    organizer_id: int | None = None
    only_upcoming: bool = False
    sort_by: str = "start_time"
    sort_desc: bool = False


@runtime_checkable
class Clock(Protocol):
    def now(self) -> datetime:
        """Current time, always timezone-aware UTC."""


@runtime_checkable
class PasswordHasher(Protocol):
    def hash(self, raw_password: str) -> str: ...

    def verify(self, raw_password: str, password_hash: str) -> bool: ...


@runtime_checkable
class TokenService(Protocol):
    def issue(self, user: User) -> tuple[str, int]:
        """Return ``(token, expires_in_seconds)``."""

    def verify(self, token: str) -> TokenClaims:
        """Return the claims, or raise ``UnauthorizedError`` if the token is not valid."""


@runtime_checkable
class UserRepository(Protocol):
    def add(self, user: User) -> User: ...

    def get_by_id(self, user_id: int) -> User | None: ...

    def get_by_email(self, email: str) -> User | None: ...

    def exists_by_email(self, email: str) -> bool: ...


@runtime_checkable
class EventRepository(Protocol):
    def add(self, event: Event) -> Event: ...

    def get_by_id(self, event_id: int) -> Event | None: ...

    def get_for_update(self, event_id: int) -> Event | None:
        """Read an event with a row-level write lock held until the transaction ends.

        The business layer expresses the *intent* (serialise concurrent ticket
        reservations); the adapter decides how, e.g. ``SELECT ... FOR UPDATE``.
        """

    def update(self, event: Event) -> Event: ...

    def delete(self, event_id: int) -> None: ...

    def search(self, query: EventQuery, page: int, size: int) -> tuple[list[Event], int]:
        """Return ``(items, total_count)`` for the given 1-based page."""


@runtime_checkable
class BookingRepository(Protocol):
    def add(self, booking: Booking) -> Booking: ...

    def get_by_id(self, booking_id: int) -> Booking | None: ...

    def update(self, booking: Booking) -> Booking: ...

    def list_by_user(
        self, user_id: int, page: int, size: int, status: BookingStatus | None = None
    ) -> tuple[list[Booking], int]: ...

    def count_active_for_event(self, event_id: int) -> int: ...


@runtime_checkable
class UnitOfWork(Protocol):
    """Transaction boundary. Services open one per use case and commit at the end."""

    users: UserRepository
    events: EventRepository
    bookings: BookingRepository

    def __enter__(self) -> "UnitOfWork": ...

    def __exit__(self, exc_type, exc, tb) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...
