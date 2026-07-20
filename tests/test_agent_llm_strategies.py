from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel

from intelliticket_backend.errors import AppError
from intelliticket_backend.schemas.tickets import (
    CandidateRootCause,
    DataMode,
    DiagnosisResult,
    RecommendedAction,
    TicketCategory,
    TicketClassification,
    TicketPriority,
)
from intelliticket_backend.services.agents.diagnosis import DiagnosisAgent
from intelliticket_backend.services.agents.intake import IntakeAgent, IntakeLlmClassification
from intelliticket_backend.services.agents.support_reply import (
    SupportReplyAgent,
    SupportReplyLlmOutput,
)
from intelliticket_backend.services.llm import LlmClient, LlmClientError


class FakeLlmClient(LlmClient):
    """测试用 LLM 客户端，返回预置结构化输出。"""

    def __init__(self, output: BaseModel) -> None:
        self._output = output

    def structured_json_call(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, Any],
        response_schema: type[BaseModel],
        temperature: float | None = None,
    ) -> Any:
        return self._output


class FailingLlmClient(LlmClient):
    """模拟 LLM 调用失败的客户端。"""

    def structured_json_call(self, **_: Any) -> Any:
        raise LlmClientError("LLM_DOWN", "模拟 LLM 不可用", {"test": True})


# ---------------------------------------------------------------------------
# IntakeAgent LLM strategy
# ---------------------------------------------------------------------------


def test_intake_llm_classifies_ticket() -> None:
    llm_output = IntakeLlmClassification(
        category=TicketCategory.OPS_ALERT,
        summary="payment-service 出现超时告警",
        affected_service="payment-service",
        symptoms=["timeout", "order_volume_drop"],
        priority=TicketPriority.P1,
        priority_reason="核心支付服务超时且订单量下降超过 50%。",
        extracted_metrics={"order_qps_before": 1000, "order_qps_after": 300},
    )
    agent = IntakeAgent(llm_client=FakeLlmClient(llm_output), strategy="llm")

    run = agent.run(
        ticket_id="TCK-20260715-TEST01",
        text="线上支付服务出现超时告警，订单量从正常1000/min降到300/min",
        data_mode=DataMode.MOCK,
        observed_at="2026-07-15T00:00:00+00:00",
    )

    assert run.status == "completed"
    assert run.classification is not None
    assert run.classification.category == TicketCategory.OPS_ALERT
    assert run.classification.priority == TicketPriority.P1
    assert run.classification.affected_service == "payment-service"
    assert "timeout" in run.classification.symptoms
    assert any("LLM" in obs for obs in run.observations)


def test_intake_llm_fails_closed_when_llm_unavailable() -> None:
    agent = IntakeAgent(llm_client=FailingLlmClient(), strategy="llm")

    with pytest.raises(AppError) as exc_info:
        agent.run(
            ticket_id="TCK-20260715-TEST02",
            text="测试工单",
            data_mode=DataMode.MOCK,
            observed_at="2026-07-15T00:00:00+00:00",
        )

    assert exc_info.value.code == "INTAKE_LLM_FAILED"


def test_intake_llm_fails_closed_when_client_missing() -> None:
    agent = IntakeAgent(llm_client=None, strategy="llm")

    with pytest.raises(AppError) as exc_info:
        agent.run(
            ticket_id="TCK-20260715-TEST03",
            text="测试工单",
            data_mode=DataMode.MOCK,
            observed_at="2026-07-15T00:00:00+00:00",
        )

    assert exc_info.value.code == "INTAKE_LLM_CLIENT_MISSING"


def test_intake_rejects_invalid_strategy() -> None:
    agent = IntakeAgent(strategy="unsupported")

    with pytest.raises(AppError) as exc_info:
        agent.run(
            ticket_id="TCK-20260715-TEST04",
            text="测试工单",
            data_mode=DataMode.MOCK,
            observed_at="2026-07-15T00:00:00+00:00",
        )

    assert exc_info.value.code == "INTAKE_STRATEGY_INVALID"


# ---------------------------------------------------------------------------
# DiagnosisAgent LLM strategy
# ---------------------------------------------------------------------------


