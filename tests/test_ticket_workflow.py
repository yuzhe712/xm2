from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from intelliticket_backend.db import session_scope
from intelliticket_backend.main import app
from intelliticket_backend.models import Ticket, User


def _login(username: str, password: str) -> dict[str, str]:
    response = TestClient(app).post(
        "/api/v1/auth/login",
        json={"user_id": username, "password": password},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['token']}"}


def _submit(headers: dict[str, str], *, priority: str = "P3") -> dict:
    response = TestClient(app).post(
        "/api/v1/tickets/submit",
        headers=headers,
        json={
            "title": "支付服务访问异常",
            "text": "员工无法访问支付服务，请人工协助处理。",
            "desk_id": "ops",
            "priority": priority,
        },
    )
    assert response.status_code == 200
    return response.json()


def _triage_and_claim(
    ticket_id: str,
    operator_headers: dict[str, str],
) -> dict:
    client = TestClient(app)
    triaged = client.post(
        f"/api/v1/tickets/{ticket_id}/triage-complete",
        headers=operator_headers,
        json={"version": 1, "category": "access", "priority": "P2"},
    )
    assert triaged.status_code == 200
    claimed = client.post(
        f"/api/v1/tickets/{ticket_id}/claim",
        headers=operator_headers,
        json={"version": triaged.json()["version"]},
    )
    assert claimed.status_code == 200
    return claimed.json()


