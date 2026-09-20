"""Booking request and response DTOs."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.domain.enums import BookingStatus
from app.domain.models import MAX_TICKETS_PER_BOOKING


class CreateBookingRequest(BaseModel):
    event_id: int = Field(gt=0)
    quantity: int = Field(gt=0, le=MAX_TICKETS_PER_BOOKING)


class BookingResponse(BaseModel):
    id: int
    user_id: int
    event_id: int
    event_title: str
    event_start_time: datetime | None
    quantity: int
    unit_price: Decimal
    total_price: Decimal
    status: BookingStatus
    created_at: datetime
    cancelled_at: datetime | None
