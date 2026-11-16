from datetime import datetime, timedelta, timezone

import pytest

from app.domain.enums import ReservationStatus
from app.domain.errors import ConflictError
from app.domain.reservation import Reservation


def test_hold_is_active_only_before_expiry():
    now = datetime(2026, 11, 11, tzinfo=timezone.utc)
    deadline = now + timedelta(minutes=10)
    hold = Reservation(user_id=1, event_id=1, quantity=1, expires_at=deadline, created_at=now)

    hold.require_active(deadline - timedelta(microseconds=1))
    assert hold.is_due(deadline)
    with pytest.raises(ConflictError) as error:
        hold.require_active(deadline)
    assert error.value.code == "RESERVATION_EXPIRED"


@pytest.mark.parametrize("status", [ReservationStatus.CANCELLED, ReservationStatus.CONFIRMED])
def test_terminal_holds_never_become_due_again(status):
    now = datetime(2026, 11, 11, tzinfo=timezone.utc)
    hold = Reservation(
        user_id=1, event_id=1, quantity=1, expires_at=now, created_at=now, status=status
    )

    assert not hold.is_due(now)
    with pytest.raises(ConflictError):
        hold.require_active(now)
