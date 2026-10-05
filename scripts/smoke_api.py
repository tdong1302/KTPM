"""Run the essential EventHub HTTP workflow against an already running API."""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
import uuid
from datetime import UTC, datetime, timedelta


def request(base_url: str, method: str, path: str, payload=None, token: str = ""):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(payload).encode() if payload is not None else None
    response = urllib.request.urlopen(
        urllib.request.Request(base_url + path, data=data, headers=headers, method=method),
        timeout=10,
    )
    body = response.read()
    return response.status, json.loads(body) if body else None


def wait_for_health(base_url: str, timeout: int = 60) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            status, body = request(base_url, "GET", "/health")
            if status == 200 and body["status"] == "UP":
                return
        except (OSError, urllib.error.URLError):
            time.sleep(1)
    raise RuntimeError("API health endpoint did not become ready")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")
    wait_for_health(base_url)

    suffix = uuid.uuid4().hex[:10]
    password = "smoke-password-123"

    def register_login(role: str) -> tuple[int, str]:
        email = f"smoke-{role.lower()}-{suffix}@example.com"
        status, _ = request(
            base_url,
            "POST",
            "/api/auth/register",
            {"email": email, "password": password, "full_name": "Smoke Test", "role": role},
        )
        assert status == 201
        status, body = request(
            base_url, "POST", "/api/auth/login", {"email": email, "password": password}
        )
        assert status == 200
        return body["user"]["id"], body["access_token"]

    _, organizer_token = register_login("ORGANIZER")
    _, buyer_token = register_login("USER")
    start = datetime.now(UTC) + timedelta(days=30)
    status, event = request(
        base_url,
        "POST",
        "/api/events",
        {
            "title": "Infrastructure smoke event",
            "description": "Disposable CI verification",
            "category": "testing",
            "city": "Hanoi",
            "location": "CI",
            "start_time": start.isoformat(),
            "end_time": (start + timedelta(hours=2)).isoformat(),
            "total_tickets": 5,
            "price": "10.00",
        },
        organizer_token,
    )
    assert status == 201
    event_id = event["id"]
    status, event = request(
        base_url, "PATCH", f"/api/events/{event_id}/publish", token=organizer_token
    )
    assert status == 200 and event["status"] == "PUBLISHED"
    status, booking = request(
        base_url,
        "POST",
        "/api/bookings",
        {"event_id": event_id, "quantity": 1},
        buyer_token,
    )
    assert status == 201 and booking["status"] == "CONFIRMED"
    status, cancelled = request(
        base_url, "DELETE", f"/api/bookings/{booking['id']}", token=buyer_token
    )
    assert status == 200 and cancelled["status"] == "CANCELLED"
    status, openapi = request(base_url, "GET", "/openapi.json")
    assert status == 200 and openapi["openapi"].startswith("3.")
    print("PASS: health, auth, event publish, booking cancellation, and OpenAPI smoke flow")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
