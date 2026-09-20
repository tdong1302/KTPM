"""Load test definition for the Phase 1 baseline.

Run it headless and keep the CSV output as evidence:

    locust -f benchmark/locustfile.py --headless \
           --host http://localhost:8000 \
           --users 50 --spawn-rate 10 --run-time 3m \
           --csv benchmark/results/baseline

Seed the database first with ``python benchmark/seed_data.py`` so that every run starts
from the same dataset. See benchmark/scenarios.md for the agreed scenarios and
docs/benchmark.md for how to record results.

IMPORTANT: no numbers are committed to this repository unless they came from an actual
run on the fixed hardware described in docs/benchmark.md.
"""

import random
import uuid

from locust import HttpUser, between, events, task

PASSWORD = "loadtest-password"


@events.test_start.add_listener
def announce(environment, **_kwargs):
    print(f"[benchmark] target={environment.host}")


class CatalogueBrowser(HttpUser):
    """Read-only traffic: the bulk of a ticketing workload."""

    weight = 7
    wait_time = between(0.1, 0.5)

    def on_start(self) -> None:
        self.event_ids = self._load_event_ids()

    def _load_event_ids(self) -> list[int]:
        response = self.client.get("/api/events?size=100", name="/api/events [warmup]")
        if response.status_code != 200:
            return []
        return [item["id"] for item in response.json().get("items", [])]

    @task(5)
    def list_events(self) -> None:
        page = random.randint(1, 3)
        self.client.get(f"/api/events?page={page}&size=20", name="GET /api/events")

    @task(3)
    def filter_events(self) -> None:
        city = random.choice(["Hanoi", "Da Nang", "Ho Chi Minh City", "Hue"])
        self.client.get(f"/api/events?city={city}&size=20", name="GET /api/events?city")

    @task(2)
    def event_detail(self) -> None:
        if not self.event_ids:
            return
        event_id = random.choice(self.event_ids)
        self.client.get(f"/api/events/{event_id}", name="GET /api/events/{id}")


class Ticketbuyer(HttpUser):
    """Authenticated read/write traffic, including the contended booking path."""

    weight = 3
    wait_time = between(0.2, 1.0)

    def on_start(self) -> None:
        self.headers: dict[str, str] = {}
        self.event_ids: list[int] = []
        self.my_bookings: list[int] = []

        email = f"load-{uuid.uuid4().hex[:12]}@example.com"
        registered = self.client.post(
            "/api/auth/register",
            json={"email": email, "password": PASSWORD, "full_name": "Load Tester"},
            name="POST /api/auth/register",
        )
        if registered.status_code != 201:
            return
        logged_in = self.client.post(
            "/api/auth/login",
            json={"email": email, "password": PASSWORD},
            name="POST /api/auth/login",
        )
        if logged_in.status_code != 200:
            return
        self.headers = {"Authorization": f"Bearer {logged_in.json()['access_token']}"}

        catalogue = self.client.get("/api/events?size=100", name="/api/events [warmup]")
        if catalogue.status_code == 200:
            self.event_ids = [item["id"] for item in catalogue.json().get("items", [])]

    @task(4)
    def list_my_bookings(self) -> None:
        if not self.headers:
            return
        self.client.get(
            "/api/bookings/me", headers=self.headers, name="GET /api/bookings/me [auth]"
        )

    @task(3)
    def book_tickets(self) -> None:
        if not self.headers or not self.event_ids:
            return
        event_id = random.choice(self.event_ids)
        with self.client.post(
            "/api/bookings",
            json={"event_id": event_id, "quantity": random.randint(1, 2)},
            headers=self.headers,
            name="POST /api/bookings [auth]",
            catch_response=True,
        ) as response:
            if response.status_code == 201:
                self.my_bookings.append(response.json()["id"])
                response.success()
            elif response.status_code == 409:
                # Sold out is a correct business outcome under contention, not a failure.
                # Counting it as an error would make the error rate meaningless.
                response.success()
            else:
                response.failure(f"unexpected status {response.status_code}")

    @task(1)
    def cancel_a_booking(self) -> None:
        """Returns inventory so a long run does not simply sell out and go idle."""
        if not self.headers or not self.my_bookings:
            return
        booking_id = self.my_bookings.pop()
        with self.client.delete(
            f"/api/bookings/{booking_id}",
            headers=self.headers,
            name="DELETE /api/bookings/{id} [auth]",
            catch_response=True,
        ) as response:
            if response.status_code in (200, 409):
                response.success()
            else:
                response.failure(f"unexpected status {response.status_code}")
