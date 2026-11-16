"""Standalone process that completes ended published events."""

import argparse
import logging
import secrets
import signal
from dataclasses import dataclass
from threading import Event as StopEvent
from time import monotonic, perf_counter
from typing import Callable, Sequence

from app.application.event_completion_service import EventCompletionService
from app.config import Settings
from app.infrastructure.clock import SystemClock
from app.infrastructure.db.base import build_engine, build_session_factory
from app.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork
from app.observability.logging import LogFormat, configure_eventhub_logging, emit_event

LOGGER = logging.getLogger("eventhub.event_completion")


@dataclass(frozen=True)
class CompletionRunResult:
    batches: int
    selected: int
    completed: int
    skipped: int


def drain(
    service: EventCompletionService,
    batch_size: int,
    logger: logging.Logger = LOGGER,
    *,
    operation_id: str | None = None,
    log_format: LogFormat = "json",
) -> CompletionRunResult:
    """Drain all currently eligible rows using bounded transactions."""
    operation_id = operation_id or secrets.token_hex(16)
    batches = selected = completed = skipped = 0
    while True:
        batch_id = secrets.token_hex(16)
        started = perf_counter()
        result = service.complete_batch(batch_size)
        duration = perf_counter() - started
        batches += 1
        selected += result.selected
        completed += result.completed
        skipped += result.skipped
        emit_event(
            logger,
            logging.INFO,
            "event_completion_batch_completed",
            log_format=log_format,
            operation_id=operation_id,
            batch_id=batch_id,
            batch_size=batch_size,
            examined=result.selected,
            completed=result.completed,
            skipped=result.skipped,
            duration_seconds=round(duration, 6),
        )
        if not result.may_have_more:
            break
        if result.completed == 0:
            raise RuntimeError("completion worker made no progress")
    return CompletionRunResult(batches, selected, completed, skipped)


def run_continuously(
    service: EventCompletionService,
    *,
    batch_size: int,
    poll_seconds: float,
    stop_event: StopEvent,
    wait: Callable[[float], bool] | None = None,
    logger: logging.Logger = LOGGER,
    operation_id: str | None = None,
    log_format: LogFormat = "json",
) -> None:
    """Process one bounded transaction per cycle and stop cooperatively."""
    operation_id = operation_id or secrets.token_hex(16)
    wait_for_stop = wait or (lambda seconds: _responsive_wait(stop_event, seconds))
    while not stop_event.is_set():
        batch_id = secrets.token_hex(16)
        started = perf_counter()
        try:
            result = service.complete_batch(batch_size)
            emit_event(
                logger,
                logging.INFO,
                "event_completion_batch_completed",
                log_format=log_format,
                operation_id=operation_id,
                batch_id=batch_id,
                batch_size=batch_size,
                examined=result.selected,
                completed=result.completed,
                skipped=result.skipped,
                duration_seconds=round(perf_counter() - started, 6),
            )
        except Exception as error:  # keep the long-running worker alive between cycles
            emit_event(
                logger,
                logging.ERROR,
                "event_completion_batch_failed",
                log_format=log_format,
                operation_id=operation_id,
                batch_id=batch_id,
                batch_size=batch_size,
                exception_type=type(error).__name__,
                duration_seconds=round(perf_counter() - started, 6),
            )
        if wait_for_stop(poll_seconds):
            break


def _responsive_wait(stop_event: StopEvent, seconds: float) -> bool:
    """Preserve the poll interval while giving PID 1 a bounded signal response time."""
    deadline = monotonic() + seconds
    while not stop_event.is_set():
        remaining = deadline - monotonic()
        if remaining <= 0:
            return False
        stop_event.wait(min(remaining, 0.5))
    return True


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--once", action="store_true", help="drain all currently eligible events and exit"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    configure_eventhub_logging()
    engine = None
    operation_id = secrets.token_hex(16)
    log_format: LogFormat = "json"
    stop_reason = "completed"
    try:
        args = _parser().parse_args(argv)
        settings = Settings()
        log_format = getattr(settings, "observability_log_format", "json")
        engine = build_engine(settings)
        session_factory = build_session_factory(engine)
        uow = SqlAlchemyUnitOfWork(session_factory)
        service = EventCompletionService(uow, SystemClock())
        stop_event = StopEvent()

        emit_event(
            LOGGER,
            logging.INFO,
            "event_completion_worker_started",
            log_format=log_format,
            operation_id=operation_id,
            mode="once" if args.once else "continuous",
            poll_seconds=getattr(settings, "event_completion_poll_seconds", "not_applicable"),
            batch_size=settings.event_completion_batch_size,
        )

        def request_stop(signum: int, frame: object) -> None:
            del frame
            emit_event(
                LOGGER,
                logging.INFO,
                "event_completion_shutdown_requested",
                log_format=log_format,
                operation_id=operation_id,
                signal=signum,
            )
            stop_event.set()

        signal.signal(signal.SIGINT, request_stop)
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, request_stop)

        if args.once:
            result = drain(
                service,
                settings.event_completion_batch_size,
                operation_id=operation_id,
                log_format=log_format,
            )
            emit_event(
                LOGGER,
                logging.INFO,
                "event_completion_run_completed",
                log_format=log_format,
                operation_id=operation_id,
                batches=result.batches,
                examined=result.selected,
                completed=result.completed,
                skipped=result.skipped,
            )
        else:
            run_continuously(
                service,
                batch_size=settings.event_completion_batch_size,
                poll_seconds=settings.event_completion_poll_seconds,
                stop_event=stop_event,
                operation_id=operation_id,
                log_format=log_format,
            )
        return 0
    except KeyboardInterrupt:
        stop_reason = "keyboard_interrupt"
        emit_event(
            LOGGER,
            logging.INFO,
            "event_completion_shutdown_requested",
            log_format=log_format,
            operation_id=operation_id,
            signal="keyboard",
        )
        return 0
    except Exception as error:
        stop_reason = "error"
        emit_event(
            LOGGER,
            logging.ERROR,
            "event_completion_worker_failed",
            log_format=log_format,
            operation_id=operation_id,
            exception_type=type(error).__name__,
        )
        return 1
    finally:
        if engine is not None:
            engine.dispose()
        emit_event(
            LOGGER,
            logging.INFO,
            "event_completion_worker_stopped",
            log_format=log_format,
            operation_id=operation_id,
            reason=stop_reason,
        )


if __name__ == "__main__":
    raise SystemExit(main())
