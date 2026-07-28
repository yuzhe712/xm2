from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from intelliticket_backend.config import get_settings
from intelliticket_backend.db import session_scope
from intelliticket_backend.errors import AppError
from intelliticket_backend.main import app
from intelliticket_backend.models import AiRun, Ticket
from intelliticket_backend.repositories.ai_runs import AiRunRepository
from intelliticket_backend.services.ai_pipeline import AiPipeline
from intelliticket_backend.services.worker_tasks import process_ai_run


def _login(username: str, password: str) -> dict[str, str]:
    response = TestClient(app).post(
        "/api/v1/auth/login",
        json={"user_id": username, "password": password},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['token']}"}


def _submit(headers: dict[str, str]) -> dict:
    response = TestClient(app).post(
        "/api/v1/tickets/submit",
        headers=headers,
        json={
            "title": "支付服务超时",
            "text": "线上支付服务出现超时告警，订单量从正常1000/min降到300/min",
            "desk_id": "ops",
        },
    )
    assert response.status_code == 200
    return response.json()


def test_submit_commits_queued_run_before_dispatch(monkeypatch) -> None:
    employee = _login("wangwu", "wangwu123456")
    observed: dict[str, str] = {}

    def fake_dispatch(run_id: str) -> str:
        with session_scope() as session:
            run = session.get(AiRun, run_id)
            assert run is not None
            assert run.status == "queued"
            ticket = session.get(Ticket, run.ticket_id)
            assert ticket is not None
            observed["ticket_id"] = ticket.ticket_id
        return "task-test"

    monkeypatch.setattr(
        "intelliticket_backend.api.tickets.dispatch_ai_run", fake_dispatch
    )
    payload = _submit(employee)

    assert payload["ai_status"] == "queued"
    assert payload["ai_run_id"].startswith("RUN-")
    assert observed["ticket_id"] == payload["ticket_id"]


def test_worker_runs_exactly_three_stages_and_persists_audit_data() -> None:
    employee = _login("wangwu", "wangwu123456")
    payload = _submit(employee)

    result = process_ai_run.apply(args=[payload["ai_run_id"]], throw=True).get()

    assert result["status"] == "completed"
    assert result["progress"] == 100
    assert [stage["name"] for stage in result["result"]["stages"]] == [
        "triage",
        "retrieve_diagnose",
        "quality_gate",
    ]
    assert result["result"]["quality_gate"]["requires_human_review"] is True
    assert result["pipeline_version"] == get_settings().ai_pipeline_version
    assert result["prompt_version"] == get_settings().ai_prompt_version
    assert result["duration_ms"] is not None
    assert result["prompt_tokens"] == 0
    assert result["completion_tokens"] == 0
    evidence_ids = {item["evidence_id"] for item in result["evidence"]}
    assert set(result["result"]["quality_gate"]["evidence_ids"]) <= evidence_ids

    with session_scope() as session:
        ticket = session.get(Ticket, payload["ticket_id"])
        assert ticket is not None
        assert ticket.ticket_status == "open"
        assert ticket.priority == "P1"


def test_ai_failure_does_not_block_manual_ticket_flow(monkeypatch) -> None:
    monkeypatch.setenv("AI_TASK_MAX_RETRIES", "0")
    get_settings.cache_clear()
    employee = _login("wangwu", "wangwu123456")
    payload = _submit(employee)

    def fail_pipeline(*_args, **_kwargs):
        raise AppError("LLM_RETRY_EXHAUSTED", "provider unavailable", 502, {})

    monkeypatch.setattr(AiPipeline, "run", fail_pipeline)
    result = process_ai_run.apply(args=[payload["ai_run_id"]], throw=True).get()

    assert result["status"] == "failed"
    assert result["error_code"] == "LLM_RETRY_EXHAUSTED"
    with session_scope() as session:
        ticket = session.get(Ticket, payload["ticket_id"])
        assert ticket is not None
        assert ticket.ticket_status == "pending"
    get_settings.cache_clear()


def test_stale_run_recovery_requeues_task(monkeypatch) -> None:
    employee = _login("wangwu", "wangwu123456")
    operator = _login("zhangsan", "zhangsan123")
    payload = _submit(employee)
    with session_scope() as session:
        run = session.get(AiRun, payload["ai_run_id"])
        assert run is not None
        run.status = "running"
        run.stage = "retrieve_diagnose"
        run.heartbeat_at = datetime.now(UTC) - timedelta(hours=1)

    dispatched: list[str] = []
    monkeypatch.setattr(
        "intelliticket_backend.api.ai_runs.dispatch_ai_run",
        lambda run_id: dispatched.append(run_id),
    )
    response = TestClient(app).post(
        "/api/v1/ai-runs/recover-stale", headers=operator
    )

    assert response.status_code == 200
    assert response.json()["recovered_run_ids"] == [payload["ai_run_id"]]
    assert dispatched == [payload["ai_run_id"]]
    with session_scope() as session:
        run = session.get(AiRun, payload["ai_run_id"])
        assert run is not None
        assert run.status == "queued"
        assert run.retry_count == 1


def test_manual_rerun_and_human_decision_are_persisted(monkeypatch) -> None:
    employee = _login("wangwu", "wangwu123456")
    operator = _login("zhangsan", "zhangsan123")
    payload = _submit(employee)
    completed = process_ai_run.apply(args=[payload["ai_run_id"]], throw=True).get()

    decision = TestClient(app).post(
        f"/api/v1/ai-runs/{completed['id']}/decision",
        headers=operator,
        json={"decision": "accepted", "note": "证据充分，接受建议"},
    )
    assert decision.status_code == 200
    assert decision.json()["decision"] == "accepted"
    assert decision.json()["decided_by"]

    dispatched: list[str] = []
    monkeypatch.setattr(
        "intelliticket_backend.api.ai_runs.dispatch_ai_run",
        lambda run_id: dispatched.append(run_id),
    )
    rerun = TestClient(app).post(
        f"/api/v1/tickets/{payload['ticket_id']}/ai-runs",
        headers=operator,
    )
    assert rerun.status_code == 202
    assert rerun.json()["id"] != completed["id"]
    assert rerun.json()["status"] == "queued"
    assert dispatched == [rerun.json()["id"]]


def test_ai_run_websocket_subscribes_to_persisted_terminal_state() -> None:
    employee = _login("wangwu", "wangwu123456")
    payload = _submit(employee)
    process_ai_run.apply(args=[payload["ai_run_id"]], throw=True).get()
    token = employee["Authorization"].removeprefix("Bearer ")

    with TestClient(app).websocket_connect(
        f"/api/v1/ai-runs/{payload['ai_run_id']}/ws?access_token={token}"
    ) as websocket:
        event = websocket.receive_json()

    assert event["type"] == "ai_run_status"
    assert event["run"]["status"] == "completed"


def test_repository_retry_state_is_finite_and_auditable() -> None:
    employee = _login("wangwu", "wangwu123456")
    payload = _submit(employee)
    with session_scope() as session:
        repository = AiRunRepository(session)
        repository.mark_running(payload["ai_run_id"])
        repository.fail(
            payload["ai_run_id"],
            "LLM_TIMEOUT",
            "retry later",
            terminal=False,
        )
        run = repository.get(payload["ai_run_id"])
        assert run is not None
        assert run.status == "queued"
        assert run.stage == "retrying"
        assert run.retry_count == 1
