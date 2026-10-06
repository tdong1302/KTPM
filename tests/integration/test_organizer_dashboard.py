"""Organizer-owned event listing over the real HTTP and repository adapters."""

import jwt

from tests.conftest import create_published_event, event_payload, register_and_login


def create_draft(client, organizer, title: str) -> dict:
    response = client.post(
        "/api/events",
        json=event_payload(title=title),
        headers=organizer.headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


class TestOrganizerEventDashboard:
    def test_returns_owned_events_in_all_reachable_statuses_and_excludes_other_owners(
        self, client, organizer
    ):
        draft = create_draft(client, organizer, "Owned draft")
        published = create_published_event(organizer, title="Owned published")
        cancelled_source = create_published_event(organizer, title="Owned cancelled")
        cancelled = client.patch(
            f"/api/events/{cancelled_source['id']}/cancel", headers=organizer.headers
        ).json()
        other = register_and_login(client, "other-organizer@example.com", role="ORGANIZER")
        foreign = create_draft(client, other, "Foreign draft")

        response = client.get("/api/events/mine", headers=organizer.headers)

        assert response.status_code == 200
        body = response.json()
        assert {item["id"] for item in body["items"]} == {
            draft["id"],
            published["id"],
            cancelled["id"],
        }
        assert foreign["id"] not in {item["id"] for item in body["items"]}
        assert {item["status"] for item in body["items"]} == {
            "DRAFT",
            "PUBLISHED",
            "CANCELLED",
        }

    def test_status_filter_and_pagination_use_existing_conventions(self, client, organizer):
        first = create_draft(client, organizer, "First draft")
        second = create_draft(client, organizer, "Second draft")
        create_published_event(organizer, title="Published")

        response = client.get(
            "/api/events/mine",
            params={"status": "DRAFT", "page": 2, "size": 1},
            headers=organizer.headers,
        )

        assert response.status_code == 200
        body = response.json()
        assert (body["total"], body["page"], body["size"], body["total_pages"]) == (2, 2, 1, 2)
        assert body["items"][0]["id"] == first["id"]
        assert body["items"][0]["id"] != second["id"]

    def test_newest_events_are_returned_first_with_deterministic_ids(self, client, organizer):
        events = [create_draft(client, organizer, f"Draft {index}") for index in range(3)]

        items = client.get("/api/events/mine", headers=organizer.headers).json()["items"]

        assert [item["id"] for item in items] == [event["id"] for event in reversed(events)]

    def test_empty_organizer_receives_an_empty_page(self, client):
        organizer = register_and_login(client, "empty-organizer@example.com", role="ORGANIZER")

        response = client.get("/api/events/mine", headers=organizer.headers)

        assert response.status_code == 200
        assert response.json() == {
            "items": [],
            "total": 0,
            "page": 1,
            "size": 20,
            "total_pages": 0,
        }

    def test_user_is_forbidden_and_admin_follows_existing_organizer_policy(
        self, client, organizer, buyer, settings
    ):
        create_draft(client, organizer, "Organizer only")
        user_response = client.get("/api/events/mine", headers=buyer.headers)
        admin_token = jwt.encode(
            {"sub": "999", "email": "admin@example.com", "role": "ADMIN", "exp": 9999999999},
            settings.jwt_secret,
            algorithm="HS256",
        )
        admin_response = client.get(
            "/api/events/mine",
            params={"organizer_id": organizer.id},
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert user_response.status_code == 403
        assert user_response.json()["code"] == "FORBIDDEN"
        assert admin_response.status_code == 200
        assert admin_response.json()["items"] == []

    def test_owner_id_query_cannot_impersonate_another_organizer(self, client, organizer):
        own = create_draft(client, organizer, "Mine")
        other = register_and_login(client, "impersonated@example.com", role="ORGANIZER")
        foreign = create_draft(client, other, "Not mine")

        items = client.get(
            "/api/events/mine",
            params={"organizer_id": other.id},
            headers=organizer.headers,
        ).json()["items"]

        assert [item["id"] for item in items] == [own["id"]]
        assert foreign["id"] not in {item["id"] for item in items}

    def test_rejects_invalid_pagination_and_status(self, client, organizer):
        assert (
            client.get(
                "/api/events/mine", params={"page": 0}, headers=organizer.headers
            ).status_code
            == 422
        )
        assert (
            client.get(
                "/api/events/mine", params={"size": 101}, headers=organizer.headers
            ).status_code
            == 422
        )
        assert (
            client.get(
                "/api/events/mine", params={"status": "UNKNOWN"}, headers=organizer.headers
            ).status_code
            == 422
        )
