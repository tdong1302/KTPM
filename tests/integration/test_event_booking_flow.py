"""End-to-end flow over HTTP: create -> publish -> browse -> book -> cancel."""

from datetime import timedelta

from tests.conftest import (
    create_published_event,
    event_payload,
    future,
    iso,
    register_and_login,
)


class TestEventLifecycleOverHttp:
    def test_organizer_creates_publishes_and_sees_the_event_listed(self, client, organizer):
        created = client.post("/api/events", json=event_payload(), headers=organizer.headers)
        assert created.status_code == 201
        body = created.json()
        assert body["status"] == "DRAFT"
        assert body["available_tickets"] == 100
        assert body["organizer_id"] == organizer.id

        # A draft is not in the public catalogue.
        assert client.get("/api/events").json()["total"] == 0

        published = client.patch(f"/api/events/{body['id']}/publish", headers=organizer.headers)
        assert published.status_code == 200
        assert published.json()["status"] == "PUBLISHED"

        catalogue = client.get("/api/events").json()
        assert catalogue["total"] == 1
        assert catalogue["items"][0]["id"] == body["id"]

    def test_plain_user_cannot_create_an_event(self, client, buyer):
        response = client.post("/api/events", json=event_payload(), headers=buyer.headers)
        assert response.status_code == 403
        assert response.json()["code"] == "FORBIDDEN"

    def test_another_organizer_cannot_publish_my_draft(self, client, organizer):
        created = client.post("/api/events", json=event_payload(), headers=organizer.headers)
        intruder = register_and_login(client, "intruder@example.com", role="ORGANIZER")

        response = client.patch(
            f"/api/events/{created.json()['id']}/publish", headers=intruder.headers
        )

        assert response.status_code == 403

    def test_draft_detail_is_hidden_from_other_users(self, client, organizer, buyer):
        created = client.post("/api/events", json=event_payload(), headers=organizer.headers)
        event_id = created.json()["id"]

        assert client.get(f"/api/events/{event_id}").status_code == 404
        assert client.get(f"/api/events/{event_id}", headers=buyer.headers).status_code == 404
        assert client.get(f"/api/events/{event_id}", headers=organizer.headers).status_code == 200

    def test_delete_removes_a_draft(self, client, organizer):
        created = client.post("/api/events", json=event_payload(), headers=organizer.headers)
        event_id = created.json()["id"]

        assert (
            client.delete(f"/api/events/{event_id}", headers=organizer.headers).status_code == 204
        )
        assert client.get(f"/api/events/{event_id}", headers=organizer.headers).status_code == 404

    def test_published_event_cannot_be_deleted(self, client, organizer):
        event = create_published_event(organizer)
        response = client.delete(f"/api/events/{event['id']}", headers=organizer.headers)
        assert response.status_code == 409

    def test_start_time_in_the_past_is_rejected(self, client, organizer):
        past = future(days=-5)
        response = client.post(
            "/api/events",
            json=event_payload(start_time=iso(past), end_time=iso(past + timedelta(hours=2))),
            headers=organizer.headers,
        )
        assert response.status_code == 400
        assert response.json()["code"] == "VALIDATION_ERROR"

    def test_zero_tickets_fails_request_validation(self, client, organizer):
        response = client.post(
            "/api/events", json=event_payload(total_tickets=0), headers=organizer.headers
        )
        assert response.status_code == 422


class TestCatalogue:
    def test_filter_by_city_and_free_text(self, client, organizer):
        create_published_event(
            organizer, title="Jazz in Hanoi", city="Hanoi", description="A quiet jazz evening"
        )
        create_published_event(
            organizer, title="Rock in Hue", city="Hue", description="Loud guitars all night"
        )

        assert client.get("/api/events", params={"city": "hanoi"}).json()["total"] == 1
        assert client.get("/api/events", params={"q": "rock"}).json()["total"] == 1
        assert client.get("/api/events", params={"q": "guitars"}).json()["total"] == 1
        assert client.get("/api/events", params={"city": "Da Nang"}).json()["total"] == 0

    def test_pagination_reports_totals(self, client, organizer):
        for index in range(5):
            create_published_event(organizer, title=f"Show {index}")

        page = client.get("/api/events", params={"page": 1, "size": 2}).json()

        assert (page["total"], page["total_pages"], len(page["items"])) == (5, 3, 2)

    def test_sort_by_price_descending(self, client, organizer):
        create_published_event(organizer, title="Cheap", price="10.00")
        create_published_event(organizer, title="Pricey", price="900.00")

        items = client.get("/api/events", params={"sort_by": "price", "sort_dir": "desc"}).json()[
            "items"
        ]

        assert [i["title"] for i in items] == ["Pricey", "Cheap"]

    def test_unknown_sort_field_is_rejected_by_the_api(self, client):
        assert client.get("/api/events", params={"sort_by": "password_hash"}).status_code == 422


