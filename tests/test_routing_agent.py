from __future__ import annotations

from intelliticket_backend.repositories.mock_ops_data import MockOpsDataRepository
from intelliticket_backend.schemas.tickets import (
    CandidateRootCause,
    DataMode,
    DiagnosisResult,
    RecommendedAction,
    RetrievedContext,
    TicketCategory,
    TicketClassification,
    TicketPriority,
)
from intelliticket_backend.services.agents.context import ContextRetrievalAgent
from intelliticket_backend.services.agents.diagnosis import DiagnosisAgent
from intelliticket_backend.services.agents.envelope import InternalTaskRequest
from intelliticket_backend.services.agents.routing import RoutingAgent

SAMPLE_TEXT = "线上支付服务出现超时告警，订单量从正常1000/min降到300/min"


class FakeRealKnowledgeService:
    def search_sops(
        self,
        *,
        query: str,
        service_name: str | None,
        data_mode: DataMode,
        limit: int | None = None,
    ) -> list[dict]:
        return [
            {
                "evidence_id": "ev_feishu_timeout_001",
                "source_type": "external_knowledge",
                "source_id": "doc-timeout",
                "source_name": "Feishu Drive Folder",
                "retrieved_at": "2026-07-19T00:00:00+00:00",
                "service": "external-knowledge",
                "sop_id": "feishu-doc-timeout",
                "title": "网络延迟、丢包与端口不通排查 SOP",
                "actions": ["检查网络连通性", "确认上游 connect timeout 错误"],
                "quality": "external_retrieved",
                "data_mode": data_mode.value,
                "summary": "业务接口 connect timeout 排查 SOP",
                "trace_uri": "https://my.feishu.cn/docx/doc-timeout",
                "quality_reason": "来自飞书 Drive 文件夹读取的真实知识文档。",
            }
        ]


def _payment_context() -> RetrievedContext:
    repository = MockOpsDataRepository()
    service_record = repository.resolve_service(SAMPLE_TEXT)
    assert service_record is not None
    return ContextRetrievalAgent(repository=repository).run(
        service_record, DataMode.MOCK
    ).context


def _classification() -> TicketClassification:
    return TicketClassification(
        category=TicketCategory.OPS_ALERT,
        summary="payment-service 运维告警",
        affected_service="payment-service",
        symptoms=["timeout", "order_volume_drop"],
        priority=TicketPriority.P1,
        priority_reason="核心支付服务超时且订单量下降超过 50%。",
        extracted_metrics={"order_qps_before": 1000, "order_qps_after": 300},
        evidence_ids=["ev_ticket_input_001", "ev_service_payment_001"],
    )


def _diagnosis(context: RetrievedContext) -> DiagnosisResult:
    return DiagnosisAgent().run(_classification(), context, DataMode.MOCK).diagnosis


def test_routing_agent_routes_payment_incident_with_sop_and_diagnosis_evidence() -> None:
    context = _payment_context()
    diagnosis = _diagnosis(context)

    run = RoutingAgent().run(context, diagnosis, DataMode.MOCK)

    assert run.agent_name == "routing_agent"
    assert run.status == "completed"
    assert run.iterations_used <= run.max_iterations
    assert run.max_tool_calls == 0
    assert run.routing.recommended_team == "支付系统运维组"
    assert "SOP-PAYMENT-TIMEOUT" in run.routing.sop_refs
    assert "SOP-DB-POOL-EXHAUSTION" in run.routing.sop_refs
    assert run.routing.recommended_actions[0].action == "检查 payment-service 最近 30 分钟部署记录"
    assert "ev_sop_payment_timeout_001" in run.routing.recommended_actions[0].evidence_ids
    assert "ev_sop_payment_timeout_001" in run.evidence_ids
    assert [step.action for step in run.react_steps] == [
        "validate_context",
        "collect_sop_actions",
        "apply_diagnosis_actions",
        "finish",
    ]


def test_routing_agent_abstains_without_service_context() -> None:
    run = RoutingAgent().run(RetrievedContext(), DiagnosisResult(), DataMode.MOCK)

    assert run.status == "abstained"
    assert run.routing.recommended_team is None
    assert run.routing.recommended_actions == []
    assert run.routing.escalation == "服务未知，建议人工确认影响系统后再分派。"


