from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select

from intelliticket_backend.api import tickets as tickets_api
from intelliticket_backend.config import get_settings
from intelliticket_backend.db import session_scope
from intelliticket_backend.main import app
from intelliticket_backend.models import NotificationDelivery
from intelliticket_backend.repositories.notifications import NotificationDeliveryRepository
from intelliticket_backend.services import worker_tasks
from intelliticket_backend.services.notifications import (
    NotificationPayload,
    NotificationResult,
)


def _login() -> dict[str, str]:
    response = TestClient(app).post(
        "/api/v1/auth/login",
        json={"user_id": "wangwu", "password": "wangwu123456"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['token']}"}


def _submit_ticket(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setattr(tickets_api, "dispatch_ai_run", lambda _run_id: "ai-task-id")
    response = TestClient(app).post(
        "/api/v1/tickets/submit",
        headers=_login(),
        json={
            "title": "异步通知测试",
            "text": "验证通知不阻塞请求线程。",
            "desk_id": "support",
            "priority": "P2",
        },
    )
    assert response.status_code == 200
    return response.json()["ticket_id"]


def _create_delivery(ticket_id: str) -> str:
    with session_scope() as session:
        delivery = NotificationDeliveryRepository(session).create(
            ticket_id=ticket_id,
            target="operator",
            event_type="ticket_created",
            payload=NotificationPayload(
                ticket_id=ticket_id,
                title="新工单",
                summary="请及时处理。",
                priority="P2",
                affected_service=None,
            ),
        )
        return delivery.id


def test_ticket_submission_persists_then_dispatches_notification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "dingtalk_enabled", True)
    monkeypatch.setattr(
        settings,
        "dingtalk_operator_webhook_url",
        SecretStr("https://oapi.dingtalk.com/robot/send?access_token=test"),
    )
    dispatched: list[str] = []
    monkeypatch.setattr(
        tickets_api,
        "dispatch_notification",
        lambda delivery_id: dispatched.append(delivery_id) or "notification-task-id",
    )
    monkeypatch.setattr(
        worker_tasks.DingTalkNotifier,
        "send",
        lambda *_args: pytest.fail("request handler must not send DingTalk synchronously"),
    )

    ticket_id = _submit_ticket(monkeypatch)

    with session_scope() as session:
        delivery = session.scalar(
            select(NotificationDelivery).where(NotificationDelivery.ticket_id == ticket_id)
        )
        assert delivery is not None
        assert delivery.status == "queued"
        assert delivery.attempts == 0
        assert dispatched == [delivery.id]


def test_notification_worker_records_success(monkeypatch: pytest.MonkeyPatch) -> None:
    ticket_id = _submit_ticket(monkeypatch)
    delivery_id = _create_delivery(ticket_id)
    settings = get_settings()
    monkeypatch.setattr(settings, "dingtalk_enabled", True)
    monkeypatch.setattr(
        settings,
        "dingtalk_operator_webhook_url",
        SecretStr("https://oapi.dingtalk.com/robot/send?access_token=test"),
    )
    monkeypatch.setattr(
        worker_tasks.DingTalkNotifier,
        "send",
        lambda *_args: NotificationResult(channel="dingtalk", status="sent"),
    )

    result = worker_tasks.send_dingtalk_notification.apply(
        args=[delivery_id], throw=True
    ).get()

    assert result["status"] == "sent"
    with session_scope() as session:
        delivery = NotificationDeliveryRepository(session).get(delivery_id)
        assert delivery is not None
        assert delivery.status == "sent"
        assert delivery.attempts == 1
        assert delivery.sent_at is not None


def test_notification_worker_retries_and_records_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ticket_id = _submit_ticket(monkeypatch)
    delivery_id = _create_delivery(ticket_id)
    settings = get_settings()
    monkeypatch.setattr(settings, "dingtalk_enabled", True)
    monkeypatch.setattr(settings, "notification_task_max_retries", 1)
    monkeypatch.setattr(settings, "notification_task_retry_backoff_seconds", 0)
    monkeypatch.setattr(
        settings,
        "dingtalk_operator_webhook_url",
        SecretStr("https://oapi.dingtalk.com/robot/send?access_token=test"),
    )
    monkeypatch.setattr(
        worker_tasks.DingTalkNotifier,
        "send",
        lambda *_args: NotificationResult(
            channel="dingtalk",
            status="failed",
            message="temporary DingTalk error",
        ),
    )

    with pytest.raises(RuntimeError, match="temporary DingTalk error"):
        worker_tasks.send_dingtalk_notification.run(delivery_id)

    with session_scope() as session:
        delivery = NotificationDeliveryRepository(session).get(delivery_id)
        assert delivery is not None
        assert delivery.status == "queued"
        assert delivery.attempts == 1
        assert delivery.last_error == "temporary DingTalk error"
