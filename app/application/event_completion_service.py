"""Use case for completing ended events in bounded, transactional batches."""

from dataclasses import dataclass

from app.application.ports import Clock, UnitOfWork
from app.domain.errors import ConflictError, ValidationError

MAX_COMPLETION_BATCH_SIZE = 1000


@dataclass(frozen=True)
class CompletionBatchResult:
    selected: int
    completed: int
    skipped: int
    may_have_more: bool


class EventCompletionService:
    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def complete_batch(self, batch_size: int = 100) -> CompletionBatchResult:
        if not 1 <= batch_size <= MAX_COMPLETION_BATCH_SIZE:
            raise ValidationError(f"batch_size must be between 1 and {MAX_COMPLETION_BATCH_SIZE}")

        now = self._clock.now()
        completed = 0
        skipped = 0
        with self._uow as uow:
            events = uow.events.list_expired_published_for_update(now=now, limit=batch_size)
            for event in events:
                try:
                    event.complete(now)
                except ConflictError:
                    skipped += 1
                    continue
                uow.events.update(event)
                completed += 1
            if events:
                uow.commit()

        selected = len(events)
        return CompletionBatchResult(
            selected=selected,
            completed=completed,
            skipped=skipped,
            may_have_more=selected == batch_size,
        )
