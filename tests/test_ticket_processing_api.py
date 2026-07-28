from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from intelliticket_backend.config import get_settings
from intelliticket_backend.main import app
from intelliticket_backend.repositories.ticket_history import TicketHistoryRepository

SAMPLE_TEXT = "线上支付服务出现超时告警，订单量从正常1000/min降到300/min"


@pytest.fixture
def history_db(tmp_path, monkeypatch):
    get_settings.cache_clear()
    db_path = tmp_path / "history.sqlite3"
    monkeypatch.setenv("TICKET_HISTORY_DB_PATH", str(db_path))
    yield db_path
    get_settings.cache_clear()


@pytest.fixture
def operator_auth() -> dict[str, str]:
    """Login as operator (zhangsan) and return Authorization header."""
    client = TestClient(app)
    resp = client.post(
        "/api/v1/auth/login",
        json={"user_id": "zhangsan", "password": "zhangsan123"},
    )
    assert resp.status_code == 200, f"Login failed: {resp.json()}"
    token = resp.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_openapi_includes_ticket_process_contract() -> None:
    client = TestClient(app)

    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/v1/tickets/process" in paths
    assert "/api/v1/tickets" in paths
    assert "/api/v1/tickets/{ticket_id}" in paths
    assert "patch" in paths["/api/v1/tickets/{ticket_id}"]
    process_post = paths["/api/v1/tickets/process"]["post"]
    assert process_post["requestBody"]
    assert process_post["responses"]["200"]


