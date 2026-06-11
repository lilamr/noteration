import pytest
from fastapi.testclient import TestClient

from noteration.api.server import app, get_core, set_vault_path
from noteration.core.vault_core import VaultCore

# Global API key for tests
TEST_API_KEY = "secret"


@pytest.fixture
def api_client(temp_vault):
    # Setup VaultCore
    core = VaultCore(temp_vault)
    # Configure API key in the config object
    core.config.set("api", "api_key", TEST_API_KEY)
    core.config.save()

    # Override the get_core dependency
    app.dependency_overrides[get_core] = lambda: core

    set_vault_path(temp_vault)
    with TestClient(app) as client:
        # Include API key in headers for all requests
        client.headers["X-API-Key"] = TEST_API_KEY
        yield client
    # Clean up override
    app.dependency_overrides.clear()


def test_api_notes_list_empty(api_client):
    response = api_client.get("/notes")
    assert response.status_code == 200
    assert response.json() == []


def test_api_note_create_and_get(api_client):
    # Create note
    payload = {"note_id": "api-test", "content": "# API Test\nHello"}
    response = api_client.post("/notes", json=payload)
    assert response.status_code == 200

    # Get note
    response = api_client.get("/notes/api-test")
    assert response.status_code == 200
    data = response.json()
    assert data["note_id"] == "api-test"
    assert "API Test" in data["content"]


def test_api_search(api_client):
    # Search on empty vault or with content
    response = api_client.get("/search?q=test")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_api_graph_stats(api_client):
    response = api_client.get("/graph/stats")
    assert response.status_code == 200
    data = response.json()
    assert "nodes" in data
    assert "links" in data


def test_api_path_traversal_attempts(api_client):
    # 1. Attempt to read outside vault
    response = api_client.get("/notes/../notes/../../../../etc/passwd")
    # Should return 404 because file doesn't exist within the vault
    assert response.status_code == 404

    # 2. Attempt to create note outside vault
    payload = {"note_id": "../../../outside", "content": "malicious"}
    response = api_client.post("/notes", json=payload)
    # Should be rejected due to path safety check
    assert response.status_code == 400

    # 3. Attempt to update note outside vault
    payload = {"note_id": "../../../outside", "content": "malicious"}
    response = api_client.put("/notes/../outside", json=payload)
    assert response.status_code == 404


def test_api_key_unauthorized(temp_vault):
    # Setup VaultCore without API key
    core = VaultCore(temp_vault)
    # Ensure no API key is set
    core.config.set("api", "api_key", "")
    core.config.save()

    # Override the get_core dependency
    app.dependency_overrides[get_core] = lambda: core

    set_vault_path(temp_vault)
    with TestClient(app) as client:
        # Request without key
        response = client.get("/notes")
        # Should return 503 as it is unconfigured
        assert response.status_code == 503
    app.dependency_overrides.clear()
