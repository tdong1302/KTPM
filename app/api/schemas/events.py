"""Event request and response DTOs."""

from datetime import datetime
from decimal import Decimal
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

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


class UpdateEventRequest(BaseModel):
    """Strict PATCH document: omitted means unchanged; explicit null is invalid."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=2000)
    category: str | None = Field(default=None, min_length=1, max_length=64)
    city: str | None = Field(default=None, min_length=1, max_length=100)
    location: str | None = Field(default=None, min_length=1, max_length=255)
    start_time: datetime | None = None
    end_time: datetime | None = None
    total_tickets: int | None = Field(default=None, gt=0, le=1_000_000)
    price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)

    @model_validator(mode="after")
    def require_non_null_change(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("at least one editable field is required")
        if any(getattr(self, name) is None for name in self.model_fields_set):
            raise ValueError("editable fields must not be null")
        return self


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
