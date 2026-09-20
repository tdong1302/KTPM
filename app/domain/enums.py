"""Domain enums. Plain stdlib, no framework or ORM types."""

from enum import Enum


class UserRole(str, Enum):
    USER = "USER"
    ORGANIZER = "ORGANIZER"
    ADMIN = "ADMIN"

    @property
    def can_organize(self) -> bool:
        return self in (UserRole.ORGANIZER, UserRole.ADMIN)


class EventStatus(str, Enum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"


class BookingStatus(str, Enum):
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"


# Allowed event status transitions, mirroring the state machine of the reference
# project (EventService.requireTransition).
EVENT_TRANSITIONS: dict[EventStatus, frozenset[EventStatus]] = {
    EventStatus.DRAFT: frozenset({EventStatus.PUBLISHED, EventStatus.CANCELLED}),
    EventStatus.PUBLISHED: frozenset({EventStatus.CANCELLED, EventStatus.COMPLETED}),
    EventStatus.CANCELLED: frozenset(),
    EventStatus.COMPLETED: frozenset(),
}
