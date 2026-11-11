"""Reclaim expired ticket holds independently of the HTTP application."""

import argparse
import logging
import signal
from collections.abc import Sequence
from threading import Event

from app.application.reservation_service import ReservationService
from app.config import Settings
from app.infrastructure.clock import SystemClock
from app.infrastructure.db.base import build_engine, build_session_factory
from app.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork

LOGGER = logging.getLogger(__name__)
POLL_SECONDS = 5


def run(service: ReservationService, stop: Event, *, once: bool) -> int:
    while not stop.is_set():
        try:
            expired = service.expire_batch()
        except Exception as error:
            LOGGER.error("reservation expiry failed error_type=%s", type(error).__name__)
            if once:
                return 1
        else:
            if expired:
                LOGGER.info("expired reservations count=%d", expired)
                continue
            if once:
                return 0
        stop.wait(POLL_SECONDS)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="reclaim currently due holds and exit")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO)

    stop = Event()

    def request_stop(_signum: int, _frame: object) -> None:
        stop.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    engine = None
    try:
        engine = build_engine(Settings())
        service = ReservationService(
            SqlAlchemyUnitOfWork(build_session_factory(engine)), SystemClock()
        )
        LOGGER.info("reservation expiry worker started")
        return run(service, stop, once=args.once)
    except Exception as error:
        LOGGER.error("reservation expiry worker stopped error_type=%s", type(error).__name__)
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
