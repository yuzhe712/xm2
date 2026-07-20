from __future__ import annotations

from fastapi.testclient import TestClient

from intelliticket_backend.main import app


def test_openapi_includes_desks_catalog_and_knowledge() -> None:
    client = TestClient(app)

    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/v1/desks/{desk_id}/catalog" in paths
    assert "/api/v1/desks/{desk_id}/knowledge" in paths


def test_get_ops_catalog_returns_mock_records() -> None:
    client = TestClient(app)

    response = client.get("/api/v1/desks/ops/catalog")

    assert response.status_code == 200
    payload = response.json()
    assert payload["desk_id"] == "ops"
    assert payload["data_mode"] == "mock"
    assert payload["items"]
    assert {item["desk_scope"] for item in payload["items"]} == {"ops"}
    assert {item["data_mode"] for item in payload["items"]} == {"mock"}
    assert payload["items"][0]["evidence_id"]


def test_get_support_catalog_returns_only_support_records() -> None:
    client = TestClient(app)

    response = client.get("/api/v1/desks/support/catalog")

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"]
    assert {item["desk_scope"] for item in payload["items"]} == {"support"}
    assert any(item["id"] == "account-permission" for item in payload["items"])


def test_get_ops_knowledge_returns_mock_records() -> None:
    client = TestClient(app)

    response = client.get("/api/v1/desks/ops/knowledge")

    assert response.status_code == 200
    payload = response.json()
    assert payload["desk_id"] == "ops"
    assert payload["items"]
    assert {item["desk_scope"] for item in payload["items"]} == {"ops"}
    assert payload["items"][0]["actions"]


def test_get_unknown_desk_returns_validation_error() -> None:
    client = TestClient(app)

    response = client.get("/api/v1/desks/unknown/catalog")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