def test_diagnosis_llm_generates_root_causes() -> None:
    llm_output = DiagnosisResult(
        candidate_root_causes=[
            CandidateRootCause(
                cause="数据库连接池耗尽导致支付服务超时",
                evidence_ids=["ev_metric_db_pool_001", "ev_incident_001"],
                confidence=0.82,
                reasoning_summary="连接池使用率达 96%，历史工单确认相似模式。",
            )
        ],
        unknowns=["未接入真实 Prometheus 指标。"],
        abstentions=[],
    )
    agent = DiagnosisAgent(llm_client=FakeLlmClient(llm_output), strategy="llm")

    classification = TicketClassification(
        category=TicketCategory.OPS_ALERT,
        summary="payment-service 出现超时告警",
        affected_service="payment-service",
        symptoms=["timeout"],
        priority=TicketPriority.P1,
        priority_reason="核心服务超时。",
        extracted_metrics={},
        evidence_ids=["ev_ticket_input_001"],
    )
    from intelliticket_backend.schemas.tickets import (
        HistoricalIncident,
        MetricSnapshot,
        RetrievedContext,
        ServiceContext,
    )

    context = RetrievedContext(
        service=ServiceContext(
            service_id="payment-service",
            name="payment-service",
            display_name="支付服务",
            aliases=["payment"],
            owner_team="支付系统运维组",
            criticality="business_critical",
            dependencies=[],
            data_mode=DataMode.MOCK,
        ),
        metrics=[
            MetricSnapshot(
                evidence_id="ev_metric_db_pool_001",
                metric_name="db_connection_pool_usage",
                value=96,
                unit="percent",
                observed_at="2026-07-15T00:00:00+00:00",
                quality="fresh",
                summary="连接池使用率 96%",
                data_mode=DataMode.MOCK,
            )
        ],
        deployments=[],
        historical_incidents=[
            HistoricalIncident(
                evidence_id="ev_incident_001",
                incident_id="INC-001",
                root_cause="连接池耗尽导致支付服务超时",
                summary="历史相似工单",
                data_mode=DataMode.MOCK,
            )
        ],
        sop_documents=[],
        unknowns=[],
    )
    run = agent.run(classification, context, DataMode.MOCK)

    assert run.status == "completed"
    assert len(run.diagnosis.candidate_root_causes) == 1
    assert "连接池" in run.diagnosis.candidate_root_causes[0].cause
    assert "LLM" in run.observations[-1]


def test_real_intake_llm_classifies_without_mock_service_evidence() -> None:
    llm_output = IntakeLlmClassification(
        category=TicketCategory.OPS_ALERT,
        summary="payment-service 出现超时告警且订单量下降 70%",
        affected_service="payment-service",
        symptoms=["timeout", "order_volume_drop"],
        priority=TicketPriority.P1,
        priority_reason="用户输入显示订单量下降 70%，影响线上支付服务。",
        extracted_metrics={"order_qps_before": 1000, "order_qps_after": 300},
    )
    agent = IntakeAgent(llm_client=FakeLlmClient(llm_output), strategy="llm")

    run = agent.run(
        ticket_id="TCK-REAL-001",
        text="线上支付服务出现超时告警，订单量从正常1000/min降到300/min",
        data_mode=DataMode.REAL,
        observed_at="2026-07-19T00:00:00+00:00",
    )

    assert run.classification is not None
    assert run.classification.affected_service == "payment-service"
    assert run.classification.priority == TicketPriority.P1
    assert run.service_record is None
    assert {item.data_mode for item in run.evidence} == {DataMode.REAL}
    assert run.evidence_ids == ["ev_ticket_input_001"]