class TestBookingFlowOverHttp:
    def test_book_then_cancel_returns_the_inventory(self, client, organizer, buyer):
        event = create_published_event(organizer, total_tickets=10)

        booked = client.post(
            "/api/bookings",
            json={"event_id": event["id"], "quantity": 3},
            headers=buyer.headers,
        )
        assert booked.status_code == 201
        booking = booked.json()
        assert booking["status"] == "CONFIRMED"
        assert booking["quantity"] == 3
        assert booking["total_price"] == "149.97"
        assert client.get(f"/api/events/{event['id']}").json()["available_tickets"] == 7

        cancelled = client.delete(f"/api/bookings/{booking['id']}", headers=buyer.headers)
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "CANCELLED"
        assert client.get(f"/api/events/{event['id']}").json()["available_tickets"] == 10

    def test_booking_persists_and_is_listed_for_the_buyer_only(self, client, organizer, buyer):
        event = create_published_event(organizer, total_tickets=10)
        client.post(
            "/api/bookings",
            json={"event_id": event["id"], "quantity": 1},
            headers=buyer.headers,
        )

        mine = client.get("/api/bookings/me", headers=buyer.headers).json()
        organizers = client.get("/api/bookings/me", headers=organizer.headers).json()

        assert mine["total"] == 1
        assert mine["items"][0]["user_id"] == buyer.id
        assert organizers["total"] == 0

    def test_cannot_book_more_than_remaining(self, client, organizer, buyer):
        event = create_published_event(organizer, total_tickets=2)

        response = client.post(
            "/api/bookings",
            json={"event_id": event["id"], "quantity": 2},
            headers=buyer.headers,
        )
        assert response.status_code == 201

        sold_out = client.post(
            "/api/bookings",
            json={"event_id": event["id"], "quantity": 1},
            headers=buyer.headers,
        )
        assert sold_out.status_code == 409
        assert sold_out.json()["code"] == "CONFLICT"
        assert client.get(f"/api/events/{event['id']}").json()["available_tickets"] == 0

    def test_cannot_book_a_draft_event(self, client, organizer, buyer):
        created = client.post("/api/events", json=event_payload(), headers=organizer.headers)
        response = client.post(
            "/api/bookings",
            json={"event_id": created.json()["id"], "quantity": 1},
            headers=buyer.headers,
        )
        assert response.status_code == 404

    def test_cannot_book_a_cancelled_event(self, client, organizer, buyer):
        event = create_published_event(organizer)
        client.patch(f"/api/events/{event['id']}/cancel", headers=organizer.headers)

        response = client.post(
            "/api/bookings",
            json={"event_id": event["id"], "quantity": 1},
            headers=buyer.headers,
        )
        assert response.status_code == 409

    def test_another_user_cannot_read_or_cancel_my_booking(self, client, organizer, buyer):
        event = create_published_event(organizer, total_tickets=10)
        booking_id = client.post(
            "/api/bookings",
            json={"event_id": event["id"], "quantity": 1},
            headers=buyer.headers,
        ).json()["id"]
        intruder = register_and_login(client, "intruder@example.com")

        assert (
            client.get(f"/api/bookings/{booking_id}", headers=intruder.headers).status_code == 403
        )
        assert (
            client.delete(f"/api/bookings/{booking_id}", headers=intruder.headers).status_code
            == 403
        )

    def test_cancelling_twice_conflicts(self, client, organizer, buyer):
        event = create_published_event(organizer, total_tickets=10)
        booking_id = client.post(
            "/api/bookings",
            json={"event_id": event["id"], "quantity": 1},
            headers=buyer.headers,
        ).json()["id"]

        assert (
            client.delete(f"/api/bookings/{booking_id}", headers=buyer.headers).status_code == 200
        )
        assert (
            client.delete(f"/api/bookings/{booking_id}", headers=buyer.headers).status_code == 409
        )

    def test_quantity_above_the_per_booking_cap_is_rejected(self, client, organizer, buyer):
        event = create_published_event(organizer, total_tickets=100)
        response = client.post(
            "/api/bookings",
            json={"event_id": event["id"], "quantity": 50},
            headers=buyer.headers,
        )
        assert response.status_code == 422


class TestOpenApiContract:
    def test_swagger_document_exposes_every_endpoint(self, client):
        spec = client.get("/openapi.json").json()
        operations = {
            (method.upper(), path) for path, ops in spec["paths"].items() for method in ops
        }

        assert ("POST", "/api/auth/login") in operations
        assert ("GET", "/api/auth/me") in operations
        assert ("POST", "/api/events") in operations
        assert ("PATCH", "/api/events/{event_id}") in operations
        assert ("DELETE", "/api/events/{event_id}") in operations
        assert ("POST", "/api/bookings") in operations
        assert ("DELETE", "/api/bookings/{booking_id}") in operations

    def test_swagger_ui_is_served(self, client):
        assert "swagger-ui" in client.get("/docs").text
