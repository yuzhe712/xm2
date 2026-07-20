from __future__ import annotations

from fastapi.testclient import TestClient

from intelliticket_backend.main import app


def test_health_check_returns_explicit_mock_mode() -> None:
    client = TestClient(app)

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "intelliticket-backend",
        "version": "0.1.0",
        "data_mode": "mock",
    }