def test_real_diagnosis_llm_selects_relevant_sop_and_synthesizes_actions() -> None:
    from intelliticket_backend.schemas.tickets import RetrievedContext, SopDocument

    llm_output = DiagnosisResult(
        candidate_root_causes=[
            CandidateRootCause(
                cause="网络连接异常是需要优先验证的排查方向",
                evidence_ids=["ev_feishu_network"],
                confidence=0.7,
                reasoning_summary=(
                    "工单出现 timeout，与网络连通性 SOP 相关；"
                    "缺少监控事实，不能确认根因。"
                ),
            )
        ],
        recommended_actions=[
            RecommendedAction(
                action="从受影响实例对上游地址执行 TCP 连通性检查并记录超时结果",
                evidence_ids=["ev_feishu_network"],
            )
        ],
        sop_refs=["feishu-network"],
        unknowns=["缺少真实网络监控数据"],
        abstentions=["SOP 仅作为排查方向"],
    )
    agent = DiagnosisAgent(llm_client=FakeLlmClient(llm_output), strategy="llm")
    context = RetrievedContext(
        sop_documents=[
            SopDocument(
                evidence_id="ev_feishu_network",
                sop_id="feishu-network",
                title="网络延迟、丢包与端口不通排查 SOP",
                actions=["12.1 适用场景", "业务接口调用失败，报 connect timeout。"],
                data_mode=DataMode.REAL,
            ),
            SopDocument(
                evidence_id="ev_feishu_kafka",
                sop_id="feishu-kafka",
                title="Kafka 消费积压深度排查 SOP",
                actions=["Kafka current-lag 持续增加。"],
                data_mode=DataMode.REAL,
            ),
        ]
    )
    classification = TicketClassification(
        category=TicketCategory.OPS_ALERT,
        summary="payment-service 超时",
        affected_service="payment-service",
        symptoms=["timeout"],
        priority=TicketPriority.P1,
        priority_reason="支付服务订单量下降。",
        evidence_ids=["ev_ticket_input_001"],
    )

    run = agent.run(
        classification,
        context,
        DataMode.REAL,
        ticket_text="线上支付服务出现超时告警",
    )

    assert run.diagnosis.sop_refs == ["feishu-network"]
    assert run.diagnosis.recommended_actions[0].evidence_ids == ["ev_feishu_network"]
    assert "ev_feishu_kafka" not in run.evidence_ids
    assert run.diagnosis.candidate_root_causes[0].confidence == 0.49


def test_real_diagnosis_llm_rejects_raw_retrieval_line_as_action() -> None:
    from intelliticket_backend.schemas.tickets import RetrievedContext, SopDocument

    raw_line = "12.1 适用场景"
    output = DiagnosisResult(
        recommended_actions=[
            RecommendedAction(action=raw_line, evidence_ids=["ev_feishu_network"])
        ],
        sop_refs=["feishu-network"],
    )
    agent = DiagnosisAgent(llm_client=FakeLlmClient(output), strategy="llm")
    context = RetrievedContext(
        sop_documents=[
            SopDocument(
                evidence_id="ev_feishu_network",
                sop_id="feishu-network",
                title="网络排查 SOP",
                actions=[raw_line],
                data_mode=DataMode.REAL,
            )
        ]
    )
    classification = TicketClassification(
        category=TicketCategory.OPS_ALERT,
        summary="网络超时",
        affected_service=None,
        symptoms=["timeout"],
        priority=TicketPriority.P3,
        priority_reason="待确认",
        evidence_ids=["ev_ticket_input_001"],
    )

    with pytest.raises(AppError) as exc_info:
        agent.run(classification, context, DataMode.REAL, ticket_text="网络超时")

    assert exc_info.value.code == "DIAGNOSIS_LLM_ACTION_INVALID"


def test_diagnosis_llm_rejects_invalid_evidence_refs() -> None:
    """LLM 诊断引用不存在的 evidence_id 时 fail-closed。"""
    llm_output = DiagnosisResult(
        candidate_root_causes=[
            CandidateRootCause(
                cause="某个根因",
                evidence_ids=["ev_nonexistent_001"],
                confidence=0.5,
                reasoning_summary="编造的证据引用。",
            )
        ],
        unknowns=[],
        abstentions=[],
    )
    agent = DiagnosisAgent(llm_client=FakeLlmClient(llm_output), strategy="llm")

    classification = TicketClassification(
        category=TicketCategory.OPS_ALERT,
        summary="test",
        affected_service="payment-service",
        symptoms=["test"],
        priority=TicketPriority.P3,
        priority_reason="test",
        extracted_metrics={},
        evidence_ids=["ev_ticket_input_001"],
    )
    from intelliticket_backend.schemas.tickets import RetrievedContext, ServiceContext

    context = RetrievedContext(
        service=ServiceContext(
            service_id="payment-service",
            name="payment-service",
            display_name="支付服务",
            aliases=[],
            owner_team="支付系统运维组",
            criticality="business_critical",
            dependencies=[],
            data_mode=DataMode.MOCK,
        ),
    )

    with pytest.raises(AppError) as exc_info:
        agent.run(classification, context, DataMode.MOCK)

    assert exc_info.value.code == "DIAGNOSIS_LLM_EVIDENCE_INVALID"


