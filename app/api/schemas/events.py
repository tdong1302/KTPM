"""Event request and response DTOs."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.domain.enums import EventStatus


class CreateEventRequest(BaseModel):
    title: str = Field(min_length=1, max_length=150)
    description: str = Field(default="", max_length=2000)
    category: str = Field(min_length=1, max_length=64)
    city: str = Field(min_length=1, max_length=100)
    location: str = Field(min_length=1, max_length=255)
    start_time: datetime
    end_time: datetime
    total_tickets: int = Field(gt=0, le=1_000_000)
    price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)


class EventResponse(BaseModel):
    id: int
    title: str
    description: str
    category: str
    city: str
    location: str
    start_time: datetime
    end_time: datetime
    total_tickets: int
    available_tickets: int
    price: Decimal
    status: EventStatus
    organizer_id: int
    created_at: datetime
    updated_at: datetime
