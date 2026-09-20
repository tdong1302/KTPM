"""Dependency wiring: builds business services out of infrastructure adapters.

This module is the composition root for a request. It is the only place where the API
layer knows which concrete adapters exist.
"""

from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPBearer

from app.application.auth_service import AuthService
from app.application.booking_service import BookingService
from app.application.event_service import EventService
from app.application.ports import TokenClaims
from app.domain.errors import UnauthorizedError
from app.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork

# auto_error=False: this scheme exists so Swagger renders an "Authorize" button and marks
# protected operations with a padlock. It does NOT enforce anything - AuthenticationMiddleware
# already did that before the route was reached.
bearer_scheme = HTTPBearer(auto_error=False, description="Paste the access token from /api/auth/login")


def get_unit_of_work(request: Request) -> SqlAlchemyUnitOfWork:
    return SqlAlchemyUnitOfWork(request.app.state.session_factory)


def get_auth_service(request: Request) -> AuthService:
    return AuthService(
        uow=get_unit_of_work(request),
        hasher=request.app.state.password_hasher,
        tokens=request.app.state.token_service,
        clock=request.app.state.clock,
    )


def get_event_service(request: Request) -> EventService:
    return EventService(uow=get_unit_of_work(request), clock=request.app.state.clock)


def get_booking_service(request: Request) -> BookingService:
    return BookingService(uow=get_unit_of_work(request), clock=request.app.state.clock)


def current_principal(
    request: Request, _credentials=Depends(bearer_scheme)
) -> TokenClaims:
    """Read the principal that the middleware already established."""
    principal = getattr(request.state, "principal", None)
    if principal is None:
        raise UnauthorizedError("authentication required", code="UNAUTHENTICATED")
    return principal


def optional_principal(request: Request) -> TokenClaims | None:
    return getattr(request.state, "principal", None)


CurrentUser = Annotated[TokenClaims, Depends(current_principal)]
OptionalUser = Annotated[TokenClaims | None, Depends(optional_principal)]
AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
EventServiceDep = Annotated[EventService, Depends(get_event_service)]
BookingServiceDep = Annotated[BookingService, Depends(get_booking_service)]
