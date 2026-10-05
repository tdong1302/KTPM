"""In-memory adapters used by the unit tests.

Their existence is the point of the ports: business logic can be exercised with no
database, no HTTP server and no cryptography, which keeps the unit suite fast.
"""

from dataclasses import replace
from datetime import datetime, timedelta, timezone

from app.application.ports import EventQuery, TokenClaims
from app.domain.enums import BookingStatus, EventStatus
from app.domain.errors import UnauthorizedError
from app.domain.models import Booking, Event, User


class FakeClock:
    def __init__(self, now: datetime | None = None) -> None:
        self._now = now or datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)

    def now(self) -> datetime:
        return self._now

    def advance(self, **kwargs) -> None:
        self._now = self._now + timedelta(**kwargs)


class FakeHasher:
    """Reversible stand-in for bcrypt; keeps the unit suite fast."""

    def hash(self, raw_password: str) -> str:
        return f"hashed::{raw_password}"

    def verify(self, raw_password: str, password_hash: str) -> bool:
        return password_hash == f"hashed::{raw_password}"


class FakeTokenService:
    def __init__(self) -> None:
        self.issued: dict[str, TokenClaims] = {}

    def issue(self, user: User) -> tuple[str, int]:
        token = f"token-{user.id}"
        self.issued[token] = TokenClaims(user_id=user.id, email=user.email, role=user.role)
        return token, 3600

    def verify(self, token: str) -> TokenClaims:
        if token not in self.issued:
            raise UnauthorizedError("access token is invalid", code="TOKEN_INVALID")
        return self.issued[token]


class FakeUserRepository:
    def __init__(self) -> None:
        self.rows: dict[int, User] = {}
        self._next_id = 1

    def add(self, user: User) -> User:
        stored = replace(user, id=self._next_id)
        self.rows[self._next_id] = stored
        self._next_id += 1
        return replace(stored)

    def get_by_id(self, user_id: int) -> User | None:
        found = self.rows.get(user_id)
        return replace(found) if found else None

    def get_by_email(self, email: str) -> User | None:
        for user in self.rows.values():
            if user.email == email.strip().lower():
                return replace(user)
        return None

    def exists_by_email(self, email: str) -> bool:
        return self.get_by_email(email) is not None


class FakeEventRepository:
    def __init__(self) -> None:
        self.rows: dict[int, Event] = {}
        self._next_id = 1
        self.lock_calls = 0

    def add(self, event: Event) -> Event:
        stored = replace(event, id=self._next_id)
        self.rows[self._next_id] = stored
        self._next_id += 1
        return replace(stored)

    def get_by_id(self, event_id: int) -> Event | None:
        found = self.rows.get(event_id)
        return replace(found) if found else None

    def get_for_update(self, event_id: int) -> Event | None:
        self.lock_calls += 1
        return self.get_by_id(event_id)

    def update(self, event: Event) -> Event:
        self.rows[event.id] = replace(event)
        return replace(event)

    def delete(self, event_id: int) -> None:
        self.rows.pop(event_id, None)

    def search(self, query: EventQuery, page: int, size: int) -> tuple[list[Event], int]:
        items = list(self.rows.values())
        if query.status is not None:
            items = [e for e in items if e.status == query.status]
        if query.city:
            items = [e for e in items if e.city.lower() == query.city.lower()]
        if query.category:
            items = [e for e in items if e.category.lower() == query.category.lower()]
        if query.organizer_id is not None:
            items = [e for e in items if e.organizer_id == query.organizer_id]
        if query.q:
            needle = query.q.lower()
            items = [
                e for e in items if needle in e.title.lower() or needle in e.description.lower()
            ]
        items.sort(key=lambda e: getattr(e, query.sort_by), reverse=query.sort_desc)
        total = len(items)
        start = (page - 1) * size
        return [replace(e) for e in items[start : start + size]], total


class FakeBookingRepository:
    def __init__(self) -> None:
        self.rows: dict[int, Booking] = {}
        self._next_id = 1
        self.lock_calls = 0

    def add(self, booking: Booking) -> Booking:
        stored = replace(booking, id=self._next_id)
        self.rows[self._next_id] = stored
        self._next_id += 1
        return replace(stored)

    def get_by_id(self, booking_id: int) -> Booking | None:
        found = self.rows.get(booking_id)
        return replace(found) if found else None

    def get_for_update(self, booking_id: int) -> Booking | None:
        self.lock_calls += 1
        return self.get_by_id(booking_id)

    def update(self, booking: Booking) -> Booking:
        self.rows[booking.id] = replace(booking)
        return replace(booking)

    def list_by_user(
        self, user_id: int, page: int, size: int, status: BookingStatus | None = None
    ) -> tuple[list[Booking], int]:
        items = [b for b in self.rows.values() if b.user_id == user_id]
        if status is not None:
            items = [b for b in items if b.status == status]
        items.sort(key=lambda b: b.created_at, reverse=True)
        total = len(items)
        start = (page - 1) * size
        return [replace(b) for b in items[start : start + size]], total

    def count_active_for_event(self, event_id: int) -> int:
        return sum(
            1
            for b in self.rows.values()
            if b.event_id == event_id and b.status == BookingStatus.CONFIRMED
        )


class FakeUnitOfWork:
    def __init__(self) -> None:
        self.users = FakeUserRepository()
        self.events = FakeEventRepository()
        self.bookings = FakeBookingRepository()
        self.commits = 0
        self.rollbacks = 0

    def __enter__(self) -> "FakeUnitOfWork":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is not None:
            self.rollbacks += 1

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


def make_event(
    uow: FakeUnitOfWork,
    organizer_id: int = 1,
    status: EventStatus = EventStatus.PUBLISHED,
    total_tickets: int = 100,
    available_tickets: int | None = None,
    start_time: datetime | None = None,
    price: str = "50.00",
) -> Event:
    from decimal import Decimal

    start = start_time or datetime(2026, 6, 1, 19, 0, tzinfo=timezone.utc)
    return uow.events.add(
        Event(
            title="Concert",
            description="A live concert",
            category="music",
            city="Hanoi",
            location="Main Hall",
            start_time=start,
            end_time=start + timedelta(hours=3),
            total_tickets=total_tickets,
            available_tickets=available_tickets,
            price=Decimal(price),
            organizer_id=organizer_id,
            status=status,
        )
    )
