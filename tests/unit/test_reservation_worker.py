from threading import Event
from unittest.mock import Mock

from app.workers.reservation_expiry import run


def test_once_drains_batches():
    service = Mock()
    service.expire_batch.side_effect = [2, 1, 0]
    assert run(service, Event(), once=True) == 0
    assert service.expire_batch.call_count == 3


def test_once_reports_failure_without_logging_exception_message(caplog):
    service = Mock()
    service.expire_batch.side_effect = RuntimeError("private connection details")
    assert run(service, Event(), once=True) == 1
    assert "RuntimeError" in caplog.text
    assert "private connection details" not in caplog.text


def test_continuous_worker_waits_after_failure():
    service = Mock()
    service.expire_batch.side_effect = RuntimeError
    stop = Mock()
    stop.is_set.side_effect = [False, True]
    assert run(service, stop, once=False) == 0
    stop.wait.assert_called_once()
