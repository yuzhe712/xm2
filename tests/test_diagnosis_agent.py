from __future__ import annotations

from intelliticket_backend.repositories.mock_ops_data import MockOpsDataRepository
from intelliticket_backend.schemas.tickets import (
    DataMode,
    RetrievedContext,
    TicketCategory,
    TicketClassification,
    TicketPriority,
)
from intelliticket_backend.services.agents.context import ContextRetrievalAgent
from intelliticket_backend.services.agents.diagnosis import DiagnosisAgent
from intelliticket_backend.services.agents.envelope import InternalTaskRequest

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


def _payment_context() -> RetrievedContext:
    repository = MockOpsDataRepository()
    service_record = repository.resolve_service(SAMPLE_TEXT)
    assert service_record is not None
    return ContextRetrievalAgent(repository=repository).run(service_record, DataMode.MOCK).context


def test_diagnosis_agent_generates_candidates_from_payment_context() -> None:
    run = DiagnosisAgent().run(_classification(), _payment_context(), DataMode.MOCK)

    assert run.agent_name == "diagnosis_agent"
    assert run.status == "completed"
    assert run.iterations_used <= run.max_iterations
    assert run.max_tool_calls == 4
    assert len(run.diagnosis.candidate_root_causes) == 1
    assert "ev_metric_db_pool_001" not in run.evidence_ids
    assert "ev_incident_payment_db_pool_001" in run.evidence_ids
    assert run.diagnosis.candidate_root_causes[0].confidence < 0.5
    assert any("未接入真实监控指标" in item for item in run.diagnosis.abstentions)
    assert [step.action for step in run.react_steps] == [
        "validate_context",
        "evaluate_db_pool_cause",
        "evaluate_deployment_cause",
        "finish",
    ]


def test_diagnosis_agent_abstains_without_service_context() -> None:
    run = DiagnosisAgent().run(_classification(), RetrievedContext(), DataMode.MOCK)

    assert run.status == "abstained"
    assert run.diagnosis.candidate_root_causes == []
    assert run.diagnosis.abstentions == ["缺少服务目录证据，无法生成可信根因诊断。"]


def test_diagnosis_agent_does_not_invent_db_pool_cause_without_required_metric() -> None:
    context = _payment_context()
    context.metrics = [
        metric for metric in context.metrics if metric.metric_name != "db_connection_pool_usage"
    ]

    run = DiagnosisAgent().run(_classification(), context, DataMode.MOCK)

    causes = [cause.cause for cause in run.diagnosis.candidate_root_causes]
    assert "数据库连接池耗尽导致支付服务超时" not in causes
    assert run.diagnosis.abstentions


def test_diagnosis_agent_uses_history_as_direction_when_monitoring_metrics_are_absent() -> None:
    context = _payment_context()

    run = DiagnosisAgent().run(_classification(), context, DataMode.MOCK)

    causes = [cause.cause for cause in run.diagnosis.candidate_root_causes]
    assert "数据库连接池耗尽导致支付服务超时" not in causes
    assert "历史案例提示需优先排查数据库连接池或下游依赖" in causes
    direction = run.diagnosis.candidate_root_causes[0]
    assert direction.evidence_ids == ["ev_incident_payment_db_pool_001"]
    assert "不能确认" in direction.reasoning_summary


def test_diagnosis_agent_real_mode_uses_real_sop_as_direction_only() -> None:
    context = ContextRetrievalAgent(knowledge_service=FakeRealKnowledgeService()).run(
        None, DataMode.REAL, SAMPLE_TEXT
    ).context

    run = DiagnosisAgent().run(_classification(), context, DataMode.REAL)

    assert run.status == "completed"
    assert run.diagnosis.candidate_root_causes
    assert run.diagnosis.candidate_root_causes[0].confidence < 0.5
    assert "不能确认当前根因" in run.diagnosis.candidate_root_causes[0].reasoning_summary
    assert all(evidence_id.startswith("ev_feishu_") for evidence_id in run.evidence_ids)


def _diagnosis_task_request(payload: dict) -> InternalTaskRequest:
    return InternalTaskRequest(
        task_id="task-001",
        ticket_id="TCK-001",
        run_id="RUN-001",
        from_agent="context_retrieval_agent",
        to_agent="diagnosis_agent",
        message_type="diagnosis_request",
        payload=payload,
        evidence_ids=["ev_service_payment_001"],
        idempotency_key="TCK-001:diagnosis",
    )


def test_diagnosis_agent_handle_task_returns_internal_result() -> None:
    classification = _classification()
    context = _payment_context()
    request = _diagnosis_task_request(
        {
            "classification": classification.model_dump(mode="json"),
            "context": context.model_dump(mode="json"),
            "data_mode": DataMode.MOCK.value,
        }
    )

    result = DiagnosisAgent().handle_task(request)

    assert result.agent_name == "diagnosis_agent"
    assert result.status == "completed"
    assert result.error is None
    assert result.payload["diagnosis"]["candidate_root_causes"]
    assert "ev_metric_db_pool_001" not in result.evidence_ids
    assert "ev_incident_payment_db_pool_001" in result.evidence_ids
    assert result.react_steps
    dumped_steps = [step.model_dump() for step in result.react_steps]
    assert all("thought" not in step for step in dumped_steps)
    assert all("chain_of_thought" not in step for step in dumped_steps)


def test_diagnosis_agent_handle_task_rejects_wrong_target() -> None:
    request = _diagnosis_task_request({})
    request = request.model_copy(update={"to_agent": "routing_agent"})

    result = DiagnosisAgent().handle_task(request)

    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "INVALID_AGENT_TARGET"


def test_diagnosis_agent_handle_task_rejects_malformed_payload() -> None:
    request = _diagnosis_task_request({"classification": {}})

    result = DiagnosisAgent().handle_task(request)

    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "INVALID_TASK_PAYLOAD"
    assert result.react_steps == []
