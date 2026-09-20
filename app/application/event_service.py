"""Event lifecycle use cases.

Authorisation that depends on business state (who owns the event, which status allows
what) lives here rather than in the controller, so it is unit-testable without HTTP.
Note that the actor is passed as plain ``int`` + ``UserRole``, never as a security
principal object: the business layer must not know how callers are authenticated.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.application.ports import Clock, EventQuery, UnitOfWork
from app.domain.enums import EventStatus, UserRole
from app.domain.errors import ForbiddenError, NotFoundError, ValidationError
from app.domain.models import Event, Page

MAX_PAGE_SIZE = 100
SORTABLE_FIELDS = frozenset({"start_time", "price", "created_at"})


@dataclass(frozen=True)
class CreateEventCommand:
    title: str
    description: str
    category: str
    city: str
    location: str
    start_time: datetime
    end_time: datetime
    total_tickets: int
    price: Decimal


def normalise_paging(page: int, size: int) -> tuple[int, int]:
    page = max(1, page)
    size = min(max(1, size), MAX_PAGE_SIZE)
    return page, size


class EventService:
    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def search_public(self, query: EventQuery, page: int, size: int) -> Page[Event]:
        """Public catalogue: only published events that have not ended yet."""
        page, size = normalise_paging(page, size)
        sort_by = query.sort_by if query.sort_by in SORTABLE_FIELDS else "start_time"
        effective = EventQuery(
            q=query.q,
            city=query.city,
            category=query.category,
            status=EventStatus.PUBLISHED,
            organizer_id=query.organizer_id,
            only_upcoming=True,
            sort_by=sort_by,
            sort_desc=query.sort_desc,
        )
        with self._uow as uow:
            items, total = uow.events.search(effective, page, size)
            return Page(items=items, total=total, page=page, size=size)

    def get(
        self, event_id: int, actor_id: int | None = None, actor_role: UserRole | None = None
    ) -> Event:
        with self._uow as uow:
            event = self._require_event(uow, event_id)
            if not event.is_visible_to(actor_id, actor_role):
                # Do not reveal that a hidden event exists.
                raise NotFoundError("event not found")
            return event

    def create(self, actor_id: int, actor_role: UserRole, command: CreateEventCommand) -> Event:
        if not actor_role.can_organize:
            raise ForbiddenError("only ORGANIZER or ADMIN can create events")
        now = self._clock.now()
        event = Event(
            title=command.title.strip(),
            description=(command.description or "").strip(),
            category=command.category.strip(),
            city=command.city.strip(),
            location=command.location.strip(),
            start_time=command.start_time,
            end_time=command.end_time,
            total_tickets=command.total_tickets,
            price=command.price,
            organizer_id=actor_id,
            status=EventStatus.DRAFT,
            created_at=now,
            updated_at=now,
        )
        event.validate_basics()
        if event.start_time <= now:
            raise ValidationError("start_time must be in the future")
        with self._uow as uow:
            created = uow.events.add(event)
            uow.commit()
            return created

    def publish(self, event_id: int, actor_id: int, actor_role: UserRole) -> Event:
        return self._transition(event_id, actor_id, actor_role, EventStatus.PUBLISHED)

    def cancel(self, event_id: int, actor_id: int, actor_role: UserRole) -> Event:
        return self._transition(event_id, actor_id, actor_role, EventStatus.CANCELLED)

    def delete(self, event_id: int, actor_id: int, actor_role: UserRole) -> None:
        with self._uow as uow:
            event = self._require_event(uow, event_id)
            self._require_owner_or_admin(event, actor_id, actor_role)
            event.ensure_deletable()
            if uow.bookings.count_active_for_event(event_id) > 0:
                raise ValidationError("event has active bookings and cannot be deleted")
            uow.events.delete(event_id)
            uow.commit()

    def _transition(
        self, event_id: int, actor_id: int, actor_role: UserRole, target: EventStatus
    ) -> Event:
        with self._uow as uow:
            event = self._require_event(uow, event_id)
            self._require_owner_or_admin(event, actor_id, actor_role)
            event.transition_to(target, self._clock.now())
            updated = uow.events.update(event)
            uow.commit()
            return updated

    @staticmethod
    def _require_event(uow: UnitOfWork, event_id: int) -> Event:
        event = uow.events.get_by_id(event_id)
        if event is None:
            raise NotFoundError("event not found")
        return event

    @staticmethod
    def _require_owner_or_admin(event: Event, actor_id: int, actor_role: UserRole) -> None:
        if actor_role == UserRole.ADMIN:
            return
        if event.organizer_id != actor_id:
            raise ForbiddenError("only the organizer who owns this event may modify it")
