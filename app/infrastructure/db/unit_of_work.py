"""Transaction boundary adapter."""

from sqlalchemy.orm import Session, sessionmaker

from app.infrastructure.db.repositories import (
    SqlAlchemyBookingRepository,
    SqlAlchemyEventRepository,
    SqlAlchemyUserRepository,
)


class SqlAlchemyUnitOfWork:
    """Opens a session on entry and always closes it on exit.

    A use case that raises leaves the transaction rolled back, so a failed booking can
    never leave the ticket counter decremented. Events and bookings share one database and
    one transaction, so no compensating action is needed to undo a partial write.

    Entering is re-entrant (a service may call another service) so only the outermost
    block owns the session.
    """

    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None
        self._depth = 0
        self.users: SqlAlchemyUserRepository | None = None
        self.events: SqlAlchemyEventRepository | None = None
        self.bookings: SqlAlchemyBookingRepository | None = None

    def __enter__(self) -> "SqlAlchemyUnitOfWork":
        if self._depth == 0:
            self._session = self._session_factory()
            self.users = SqlAlchemyUserRepository(self._session)
            self.events = SqlAlchemyEventRepository(self._session)
            self.bookings = SqlAlchemyBookingRepository(self._session)
        self._depth += 1
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self._depth -= 1
        if self._depth > 0:
            return
        session = self._session
        if session is None:
            return
        try:
            if exc_type is not None:
                session.rollback()
        finally:
            session.close()
            self._session = None

    @property
    def session(self) -> Session:
        if self._session is None:
            raise RuntimeError("unit of work is not active; use it as a context manager")
        return self._session

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()
