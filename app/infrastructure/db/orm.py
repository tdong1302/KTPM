"""SQLAlchemy mapped classes.

These are persistence records, intentionally kept separate from the domain dataclasses in
``app.domain.models``. ``app.infrastructure.db.mappers`` translates between the two, which
is what lets the domain stay free of ORM imports.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base


class UserRecord(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint("role IN ('USER', 'ORGANIZER', 'ADMIN')", name="ck_users_role"),
    )


class EventRecord(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    location: Mapped[str] = mapped_column(String(255), nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    total_tickets: Mapped[int] = mapped_column(Integer, nullable=False)
    available_tickets: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    organizer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint("total_tickets > 0", name="ck_events_total_tickets_positive"),
        CheckConstraint("available_tickets >= 0", name="ck_events_available_nonnegative"),
        CheckConstraint(
            "available_tickets <= total_tickets", name="ck_events_available_within_total"
        ),
        CheckConstraint("price >= 0", name="ck_events_price_nonnegative"),
        CheckConstraint("start_time < end_time", name="ck_events_time_order"),
        CheckConstraint(
            "status IN ('DRAFT', 'PUBLISHED', 'CANCELLED', 'COMPLETED')",
            name="ck_events_status",
        ),
        # Serves the public catalogue query: status = PUBLISHED AND end_time > now
        # ordered by start_time.
        Index("ix_events_status_start_time", "status", "start_time"),
        Index("ix_events_organizer_id", "organizer_id"),
    )


class BookingRecord(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    event_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    event_title: Mapped[str] = mapped_column(String(150), nullable=False, default="")
    event_start_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("quantity > 0 AND quantity <= 10", name="ck_bookings_quantity"),
        CheckConstraint("unit_price >= 0", name="ck_bookings_unit_price_nonnegative"),
        CheckConstraint(
            "status IN ('CONFIRMED', 'CANCELLED')", name="ck_bookings_status"
        ),
        Index("ix_bookings_user_id_created_at", "user_id", "created_at"),
        Index("ix_bookings_event_id_status", "event_id", "status"),
    )
