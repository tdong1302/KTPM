from datetime import timedelta

from tests.conftest import create_published_event, register_and_login
from tests.unit.fakes import FakeClock

PATH = "/api/reservations"


def reserve(client, buyer, event_id, quantity=1):
    return client.post(
        PATH, headers=buyer.headers, json={"event_id": event_id, "quantity": quantity}
    )


def test_confirmed_reservation_appears_in_booking_history(client, organizer, buyer):
    event = create_published_event(organizer, total_tickets=1)
    payload = {"event_id": event["id"], "quantity": 1}
    assert client.post(PATH, json=payload).status_code == 401
    assert reserve(client, buyer, event["id"], 11).status_code == 422
    assert reserve(client, buyer, 999).status_code == 404
    response = reserve(client, buyer, event["id"])
    assert response.status_code == 201
    hold = response.json()
    path = f"{PATH}/{hold['id']}"
    assert hold["status"] == "RESERVED"
    assert hold["booking_id"] is None
    assert hold["expires_at"].endswith("Z")
    assert client.get(path, headers=buyer.headers).json() == hold
    assert client.post("/api/bookings", headers=buyer.headers, json=payload).status_code == 409
    assert reserve(client, buyer, event["id"]).status_code == 409
    assert client.get("/api/bookings/me", headers=buyer.headers).json()["items"] == []

    confirmed = client.post(f"{path}/confirm", headers=buyer.headers)
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "CONFIRMED"
    assert client.post(f"{path}/confirm", headers=buyer.headers).json() == confirmed.json()
    history = client.get("/api/bookings/me", headers=buyer.headers).json()["items"]
    assert [item["id"] for item in history] == [confirmed.json()["booking_id"]]
    assert client.get(f"/api/events/{event['id']}").json()["available_tickets"] == 0
    assert client.delete(path, headers=buyer.headers).status_code == 409


def test_only_owner_can_read_confirm_and_cancel(client, organizer, buyer):
    outsider = register_and_login(client, "outsider@example.com")
    event = create_published_event(organizer, total_tickets=2)
    hold = reserve(client, buyer, event["id"], 2).json()
    path = f"{PATH}/{hold['id']}"
    assert client.get(f"{PATH}/999", headers=buyer.headers).status_code == 404
    assert client.get(path, headers=outsider.headers).status_code == 403
    assert client.delete(path, headers=outsider.headers).status_code == 403
    assert client.post(f"{path}/confirm", headers=outsider.headers).status_code == 403
    cancelled = client.delete(path, headers=buyer.headers)
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "CANCELLED"
    assert client.delete(path, headers=buyer.headers).status_code == 409
    assert client.post(f"{path}/confirm", headers=buyer.headers).status_code == 409
    assert client.get(f"/api/events/{event['id']}").json()["available_tickets"] == 2


def test_expiry_worker_reclaims_at_deadline(client, organizer, buyer, monkeypatch):
    from app.application.reservation_service import ReservationService
    from app.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork

    clock = FakeClock(client.app.state.clock.now())
    monkeypatch.setattr(client.app.state, "clock", clock)
    event = create_published_event(organizer)
    hold = reserve(client, buyer, event["id"]).json()
    path = f"{PATH}/{hold['id']}"
    expiry = ReservationService(SqlAlchemyUnitOfWork(client.app.state.session_factory), clock)
    clock.advance(minutes=10, microseconds=-1)
    assert expiry.expire_batch() == 0
    clock.advance(microseconds=1)
    response = client.post(f"{path}/confirm", headers=buyer.headers)
    assert response.status_code == 409
    assert response.json()["code"] == "RESERVATION_EXPIRED"
    assert client.delete(path, headers=buyer.headers).status_code == 409
    assert expiry.expire_batch() == 1
    assert expiry.expire_batch() == 0
    assert client.get(path, headers=buyer.headers).json()["status"] == "EXPIRED"
    assert client.get(f"/api/events/{event['id']}").json()["available_tickets"] == 100


def test_confirm_rejects_cancelled_event(client, organizer, buyer):
    event = create_published_event(organizer)
    hold = reserve(client, buyer, event["id"]).json()
    cancelled = client.patch(f"/api/events/{event['id']}/cancel", headers=organizer.headers)
    assert cancelled.status_code == 200
    path = f"{PATH}/{hold['id']}"
    assert client.post(f"{path}/confirm", headers=buyer.headers).status_code == 409
    assert client.delete(path, headers=buyer.headers).json()["status"] == "CANCELLED"


def test_hold_deadline_is_capped_at_event_start(client, organizer, buyer):
    from datetime import datetime

    start = client.app.state.clock.now() + timedelta(minutes=3)
    event = create_published_event(
        organizer, start_time=start.isoformat(), end_time=(start + timedelta(hours=1)).isoformat()
    )
    hold = reserve(client, buyer, event["id"]).json()
    assert datetime.fromisoformat(hold["expires_at"]) == start
