from __future__ import annotations

from intelliticket_backend.repositories.mock_ops_data import MockOpsDataRepository
from intelliticket_backend.schemas.tickets import (
    DataMode,
    DiagnosisResult,
    RetrievedContext,
    RoutingRecommendation,
    TicketCategory,
    TicketClassification,
    TicketPriority,
)
from intelliticket_backend.services.agents.context import ContextRetrievalAgent
from intelliticket_backend.services.agents.diagnosis import DiagnosisAgent
from intelliticket_backend.services.agents.envelope import InternalTaskRequest
from intelliticket_backend.services.agents.report import ReportAgent
from intelliticket_backend.services.agents.routing import RoutingAgent

SAMPLE_TEXT = "线上支付服务出现超时告警，订单量从正常1000/min降到300/min"


def _classification(evidence_ids: list[str] | None = None) -> TicketClassification:
    return TicketClassification(
        category=TicketCategory.OPS_ALERT,
        summary="payment-service 运维告警",
        affected_service="payment-service",
        symptoms=["timeout", "order_volume_drop"],
        priority=TicketPriority.P1,
        priority_reason="核心支付服务超时且订单量下降超过 50%。",
        extracted_metrics={"order_qps_before": 1000, "order_qps_after": 300},
        evidence_ids=evidence_ids if evidence_ids is not None else [
            "ev_ticket_input_001",
            "ev_service_payment_001",
        ],
    )


def _payment_context() -> RetrievedContext:
    repository = MockOpsDataRepository()
    service_record = repository.resolve_service(SAMPLE_TEXT)
    assert service_record is not None
    return ContextRetrievalAgent(repository=repository).run(service_record, DataMode.MOCK).context


def _diagnosis_and_routing(
    classification: TicketClassification,
    context: RetrievedContext,
) -> tuple[DiagnosisResult, RoutingRecommendation]:
    diagnosis = DiagnosisAgent().run(classification, context, DataMode.MOCK).diagnosis
    routing = RoutingAgent().run(context, diagnosis, DataMode.MOCK).routing
    return diagnosis, routing


def test_report_agent_generates_completed_report_with_provenance() -> None:
    classification = _classification()
    context = _payment_context()
    diagnosis, routing = _diagnosis_and_routing(classification, context)

    run = ReportAgent().run(classification, context, diagnosis, routing, DataMode.MOCK)

    assert run.agent_name == "report_agent"
    assert run.status == "completed"
    assert run.iterations_used <= run.max_iterations
    assert run.max_tool_calls == 0
    assert "payment-service" in run.report.title
    assert run.report.recommendations
    assert any(
        "未把 mock 指标作为当前故障事实" in assumption
        for assumption in run.report.assumptions
    )
    assert any("订单量从 1000/min 降至 300/min" in fact for fact in run.report.facts)
    assert "ev_ticket_input_001" in run.evidence_ids
    assert "ev_service_payment_001" in run.evidence_ids
    assert "ev_metric_db_pool_001" not in run.evidence_ids
    assert "ev_sop_payment_timeout_001" in run.evidence_ids
    assert [step.action for step in run.react_steps] == [
        "validate_report_inputs",
        "collect_report_evidence",
        "build_report",
        "finish",
    ]


def test_report_agent_real_mode_builds_evidence_bounded_report() -> None:
    classification = _classification()
    context = _payment_context()
    diagnosis, routing = _diagnosis_and_routing(classification, context)

    run = ReportAgent().run(classification, context, diagnosis, routing, DataMode.REAL)

    assert run.status == "completed"
    assert run.evidence_ids
    assert "data_mode 非 mock" not in " ".join(run.report.assumptions)


def test_report_agent_abstains_without_classification_evidence() -> None:
    classification = _classification(evidence_ids=[])
    context = _payment_context()
    diagnosis, routing = _diagnosis_and_routing(classification, context)

    run = ReportAgent().run(classification, context, diagnosis, routing, DataMode.MOCK)

    assert run.status == "abstained"
    assert "证据不足" in run.report.summary
    assert any("缺少工单输入证据" in item for item in run.report.unknowns)


def test_report_agent_does_not_invent_confident_unknown_service_report() -> None:
    classification = TicketClassification(
        category=TicketCategory.OPS_ALERT,
        summary="未知系统告警",
        affected_service=None,
        symptoms=["alert"],
        priority=TicketPriority.P3,
        priority_reason="未识别到核心业务服务的严重影响证据。",
        evidence_ids=["ev_ticket_input_001"],
    )
    context = RetrievedContext(unknowns=["未能从工单文本识别影响服务。"])
    diagnosis = DiagnosisResult(
        unknowns=["影响服务未知"],
        abstentions=["缺少服务目录证据，无法生成可信根因诊断。"],
    )
    routing = RoutingRecommendation(
        recommended_team=None,
        recommended_actions=[],
        escalation="服务未知，建议人工确认影响系统后再分派。",
    )

    run = ReportAgent().run(classification, context, diagnosis, routing, DataMode.MOCK)

    assert run.status == "completed"
    assert "未知服务" in run.report.title
    assert "证据不足，暂不判断根因" in run.report.summary
    assert run.report.unknowns


def _report_task_request(payload: dict) -> InternalTaskRequest:
    return InternalTaskRequest(
        task_id="task-report-001",
        ticket_id="TCK-TEST-001",
        run_id="RUN-TEST-001",
        from_agent="routing_agent",
        to_agent="report_agent",
        message_type="report_request",
        payload=payload,
        evidence_ids=["ev_metric_db_pool_001"],
        idempotency_key="TCK-TEST-001:report",
    )


def test_report_agent_handle_task_returns_internal_result() -> None:
    classification = _classification()
    context = _payment_context()
    diagnosis, routing = _diagnosis_and_routing(classification, context)
    request = _report_task_request(
        {
            "classification": classification.model_dump(mode="json"),
            "context": context.model_dump(mode="json"),
            "diagnosis": diagnosis.model_dump(mode="json"),
            "routing": routing.model_dump(mode="json"),
            "data_mode": DataMode.MOCK.value,
        }
    )

    result = ReportAgent().handle_task(request)

    assert result.status == "completed"
    assert result.error is None
    assert "payment-service" in result.payload["report"]["title"]
    assert "ev_metric_db_pool_001" not in result.evidence_ids
    assert "ev_incident_payment_db_pool_001" in result.evidence_ids
    assert result.react_steps
    assert all("thought" not in step.model_dump() for step in result.react_steps)


def test_report_agent_handle_task_rejects_wrong_target() -> None:
    request = _report_task_request({})
    request = request.model_copy(update={"to_agent": "routing_agent"})

    result = ReportAgent().handle_task(request)

    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "INVALID_AGENT_TARGET"


def test_report_agent_handle_task_rejects_malformed_payload() -> None:
    request = _report_task_request({"classification": {}})

    result = ReportAgent().handle_task(request)

    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "INVALID_TASK_PAYLOAD"
