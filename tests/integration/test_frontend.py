"""Static delivery contract for the dependency-free end-user frontend."""

import pytest


def test_frontend_shell_is_public_and_references_local_assets(client):
    response = client.get("/app/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert 'id="app-shell"' in response.text
    assert "./assets/styles.css" in response.text
    assert "./assets/app.js" in response.text
    assert "https://" not in response.text


@pytest.mark.parametrize(
    ("path", "content_type"),
    [
        ("/app/assets/styles.css", "text/css"),
        ("/app/assets/api.js", "javascript"),
        ("/app/assets/auth.js", "javascript"),
        ("/app/assets/ui.js", "javascript"),
        ("/app/assets/app.js", "javascript"),
        ("/app/assets/favicon.svg", "image/svg+xml"),
    ],
)
def test_frontend_assets_have_expected_content_types(client, path, content_type):
    response = client.get(path)

    assert response.status_code == 200
    assert content_type in response.headers["content-type"]


def test_missing_frontend_asset_returns_404(client):
    assert client.get("/app/assets/missing.js").status_code == 404


def test_static_mount_cannot_escape_the_frontend_directory(client):
    response = client.get("/app/%2e%2e/pyproject.toml")

    assert response.status_code != 200
    assert b"[project]" not in response.content


def test_frontend_does_not_displace_api_or_documentation(client):
    assert client.get("/health").status_code == 200
    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200

    spec_response = client.get("/openapi.json")
    assert spec_response.status_code == 200
    spec = spec_response.json()
    operations = {
        (method.upper(), path)
        for path, path_item in spec["paths"].items()
        for method in path_item
        if method in {"get", "post", "patch", "delete"}
    }
    assert len(operations) == 16
    assert ("GET", "/api/events") in operations
    assert ("GET", "/api/events/mine") in operations
    assert ("POST", "/api/bookings") in operations


def test_frontend_organizer_dashboard_uses_owned_event_endpoint(client):
    shell = client.get("/app/").text
    application = client.get("/app/assets/app.js").text

    assert 'id="organizer-event-list"' in shell
    assert 'id="organizer-status-filter"' in shell
    assert 'api.get("/api/events/mine"' in application
    assert "eventhub.organizer-events" not in application
    assert "organizerStorageKey" not in application


def test_frontend_exposes_draft_editing_flow(client):
    shell = client.get("/app/").text
    application = client.get("/app/assets/app.js").text

    assert 'id="event-edit-dialog"' in shell
    assert 'id="event-edit-form"' in shell
    assert 'organizerAction: "edit"' in application
    assert "api.patch(`/api/events/${eventId}`, payload" in application
    draft_branch = application.index('if (event.status === "DRAFT")')
    edit_action = application.index('organizerAction: "edit"')
    published_branch = application.index('else if (event.status === "PUBLISHED")')
    assert draft_branch < edit_action < published_branch
    assert application.count('organizerAction: "edit"') == 1
    assert 'organizerAction: "publish"' in application
    assert 'organizerAction: "delete"' in application
    assert '"/api/bookings"' in application


def test_frontend_renders_completed_status_without_mutation_actions(client):
    shell = client.get("/app/").text
    application = client.get("/app/assets/app.js").text
    ui = client.get("/app/assets/ui.js").text

    assert '<option value="COMPLETED">' in shell
    assert 'COMPLETED: "Đã kết thúc"' in ui
    assert 'event.status === "COMPLETED"' not in application
    assert 'else if (event.status === "PUBLISHED")' in application
    assert "statusBadge(event.status" in application
    assert 'event.status === "PUBLISHED" && !soldOut' in application
