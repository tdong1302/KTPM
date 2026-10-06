"""Draft event editing over the real HTTP and persistence adapters."""

from datetime import timedelta

import jwt
import pytest

from app.infrastructure.db.orm import EventRecord
from tests.conftest import event_payload, future, iso, register_and_login


def create_draft(client, organizer, **overrides) -> dict:
    response = client.post(
        "/api/events",
        json=event_payload(**overrides),
        headers=organizer.headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


class TestDraftEventEditing:
    def test_owner_partially_updates_a_draft_and_preserves_omitted_fields(self, client, organizer):
        draft = create_draft(client, organizer, title="Original", total_tickets=10)

        response = client.patch(
            f"/api/events/{draft['id']}",
            json={"title": "  Revised title  ", "price": "75000.50", "total_tickets": 25},
            headers=organizer.headers,
        )

        assert response.status_code == 200
        updated = response.json()
        assert updated["title"] == "Revised title"
        assert updated["price"] == "75000.50"
        assert (updated["total_tickets"], updated["available_tickets"]) == (25, 25)
        assert updated["location"] == draft["location"]
        persisted = client.get(f"/api/events/{draft['id']}", headers=organizer.headers).json()
        assert persisted == updated

    def test_another_organizer_cannot_edit_the_draft(self, client, organizer):
        draft = create_draft(client, organizer)
        intruder = register_and_login(client, "event-editor-intruder@example.com", role="ORGANIZER")

        response = client.patch(
            f"/api/events/{draft['id']}",
            json={"title": "Stolen"},
            headers=intruder.headers,
        )

        assert response.status_code == 403
        assert response.json()["code"] == "FORBIDDEN"

    def test_plain_user_cannot_edit(self, client, organizer, buyer):
        draft = create_draft(client, organizer)

        response = client.patch(
            f"/api/events/{draft['id']}",
            json={"title": "Not allowed"},
            headers=buyer.headers,
        )

        assert response.status_code == 403

    @pytest.mark.parametrize("event_status", ["PUBLISHED", "CANCELLED", "COMPLETED"])
    def test_non_draft_event_cannot_be_edited(self, client, organizer, event_status):
        draft = create_draft(client, organizer)
        if event_status == "PUBLISHED":
            client.patch(f"/api/events/{draft['id']}/publish", headers=organizer.headers)
        elif event_status == "CANCELLED":
            client.patch(f"/api/events/{draft['id']}/cancel", headers=organizer.headers)
        else:
            with client.app.state.session_factory() as session:
                record = session.get(EventRecord, draft["id"])
                record.status = event_status
                session.commit()

        response = client.patch(
            f"/api/events/{draft['id']}",
            json={"title": "Too late"},
            headers=organizer.headers,
        )

        assert response.status_code == 409
        assert response.json()["code"] == "CONFLICT"

    def test_updated_draft_appears_in_owned_listing_and_not_public_discovery(
        self, client, organizer
    ):
        draft = create_draft(client, organizer, title="Before edit")

        response = client.patch(
            f"/api/events/{draft['id']}",
            json={"title": "After edit"},
            headers=organizer.headers,
        )

        assert response.status_code == 200
        mine = client.get("/api/events/mine", headers=organizer.headers).json()["items"]
        assert next(item for item in mine if item["id"] == draft["id"])["title"] == "After edit"
        assert client.get("/api/events", params={"q": "After edit"}).json()["total"] == 0

        published = client.patch(f"/api/events/{draft['id']}/publish", headers=organizer.headers)
        assert published.status_code == 200
        assert client.get("/api/events", params={"q": "After edit"}).json()["total"] == 1

    def test_admin_uses_existing_owner_bypass_but_does_not_take_ownership(
        self, client, organizer, settings
    ):
        draft = create_draft(client, organizer)
        token = jwt.encode(
            {"sub": "999", "email": "admin@example.com", "role": "ADMIN", "exp": 9999999999},
            settings.jwt_secret,
            algorithm="HS256",
        )

        response = client.patch(
            f"/api/events/{draft['id']}",
            json={"title": "Admin correction"},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        assert response.json()["organizer_id"] == organizer.id

    def test_invalid_time_order_and_past_start_are_rejected(self, client, organizer):
        draft = create_draft(client, organizer)
        new_start = future(days=20)

        reversed_times = client.patch(
            f"/api/events/{draft['id']}",
            json={
                "start_time": iso(new_start),
                "end_time": iso(new_start - timedelta(hours=1)),
            },
            headers=organizer.headers,
        )
        past_start = client.patch(
            f"/api/events/{draft['id']}",
            json={"start_time": iso(future(days=-1))},
            headers=organizer.headers,
        )

        assert reversed_times.status_code == 400
        assert past_start.status_code == 400

    @pytest.mark.parametrize(
        "payload",
        [
            {},
            {"title": None},
            {"status": "PUBLISHED"},
            {"organizer_id": 999},
            {"available_tickets": 1},
            {"unknown": "field"},
        ],
    )
    def test_rejects_empty_null_immutable_and_unknown_payloads(self, client, organizer, payload):
        draft = create_draft(client, organizer)

        response = client.patch(
            f"/api/events/{draft['id']}", json=payload, headers=organizer.headers
        )

        assert response.status_code == 422
        assert response.json()["code"] == "REQUEST_VALIDATION_ERROR"

    def test_missing_event_is_not_found(self, client, organizer):
        response = client.patch(
            "/api/events/999999", json={"title": "Missing"}, headers=organizer.headers
        )

        assert response.status_code == 404
