"""Authentication middleware.

This is the single place where a request is authenticated. It runs before any route
handler, verifies the bearer token once, and rejects unauthenticated calls to protected
routes. No route handler repeats this logic - handlers only read the result via the thin
``current_principal`` dependency in ``app.api.deps``.
"""

import re
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.application.ports import TokenService
from app.domain.errors import UnauthorizedError

# Declarative route policy, the analogue of SecurityConfig.requestMatchers(...).permitAll().
# Everything not listed here requires a valid access token.
PUBLIC_ROUTES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("GET", re.compile(r"^/$")),
    ("GET", re.compile(r"^/health$")),
    ("GET", re.compile(r"^/docs$")),
    ("GET", re.compile(r"^/docs/oauth2-redirect$")),
    ("GET", re.compile(r"^/redoc$")),
    ("GET", re.compile(r"^/openapi\.json$")),
    ("POST", re.compile(r"^/api/auth/register$")),
    ("POST", re.compile(r"^/api/auth/login$")),
    ("GET", re.compile(r"^/api/events$")),
    ("GET", re.compile(r"^/api/events/\d+$")),
)


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