def test_process_ticket_api_returns_complete_response(history_db, operator_auth) -> None:
    client = TestClient(app)

    response = client.post(
        "/api/v1/tickets/process",
        json={"text": SAMPLE_TEXT, "data_mode": "mock"},
        headers=operator_auth,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["ticket_id"].startswith("TCK-")
    assert data["run_id"].startswith("RUN-")
    assert data["data_mode"] == "mock"
    assert data["classification"]["affected_service"] == "payment-service"
    assert data["classification"]["priority"] == "P1"
    assert data["context"]["service"]["owner_team"] == "支付系统运维组"
    assert data["diagnosis"]["candidate_root_causes"]
    assert data["routing"]["recommended_actions"]
    assert data["report"]["recommendations"]
    assert len(data["agent_trace"]) == 6

    evidence_ids = {item["evidence_id"] for item in data["evidence"]}
    intake_trace = next(item for item in data["agent_trace"] if item["step"] == "ticket_intake")
    assert "ticket_intake_agent" in intake_trace["summary"]
    assert set(intake_trace["evidence_ids"]) <= evidence_ids
    context_trace = next(
        item for item in data["agent_trace"] if item["step"] == "context_retrieval"
    )
    assert "context_retrieval_agent" in context_trace["summary"]
    assert set(context_trace["evidence_ids"]) <= evidence_ids
    routing_trace = next(item for item in data["agent_trace"] if item["step"] == "routing")
    assert "routing_agent" in routing_trace["summary"]
    assert set(routing_trace["evidence_ids"]) <= evidence_ids
    report_trace = next(item for item in data["agent_trace"] if item["step"] == "report")
    assert "report_agent" in report_trace["summary"]
    assert set(report_trace["evidence_ids"]) <= evidence_ids

    for cause in data["diagnosis"]["candidate_root_causes"]:
        assert set(cause["evidence_ids"]) <= evidence_ids
    for action in data["routing"]["recommended_actions"]:
        assert set(action["evidence_ids"]) <= evidence_ids


def test_empty_ticket_text_returns_validation_error(operator_auth) -> None:
    client = TestClient(app)

    response = client.post(
        "/api/v1/tickets/process",
        json={"text": "   ", "data_mode": "mock"},
        headers=operator_auth,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_real_data_mode_returns_real_evidence_without_mock_fallback(
    history_db, operator_auth, monkeypatch
) -> None:
    monkeypatch.setenv("DATA_MODE", "real")
    get_settings.cache_clear()
    client = TestClient(app)

    response = client.post(
        "/api/v1/tickets/process",
        json={"text": "线上支付服务出现超时告警", "data_mode": "real"},
        headers=operator_auth,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data_mode"] == "real"
    assert {item["data_mode"] for item in payload["evidence"]} == {"real"}
    assert all(
        not (item.get("trace_uri") or "").startswith("mock_data/")
        for item in payload["evidence"]
    )
    get_settings.cache_clear()


def test_ticket_history_list_and_detail_return_persisted_ticket(history_db, operator_auth) -> None:
    client = TestClient(app)
    process_response = client.post(
        "/api/v1/tickets/process",
        json={"text": SAMPLE_TEXT, "data_mode": "mock"},
        headers=operator_auth,
    )
    ticket_id = process_response.json()["ticket_id"]

    list_response = client.get("/api/v1/tickets", headers=operator_auth)
    detail_response = client.get(f"/api/v1/tickets/{ticket_id}", headers=operator_auth)

    assert list_response.status_code == 200
    listing = list_response.json()
    assert listing["total"] == 1
    assert listing["items"][0]["ticket_id"] == ticket_id
    assert listing["items"][0]["desk_id"] == "ops"
    assert listing["items"][0]["data_mode"] == "mock"
    assert listing["items"][0]["status"] == "completed"
    assert listing["items"][0]["ticket_status"] == "in_progress"
    assert listing["items"][0]["assigned_team"] == "支付系统运维组"
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["ticket_id"] == ticket_id
    assert detail["desk_id"] == "ops"
    assert detail["ticket_status"] == "in_progress"
    assert detail["latest_run"]["response"]["ticket_id"] == ticket_id
    assert detail["latest_run"]["response"]["ops_result"]["assigned_team"] == "支付系统运维组"
    assert detail["latest_run"]["evidence"]
    assert detail["latest_run"]["evidence"][0]["data_mode"] == "mock"
    assert detail["latest_run"]["agent_runs"]
    assert detail["latest_run"]["supervisor_decisions"][-1]["next_agent"] == "finish"


def test_failed_processing_is_persisted_in_history(history_db, monkeypatch, operator_auth) -> None:
    monkeypatch.setenv("ORCHESTRATOR_MAX_STEPS", "1")
    get_settings.cache_clear()
    client = TestClient(app)

    response = client.post(
        "/api/v1/tickets/process",
        json={"text": SAMPLE_TEXT, "data_mode": "mock"},
        headers=operator_auth,
    )

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "ORCHESTRATOR_STEP_LIMIT_EXCEEDED"
    listing = client.get("/api/v1/tickets", headers=operator_auth).json()
    ticket_id = listing["items"][0]["ticket_id"]
    detail = client.get(f"/api/v1/tickets/{ticket_id}", headers=operator_auth).json()

    assert listing["total"] == 1
    assert listing["items"][0]["status"] == "failed"
    assert listing["items"][0]["ticket_status"] == "open"
    assert detail["latest_run"]["status"] == "failed"
    assert detail["ticket_status"] == "open"
    assert detail["latest_run"]["response"] is None
    assert detail["latest_run"]["error"]["code"] == "ORCHESTRATOR_STEP_LIMIT_EXCEEDED"
    assert "evidence" in detail["latest_run"]


def test_validation_error_does_not_create_history_row(history_db, operator_auth) -> None:
    client = TestClient(app)

    response = client.post(
        "/api/v1/tickets/process",
        json={"text": "   ", "data_mode": "mock"},
        headers=operator_auth,
    )

    assert response.status_code == 422
    assert TicketHistoryRepository(history_db).list_tickets(limit=20, offset=0).total == 0


def test_ticket_history_list_paginates(history_db, operator_auth) -> None:
    client = TestClient(app)
    for text in [SAMPLE_TEXT, "未知系统出现异常告警"]:
        response = client.post(
            "/api/v1/tickets/process",
            json={"text": text, "data_mode": "mock"},
            headers=operator_auth,
        )
        assert response.status_code == 200

    response = client.get("/api/v1/tickets?limit=1&offset=1", headers=operator_auth)

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert len(payload["items"]) == 1


def test_ticket_history_list_filters_by_desk_id(history_db, operator_auth) -> None:
    client = TestClient(app)
    ops_response = client.post(
        "/api/v1/tickets/process",
        json={"text": SAMPLE_TEXT, "data_mode": "mock", "desk_id": "ops"},
        headers=operator_auth,
    )
    support_response = client.post(
        "/api/v1/tickets/process",
        json={"text": SAMPLE_TEXT, "data_mode": "mock", "desk_id": "support"},
        headers=operator_auth,
    )

    assert ops_response.status_code == 200
    assert support_response.status_code == 200
    support_payload = support_response.json()
    assert [item["step"] for item in support_payload["agent_trace"]] == [
        "support_intake",
        "support_kb_retrieval",
        "support_routing",
        "support_reply_suggestion",
    ]
    assert support_payload["classification"]["category"] == "support_request"
    assert support_payload["routing"]["recommended_team"] == "内部支持服务台"
    assert support_payload["support_result"]["recommended_team"] == "内部支持服务台"
    assert support_payload["ops_result"] is None
    ops_listing = client.get("/api/v1/tickets?desk_id=ops", headers=operator_auth).json()
    support_listing = client.get(
        "/api/v1/tickets?desk_id=support", headers=operator_auth
    ).json()
    all_listing = client.get("/api/v1/tickets", headers=operator_auth).json()

    assert ops_listing["total"] == 1
    assert ops_listing["items"][0]["desk_id"] == "ops"
    assert support_listing["total"] == 1
    assert support_listing["items"][0]["desk_id"] == "support"
    assert all_listing["total"] == 2


def test_patch_support_reply_draft_saves_editable_local_state(history_db, operator_auth) -> None:
    client = TestClient(app)
    process_response = client.post(
        "/api/v1/tickets/process",
        json={
            "text": "新入职同事无法访问支付服务只读监控面板，需要开通权限",
            "data_mode": "mock",
            "desk_id": "support",
        },
        headers=operator_auth,
    )
    ticket_id = process_response.json()["ticket_id"]
    run_id = process_response.json()["run_id"]
    evidence_id = process_response.json()["evidence"][0]["evidence_id"]

    response = client.patch(
        f"/api/v1/tickets/{ticket_id}/support-reply-draft",
        json={
            "reply_text": "已确认申请信息，请补充所属团队后继续处理。",
            "report_summary": "人工编辑后的支持回复摘要。",
            "evidence_ids": [evidence_id],
            "status": "approved",
            "editor": "local-operator",
        },
        headers=operator_auth,
    )

    assert response.status_code == 200
    payload = response.json()
    draft = payload["support_reply_draft"]
    assert draft["ticket_id"] == ticket_id
    assert draft["run_id"] == run_id
    assert draft["reply_text"] == "已确认申请信息，请补充所属团队后继续处理。"
    assert draft["report_summary"] == "人工编辑后的支持回复摘要。"
    assert draft["evidence_ids"] == [evidence_id]
    assert draft["status"] == "approved"
    assert draft["approved_at"]
    assert draft["sent_at"] is None
    assert payload["latest_run"]["run_id"] == run_id


def test_patch_support_reply_draft_rejects_unknown_evidence(history_db, operator_auth) -> None:
    client = TestClient(app)
    process_response = client.post(
        "/api/v1/tickets/process",
        json={"text": "无法访问监控面板", "data_mode": "mock", "desk_id": "support"},
        headers=operator_auth,
    )
    ticket_id = process_response.json()["ticket_id"]

    response = client.patch(
        f"/api/v1/tickets/{ticket_id}/support-reply-draft",
        json={
            "reply_text": "请补充信息。",
            "evidence_ids": ["ev_unknown"],
            "status": "draft",
        },
        headers=operator_auth,
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "SUPPORT_DRAFT_EVIDENCE_UNKNOWN"


def test_patch_support_reply_draft_rejects_ops_ticket(history_db, operator_auth) -> None:
    client = TestClient(app)
    process_response = client.post(
        "/api/v1/tickets/process",
        json={"text": SAMPLE_TEXT, "data_mode": "mock", "desk_id": "ops"},
        headers=operator_auth,
    )
    ticket_id = process_response.json()["ticket_id"]

    response = client.patch(
        f"/api/v1/tickets/{ticket_id}/support-reply-draft",
        json={"reply_text": "ops 不允许", "evidence_ids": [], "status": "draft"},
        headers=operator_auth,
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "SUPPORT_DRAFT_NOT_ALLOWED"


def test_preview_reprocess_ticket_does_not_update_latest_run(history_db, operator_auth) -> None:
    client = TestClient(app)
    process_response = client.post(
        "/api/v1/tickets/process",
        json={"text": SAMPLE_TEXT, "data_mode": "mock", "desk_id": "ops"},
        headers=operator_auth,
    )
    ticket_id = process_response.json()["ticket_id"]
    original_run_id = process_response.json()["run_id"]

    response = client.post(
        f"/api/v1/tickets/{ticket_id}/reprocess/preview",
        headers=operator_auth,
    )
    detail = client.get(f"/api/v1/tickets/{ticket_id}", headers=operator_auth).json()

    assert response.status_code == 200
    payload = response.json()
    assert payload["ticket_id"] == ticket_id
    assert payload["run_id"] != original_run_id
    assert detail["latest_run"]["run_id"] == original_run_id


def test_reprocess_ticket_updates_latest_run_for_same_ticket(history_db, operator_auth) -> None:
    client = TestClient(app)
    process_response = client.post(
        "/api/v1/tickets/process",
        json={"text": SAMPLE_TEXT, "data_mode": "mock", "desk_id": "ops"},
        headers=operator_auth,
    )
    ticket_id = process_response.json()["ticket_id"]
    original_run_id = process_response.json()["run_id"]

    response = client.post(
        f"/api/v1/tickets/{ticket_id}/reprocess",
        headers=operator_auth,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ticket_id"] == ticket_id
    assert payload["latest_run"]["status"] == "completed"
    assert payload["latest_run"]["run_id"] != original_run_id
    assert payload["latest_run"]["response"]["ticket_id"] == ticket_id
    assert payload["latest_run"]["response"]["run_id"] == payload["latest_run"]["run_id"]


def test_reprocess_unknown_ticket_returns_404(history_db, operator_auth) -> None:
    client = TestClient(app)

    response = client.post(
        "/api/v1/tickets/TCK-20260715-FFFFFFFF/reprocess",
        headers=operator_auth,
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "TICKET_NOT_FOUND"


def test_generic_patch_cannot_change_business_status(
    history_db, operator_auth
) -> None:
    client = TestClient(app)
    process_response = client.post(
        "/api/v1/tickets/process",
        json={"text": SAMPLE_TEXT, "data_mode": "mock"},
        headers=operator_auth,
    )
    ticket_id = process_response.json()["ticket_id"]
    response = client.patch(
        f"/api/v1/tickets/{ticket_id}",
        json={
            "ticket_status": "closed",
            "resolution_summary": "已按 AI 建议完成处理。",
        },
        headers=operator_auth,
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "TICKET_COMMAND_REQUIRED"


def test_patch_unknown_ticket_returns_404(history_db, operator_auth) -> None:
    client = TestClient(app)

    response = client.patch(
        "/api/v1/tickets/TCK-20260715-FFFFFFFF",
        json={"ticket_status": "closed"},
        headers=operator_auth,
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "TICKET_NOT_FOUND"


def test_invalid_desk_id_returns_validation_error(history_db, operator_auth) -> None:
    client = TestClient(app)

    response = client.get("/api/v1/tickets?desk_id=unknown", headers=operator_auth)

    assert response.status_code == 422


def test_ticket_history_detail_validates_ticket_id(history_db, operator_auth) -> None:
    client = TestClient(app)

    response = client.get("/api/v1/tickets/TCK-001", headers=operator_auth)

    assert response.status_code == 422


def test_ticket_history_detail_returns_404_for_unknown_ticket(history_db, operator_auth) -> None:
    client = TestClient(app)

    response = client.get(
        "/api/v1/tickets/TCK-20260715-FFFFFFFF", headers=operator_auth
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "TICKET_NOT_FOUND"
