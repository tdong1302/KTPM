"""Integration test fixtures.

These drive the real FastAPI app, the real middleware, the real SQLAlchemy repositories
and real JWT/bcrypt adapters, against an in-memory SQLite database. Only the database
engine differs from production, which keeps the suite fast enough to run on every change.
"""

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def settings() -> Settings:
    return Settings(
        database_url="sqlite+pysqlite:///:memory:",
        db_auto_create=True,
        jwt_secret="test-secret-not-used-anywhere-else",
        # bcrypt at its default cost would dominate the runtime of this suite.
        bcrypt_rounds=4,
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def iso(dt: datetime) -> str:
    return dt.isoformat()


def future(**kwargs) -> datetime:
    return datetime.now(timezone.utc) + timedelta(**kwargs)


class ApiActor:
    """A registered, logged-in user plus the header needed to act as them."""

    def __init__(self, client: TestClient, user: dict, token: str) -> None:
        self.client = client
        self.user = user
        self.token = token

    @property
    def id(self) -> int:
        return self.user["id"]

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


def register_and_login(
    client: TestClient, email: str, role: str = "USER", password: str = "password123"
) -> ApiActor:
    registered = client.post(
        "/api/auth/register",
        json={"email": email, "password": password, "full_name": email.split("@")[0], "role": role},
    )
    assert registered.status_code == 201, registered.text
    logged_in = client.post("/api/auth/login", json={"email": email, "password": password})
    assert logged_in.status_code == 200, logged_in.text
    body = logged_in.json()
    return ApiActor(client, body["user"], body["access_token"])


@pytest.fixture
def organizer(client: TestClient) -> ApiActor:
    return register_and_login(client, "organizer@example.com", role="ORGANIZER")


@pytest.fixture
def buyer(client: TestClient) -> ApiActor:
    return register_and_login(client, "buyer@example.com", role="USER")


def event_payload(**overrides) -> dict:
    start = future(days=30)
    payload = {
        "title": "Rock Night",
        "description": "An evening of live rock music",
        "category": "music",
        "city": "Hanoi",
        "location": "Main Hall",
        "start_time": iso(start),
        "end_time": iso(start + timedelta(hours=3)),
        "total_tickets": 100,
        "price": "49.99",
    }
    payload.update(overrides)
    return payload


def create_published_event(organizer: ApiActor, **overrides) -> dict:
    created = organizer.client.post(
        "/api/events", json=event_payload(**overrides), headers=organizer.headers
    )
    assert created.status_code == 201, created.text
    event_id = created.json()["id"]
    published = organizer.client.patch(f"/api/events/{event_id}/publish", headers=organizer.headers)
    assert published.status_code == 200, published.text
    return published.json()