def test_routing_agent_real_mode_uses_real_sop_actions_with_manual_team() -> None:
    context = ContextRetrievalAgent(knowledge_service=FakeRealKnowledgeService()).run(
        _payment_context().service.model_dump(mode="json"), DataMode.REAL, SAMPLE_TEXT
    ).context
    diagnosis = DiagnosisResult(
        recommended_actions=[
            RecommendedAction(
                action="从受影响实例检查上游 TCP 连通性",
                evidence_ids=["ev_feishu_timeout_001"],
            )
        ],
        sop_refs=["feishu-doc-timeout"],
    )

    run = RoutingAgent().run(context, diagnosis, DataMode.REAL)

    assert run.status == "completed"
    assert run.routing.recommended_team == "待人工确认"
    assert run.routing.recommended_actions
    assert "飞书 SOP" in run.routing.escalation
    assert all(evidence_id.startswith("ev_feishu_") for evidence_id in run.evidence_ids)


def test_routing_agent_mock_mode_allows_real_sop_as_knowledge_reference() -> None:
    context = _payment_context()
    diagnosis = _diagnosis(context)
    context.sop_documents[0] = context.sop_documents[0].model_copy(
        update={"data_mode": DataMode.REAL}
    )

    run = RoutingAgent().run(context, diagnosis, DataMode.MOCK)

    assert run.status == "completed"
    assert run.routing.recommended_actions
    assert context.sop_documents[0].evidence_id in run.evidence_ids


def test_routing_agent_allows_owner_team_and_diagnosis_action_without_sops() -> None:
    context = _payment_context()
    diagnosis = _diagnosis(context)
    context.sop_documents = []

    run = RoutingAgent().run(context, diagnosis, DataMode.MOCK)

    assert run.status == "completed"
    assert run.routing.recommended_team == "支付系统运维组"
    assert run.routing.sop_refs == []
    assert run.routing.recommended_actions == []


def test_routing_agent_does_not_prepend_db_pool_action_without_db_pool_cause() -> None:
    context = _payment_context()
    diagnosis = DiagnosisResult(
        candidate_root_causes=[
            CandidateRootCause(
                cause="最近发布版本可能引入性能退化或连接泄漏",
                evidence_ids=["ev_deploy_payment_190"],
                confidence=0.58,
                reasoning_summary="告警窗口附近存在新版本发布。",
            )
        ]
    )

    run = RoutingAgent().run(context, diagnosis, DataMode.MOCK)

    assert run.status == "completed"
    assert run.routing.recommended_actions[0].action != "立即检查并临时扩容 payment-db 连接池"


def _routing_task_request(payload: dict) -> InternalTaskRequest:
    return InternalTaskRequest(
        task_id="task-routing-001",
        ticket_id="TCK-TEST-001",
        run_id="RUN-TEST-001",
        from_agent="diagnosis_agent",
        to_agent="routing_agent",
        message_type="routing_request",
        payload=payload,
        evidence_ids=["ev_metric_db_pool_001"],
        idempotency_key="TCK-TEST-001:routing",
    )


def test_routing_agent_handle_task_returns_internal_result() -> None:
    context = _payment_context()
    diagnosis = _diagnosis(context)
    request = _routing_task_request(
        {
            "context": context.model_dump(mode="json"),
            "diagnosis": diagnosis.model_dump(mode="json"),
            "data_mode": DataMode.MOCK.value,
        }
    )

    result = RoutingAgent().handle_task(request)

    assert result.status == "completed"
    assert result.error is None
    assert result.payload["routing"]["recommended_team"] == "支付系统运维组"
    assert "ev_sop_payment_timeout_001" in result.evidence_ids
    assert result.react_steps
    assert all("chain_of_thought" not in step.model_dump() for step in result.react_steps)


def test_routing_agent_handle_task_rejects_wrong_target() -> None:
    request = _routing_task_request({})
    request = request.model_copy(update={"to_agent": "report_agent"})

    result = RoutingAgent().handle_task(request)

    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "INVALID_AGENT_TARGET"


def test_routing_agent_handle_task_rejects_malformed_payload() -> None:
    request = _routing_task_request({"context": {}})

    result = RoutingAgent().handle_task(request)

    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "INVALID_TASK_PAYLOAD"
