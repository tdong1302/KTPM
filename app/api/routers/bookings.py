"""Booking endpoints. Every route here requires authentication."""

from fastapi import APIRouter, Query, status

from app.api.deps import BookingServiceDep, CurrentUser
from app.api.schemas.bookings import BookingResponse, CreateBookingRequest
from app.api.schemas.common import ErrorResponse, PageResponse
from app.domain.models import Booking

router = APIRouter(prefix="/api/bookings", tags=["bookings"])

UNAUTHORIZED = {401: {"model": ErrorResponse, "description": "Missing or invalid token"}}
CONFLICT = {409: {"model": ErrorResponse, "description": "Sold out, not bookable, or already cancelled"}}
NOT_FOUND = {404: {"model": ErrorResponse, "description": "Booking or event not found"}}


def to_booking_response(booking: Booking) -> BookingResponse:
    return BookingResponse(
        id=booking.id,
        user_id=booking.user_id,
        event_id=booking.event_id,
        event_title=booking.event_title,
        event_start_time=booking.event_start_time,
        quantity=booking.quantity,
        unit_price=booking.unit_price,
        total_price=booking.total_price,
        status=booking.status,
        created_at=booking.created_at,
        cancelled_at=booking.cancelled_at,
    )


@router.post(
    "",
    response_model=BookingResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Book tickets (requires authentication)",
    responses={**UNAUTHORIZED, **NOT_FOUND, **CONFLICT},
)
def create_booking(
    payload: CreateBookingRequest, service: BookingServiceDep, principal: CurrentUser
) -> BookingResponse:
    booking = service.book(
        actor_id=principal.user_id, event_id=payload.event_id, quantity=payload.quantity
    )
    return to_booking_response(booking)


@router.get(
    "/me",
    response_model=PageResponse[BookingResponse],
    summary="My bookings (requires authentication)",
    responses=UNAUTHORIZED,
)
def list_my_bookings(
    service: BookingServiceDep,
    principal: CurrentUser,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
) -> PageResponse[BookingResponse]:
    result = service.list_mine(principal.user_id, page=page, size=size)
    return PageResponse[BookingResponse](
        items=[to_booking_response(b) for b in result.items],
        total=result.total,
        page=result.page,
        size=result.size,
        total_pages=result.total_pages,
    )


@router.get(
    "/{booking_id}",
    response_model=BookingResponse,
    summary="Booking detail (requires authentication, owner or ADMIN)",
    responses={**UNAUTHORIZED, **NOT_FOUND},
)
def get_booking(
    booking_id: int, service: BookingServiceDep, principal: CurrentUser
) -> BookingResponse:
    return to_booking_response(service.get(booking_id, principal.user_id, principal.role))


@router.delete(
    "/{booking_id}",
    response_model=BookingResponse,
    summary="Cancel a booking and release its tickets (requires authentication)",
    responses={**UNAUTHORIZED, **NOT_FOUND, **CONFLICT},
)
def cancel_booking(
    booking_id: int, service: BookingServiceDep, principal: CurrentUser
) -> BookingResponse:
    return to_booking_response(service.cancel(booking_id, principal.user_id, principal.role))
