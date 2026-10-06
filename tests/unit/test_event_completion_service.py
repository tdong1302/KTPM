"""Automatic completion rules without a database or web framework."""

from dataclasses import replace
from datetime import timedelta

import pytest

from app.application.event_completion_service import EventCompletionService
from app.domain.enums import EventStatus
from app.domain.errors import ConflictError, ValidationError
from tests.unit.fakes import FakeClock, FakeUnitOfWork, make_event


def expired_event(uow: FakeUnitOfWork, clock: FakeClock, **overrides):
    end = overrides.pop("end_time", clock.now() - timedelta(hours=1))
    start = overrides.pop("start_time", end - timedelta(hours=2))
    return make_event(uow, start_time=start, end_time=end, **overrides)


class TestCompletionDomainRule:
    def test_published_event_completes_exactly_at_end_time(self):
        clock = FakeClock()
        uow = FakeUnitOfWork()
        event = expired_event(uow, clock, end_time=clock.now())
        original = replace(event)

        event.complete(clock.now())

        assert event.status == EventStatus.COMPLETED
        assert event.updated_at == clock.now()
        assert (event.title, event.available_tickets, event.organizer_id) == (
            original.title,
            original.available_tickets,
            original.organizer_id,
        )

    def test_published_event_cannot_complete_before_end_time(self):
        clock = FakeClock()
        event = make_event(
            FakeUnitOfWork(),
            start_time=clock.now() - timedelta(hours=1),
            end_time=clock.now() + timedelta(seconds=1),
        )

        with pytest.raises(ConflictError, match="not ended"):
            event.complete(clock.now())
        assert event.status == EventStatus.PUBLISHED

    def test_published_event_completes_after_end_time(self):
        clock = FakeClock()
        event = expired_event(FakeUnitOfWork(), clock)

        event.complete(clock.now())

        assert event.status == EventStatus.COMPLETED

    @pytest.mark.parametrize(
        "status", [EventStatus.DRAFT, EventStatus.CANCELLED, EventStatus.COMPLETED]
    )
    def test_only_published_events_can_complete(self, status):
        clock = FakeClock()
        event = expired_event(FakeUnitOfWork(), clock, status=status)

        with pytest.raises(ConflictError):
            event.complete(clock.now())
        assert event.status == status


class TestCompletionBatch:
    def test_completes_only_eligible_rows_in_deterministic_bounded_order(self):
        clock = FakeClock()
        uow = FakeUnitOfWork()
        later = expired_event(uow, clock, end_time=clock.now() - timedelta(minutes=1))
        earliest = expired_event(uow, clock, end_time=clock.now() - timedelta(hours=3))
        expired_event(uow, clock, status=EventStatus.CANCELLED)
        expired_event(uow, clock, status=EventStatus.DRAFT)
        expired_event(uow, clock, status=EventStatus.COMPLETED)
        make_event(uow, start_time=clock.now() + timedelta(hours=1))
        service = EventCompletionService(uow, clock)

        result = service.complete_batch(batch_size=1)

        assert result.selected == result.completed == 1
        assert result.skipped == 0
        assert result.may_have_more is True
        assert uow.events.get_by_id(earliest.id).status == EventStatus.COMPLETED
        assert uow.events.get_by_id(later.id).status == EventStatus.PUBLISHED
        assert uow.events.completion_query_calls == [(clock.now(), 1)]
        assert uow.commits == 1

    def test_empty_batch_is_a_noop_and_repeated_runs_are_idempotent(self):
        clock = FakeClock()
        uow = FakeUnitOfWork()
        expired_event(uow, clock)
        service = EventCompletionService(uow, clock)

        first = service.complete_batch()
        second = service.complete_batch()

        assert (first.completed, second.completed, second.selected) == (1, 0, 0)
        assert uow.commits == 1

    def test_rechecks_claimed_rows_and_skips_stale_state(self):
        clock = FakeClock()
        uow = FakeUnitOfWork()
        stale = expired_event(uow, clock)
        stale.status = EventStatus.CANCELLED
        uow.events.list_expired_published_for_update = lambda **kwargs: [stale]

        result = EventCompletionService(uow, clock).complete_batch()

        assert (result.selected, result.completed, result.skipped) == (1, 0, 1)
        assert stale.status == EventStatus.CANCELLED
        assert uow.commits == 1

    def test_unexpected_failure_rolls_back_and_propagates(self):
        clock = FakeClock()
        uow = FakeUnitOfWork()
        expired_event(uow, clock)

        def fail_update(event):
            raise RuntimeError("database failure")

        uow.events.update = fail_update
        with pytest.raises(RuntimeError, match="database failure"):
            EventCompletionService(uow, clock).complete_batch()

        assert uow.commits == 0
        assert uow.rollbacks == 1

    @pytest.mark.parametrize("batch_size", [0, 1001])
    def test_rejects_invalid_batch_sizes_without_querying(self, batch_size):
        clock = FakeClock()
        uow = FakeUnitOfWork()

        with pytest.raises(ValidationError):
            EventCompletionService(uow, clock).complete_batch(batch_size)

        assert uow.events.completion_query_calls == []
