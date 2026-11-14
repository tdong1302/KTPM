"""Locust workloads for the reproducible Phase 2 BEFORE benchmark.

The runner selects a workload with ``EVENTHUB_BENCHMARK_SCENARIO``. S2 and S3 retain the
original 7:3 catalogue/buyer mix. S1 uses only public catalogue operations. S4 reuses the S2
mix at a configurable concurrency ladder.
"""

from __future__ import annotations

import os
import random
import uuid
from pathlib import Path

import gevent
from locust import HttpUser, between, events, task

from benchmark.support import HttpResultCounter, write_json

PASSWORD = "loadtest-password"
SCENARIO = os.getenv("EVENTHUB_BENCHMARK_SCENARIO", "s2").lower()
WARMUP_SECONDS = max(0.0, float(os.getenv("EVENTHUB_BENCHMARK_WARMUP_SECONDS", "30")))
WARMUP_FILE = os.getenv("EVENTHUB_BENCHMARK_WARMUP_FILE")
STATUS_FILE = os.getenv("EVENTHUB_BENCHMARK_STATUS_FILE")

_counter = HttpResultCounter()
_environment = None
_measurement_started = False


@events.test_start.add_listener
def on_test_start(environment, **_kwargs):
    global _environment, _measurement_started
    _environment = environment
    _measurement_started = False
    _counter.reset()
    print(f"[benchmark] target={environment.host} scenario={SCENARIO}")


def _finish_warmup() -> None:
    global _measurement_started
    if _environment is None or _environment.runner is None:
        return
    total = _environment.runner.stats.total
    payload = {
        "warmup_seconds_after_spawn": WARMUP_SECONDS,
        "warmup_requests_including_ramp": total.num_requests,
        "warmup_failures_including_ramp": total.num_failures,
    }
    if WARMUP_FILE:
        from datetime import datetime, timezone

        payload["measured_from_utc"] = datetime.now(timezone.utc).isoformat()
        write_json(Path(WARMUP_FILE), payload)
    _environment.runner.stats.reset_all()
    _counter.reset()
    _measurement_started = True
    print(
        "[benchmark] warm-up discarded; measurement started "
        f"after {payload['warmup_requests_including_ramp']} requests"
    )


@events.spawning_complete.add_listener
def on_spawning_complete(user_count, **_kwargs):
    del user_count
    gevent.spawn_later(WARMUP_SECONDS, _finish_warmup)


@events.request.add_listener
def count_http_result(response=None, exception=None, **_kwargs):
    if not _measurement_started:
        return
    _counter.record(getattr(response, "status_code", None), exception)


@events.quitting.add_listener
def write_status_distribution(environment, **_kwargs):
    if STATUS_FILE:
        stats = environment.runner.stats if environment.runner else None

        def serialize_entry(entry):
            return {
                "method": entry.method,
                "name": entry.name,
                "requests": entry.num_requests,
                "failures": entry.num_failures,
                "rps": entry.total_rps,
                "p50_ms": entry.get_response_time_percentile(0.50),
                "p95_ms": entry.get_response_time_percentile(0.95),
                "p99_ms": entry.get_response_time_percentile(0.99),
            }

        write_json(
            Path(STATUS_FILE),
            {
                "scenario": SCENARIO,
                "status_counts": _counter.snapshot(),
                "final_stats": {
                    "aggregate": serialize_entry(stats.total),
                    "endpoints": [
                        serialize_entry(entry)
                        for entry in stats.entries.values()
                        if entry.num_requests > 0
                    ],
                }
                if stats
                else None,
            },
        )


class ReadPathBrowser(HttpUser):
    """S1 only: representative public catalogue reads, without auth or writes."""

    abstract = SCENARIO != "s1"
    wait_time = between(0.1, 0.5)

    def on_start(self) -> None:
        response = self.client.get("/api/events?size=100", name="SETUP /api/events")
        self.event_ids = (
            [item["id"] for item in response.json().get("items", [])]
            if response.status_code == 200
            else []
        )

    @task(5)
    def list_events(self) -> None:
        page = random.randint(1, 3)
        self.client.get(f"/api/events?page={page}&size=20", name="GET /api/events")

    @task(3)
    def filter_events(self) -> None:
        city = random.choice(["Hanoi", "Da Nang", "Ho Chi Minh City", "Hue"])
        self.client.get(f"/api/events?city={city}&size=20", name="GET /api/events?city")

    @task(2)
    def search_and_sort_events(self) -> None:
        self.client.get(
            "/api/events?q=Benchmark&category=music&sort_by=price&sort_dir=desc&size=20",
            name="GET /api/events?search-filter-sort",
        )

    @task(2)
    def event_detail(self) -> None:
        if self.event_ids:
            event_id = random.choice(self.event_ids)
            self.client.get(f"/api/events/{event_id}", name="GET /api/events/{id}")


class CatalogueBrowser(HttpUser):
    """Original S2/S3 catalogue traffic; S4 uses the same representative mix."""

    abstract = SCENARIO not in {"s2", "s3", "s4"}
    weight = 7
    wait_time = between(0.1, 0.5)

    def on_start(self) -> None:
        self.event_ids = self._load_event_ids()

    def _load_event_ids(self) -> list[int]:
        response = self.client.get("/api/events?size=100", name="SETUP /api/events")
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
        if self.event_ids:
            event_id = random.choice(self.event_ids)
            self.client.get(f"/api/events/{event_id}", name="GET /api/events/{id}")


class TicketBuyer(HttpUser):
    """Original authenticated read/write traffic, with explicit booking result names."""

    abstract = SCENARIO not in {"s2", "s3", "s4"}
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
            name="SETUP POST /api/auth/register",
        )
        if registered.status_code != 201:
            return
        logged_in = self.client.post(
            "/api/auth/login",
            json={"email": email, "password": PASSWORD},
            name="SETUP POST /api/auth/login",
        )
        if logged_in.status_code != 200:
            return
        self.headers = {"Authorization": f"Bearer {logged_in.json()['access_token']}"}

        catalogue = self.client.get("/api/events?size=100", name="SETUP /api/events")
        if catalogue.status_code == 200:
            self.event_ids = [item["id"] for item in catalogue.json().get("items", [])]

    @task(4)
    def list_my_bookings(self) -> None:
        if self.headers:
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
            name="POST /api/bookings [pending]",
            catch_response=True,
        ) as response:
            if response.status_code == 201:
                response.request_meta["name"] = "POST /api/bookings [201 created]"
                self.my_bookings.append(response.json()["id"])
                response.success()
            elif response.status_code == 409:
                response.request_meta["name"] = "POST /api/bookings [409 sold-out]"
                response.success()
            else:
                response.request_meta["name"] = "POST /api/bookings [unexpected]"
                response.failure(f"unexpected status {response.status_code}")

    @task(1)
    def cancel_a_booking(self) -> None:
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
