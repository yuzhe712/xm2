from __future__ import annotations

from fastapi.testclient import TestClient

from intelliticket_backend.main import app


def websocket_url(auth: dict[str, str]) -> str:
    token = auth["Authorization"].removeprefix("Bearer ")
    return f"/api/v1/tickets/process/ws?access_token={token}"


def test_legacy_processing_websocket_is_deprecated_without_starting_work(
    operator_auth,
) -> None:
    with TestClient(app).websocket_connect(websocket_url(operator_auth)) as websocket:
        event = websocket.receive_json()

    assert event["type"] == "error"
    assert event["error"]["code"] == "WS_PROCESSING_DEPRECATED"


def test_legacy_processing_websocket_still_requires_authentication() -> None:
    client = TestClient(app)

    try:
        with client.websocket_connect("/api/v1/tickets/process/ws"):
            raise AssertionError("anonymous websocket unexpectedly connected")
    except Exception as exc:
        assert getattr(exc, "code", None) == 4401
