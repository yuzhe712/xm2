from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from intelliticket_backend.api import health as health_api
from intelliticket_backend.config import get_settings
from intelliticket_backend.db import session_scope
from intelliticket_backend.errors import AppError
from intelliticket_backend.main import app
from intelliticket_backend.models import AiRun, NotificationDelivery, TicketEvent
from intelliticket_backend.services.ai_pipeline import AiPipeline
from intelliticket_backend.services.worker_tasks import (
    process_ai_run,
    send_dingtalk_notification,
)


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
            "title": "P5 failure-path ticket",
            "text": "The payment API is timing out and needs manual investigation.",
            "desk_id": "ops",
        },
    )
    assert response.status_code == 200
    return response.json()


def test_repeated_llm_timeout_still_allows_manual_close(monkeypatch) -> None:
    monkeypatch.setenv("AI_TASK_MAX_RETRIES", "0")
    get_settings.cache_clear()
    employee = _login("wangwu", "wangwu123456")
    operator = _login("zhangsan", "zhangsan123")
    ticket = _submit(employee)

    def timeout(*_args, **_kwargs):
        raise AppError("LLM_TIMEOUT", "provider timed out", 504, {})

    monkeypatch.setattr(AiPipeline, "run", timeout)
    failed = process_ai_run.apply(args=[ticket["ai_run_id"]], throw=True).get()
    assert failed["status"] == "failed"
    assert failed["error_code"] == "LLM_TIMEOUT"

    client = TestClient(app)
    claimed = client.post(
        f"/api/v1/tickets/{ticket['ticket_id']}/claim",
        headers=operator,
        json={"version": 1},
    )
    assert claimed.status_code == 200
    reply = client.post(
        f"/api/v1/tickets/{ticket['ticket_id']}/comments",
        headers=operator,
        json={
            "version": claimed.json()["version"],
            "visibility": "public",
            "body": "AI is unavailable; manual investigation has started.",
        },
    )
    assert reply.status_code == 201
    current = client.get(
        f"/api/v1/tickets/{ticket['ticket_id']}/workflow",
        headers=operator,
    ).json()
    resolved = client.post(
        f"/api/v1/tickets/{ticket['ticket_id']}/resolve",
        headers=operator,
        json={
            "version": current["version"],
            "resolution_summary": "Manual remediation completed.",
            "root_cause": "A stale upstream connection pool.",
            "fix_action": "Recycled the pool and adjusted limits.",
            "verification": "Health checks and payment probes passed.",
        },
    )
    assert resolved.status_code == 200
    closed = client.post(
        f"/api/v1/tickets/{ticket['ticket_id']}/confirm",
        headers=employee,
        json={"version": resolved.json()["version"]},
    )
    assert closed.status_code == 200
    assert closed.json()["status"] == "closed"
    get_settings.cache_clear()


def test_redis_dispatch_failure_is_persisted_without_losing_ticket(monkeypatch) -> None:
    def unavailable(*_args, **_kwargs):
        raise ConnectionError("redis unavailable")

    monkeypatch.setattr(process_ai_run, "apply_async", unavailable)
    monkeypatch.setattr(send_dingtalk_notification, "apply_async", unavailable)
    employee = _login("wangwu", "wangwu123456")
    ticket = _submit(employee)

    assert ticket["ai_status"] == "failed"
    detail = TestClient(app).get(
        f"/api/v1/tickets/{ticket['ticket_id']}/workflow",
        headers=employee,
    )
    assert detail.status_code == 200
    assert detail.json()["status"] == "pending"
    with session_scope() as session:
        run = session.get(AiRun, ticket["ai_run_id"])
        assert run is not None
        assert run.status == "failed"
        assert run.error_code == "AI_QUEUE_UNAVAILABLE"
        delivery = session.scalar(
            select(NotificationDelivery).where(
                NotificationDelivery.ticket_id == ticket["ticket_id"]
            )
        )
        assert delivery is not None
        assert delivery.status == "failed"

    monkeypatch.setattr(health_api, "_check_database", lambda: True)
    monkeypatch.setattr(health_api, "_check_redis", lambda: False)
    assert TestClient(app).get("/health").status_code == 200
    assert TestClient(app).get("/ready").status_code == 503


def test_worker_restart_recovery_is_idempotent(monkeypatch) -> None:
    employee = _login("wangwu", "wangwu123456")
    operator = _login("zhangsan", "zhangsan123")
    ticket = _submit(employee)
    with session_scope() as session:
        run = session.get(AiRun, ticket["ai_run_id"])
        assert run is not None
        run.status = "running"
        run.stage = "retrieve_diagnose"
        run.heartbeat_at = datetime.now(UTC) - timedelta(hours=1)

    dispatched: list[str] = []
    monkeypatch.setattr(
        "intelliticket_backend.api.ai_runs.dispatch_ai_run",
        lambda run_id: dispatched.append(run_id),
    )
    recovered = TestClient(app).post(
        "/api/v1/ai-runs/recover-stale",
        headers=operator,
    )
    assert recovered.status_code == 200
    assert recovered.json()["recovered_run_ids"] == [ticket["ai_run_id"]]
    assert dispatched == [ticket["ai_run_id"]]

    first = process_ai_run.apply(args=[ticket["ai_run_id"]], throw=True).get()
    second = process_ai_run.apply(args=[ticket["ai_run_id"]], throw=True).get()
    assert first["status"] == second["status"] == "completed"
    assert first["result"] == second["result"]
    with session_scope() as session:
        completed_events = session.scalar(
            select(func.count())
            .select_from(TicketEvent)
            .where(
                TicketEvent.ticket_id == ticket["ticket_id"],
                TicketEvent.event_type == "ai_triage_completed",
            )
        )
        assert completed_events == 1


def test_concurrent_duplicate_claim_has_one_winner() -> None:
    employee = _login("wangwu", "wangwu123456")
    operators = [
        _login("zhangsan", "zhangsan123"),
        _login("lisi", "lisi12345678"),
    ]
    ticket = _submit(employee)
    barrier = Barrier(2)

    def claim(headers: dict[str, str]):
        barrier.wait(timeout=5)
        return TestClient(app).post(
            f"/api/v1/tickets/{ticket['ticket_id']}/claim",
            headers=headers,
            json={"version": 1},
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(claim, operators))

    assert sorted(response.status_code for response in responses) == [200, 409]
    conflict = next(response for response in responses if response.status_code == 409)
    assert conflict.json()["error"]["code"] == "TICKET_VERSION_CONFLICT"


def test_employee_cannot_cross_ticket_or_role_boundaries() -> None:
    owner = _login("wangwu", "wangwu123456")
    other = _login("zhaoliu", "zhaoliu123456")
    ticket = _submit(owner)
    client = TestClient(app)

    assert (
        client.get(
            f"/api/v1/tickets/{ticket['ticket_id']}/workflow",
            headers=other,
        ).status_code
        == 403
    )
    assert (
        client.get(
            f"/api/v1/tickets/{ticket['ticket_id']}/attachments",
            headers=other,
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/v1/tickets/{ticket['ticket_id']}/claim",
            headers=owner,
            json={"version": 1},
        ).status_code
        == 403
    )
    assert client.get("/api/v1/users", headers=owner).status_code == 403