def test_diagnosis_llm_fails_closed_when_client_missing() -> None:
    agent = DiagnosisAgent(llm_client=None, strategy="llm")

    classification = TicketClassification(
        category=TicketCategory.OPS_ALERT,
        summary="test",
        affected_service="payment-service",
        symptoms=["test"],
        priority=TicketPriority.P3,
        priority_reason="test",
        extracted_metrics={},
        evidence_ids=["ev_ticket_input_001"],
    )
    from intelliticket_backend.schemas.tickets import RetrievedContext, ServiceContext

    context = RetrievedContext(
        service=ServiceContext(
            service_id="payment-service",
            name="payment-service",
            display_name="支付服务",
            aliases=[],
            owner_team="支付系统运维组",
            criticality="business_critical",
            dependencies=[],
            data_mode=DataMode.MOCK,
        ),
    )

    with pytest.raises(AppError) as exc_info:
        agent.run(classification, context, DataMode.MOCK)

    assert exc_info.value.code == "DIAGNOSIS_LLM_CLIENT_MISSING"


def test_diagnosis_rejects_invalid_strategy() -> None:
    agent = DiagnosisAgent(strategy="unsupported")

    classification = TicketClassification(
        category=TicketCategory.OPS_ALERT,
        summary="test",
        affected_service="payment-service",
        symptoms=["test"],
        priority=TicketPriority.P3,
        priority_reason="test",
        extracted_metrics={},
        evidence_ids=["ev_ticket_input_001"],
    )
    from intelliticket_backend.schemas.tickets import RetrievedContext, ServiceContext

    context = RetrievedContext(
        service=ServiceContext(
            service_id="payment-service",
            name="payment-service",
            display_name="支付服务",
            aliases=[],
            owner_team="支付系统运维组",
            criticality="business_critical",
            dependencies=[],
            data_mode=DataMode.MOCK,
        ),
    )

    with pytest.raises(AppError) as exc_info:
        agent.run(classification, context, DataMode.MOCK)

    assert exc_info.value.code == "DIAGNOSIS_STRATEGY_INVALID"


# ---------------------------------------------------------------------------
# SupportReplyAgent LLM strategy
# ---------------------------------------------------------------------------


def test_support_reply_llm_generates_natural_language_replies() -> None:
    llm_output = SupportReplyLlmOutput(
        reply_suggestions=[
            "您好，已收到您的监控面板权限申请。请补充以下信息："
            "1) 所属团队，2) 需要的监控面板名称。",
            "根据知识库指引，只读权限通常由运维团队在 1 个工作日内开通。",
        ],
        report_title="监控面板权限申请处理建议",
        report_summary="用户申请监控面板只读权限，已基于知识库生成回复建议。",
        facts=["用户请求：需要开通监控面板只读权限"],
        derived_findings=["该请求属于标准账号权限问题，建议按 SOP 处理。"],
        recommendations=[
            "确认申请人所属团队和申请系统",
            "核对所需角色是否为只读权限",
        ],
    )
    agent = SupportReplyAgent(llm_client=FakeLlmClient(llm_output), strategy="llm")

    run = agent.run(
        text="需要开通监控面板只读权限",
        matched_articles=[
            {
                "article_id": "KB-SUPPORT-ACCOUNT-PERMISSION",
                "service": "monitoring-console",
                "title": "账号权限问题处理说明",
                "summary": "处理员工账号权限开通请求的标准流程。",
                "actions": ["确认申请人所属团队", "核对所需角色"],
                "category": "账号权限",
            }
        ],
        evidence_ids=["ev_kb_support_account_001"],
        data_mode=DataMode.MOCK,
    )

    assert run.status == "completed"
    assert len(run.reply_suggestions) == 2
    assert "监控面板" in run.reply_suggestions[0]
    assert run.routing is not None
    assert run.routing.recommended_team == "内部支持服务台"
    assert run.report is not None
    assert run.report.title == "监控面板权限申请处理建议"
    assert any("LLM" in obs for obs in run.observations)


def test_support_reply_llm_fails_closed_when_client_missing() -> None:
    agent = SupportReplyAgent(llm_client=None, strategy="llm")

    with pytest.raises(AppError) as exc_info:
        agent.run(
            text="需要开通权限",
            matched_articles=[],
            evidence_ids=[],
            data_mode=DataMode.MOCK,
        )

    assert exc_info.value.code == "SUPPORT_REPLY_LLM_CLIENT_MISSING"


def test_support_reply_rejects_invalid_strategy() -> None:
    agent = SupportReplyAgent(strategy="unsupported")

    with pytest.raises(AppError) as exc_info:
        agent.run(
            text="需要开通权限",
            matched_articles=[],
            evidence_ids=[],
            data_mode=DataMode.MOCK,
        )

    assert exc_info.value.code == "SUPPORT_REPLY_STRATEGY_INVALID"
