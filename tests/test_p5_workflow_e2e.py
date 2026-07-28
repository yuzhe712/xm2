from __future__ import annotations

from fastapi.testclient import TestClient

from intelliticket_backend.main import app
from intelliticket_backend.services.worker_tasks import process_ai_run


def _login(client: TestClient, username: str, password: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"user_id": username, "password": password},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['token']}"}


def test_employee_ai_triage_operator_resolution_employee_close() -> None:
    client = TestClient(app)
    employee = _login(client, "wangwu", "wangwu123456")
    operator = _login(client, "zhangsan", "zhangsan123")

    submitted = client.post(
        "/api/v1/tickets/submit",
        headers=employee,
        json={
            "title": "Payment API timeout",
            "text": "Payment success rate dropped from 99.9% to 72% for ten minutes.",
            "desk_id": "ops",
            "priority": "P3",
        },
    )
    assert submitted.status_code == 200
    ticket = submitted.json()
    assert ticket["status"] == "pending"
    assert ticket["ai_status"] == "queued"

    ai_run = process_ai_run.apply(args=[ticket["ai_run_id"]], throw=True).get()
    assert ai_run["status"] == "completed"
    assert ai_run["result"]["quality_gate"]["requires_human_review"] is True
    assert ai_run["evidence"]

    after_triage = client.get(
        f"/api/v1/tickets/{ticket['ticket_id']}/workflow",
        headers=operator,
    )
    assert after_triage.status_code == 200
    assert after_triage.json()["status"] == "open"
    assert after_triage.json()["version"] == 2

    claimed = client.post(
        f"/api/v1/tickets/{ticket['ticket_id']}/claim",
        headers=operator,
        json={"version": after_triage.json()["version"]},
    )
    assert claimed.status_code == 200
    assert claimed.json()["status"] == "in_progress"
    assert claimed.json()["claimed_by"] == "zhangsan"

    reply = client.post(
        f"/api/v1/tickets/{ticket['ticket_id']}/comments",
        headers=operator,
        json={
            "version": claimed.json()["version"],
            "visibility": "public",
            "body": "The incident is isolated and mitigation is in progress.",
        },
    )
    assert reply.status_code == 201

    after_reply = client.get(
        f"/api/v1/tickets/{ticket['ticket_id']}/workflow",
        headers=operator,
    ).json()
    assert after_reply["first_responded_at"] is not None

    resolved = client.post(
        f"/api/v1/tickets/{ticket['ticket_id']}/resolve",
        headers=operator,
        json={
            "version": after_reply["version"],
            "resolution_summary": "Payment traffic is healthy again.",
            "root_cause": "An exhausted upstream connection pool.",
            "fix_action": "Recycled the pool and corrected its capacity limit.",
            "verification": "Success rate remained above 99.9% for fifteen minutes.",
        },
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"

    closed = client.post(
        f"/api/v1/tickets/{ticket['ticket_id']}/confirm",
        headers=employee,
        json={"version": resolved.json()["version"]},
    )
    assert closed.status_code == 200
    assert closed.json()["status"] == "closed"
    assert closed.json()["closed_at"] is not None

    employee_comments = client.get(
        f"/api/v1/tickets/{ticket['ticket_id']}/comments",
        headers=employee,
    )
    assert [item["body"] for item in employee_comments.json()["items"]] == [
        "The incident is isolated and mitigation is in progress."
    ]

    operator_timeline = client.get(
        f"/api/v1/tickets/{ticket['ticket_id']}/timeline",
        headers=operator,
    )
    assert [item["event_type"] for item in operator_timeline.json()["items"]] == [
        "ticket_created",
        "ai_triage_queued",
        "ai_triage_completed",
        "ticket_claimed",
        "comment_added",
        "ticket_resolved",
        "ticket_closed",
    ]
