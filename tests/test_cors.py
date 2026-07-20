from __future__ import annotations

from fastapi.testclient import TestClient

from intelliticket_backend.main import app


def test_local_vite_origin_is_allowed_for_rest_preflight() -> None:
    client = TestClient(app)

    response = client.options(
        "/api/v1/tickets/process",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"


def test_unrelated_origin_is_not_allowed_for_rest_preflight() -> None:
    client = TestClient(app)

    response = client.options(
        "/api/v1/tickets/process",
        headers={
            "Origin": "https://example.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers
