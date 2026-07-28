from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from intelliticket_backend.config import get_settings
from intelliticket_backend.main import app
from intelliticket_backend.repositories.ticket_history import TicketHistoryRepository


def _login(username: str, password: str) -> dict[str, str]:
    response = TestClient(app).post(
        "/api/v1/auth/login",
        json={"user_id": username, "password": password},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['token']}"}


@pytest.fixture
def permission_history(tmp_path, monkeypatch):
    db_path = tmp_path / "permissions.sqlite3"
    monkeypatch.setenv("TICKET_HISTORY_DB_PATH", str(db_path))
    monkeypatch.setenv("DATA_MODE", "mock")
    get_settings.cache_clear()
    yield TicketHistoryRepository(db_path)
    get_settings.cache_clear()


def test_ticket_data_endpoints_require_authentication() -> None:
    client = TestClient(app)

    assert client.get("/api/v1/tickets").status_code == 401
    assert client.get("/api/v1/tickets/mine").status_code == 401
    assert client.get("/api/v1/tickets/TCK-20260728-AAAAAAAA").status_code == 401
    assert client.get("/api/v1/knowledge/stats").status_code == 401


def test_employee_cannot_view_another_employees_ticket(permission_history) -> None:
    permission_history.save_pending_ticket(
        ticket_id="TCK-20260728-AAAAAAAA",
        text="员工 A 的工单",
        data_mode="mock",
        desk_id="ops",
        submitter="wangwu",
    )
    permission_history.save_pending_ticket(
        ticket_id="TCK-20260728-BBBBBBBB",
        text="员工 B 的工单",
        data_mode="mock",
        desk_id="ops",
        submitter="zhaoliu",
    )
    headers = _login("wangwu", "wangwu123456")
    client = TestClient(app)

    own = client.get("/api/v1/tickets/TCK-20260728-AAAAAAAA", headers=headers)
    other = client.get("/api/v1/tickets/TCK-20260728-BBBBBBBB", headers=headers)
    all_tickets = client.get("/api/v1/tickets", headers=headers)

    assert own.status_code == 200
    assert other.status_code == 403
    assert other.json()["error"]["code"] == "TICKET_ACCESS_DENIED"
    assert all_tickets.status_code == 403


def test_backend_data_mode_overrides_client_value(permission_history, monkeypatch) -> None:
    monkeypatch.setenv("DATA_MODE", "mock")
    get_settings.cache_clear()
    headers = _login("wangwu", "wangwu123456")

    response = TestClient(app).post(
        "/api/v1/tickets/submit",
        json={"text": "客户端尝试强制 real", "desk_id": "ops", "data_mode": "real"},
        headers=headers,
    )

    assert response.status_code == 200
    detail = permission_history.get_ticket(response.json()["ticket_id"])
    assert detail is not None
    assert detail.data_mode == "mock"


def test_websocket_rejects_anonymous_connection() -> None:
    client = TestClient(app)

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/api/v1/tickets/process/ws"):
            pass

    assert exc_info.value.code == 4401
