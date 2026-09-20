"""SQLAlchemy engine and session factory."""

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import Settings


class Base(DeclarativeBase):
    pass


def build_engine(settings: Settings) -> Engine:
    if settings.is_sqlite:
        # SQLite is only used by the fast integration tests. StaticPool + a shared
        # connection keeps an in-memory database alive across sessions.
        from sqlalchemy.pool import StaticPool

        return create_engine(
            settings.database_url,
            echo=settings.db_echo,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    return create_engine(
        settings.database_url,
        echo=settings.db_echo,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout,
        pool_pre_ping=True,
    )


def build_session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
