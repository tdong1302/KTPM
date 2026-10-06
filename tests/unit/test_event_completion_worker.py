"""Worker control flow uses injected waits and services, never real sleeping."""

import logging
from threading import Event as StopEvent

from app.application.event_completion_service import CompletionBatchResult
from app.workers import event_completion as worker
from app.workers.event_completion import drain, run_continuously


class StubService:
    def __init__(self, results):
        self.results = list(results)
        self.batch_sizes = []

    def complete_batch(self, batch_size):
        self.batch_sizes.append(batch_size)
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def test_once_drains_multiple_bounded_batches():
    service = StubService(
        [
            CompletionBatchResult(2, 2, 0, True),
            CompletionBatchResult(1, 1, 0, False),
        ]
    )

    result = drain(service, batch_size=2)

    assert (result.batches, result.selected, result.completed) == (2, 3, 3)
    assert service.batch_sizes == [2, 2]


def test_continuous_mode_uses_configured_interval_and_stops_cooperatively():
    stop = StopEvent()
    service = StubService([CompletionBatchResult(0, 0, 0, False)])
    waits = []

    def wait(seconds):
        waits.append(seconds)
        stop.set()
        return True

    run_continuously(
        service,
        batch_size=17,
        poll_seconds=2.5,
        stop_event=stop,
        wait=wait,
    )

    assert service.batch_sizes == [17]
    assert waits == [2.5]


def test_continuous_mode_logs_only_exception_type_and_retries(caplog):
    stop = StopEvent()
    secret = "postgresql://user:super-secret@example/db"
    service = StubService([RuntimeError(secret)])

    with caplog.at_level(logging.ERROR):
        run_continuously(
            service,
            batch_size=10,
            poll_seconds=1,
            stop_event=stop,
            wait=lambda seconds: True,
        )

    assert "RuntimeError" in caplog.text
    assert secret not in caplog.text


def test_main_returns_nonzero_without_logging_sensitive_exception_text(monkeypatch, caplog):
    secret = "postgresql://user:super-secret@example/db"

    def fail_settings():
        raise RuntimeError(secret)

    monkeypatch.setattr(worker, "Settings", fail_settings)
    with caplog.at_level(logging.ERROR):
        exit_code = worker.main(["--once"])

    assert exit_code == 1
    assert "RuntimeError" in caplog.text
    assert secret not in caplog.text


def test_main_disposes_engine_after_successful_once_run(monkeypatch):
    class StubSettings:
        event_completion_batch_size = 7

    class StubEngine:
        disposed = False

        def dispose(self):
            self.disposed = True

    engine = StubEngine()
    seen = []
    monkeypatch.setattr(worker, "Settings", StubSettings)
    monkeypatch.setattr(worker, "build_engine", lambda settings: engine)
    monkeypatch.setattr(worker, "build_session_factory", lambda engine: object())
    monkeypatch.setattr(worker, "SqlAlchemyUnitOfWork", lambda factory: object())
    monkeypatch.setattr(worker, "EventCompletionService", lambda uow, clock: object())
    monkeypatch.setattr(
        worker,
        "drain",
        lambda service, batch_size: (
            seen.append(batch_size) or worker.CompletionRunResult(1, 0, 0, 0)
        ),
    )
    monkeypatch.setattr(worker.signal, "signal", lambda *args: None)

    assert worker.main(["--once"]) == 0
    assert seen == [7]
    assert engine.disposed is True


def test_main_returns_nonzero_and_disposes_engine_after_batch_failure(monkeypatch, caplog):
    class StubSettings:
        event_completion_batch_size = 7

    class StubEngine:
        disposed = False

        def dispose(self):
            self.disposed = True

    engine = StubEngine()
    secret = "database-password-must-not-appear"
    monkeypatch.setattr(worker, "Settings", StubSettings)
    monkeypatch.setattr(worker, "build_engine", lambda settings: engine)
    monkeypatch.setattr(worker, "build_session_factory", lambda engine: object())
    monkeypatch.setattr(worker, "SqlAlchemyUnitOfWork", lambda factory: object())
    monkeypatch.setattr(worker, "EventCompletionService", lambda uow, clock: object())
    monkeypatch.setattr(
        worker, "drain", lambda service, batch_size: (_ for _ in ()).throw(RuntimeError(secret))
    )
    monkeypatch.setattr(worker.signal, "signal", lambda *args: None)

    with caplog.at_level(logging.ERROR):
        assert worker.main(["--once"]) == 1
    assert engine.disposed is True
    assert "RuntimeError" in caplog.text
    assert secret not in caplog.text


def test_keyboard_interrupt_is_graceful_and_disposes_engine(monkeypatch):
    class StubSettings:
        event_completion_batch_size = 7
        event_completion_poll_seconds = 3

    class StubEngine:
        disposed = False

        def dispose(self):
            self.disposed = True

    engine = StubEngine()
    monkeypatch.setattr(worker, "Settings", StubSettings)
    monkeypatch.setattr(worker, "build_engine", lambda settings: engine)
    monkeypatch.setattr(worker, "build_session_factory", lambda engine: object())
    monkeypatch.setattr(worker, "SqlAlchemyUnitOfWork", lambda factory: object())
    monkeypatch.setattr(worker, "EventCompletionService", lambda uow, clock: object())
    monkeypatch.setattr(
        worker,
        "run_continuously",
        lambda *args, **kwargs: (_ for _ in ()).throw(KeyboardInterrupt()),
    )
    monkeypatch.setattr(worker.signal, "signal", lambda *args: None)

    assert worker.main([]) == 0
    assert engine.disposed is True
