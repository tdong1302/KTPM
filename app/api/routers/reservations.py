"""Authenticated ticket reservation endpoints."""

from fastapi import APIRouter

from app.api.deps import CurrentUser, ReservationServiceDep
from app.api.schemas.common import ErrorResponse
from app.api.schemas.reservations import CreateReservationRequest, ReservationResponse

router = APIRouter(
    prefix="/api/reservations",
    tags=["reservations"],
    responses={
        401: {"model": ErrorResponse, "description": "Missing or invalid token"},
        404: {"model": ErrorResponse, "description": "Reservation or event not found"},
    },
)

FORBIDDEN = {403: {"model": ErrorResponse, "description": "Reservation belongs to another user"}}
CONFLICT = {409: {"model": ErrorResponse, "description": "Inventory or lifecycle conflict"}}


@router.post("", response_model=ReservationResponse, status_code=201, responses=CONFLICT)
def reserve_tickets(
    payload: CreateReservationRequest, service: ReservationServiceDep, principal: CurrentUser
) -> ReservationResponse:
    reservation = service.reserve(principal.user_id, payload.event_id, payload.quantity)
    return ReservationResponse.model_validate(reservation)


@router.get("/{reservation_id}", response_model=ReservationResponse, responses=FORBIDDEN)
def get_reservation(
    reservation_id: int, service: ReservationServiceDep, principal: CurrentUser
) -> ReservationResponse:
    return ReservationResponse.model_validate(service.get(reservation_id, principal.user_id))


@router.post(
    "/{reservation_id}/confirm",
    response_model=ReservationResponse,
    responses={**FORBIDDEN, **CONFLICT},
)
def confirm_reservation(
    reservation_id: int, service: ReservationServiceDep, principal: CurrentUser
) -> ReservationResponse:
    return ReservationResponse.model_validate(service.confirm(reservation_id, principal.user_id))


@router.delete(
    "/{reservation_id}", response_model=ReservationResponse, responses={**FORBIDDEN, **CONFLICT}
)
def cancel_reservation(
    reservation_id: int, service: ReservationServiceDep, principal: CurrentUser
) -> ReservationResponse:
    return ReservationResponse.model_validate(service.cancel(reservation_id, principal.user_id))
