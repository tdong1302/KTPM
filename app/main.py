"""Application factory and composition root."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.exception_handlers import register_exception_handlers
from app.api.middleware import AuthenticationMiddleware
from app.api.routers import auth, bookings, events, health
from app.config import Settings, get_settings
from app.infrastructure.clock import SystemClock
from app.infrastructure.db import orm  # noqa: F401  (registers tables on Base.metadata)
from app.infrastructure.db.base import Base, build_engine, build_session_factory
from app.infrastructure.security.bcrypt_hasher import BcryptPasswordHasher
from app.infrastructure.security.jwt_token_service import JwtTokenService

DESCRIPTION = """
Event ticket booking service - baseline (Phase 1) for the Software Engineering course.

**Architecture**: `api` -> `application` (business) -> `infrastructure` (repositories) -> PostgreSQL.
The business layer imports no web framework and no database library; it talks to the
outside world only through the Protocols in `app.application.ports`.

**Authentication**: a single Starlette middleware verifies the bearer token before any
route handler runs. Handlers never repeat authentication logic.

Obtain a token from `POST /api/auth/login`, then press **Authorize** above.
"""

TAGS_METADATA = [
    {"name": "health", "description": "Liveness probe."},
    {"name": "auth", "description": "Registration, login and the current account."},
    {"name": "events", "description": "Event catalogue and lifecycle."},
    {"name": "bookings", "description": "Ticket booking and cancellation."},
]

FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    engine = build_engine(settings)
    session_factory = build_session_factory(engine)

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        if settings.db_auto_create:
            # Convenience path for CI and the Kaggle benchmark. Production uses Alembic.
            Base.metadata.create_all(bind=engine)
        yield
        engine.dispose()

    application = FastAPI(
        title=settings.app_name,
        description=DESCRIPTION,
        version="0.1.0",
        openapi_tags=TAGS_METADATA,
        lifespan=lifespan,
    )

    application.state.settings = settings
    application.state.engine = engine
    application.state.session_factory = session_factory
    application.state.clock = SystemClock()
    application.state.password_hasher = BcryptPasswordHasher(rounds=settings.bcrypt_rounds)
    application.state.token_service = JwtTokenService(
        secret=settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
        expires_minutes=settings.jwt_expires_minutes,
    )

    application.add_middleware(
        AuthenticationMiddleware, token_service=application.state.token_service
    )
    register_exception_handlers(application)

    application.include_router(health.router)
    application.include_router(auth.router)
    application.include_router(events.router)
    application.include_router(bookings.router)
    application.mount(
        "/app",
        StaticFiles(directory=FRONTEND_DIR, html=True),
        name="frontend",
    )

    return application


app = create_app()
