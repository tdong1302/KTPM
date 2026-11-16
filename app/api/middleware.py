"""Authentication middleware.

This is the single place where a request is authenticated. It runs before any route
handler, verifies the bearer token once, and rejects unauthenticated calls to protected
routes. No route handler repeats this logic - handlers only read the result via the thin
``current_principal`` dependency in ``app.api.deps``.
"""

import logging
import re
from collections.abc import Awaitable, Callable, Sequence
from time import perf_counter

from starlette.datastructures import Headers, MutableHeaders
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import BaseRoute, Match
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.application.ports import TokenService
from app.domain.errors import UnauthorizedError
from app.observability.context import (
    effective_correlation_id,
    reset_correlation_id,
    set_correlation_id,
)
from app.observability.logging import LogFormat, emit_event
from app.observability.metrics import MetricsRegistry, safe_method, status_class

LOGGER = logging.getLogger("eventhub.api")

# Declarative route policy, the analogue of SecurityConfig.requestMatchers(...).permitAll().
# Everything not listed here requires a valid access token.
PUBLIC_ROUTES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("GET", re.compile(r"^/$")),
    ("GET", re.compile(r"^/health$")),
    ("GET", re.compile(r"^/ready$")),
    ("GET", re.compile(r"^/metrics$")),
    ("GET", re.compile(r"^/docs$")),
    ("GET", re.compile(r"^/docs/oauth2-redirect$")),
    ("GET", re.compile(r"^/redoc$")),
    ("GET", re.compile(r"^/openapi\.json$")),
    ("GET", re.compile(r"^/app(?:/.*)?$")),
    ("HEAD", re.compile(r"^/app(?:/.*)?$")),
    ("POST", re.compile(r"^/api/auth/register$")),
    ("POST", re.compile(r"^/api/auth/login$")),
    ("GET", re.compile(r"^/api/events$")),
    ("GET", re.compile(r"^/api/events/\d+$")),
)


def route_template(routes: Sequence[BaseRoute], scope: Scope) -> str:
    """Resolve a configured template without ever falling back to the raw request path."""
    for route in routes:
        match, _ = route.matches(scope)
        if match == Match.FULL:
            path = getattr(route, "path_format", None) or getattr(route, "path", None)
            if path:
                return str(path)
    return "unmatched"


def dispatched_route_template(scope: Scope, fallback: str) -> str:
    """Read Starlette's authoritative route after dispatch has selected it."""
    route = scope.get("route")
    path = getattr(route, "path_format", None) or getattr(route, "path", None)
    return str(path) if path else fallback


class ObservabilityMiddleware:
    """Correlate, measure and safely log one complete HTTP request."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        metrics: MetricsRegistry,
        routes_provider: Callable[[], Sequence[BaseRoute]],
        log_format: LogFormat,
    ) -> None:
        self.app = app
        self.metrics = metrics
        self.routes_provider = routes_provider
        self.log_format = log_format

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = effective_correlation_id(Headers(scope=scope).get("x-request-id"))
        token = set_correlation_id(request_id)
        method = safe_method(str(scope.get("method", "OTHER")))
        route = route_template(self.routes_provider(), scope)
        inflight_labels = (method, route)
        started = perf_counter()
        status_code = 500
        response_started = False
        self.metrics.gauge_add("eventhub_http_requests_in_flight", inflight_labels, 1)

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code, response_started
            if message["type"] == "http.response.start":
                response_started = True
                status_code = int(message["status"])
                MutableHeaders(scope=message)["X-Request-ID"] = request_id
            await send(message)

        try:
            try:
                await self.app(scope, receive, send_with_request_id)
            except Exception as error:
                route = dispatched_route_template(scope, route)
                self.metrics.increment("eventhub_http_unhandled_exceptions_total", (method, route))
                emit_event(
                    LOGGER,
                    logging.ERROR,
                    "http_request_unhandled_exception",
                    log_format=self.log_format,
                    exception_type=type(error).__name__,
                    method=method,
                    route=route,
                )
                if response_started:
                    raise
                response = JSONResponse(
                    status_code=500,
                    content={"code": "INTERNAL_SERVER_ERROR", "message": "internal server error"},
                )
                await response(scope, receive, send_with_request_id)
        finally:
            route = dispatched_route_template(scope, route)
            labels = (method, route)
            duration = perf_counter() - started
            self.metrics.gauge_add("eventhub_http_requests_in_flight", inflight_labels, -1)
            self.metrics.increment("eventhub_http_requests_total", labels)
            self.metrics.increment(
                "eventhub_http_responses_total", (*labels, status_class(status_code))
            )
            self.metrics.observe("eventhub_http_request_duration_seconds", duration, labels)
            emit_event(
                LOGGER,
                logging.INFO if status_code < 500 else logging.ERROR,
                "http_request_completed",
                log_format=self.log_format,
                method=method,
                route=route,
                status_code=status_code,
                duration_seconds=round(duration, 6),
            )
            reset_correlation_id(token)


def is_public(method: str, path: str) -> bool:
    if method == "OPTIONS":
        return True
    normalised = path.rstrip("/") or "/"
    return any(
        method == allowed_method and pattern.match(normalised)
        for allowed_method, pattern in PUBLIC_ROUTES
    )


class AuthenticationMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, token_service: TokenService) -> None:
        super().__init__(app)
        self._tokens = token_service

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request.state.principal = None
        auth_error: UnauthorizedError | None = None

        header = request.headers.get("authorization", "")
        scheme, _, token = header.partition(" ")
        if scheme.lower() == "bearer" and token.strip():
            try:
                request.state.principal = self._tokens.verify(token.strip())
            except UnauthorizedError as exc:
                auth_error = exc

        if is_public(request.method, request.url.path):
            # A bad token on a public route is ignored; the caller is simply anonymous.
            return await call_next(request)

        if request.state.principal is None:
            error = auth_error or UnauthorizedError(
                "authentication required", code="UNAUTHENTICATED"
            )
            return JSONResponse(
                status_code=401,
                content={"code": error.code, "message": error.message},
                headers={"WWW-Authenticate": "Bearer"},
            )

        return await call_next(request)
