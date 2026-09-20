"""Event endpoints.

GET /api/events and GET /api/events/{id} are public; everything else is protected by
AuthenticationMiddleware. Ownership rules are enforced by the business layer.
"""

from fastapi import APIRouter, Query, Response, status

from app.api.deps import CurrentUser, EventServiceDep, OptionalUser
from app.api.schemas.common import ErrorResponse, PageResponse
from app.api.schemas.events import CreateEventRequest, EventResponse
from app.application.event_service import CreateEventCommand
from app.application.ports import EventQuery
from app.domain.models import Event

router = APIRouter(prefix="/api/events", tags=["events"])

UNAUTHORIZED = {401: {"model": ErrorResponse, "description": "Missing or invalid token"}}
FORBIDDEN = {403: {"model": ErrorResponse, "description": "Not the owner of this event"}}
NOT_FOUND = {404: {"model": ErrorResponse, "description": "Event not found"}}


def to_event_response(event: Event) -> EventResponse:
    return EventResponse(
        id=event.id,
        title=event.title,
        description=event.description,
        category=event.category,
        city=event.city,
        location=event.location,
        start_time=event.start_time,
        end_time=event.end_time,
        total_tickets=event.total_tickets,
        available_tickets=event.available_tickets,
        price=event.price,
        status=event.status,
        organizer_id=event.organizer_id,
        created_at=event.created_at,
        updated_at=event.updated_at,
    )


@router.get(
    "",
    response_model=PageResponse[EventResponse],
    summary="Browse published events (public)",
)
def list_events(
    service: EventServiceDep,
    q: str | None = Query(default=None, description="Free text over title and description"),
    city: str | None = None,
    category: str | None = None,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    sort_by: str = Query(default="start_time", pattern="^(start_time|price|created_at)$"),
    sort_dir: str = Query(default="asc", pattern="^(asc|desc)$"),
) -> PageResponse[EventResponse]:
    result = service.search_public(
        EventQuery(
            q=q, city=city, category=category, sort_by=sort_by, sort_desc=sort_dir == "desc"
        ),
        page=page,
        size=size,
    )
    return PageResponse[EventResponse](
        items=[to_event_response(e) for e in result.items],
        total=result.total,
        page=result.page,
        size=result.size,
        total_pages=result.total_pages,
    )


@router.get(
    "/{event_id}",
    response_model=EventResponse,
    summary="Event detail (public for published events)",
    responses=NOT_FOUND,
)
def get_event(event_id: int, service: EventServiceDep, principal: OptionalUser) -> EventResponse:
    actor_id = principal.user_id if principal else None
    actor_role = principal.role if principal else None
    return to_event_response(service.get(event_id, actor_id, actor_role))


@router.post(
    "",
    response_model=EventResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a draft event (requires authentication, ORGANIZER or ADMIN)",
    responses={**UNAUTHORIZED, 403: {"model": ErrorResponse, "description": "Role cannot organize"}},
)
def create_event(
    payload: CreateEventRequest, service: EventServiceDep, principal: CurrentUser
) -> EventResponse:
    event = service.create(
        actor_id=principal.user_id,
        actor_role=principal.role,
        command=CreateEventCommand(
            title=payload.title,
            description=payload.description,
            category=payload.category,
            city=payload.city,
            location=payload.location,
            start_time=payload.start_time,
            end_time=payload.end_time,
            total_tickets=payload.total_tickets,
            price=payload.price,
        ),
    )
    return to_event_response(event)


@router.patch(
    "/{event_id}/publish",
    response_model=EventResponse,
    summary="Publish a draft event (requires authentication, owner or ADMIN)",
    responses={**UNAUTHORIZED, **FORBIDDEN, **NOT_FOUND},
)
def publish_event(
    event_id: int, service: EventServiceDep, principal: CurrentUser
) -> EventResponse:
    return to_event_response(service.publish(event_id, principal.user_id, principal.role))


@router.patch(
    "/{event_id}/cancel",
    response_model=EventResponse,
    summary="Cancel an event (requires authentication, owner or ADMIN)",
    responses={**UNAUTHORIZED, **FORBIDDEN, **NOT_FOUND},
)
def cancel_event(
    event_id: int, service: EventServiceDep, principal: CurrentUser
) -> EventResponse:
    return to_event_response(service.cancel(event_id, principal.user_id, principal.role))


@router.delete(
    "/{event_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a draft event (requires authentication, owner or ADMIN)",
    responses={**UNAUTHORIZED, **FORBIDDEN, **NOT_FOUND},
)
def delete_event(event_id: int, service: EventServiceDep, principal: CurrentUser) -> Response:
    service.delete(event_id, principal.user_id, principal.role)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
