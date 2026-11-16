"""SQLAlchemy engine and session factory."""

from typing import TYPE_CHECKING

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import Settings

if TYPE_CHECKING:
    from app.observability.metrics import MetricsRegistry


class Base(DeclarativeBase):
    pass


def build_engine(
    settings: Settings,
    metrics: "MetricsRegistry | None" = None,
) -> Engine:
    if settings.is_sqlite:
        # SQLite is only used by the fast integration tests. StaticPool + a shared
        # connection keeps an in-memory database alive across sessions.
        from sqlalchemy.pool import StaticPool

        engine = create_engine(
            settings.database_url,
            echo=settings.db_echo,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    else:
        engine = create_engine(
            settings.database_url,
            echo=settings.db_echo,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_timeout=settings.db_pool_timeout,
            pool_pre_ping=True,
        )
    if metrics is not None:
        from app.observability.sqlalchemy_metrics import instrument_sqlalchemy

        instrument_sqlalchemy(engine, metrics)
    return engine


def build_session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
