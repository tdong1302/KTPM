"""Lifecycle of a temporary hold on event inventory."""

from dataclasses import dataclass
from datetime import datetime

from app.domain.enums import ReservationStatus
from app.domain.errors import ConflictError


@dataclass
class Reservation:
    user_id: int
    event_id: int
    quantity: int
    expires_at: datetime
    created_at: datetime
    status: ReservationStatus = ReservationStatus.RESERVED
    id: int | None = None
    booking_id: int | None = None

    def is_due(self, now: datetime) -> bool:
        return self.status == ReservationStatus.RESERVED and self.expires_at <= now

    def require_active(self, now: datetime) -> None:
        if self.status == ReservationStatus.EXPIRED or self.is_due(now):
            raise ConflictError("reservation has expired", code="RESERVATION_EXPIRED")
        if self.status != ReservationStatus.RESERVED:
            raise ConflictError("reservation is no longer active")
