"""Maps domain errors onto HTTP responses.

The business layer raises domain errors that carry a stable code and know nothing about
HTTP; the translation happens here, once, for every route.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse

from app.domain.errors import (
    ConflictError,
    DomainError,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)
from app.observability.logging import emit_event

LOGGER = logging.getLogger("eventhub.api.errors")

STATUS_BY_ERROR: dict[type[DomainError], int] = {
    ValidationError: 400,
    UnauthorizedError: 401,
    ForbiddenError: 403,
    NotFoundError: 404,
    ConflictError: 409,
}


def _status_for(error: DomainError) -> int:
    for error_type, status in STATUS_BY_ERROR.items():
        if isinstance(error, error_type):
            return status
    return 400


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def handle_domain_error(request: Request, exc: DomainError) -> JSONResponse:
        emit_event(
            LOGGER,
            logging.WARNING,
            "http_handled_error",
            log_format=request.app.state.settings.observability_log_format,
            exception_type=type(exc).__name__,
            status_code=_status_for(exc),
            error_code=exc.code,
        )
        headers = {"WWW-Authenticate": "Bearer"} if isinstance(exc, UnauthorizedError) else None
        return JSONResponse(
            status_code=_status_for(exc),
            content={"code": exc.code, "message": exc.message},
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        emit_event(
            LOGGER,
            logging.WARNING,
            "http_handled_error",
            log_format=request.app.state.settings.observability_log_format,
            exception_type=type(exc).__name__,
            status_code=422,
            error_code="REQUEST_VALIDATION_ERROR",
        )
        first = exc.errors()[0] if exc.errors() else {}
        field = ".".join(str(part) for part in first.get("loc", [])[1:]) or "body"
        return JSONResponse(
            status_code=422,
            content={
                "code": "REQUEST_VALIDATION_ERROR",
                "message": f"{field}: {first.get('msg', 'invalid request')}",
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        emit_event(
            LOGGER,
            logging.WARNING,
            "http_handled_error",
            log_format=request.app.state.settings.observability_log_format,
            exception_type=type(exc).__name__,
            status_code=exc.status_code,
            error_code=f"HTTP_{exc.status_code}",
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": f"HTTP_{exc.status_code}", "message": str(exc.detail)},
            headers=getattr(exc, "headers", None),
        )
