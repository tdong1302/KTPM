"""Public operational probes and Prometheus-compatible metrics exposition."""

import logging

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.observability.logging import emit_event

router = APIRouter(tags=["operations"])
LOGGER = logging.getLogger("eventhub.readiness")


class ReadinessResponse(BaseModel):
    status: str
    service: str


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={503: {"model": ReadinessResponse}},
    summary="PostgreSQL readiness probe",
)
def readiness(request: Request, response: Response) -> ReadinessResponse:
    try:
        with request.app.state.engine.connect() as connection:
            connection.execute(text("SELECT 1")).scalar_one()
    except SQLAlchemyError as error:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        emit_event(
            LOGGER,
            logging.WARNING,
            "readiness_check_failed",
            log_format=request.app.state.settings.observability_log_format,
            exception_type=type(error).__name__,
        )
        return ReadinessResponse(status="NOT_READY", service="eventhub-ktpm")
    return ReadinessResponse(status="READY", service="eventhub-ktpm")


@router.get(
    "/metrics",
    include_in_schema=True,
    summary="Prometheus metrics exposition",
    response_class=Response,
)
def metrics(request: Request) -> Response:
    return Response(
        content=request.app.state.metrics.render_prometheus(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
