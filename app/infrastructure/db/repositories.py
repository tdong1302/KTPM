"""Repository adapters: the concrete side of the ports in ``app.application.ports``."""

from datetime import datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.application.ports import EventQuery
from app.domain.enums import BookingStatus
from app.domain.models import Booking, Event, User
from app.infrastructure.db import mappers
from app.infrastructure.db.orm import BookingRecord, EventRecord, UserRecord

_SORT_COLUMNS = {
    "start_time": EventRecord.start_time,
    "price": EventRecord.price,
    "created_at": EventRecord.created_at,
}


def _supports_row_locks(session: Session) -> bool:
    """SQLite has no ``SELECT ... FOR UPDATE``; it serialises writers anyway."""
    bind = session.get_bind()
    return bind.dialect.name != "sqlite"


class SqlAlchemyUserRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, user: User) -> User:
        record = mappers.user_to_record(user)
        self._session.add(record)
        self._session.flush()
        return mappers.user_to_domain(record)

    def get_by_id(self, user_id: int) -> User | None:
        record = self._session.get(UserRecord, user_id)
        return mappers.user_to_domain(record) if record else None

    def get_by_email(self, email: str) -> User | None:
        record = self._session.scalar(
            select(UserRecord).where(UserRecord.email == email.strip().lower())
        )
        return mappers.user_to_domain(record) if record else None

    def exists_by_email(self, email: str) -> bool:
        found = self._session.scalar(
            select(UserRecord.id).where(UserRecord.email == email.strip().lower()).limit(1)
        )
        return found is not None


class SqlAlchemyEventRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, event: Event) -> Event:
        record = mappers.event_to_record(event)
        self._session.add(record)
        self._session.flush()
        return mappers.event_to_domain(record)

    def get_by_id(self, event_id: int) -> Event | None:
        record = self._session.get(EventRecord, event_id)
        return mappers.event_to_domain(record) if record else None

    def get_for_update(self, event_id: int) -> Event | None:
        """Read the row holding a write lock until the transaction commits.

        This is the single serialisation point that prevents overselling tickets.
        """
        stmt = select(EventRecord).where(EventRecord.id == event_id)
        if _supports_row_locks(self._session):
            stmt = stmt.with_for_update()
        record = self._session.scalar(stmt)
        return mappers.event_to_domain(record) if record else None

    def update(self, event: Event) -> Event:
        record = self._session.get(EventRecord, event.id)
        if record is None:
            return event
        mappers.apply_event(record, event)
        self._session.flush()
        return mappers.event_to_domain(record)

    def delete(self, event_id: int) -> None:
        record = self._session.get(EventRecord, event_id)
        if record is not None:
            self._session.delete(record)
            self._session.flush()

    def search(self, query: EventQuery, page: int, size: int) -> tuple[list[Event], int]:
        conditions = []
        if query.status is not None:
            conditions.append(EventRecord.status == query.status.value)
        if query.city:
            conditions.append(func.lower(EventRecord.city) == query.city.strip().lower())
        if query.category:
            conditions.append(func.lower(EventRecord.category) == query.category.strip().lower())
        if query.organizer_id is not None:
            conditions.append(EventRecord.organizer_id == query.organizer_id)
        if query.only_upcoming:
            conditions.append(EventRecord.end_time > datetime.now(timezone.utc))
        if query.q:
            pattern = "%" + query.q.strip().lower() + "%"
            conditions.append(
                or_(
                    func.lower(EventRecord.title).like(pattern),
                    func.lower(EventRecord.description).like(pattern),
                )
            )

        total = self._session.scalar(
            select(func.count()).select_from(EventRecord).where(*conditions)
        )
        column = _SORT_COLUMNS.get(query.sort_by, EventRecord.start_time)
        order = column.desc() if query.sort_desc else column.asc()
        records = self._session.scalars(
            select(EventRecord)
            .where(*conditions)
            .order_by(order, EventRecord.id.asc())
            .offset((page - 1) * size)
            .limit(size)
        ).all()
        return [mappers.event_to_domain(r) for r in records], int(total or 0)


class SqlAlchemyBookingRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, booking: Booking) -> Booking:
        record = mappers.booking_to_record(booking)
        self._session.add(record)
        self._session.flush()
        return mappers.booking_to_domain(record)

    def get_by_id(self, booking_id: int) -> Booking | None:
        record = self._session.get(BookingRecord, booking_id)
        return mappers.booking_to_domain(record) if record else None

    def update(self, booking: Booking) -> Booking:
        record = self._session.get(BookingRecord, booking.id)
        if record is None:
            return booking
        mappers.apply_booking(record, booking)
        self._session.flush()
        return mappers.booking_to_domain(record)

    def list_by_user(
        self, user_id: int, page: int, size: int, status: BookingStatus | None = None
    ) -> tuple[list[Booking], int]:
        conditions = [BookingRecord.user_id == user_id]
        if status is not None:
            conditions.append(BookingRecord.status == status.value)
        total = self._session.scalar(
            select(func.count()).select_from(BookingRecord).where(*conditions)
        )
        records = self._session.scalars(
            select(BookingRecord)
            .where(*conditions)
            .order_by(BookingRecord.created_at.desc(), BookingRecord.id.desc())
            .offset((page - 1) * size)
            .limit(size)
        ).all()
        return [mappers.booking_to_domain(r) for r in records], int(total or 0)

    def count_active_for_event(self, event_id: int) -> int:
        total = self._session.scalar(
            select(func.count())
            .select_from(BookingRecord)
            .where(
                BookingRecord.event_id == event_id,
                BookingRecord.status == BookingStatus.CONFIRMED.value,
            )
        )
        return int(total or 0)
