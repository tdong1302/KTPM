"""Proves that authentication is enforced centrally, before any route handler runs."""

import pytest

from tests.conftest import register_and_login

PROTECTED_ROUTES = [
    ("GET", "/api/auth/me"),
    ("GET", "/api/events/mine"),
    ("POST", "/api/events"),
    ("PATCH", "/api/events/1"),
    ("PATCH", "/api/events/1/publish"),
    ("PATCH", "/api/events/1/cancel"),
    ("DELETE", "/api/events/1"),
    ("POST", "/api/bookings"),
    ("GET", "/api/bookings/me"),
    ("GET", "/api/bookings/1"),
    ("DELETE", "/api/bookings/1"),
]

PUBLIC_ROUTES = [
    ("GET", "/health"),
    ("GET", "/api/events"),
    ("GET", "/openapi.json"),
    ("GET", "/docs"),
]


class TestMiddlewareGuards:
    @pytest.mark.parametrize("method,path", PROTECTED_ROUTES)
    def test_protected_route_rejects_anonymous_caller(self, client, method, path):
        response = client.request(method, path, json={})

        assert response.status_code == 401
        assert response.json()["code"] == "UNAUTHENTICATED"
        assert response.headers["WWW-Authenticate"] == "Bearer"

    @pytest.mark.parametrize("method,path", PROTECTED_ROUTES)
    def test_protected_route_rejects_a_garbage_token(self, client, method, path):
        response = client.request(
            method, path, json={}, headers={"Authorization": "Bearer not-a-jwt"}
        )

        assert response.status_code == 401
        assert response.json()["code"] == "TOKEN_INVALID"

    @pytest.mark.parametrize("method,path", PUBLIC_ROUTES)
    def test_public_route_needs_no_token(self, client, method, path):
        assert client.request(method, path).status_code == 200

    def test_public_route_tolerates_a_bad_token(self, client):
        """A broken token on a public route means anonymous, not an error."""
        response = client.get("/api/events", headers={"Authorization": "Bearer nonsense"})
        assert response.status_code == 200

    def test_a_token_signed_with_another_secret_is_rejected(self, client):
        import jwt

        forged = jwt.encode(
            {"sub": "1", "email": "attacker@example.com", "role": "ADMIN", "exp": 9999999999},
            "some-other-test-secret-that-is-at-least-32-bytes",
            algorithm="HS256",
        )
        response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {forged}"})
        assert response.status_code == 401

    def test_expired_token_is_reported_as_expired(self, client, settings):
        import jwt

        expired = jwt.encode(
            {"sub": "1", "email": "a@example.com", "role": "USER", "exp": 1_000_000_000},
            settings.jwt_secret,
            algorithm="HS256",
        )
        response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired}"})
        assert response.status_code == 401
        assert response.json()["code"] == "TOKEN_EXPIRED"


class TestRegisterAndLogin:
    def test_register_then_login_then_read_own_profile(self, client):
        actor = register_and_login(client, "alice@example.com")

        response = client.get("/api/auth/me", headers=actor.headers)

        assert response.status_code == 200
        assert response.json()["email"] == "alice@example.com"

    def test_registering_the_same_email_twice_conflicts(self, client):
        register_and_login(client, "alice@example.com")
        response = client.post(
            "/api/auth/register",
            json={"email": "alice@example.com", "password": "password123", "full_name": "A"},
        )
        assert response.status_code == 409
        assert response.json()["code"] == "CONFLICT"

    def test_login_with_a_wrong_password_is_unauthorized(self, client):
        register_and_login(client, "alice@example.com")
        response = client.post(
            "/api/auth/login", json={"email": "alice@example.com", "password": "nope-wrong"}
        )
        assert response.status_code == 401
        assert response.json()["code"] == "INVALID_CREDENTIALS"

    def test_response_never_leaks_the_password_hash(self, client):
        actor = register_and_login(client, "alice@example.com")
        body = client.get("/api/auth/me", headers=actor.headers).json()
        assert "password" not in " ".join(body.keys()).lower()

    def test_short_password_fails_request_validation(self, client):
        response = client.post(
            "/api/auth/register",
            json={"email": "alice@example.com", "password": "abc", "full_name": "A"},
        )
        assert response.status_code == 422
        assert response.json()["code"] == "REQUEST_VALIDATION_ERROR"

    def test_admin_role_is_not_offered_by_the_api(self, client):
        response = client.post(
            "/api/auth/register",
            json={
                "email": "root@example.com",
                "password": "password123",
                "full_name": "Root",
                "role": "ADMIN",
            },
        )
        assert response.status_code == 422
