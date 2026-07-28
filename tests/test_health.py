from __future__ import annotations

from fastapi.testclient import TestClient

from intelliticket_backend.api import health as health_api
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


def test_root_health_check_keeps_liveness_dependency_free() -> None:
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readiness_requires_database_and_redis(monkeypatch) -> None:
    monkeypatch.setattr(health_api, "_check_database", lambda: True)
    monkeypatch.setattr(health_api, "_check_redis", lambda: True)

    ready = TestClient(app).get("/ready")

    assert ready.status_code == 200
    assert ready.json() == {
        "status": "ready",
        "checks": {"database": True, "redis": True},
    }

    monkeypatch.setattr(health_api, "_check_redis", lambda: False)
    not_ready = TestClient(app).get("/ready")
    assert not_ready.status_code == 503
    assert not_ready.json()["checks"] == {"database": True, "redis": False}


def test_metrics_exposes_required_operational_series() -> None:
    client = TestClient(app)
    client.get("/api/v1/health")

    response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    content = response.text
    assert "intelliticket_http_requests_total" in content
    assert "intelliticket_http_request_duration_seconds" in content
    assert "intelliticket_ai_tasks_total" in content
    assert "intelliticket_ai_queue_length" in content
    assert "intelliticket_sla_overdue_tickets" in content
