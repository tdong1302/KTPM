"""End-to-end observability behavior through the real FastAPI stack."""

import logging

from sqlalchemy.exc import SQLAlchemyError


def test_request_id_is_generated_preserved_and_replaced(client) -> None:
    generated = client.get("/health")
    assert len(generated.headers["X-Request-ID"]) == 32

    preserved = client.get("/health", headers={"X-Request-ID": "caller-request-42"})
    assert preserved.headers["X-Request-ID"] == "caller-request-42"

    invalid = client.get("/health", headers={"X-Request-ID": "x" * 65})
    assert invalid.headers["X-Request-ID"] != "x" * 65
    assert len(invalid.headers["X-Request-ID"]) == 32


def test_handled_error_response_and_log_carry_request_id(client, caplog) -> None:
    with caplog.at_level(logging.WARNING, logger="eventhub.api.errors"):
        response = client.get("/api/events/999999", headers={"X-Request-ID": "missing-event"})

    assert response.status_code == 404
    assert response.headers["X-Request-ID"] == "missing-event"
    handled = [
        record.event_fields
        for record in caplog.records
        if getattr(record, "event_name", "") == "http_handled_error"
    ]
    assert handled[-1]["correlation_id"] == "missing-event"
    assert handled[-1]["status_code"] == 404


def test_structured_completion_log_has_required_fields_and_no_secrets(client, caplog) -> None:
    secret = "body-password-must-not-be-logged"
    with caplog.at_level(logging.INFO, logger="eventhub.api"):
        response = client.post(
            "/api/auth/login?token=query-secret",
            json={"email": "nobody@example.com", "password": secret},
            headers={"Authorization": "Bearer header-secret", "X-Request-ID": "login-attempt"},
        )

    assert response.status_code == 401
    records = [
        record.event_fields
        for record in caplog.records
        if getattr(record, "event_name", "") == "http_request_completed"
    ]
    assert records
    event = records[-1]
    assert event["correlation_id"] == "login-attempt"
    assert event["method"] == "POST"
    assert event["route"] == "/api/auth/login"
    assert event["status_code"] == 401
    assert event["duration_seconds"] >= 0
    assert {"timestamp", "level", "logger", "event"}.issubset(event)
    assert secret not in caplog.text
    assert "query-secret" not in caplog.text
    assert "header-secret" not in caplog.text


def test_metrics_use_route_templates_and_not_resource_ids(client) -> None:
    client.get("/api/events/987654321")
    client.get("/api/events/123456789")
    response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    body = response.text
    assert 'route="/api/events/{event_id}"' in body
    assert "987654321" not in body
    assert "123456789" not in body
    assert "correlation_id" not in body
    assert "eventhub_http_request_duration_seconds" in body
    assert "eventhub_db_connection_hold_duration_seconds" in body
    assert "eventhub_db_query_duration_seconds" in body
    assert "eventhub_db_pool_acquisition_wait" not in body


def test_readiness_succeeds_without_changing_liveness(client) -> None:
    assert client.get("/health").json()["status"] == "UP"
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "READY", "service": "eventhub-ktpm"}


def test_readiness_failure_is_safe_and_liveness_remains_up(client) -> None:
    class UnavailableEngine:
        def connect(self):
            raise SQLAlchemyError("database-host-and-password-must-not-leak")

    client.app.state.engine = UnavailableEngine()
    response = client.get("/ready", headers={"X-Request-ID": "readiness-failure"})

    assert response.status_code == 503
    assert response.headers["X-Request-ID"] == "readiness-failure"
    assert response.json() == {"status": "NOT_READY", "service": "eventhub-ktpm"}
    assert "database" not in response.text.lower()
    assert client.get("/health").status_code == 200
