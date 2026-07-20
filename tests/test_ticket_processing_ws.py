from __future__ import annotations

from fastapi.testclient import TestClient

from intelliticket_backend.config import get_settings
from intelliticket_backend.main import app
from intelliticket_backend.repositories.ticket_history import TicketHistoryRepository

SAMPLE_TEXT = "线上支付服务出现超时告警，订单量从正常1000/min降到300/min"


def test_ticket_processing_websocket_support_desk_is_persisted(tmp_path, monkeypatch) -> None:
    get_settings.cache_clear()
    db_path = tmp_path / "history.sqlite3"
    monkeypatch.setenv("TICKET_HISTORY_DB_PATH", str(db_path))
    client = TestClient(app)

    with client.websocket_connect("/api/v1/tickets/process/ws") as websocket:
        websocket.send_json(
            {
                "type": "start",
                "request": {"text": SAMPLE_TEXT, "data_mode": "mock", "desk_id": "support"},
            }
        )
        assert websocket.receive_json()["type"] == "started"
        progress = []
        while True:
            event = websocket.receive_json()
            if event["type"] == "agent_progress":
                progress.append(event)
            if event["type"] == "completed":
                ticket_id = event["ticket_id"]
                completed = event
                break

    detail = TicketHistoryRepository(db_path).get_ticket(ticket_id)
    assert detail is not None
    assert detail.desk_id == "support"
    assert [event["step"] for event in progress] == [
        "support_intake",
        "support_kb_retrieval",
        "support_routing",
        "support_reply_suggestion",
    ]
    assert completed["result"]["classification"]["category"] == "support_request"
    get_settings.cache_clear()


def test_ticket_processing_websocket_streams_progress_and_completion() -> None:
    client = TestClient(app)

    with client.websocket_connect("/api/v1/tickets/process/ws") as websocket:
        websocket.send_json(
            {
                "type": "start",
                "request": {"text": SAMPLE_TEXT, "data_mode": "mock"},
            }
        )
        started = websocket.receive_json()
        assert started["type"] == "started"
        ticket_id = started["ticket_id"]
        run_id = started["run_id"]

        progress = []
        completed = None
        while True:
            event = websocket.receive_json()
            if event["type"] == "agent_progress":
                progress.append(event)
            elif event["type"] == "completed":
                completed = event
                break

        assert ticket_id.startswith("TCK-")
        assert run_id.startswith("RUN-")
        assert [event["step"] for event in progress] == [
            "ticket_intake",
            "context_retrieval",
            "diagnosis",
            "routing",
            "review",
            "report",
        ]
        assert completed is not None
        assert completed["ticket_id"] == ticket_id
        assert completed["run_id"] == run_id
        assert completed["result"]["classification"]["affected_service"] == "payment-service"
        evidence_ids = {
            item["evidence_id"] for item in completed["result"]["evidence"]
        }
        for event in progress:
            assert {ref["evidence_id"] for ref in event["evidence_refs"]} <= evidence_ids


def test_ticket_processing_websocket_rejects_invalid_start_message() -> None:
    client = TestClient(app)

    with client.websocket_connect("/api/v1/tickets/process/ws") as websocket:
        websocket.send_json({"type": "start", "request": {"text": "   ", "data_mode": "mock"}})
        event = websocket.receive_json()

    assert event["type"] == "error"
    assert event["error"]["code"] == "WS_INVALID_START_MESSAGE"


def test_ticket_processing_websocket_real_mode_completes_without_mock_evidence() -> None:
    client = TestClient(app)

    with client.websocket_connect("/api/v1/tickets/process/ws") as websocket:
        websocket.send_json(
            {
                "type": "start",
                "request": {"text": SAMPLE_TEXT, "data_mode": "real"},
            }
        )
        assert websocket.receive_json()["type"] == "started"
        while True:
            event = websocket.receive_json()
            if event["type"] == "completed":
                break

    assert event["result"]["data_mode"] == "real"
    assert {item["data_mode"] for item in event["result"]["evidence"]} == {"real"}
    assert all(
        not (item.get("trace_uri") or "").startswith("mock_data/")
        for item in event["result"]["evidence"]
    )


def test_ticket_processing_websocket_cancel_is_best_effort_after_start() -> None:
    client = TestClient(app)

    with client.websocket_connect("/api/v1/tickets/process/ws") as websocket:
        websocket.send_json(
            {
                "type": "start",
                "request": {"text": SAMPLE_TEXT, "data_mode": "mock"},
            }
        )
        assert websocket.receive_json()["type"] == "started"
        websocket.send_json({"type": "cancel", "reason": "test"})

        terminal = None
        for _ in range(10):
            event = websocket.receive_json()
            if event["type"] in {"cancelled", "completed", "error"}:
                terminal = event
                break

    assert terminal is not None
    assert terminal["type"] in {"cancelled", "completed"}