def test_manual_ticket_flow_completes_without_ai_and_hides_internal_notes() -> None:
    client = TestClient(app)
    employee = _login("wangwu", "wangwu123456")
    operator = _login("zhangsan", "zhangsan123")
    submitted = _submit(employee)
    ticket_id = submitted["ticket_id"]
    assert submitted["status"] == "pending"
    assert submitted["version"] == 1

    claimed = _triage_and_claim(ticket_id, operator)
    assert claimed["status"] == "in_progress"
    assert claimed["claimed_by"] == "zhangsan"

    public_comment = client.post(
        f"/api/v1/tickets/{ticket_id}/comments",
        headers=operator,
        json={
            "version": claimed["version"],
            "visibility": "public",
            "body": "已开始处理，请稍候。",
        },
    )
    assert public_comment.status_code == 201
    after_public = client.get(
        f"/api/v1/tickets/{ticket_id}/workflow", headers=operator
    ).json()
    assert after_public["first_responded_at"]

    internal_comment = client.post(
        f"/api/v1/tickets/{ticket_id}/comments",
        headers=operator,
        json={
            "version": after_public["version"],
            "visibility": "internal",
            "body": "内部排查记录：权限组配置缺失。",
        },
    )
    assert internal_comment.status_code == 201
    after_internal = client.get(
        f"/api/v1/tickets/{ticket_id}/workflow", headers=operator
    ).json()

    resolved = client.post(
        f"/api/v1/tickets/{ticket_id}/resolve",
        headers=operator,
        json={
            "version": after_internal["version"],
            "resolution_summary": "访问权限已恢复",
            "root_cause": "权限组配置缺失",
            "fix_action": "补充员工到只读权限组",
            "verification": "员工重新登录后确认可访问",
        },
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"

    employee_comments = client.get(
        f"/api/v1/tickets/{ticket_id}/comments", headers=employee
    )
    assert [item["body"] for item in employee_comments.json()["items"]] == [
        "已开始处理，请稍候。"
    ]
    employee_timeline = client.get(
        f"/api/v1/tickets/{ticket_id}/timeline", headers=employee
    ).json()["items"]
    assert "internal_note_added" not in {item["event_type"] for item in employee_timeline}

    confirmed = client.post(
        f"/api/v1/tickets/{ticket_id}/confirm",
        headers=employee,
        json={"version": resolved.json()["version"]},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "closed"
    assert confirmed.json()["closed_at"]

    operator_timeline = client.get(
        f"/api/v1/tickets/{ticket_id}/timeline", headers=operator
    ).json()["items"]
    event_types = [item["event_type"] for item in operator_timeline]
    assert event_types == [
        "ticket_created",
        "ai_triage_queued",
        "triage_completed",
        "ticket_claimed",
        "comment_added",
        "internal_note_added",
        "ticket_resolved",
        "ticket_closed",
    ]


def test_claim_with_stale_version_returns_conflict() -> None:
    employee = _login("wangwu", "wangwu123456")
    operator_a = _login("zhangsan", "zhangsan123")
    operator_b = _login("lisi", "lisi12345678")
    ticket_id = _submit(employee)["ticket_id"]
    client = TestClient(app)

    first = client.post(
        f"/api/v1/tickets/{ticket_id}/claim",
        headers=operator_a,
        json={"version": 1},
    )
    second = client.post(
        f"/api/v1/tickets/{ticket_id}/claim",
        headers=operator_b,
        json={"version": 1},
    )

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "TICKET_VERSION_CONFLICT"


def test_admin_can_assign_but_operator_cannot_resolve_anothers_ticket() -> None:
    employee = _login("wangwu", "wangwu123456")
    admin = _login("testadmin", "admin-test-password")
    operator_a = _login("zhangsan", "zhangsan123")
    operator_b = _login("lisi", "lisi12345678")
    ticket_id = _submit(employee)["ticket_id"]
    with session_scope() as session:
        assignee_id = session.scalar(select(User.id).where(User.username == "zhangsan"))
    assert assignee_id is not None

    assigned = TestClient(app).post(
        f"/api/v1/tickets/{ticket_id}/assign",
        headers=admin,
        json={"version": 1, "assignee_id": assignee_id},
    )
    assert assigned.status_code == 200
    assert assigned.json()["claimed_by"] == "zhangsan"

    forbidden = TestClient(app).post(
        f"/api/v1/tickets/{ticket_id}/resolve",
        headers=operator_b,
        json={
            "version": assigned.json()["version"],
            "resolution_summary": "错误处理人尝试解决",
            "root_cause": "测试",
            "fix_action": "测试",
            "verification": "测试",
        },
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "AUTH_FORBIDDEN"

    resolved = TestClient(app).post(
        f"/api/v1/tickets/{ticket_id}/resolve",
        headers=operator_a,
        json={
            "version": assigned.json()["version"],
            "resolution_summary": "正确处理人解决",
            "root_cause": "配置缺失",
            "fix_action": "补充配置",
            "verification": "验证通过",
        },
    )
    assert resolved.status_code == 200


def test_reopen_and_cancel_enforce_state_machine() -> None:
    employee = _login("wangwu", "wangwu123456")
    operator = _login("zhangsan", "zhangsan123")
    client = TestClient(app)
    ticket_id = _submit(employee)["ticket_id"]

    invalid_reopen = client.post(
        f"/api/v1/tickets/{ticket_id}/reopen",
        headers=employee,
        json={"version": 1, "reason": "尚未解决不能重开"},
    )
    assert invalid_reopen.status_code == 409
    assert invalid_reopen.json()["error"]["code"] == "TICKET_INVALID_TRANSITION"

    claimed = _triage_and_claim(ticket_id, operator)
    resolved = client.post(
        f"/api/v1/tickets/{ticket_id}/resolve",
        headers=operator,
        json={
            "version": claimed["version"],
            "resolution_summary": "已恢复",
            "root_cause": "配置错误",
            "fix_action": "修复配置",
            "verification": "验证成功",
        },
    ).json()
    reopened = client.post(
        f"/api/v1/tickets/{ticket_id}/reopen",
        headers=employee,
        json={"version": resolved["version"], "reason": "问题再次出现"},
    )
    assert reopened.status_code == 200
    assert reopened.json()["status"] == "open"

    cancelled = client.post(
        f"/api/v1/tickets/{ticket_id}/cancel",
        headers=employee,
        json={"version": reopened.json()["version"], "reason": "不再需要处理"},
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"


def test_employee_cannot_add_internal_note_or_view_another_sql_ticket() -> None:
    owner = _login("wangwu", "wangwu123456")
    other = _login("zhaoliu", "zhaoliu123456")
    submitted = _submit(owner)
    ticket_id = submitted["ticket_id"]
    client = TestClient(app)

    internal = client.post(
        f"/api/v1/tickets/{ticket_id}/comments",
        headers=owner,
        json={"version": 1, "visibility": "internal", "body": "越权备注"},
    )
    detail = client.get(f"/api/v1/tickets/{ticket_id}/workflow", headers=other)

    assert internal.status_code == 403
    assert detail.status_code == 403


def test_sla_overdue_query_reports_response_and_resolution_breaches() -> None:
    employee = _login("wangwu", "wangwu123456")
    operator = _login("zhangsan", "zhangsan123")
    ticket_id = _submit(employee, priority="P1")["ticket_id"]
    past = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    with session_scope() as session:
        ticket = session.get(Ticket, ticket_id)
        assert ticket is not None
        ticket.response_due_at = past
        ticket.resolution_due_at = past

    response = TestClient(app).get("/api/v1/tickets/sla/overdue", headers=operator)

    assert response.status_code == 200
    breach = response.json()["items"][0]
    assert breach["ticket_id"] == ticket_id
    assert breach["response_overdue"] is True
    assert breach["resolution_overdue"] is True
