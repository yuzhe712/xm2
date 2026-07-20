from __future__ import annotations

from intelliticket_backend.schemas.tickets import DataMode, DeskId
from intelliticket_backend.services.agents.envelope import InternalTaskRequest
from intelliticket_backend.services.agents.support_kb import SupportKbRetrievalAgent
from intelliticket_backend.services.agents.support_reply import SupportReplyAgent


def make_request(
    *,
    task_id: str,
    to_agent: str,
    payload: dict,
    evidence_ids: list[str] | None = None,
) -> InternalTaskRequest:
    return InternalTaskRequest(
        task_id=task_id,
        ticket_id="TCK-20260715-ABCDEF12",
        run_id="RUN-20260715-1234ABCD",
        from_agent="support_workflow",
        to_agent=to_agent,
        message_type=f"{to_agent}_request",
        payload=payload,
        evidence_ids=evidence_ids or [],
        idempotency_key=f"RUN-20260715-1234ABCD:{task_id}",
    )


def test_support_kb_agent_returns_mock_evidence_with_provenance() -> None:
    agent = SupportKbRetrievalAgent()

    result = agent.handle_task(
        make_request(
            task_id="TASK-1",
            to_agent="support_kb_retrieval_agent",
            payload={
                "text": "新同事无法访问监控面板，需要开通只读权限",
                "desk_id": DeskId.SUPPORT.value,
                "data_mode": DataMode.MOCK.value,
            },
        )
    )

    assert result.status == "completed"
    assert result.payload["matched_articles"]
    evidence = result.payload["evidence"][0]
    assert evidence["data_mode"] == "mock"
    assert evidence["producer"] == "support_kb_retrieval_agent"
    assert evidence["run_id"] == "RUN-20260715-1234ABCD"
    assert evidence["trace_uri"].startswith("mock_data/support_kb.json#")
    assert evidence["quality_reason"] == "来自本地 mock support_kb.json，data_mode=mock。"
    assert result.evidence_ids == [evidence["evidence_id"]]


def test_support_kb_agent_real_mode_does_not_return_mock_articles() -> None:
    agent = SupportKbRetrievalAgent()

    result = agent.handle_task(
        make_request(
            task_id="TASK-1",
            to_agent="support_kb_retrieval_agent",
            payload={
                "text": "无法访问监控面板",
                "desk_id": DeskId.SUPPORT.value,
                "data_mode": DataMode.REAL.value,
            },
        )
    )

    assert result.status == "completed"
    assert result.payload["matched_articles"] == []
    assert result.payload["evidence"] == []
    assert result.evidence_ids == []


def test_support_reply_agent_builds_deterministic_reply_from_kb_actions() -> None:
    agent = SupportReplyAgent()
    article = {
        "article_id": "KB-SUPPORT-ACCOUNT-PERMISSION",
        "service": "monitoring-console",
        "title": "账号权限问题处理说明",
        "actions": ["确认申请人所属团队和申请系统", "核对所需角色是否为只读权限"],
    }

    result = agent.handle_task(
        make_request(
            task_id="TASK-2",
            to_agent="support_reply_agent",
            payload={
                "text": "需要开通监控面板只读权限",
                "matched_articles": [article],
                "evidence_ids": ["ev_kb_support_account_001"],
                "data_mode": DataMode.MOCK.value,
            },
            evidence_ids=["ev_kb_support_account_001"],
        )
    )

    assert result.status == "completed"
    assert result.payload["reply_suggestions"] == article["actions"]
    assert result.payload["routing"]["recommended_team"] == "内部支持服务台"
    assert result.payload["support_result"]["matched_articles"] == ["KB-SUPPORT-ACCOUNT-PERMISSION"]
    assert result.payload["support_result"]["evidence_ids"] == ["ev_kb_support_account_001"]


def test_support_reply_agent_real_mode_uses_real_knowledge_assumption() -> None:
    agent = SupportReplyAgent()

    result = agent.handle_task(
        make_request(
            task_id="TASK-2",
            to_agent="support_reply_agent",
            payload={
                "text": "需要开通权限",
                "matched_articles": [],
                "evidence_ids": [],
                "data_mode": DataMode.REAL.value,
            },
        )
    )

    assert result.status == "completed"
    assert "mock" not in " ".join(result.payload["report"]["assumptions"])
    assert result.payload["support_result"]["reply_suggestions"] == [
        "记录用户问题并交由内部支持服务台人工确认"
    ]
