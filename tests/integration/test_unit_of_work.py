"""Transaction and database-invariant behavior using real SQLAlchemy adapters."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.domain.enums import UserRole
from app.domain.models import User
from app.infrastructure.db.orm import EventRecord, UserRecord
from app.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork


def test_exception_rolls_back_uncommitted_writes(client) -> None:
    session_factory = client.app.state.session_factory
    uow = SqlAlchemyUnitOfWork(session_factory)

    with pytest.raises(RuntimeError, match="force rollback"):
        with uow:
            uow.users.add(
                User(
                    email="rollback@example.com",
                    password_hash="not-a-real-hash",
                    full_name="Rollback Test",
                    role=UserRole.USER,
                )
            )
            raise RuntimeError("force rollback")

    with SqlAlchemyUnitOfWork(session_factory) as verification:
        assert verification.users.get_by_email("rollback@example.com") is None


def test_database_rejects_negative_event_inventory(client) -> None:
    session_factory = client.app.state.session_factory
    now = datetime.now(timezone.utc)

    with session_factory() as session:
        organizer = UserRecord(
            email="constraint@example.com",
            password_hash="not-a-real-hash",
            full_name="Constraint Test",
            role="ORGANIZER",
            created_at=now,
        )
        session.add(organizer)
        session.flush()
        session.add(
            EventRecord(
                title="Invalid inventory",
                description="Database constraint regression test",
                category="test",
                city="Hanoi",
                location="Test Hall",
                start_time=now + timedelta(days=1),
                end_time=now + timedelta(days=1, hours=1),
                total_tickets=10,
                available_tickets=-1,
                price=Decimal("1.00"),
                status="DRAFT",
                organizer_id=organizer.id,
                created_at=now,
                updated_at=now,
            )
        )

        with pytest.raises(IntegrityError):
            session.commit()
