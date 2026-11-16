"""Request and response models for ticket holds."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.api.schemas.bookings import CreateBookingRequest
from app.domain.enums import ReservationStatus


class CreateReservationRequest(CreateBookingRequest):
    """Uses the same event and quantity validation as direct booking."""


class ReservationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_id: int
    quantity: int
    status: ReservationStatus
    expires_at: datetime
    booking_id: int | None
