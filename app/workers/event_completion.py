"""Standalone process that completes ended published events."""

import argparse
import logging
import signal
from dataclasses import dataclass
from threading import Event as StopEvent
from typing import Callable, Sequence

from app.application.event_completion_service import EventCompletionService
from app.config import Settings
from app.infrastructure.clock import SystemClock
from app.infrastructure.db.base import build_engine, build_session_factory
from app.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork

LOGGER = logging.getLogger("eventhub.event_completion")


@dataclass(frozen=True)
class CompletionRunResult:
    batches: int
    selected: int
    completed: int
    skipped: int


def drain(
    service: EventCompletionService, batch_size: int, logger: logging.Logger = LOGGER
) -> CompletionRunResult:
    """Drain all currently eligible rows using bounded transactions."""
    batches = selected = completed = skipped = 0
    while True:
        result = service.complete_batch(batch_size)
        batches += 1
        selected += result.selected
        completed += result.completed
        skipped += result.skipped
        logger.info(
            "completion batch selected=%d completed=%d skipped=%d",
            result.selected,
            result.completed,
            result.skipped,
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
) -> None:
    """Process one bounded transaction per cycle and stop cooperatively."""
    wait_for_stop = wait or stop_event.wait
    while not stop_event.is_set():
        try:
            result = service.complete_batch(batch_size)
            logger.info(
                "completion cycle selected=%d completed=%d skipped=%d",
                result.selected,
                result.completed,
                result.skipped,
            )
        except Exception as error:  # keep the long-running worker alive between cycles
            logger.error("completion cycle failed error_type=%s", type(error).__name__)
        if wait_for_stop(poll_seconds):
            break


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--once", action="store_true", help="drain all currently eligible events and exit"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    engine = None
    try:
        args = _parser().parse_args(argv)
        settings = Settings()
        engine = build_engine(settings)
        session_factory = build_session_factory(engine)
        uow = SqlAlchemyUnitOfWork(session_factory)
        service = EventCompletionService(uow, SystemClock())
        stop_event = StopEvent()

        def request_stop(signum: int, frame: object) -> None:
            del frame
            LOGGER.info("shutdown requested signal=%d", signum)
            stop_event.set()

        signal.signal(signal.SIGINT, request_stop)
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, request_stop)

        if args.once:
            result = drain(service, settings.event_completion_batch_size)
            LOGGER.info(
                "completion run finished batches=%d selected=%d completed=%d skipped=%d",
                result.batches,
                result.selected,
                result.completed,
                result.skipped,
            )
        else:
            LOGGER.info(
                "completion worker started poll_seconds=%s batch_size=%d",
                settings.event_completion_poll_seconds,
                settings.event_completion_batch_size,
            )
            run_continuously(
                service,
                batch_size=settings.event_completion_batch_size,
                poll_seconds=settings.event_completion_poll_seconds,
                stop_event=stop_event,
            )
        return 0
    except KeyboardInterrupt:
        LOGGER.info("shutdown requested from keyboard")
        return 0
    except Exception as error:
        LOGGER.error("completion worker stopped error_type=%s", type(error).__name__)
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
