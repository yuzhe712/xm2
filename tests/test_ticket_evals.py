from __future__ import annotations

import pytest

from intelliticket_backend.config import Settings
from intelliticket_backend.errors import AppError
from intelliticket_backend.repositories.mock_ops_data import MockOpsDataRepository
from intelliticket_backend.schemas.tickets import (
    DataMode,
    HistoricalIncident,
    TicketCategory,
    TicketClassification,
    TicketPriority,
    TicketProcessRequest,
)
from intelliticket_backend.services.agents.context import ContextRetrievalAgent
from intelliticket_backend.services.agents.diagnosis import DiagnosisAgent
from intelliticket_backend.services.agents.intake import IntakeAgent
from intelliticket_backend.services.agents.routing import RoutingAgent
from intelliticket_backend.services.llm import LlmClient
from intelliticket_backend.services.orchestrator import SupervisorOrchestrator
from intelliticket_backend.services.ticket_processing import TicketProcessingService

SAMPLE_TEXT = "线上支付服务出现超时告警，订单量从正常1000/min降到300/min"


class InvalidRouteClient(LlmClient):
    def structured_json_call(self, **_kwargs):  # type: ignore[no-untyped-def]
        return {"next_agent": "missing_agent", "message_type": "bad", "reason_summary": "bad"}


class MissingSopRepository(MockOpsDataRepository):
    def get_sops(self, service_name: str) -> list[dict]:
        return []


def _payment_service_record() -> dict:
    record = MockOpsDataRepository().resolve_service(SAMPLE_TEXT)
    assert record is not None
    return record


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


def _payment_context():
    return ContextRetrievalAgent().run(_payment_service_record(), DataMode.MOCK).context


def test_eval_unknown_service_abstains_without_inventing_context(tmp_path) -> None:
    service = TicketProcessingService(
        settings=Settings(ticket_history_db_path=tmp_path / "history.sqlite3")
    )

    result = service.process_ticket(
        request=TicketProcessRequest(
            text="未知系统出现异常告警",
            data_mode=DataMode.MOCK,
        ),
        ticket_id="TCK-20260715-EVAL0001",
        run_id="RUN-20260715-EVAL0001",
    )

    assert result.classification.affected_service is None
    assert result.context.service is None
    assert result.diagnosis.candidate_root_causes == []
    assert result.routing.recommended_team is None


def test_eval_service_alias_is_recognized() -> None:
    run = IntakeAgent().run(
        ticket_id="TCK-20260715-EVAL0002",
        text="payment 出现 timeout 告警",
        data_mode=DataMode.MOCK,
        observed_at="2026-07-15T00:00:00+00:00",
    )

    assert run.classification is not None
    assert run.classification.affected_service == "payment-service"


def test_eval_missing_required_metric_prevents_db_pool_root_cause() -> None:
    context = _payment_context()
    context.metrics = [
        metric for metric in context.metrics if metric.metric_name != "db_connection_pool_usage"
    ]

    run = DiagnosisAgent().run(_classification(), context, DataMode.MOCK)

    assert all("连接池耗尽" not in cause.cause for cause in run.diagnosis.candidate_root_causes)
    assert run.diagnosis.abstentions


def test_eval_stale_metric_prevents_db_pool_root_cause() -> None:
    context = _payment_context()
    context.metrics = [
        metric.model_copy(update={"quality": "stale"})
        if metric.metric_name == "db_connection_pool_usage"
        else metric
        for metric in context.metrics
    ]

    run = DiagnosisAgent().run(_classification(), context, DataMode.MOCK)

    assert all("连接池耗尽" not in cause.cause for cause in run.diagnosis.candidate_root_causes)
    assert run.diagnosis.abstentions


def test_eval_conflicting_incident_does_not_support_db_pool_root_cause() -> None:
    context = _payment_context()
    context.historical_incidents = [
        HistoricalIncident(
            evidence_id="ev_incident_conflict_001",
            incident_id="INC-CONFLICT",
            root_cause="网络抖动导致短暂超时",
            summary="历史相似工单指向网络抖动，而非连接池耗尽。",
            data_mode=DataMode.MOCK,
        )
    ]

    run = DiagnosisAgent().run(_classification(), context, DataMode.MOCK)

    assert all("连接池耗尽" not in cause.cause for cause in run.diagnosis.candidate_root_causes)
    assert run.diagnosis.abstentions


def test_eval_sop_missing_keeps_routing_explainable_without_sop_refs() -> None:
    repository = MissingSopRepository()
    context_run = ContextRetrievalAgent(repository=repository).run(
        repository.resolve_service(SAMPLE_TEXT),
        DataMode.MOCK,
    )
    diagnosis = DiagnosisAgent().run(
        _classification(),
        context_run.context,
        DataMode.MOCK,
    ).diagnosis

    run = RoutingAgent().run(context_run.context, diagnosis, DataMode.MOCK)

    assert run.routing.recommended_team == "支付系统运维组"
    assert run.routing.sop_refs == []
    assert any("未发现 SOP" in observation for observation in run.observations)


def test_eval_real_mode_request_fails_closed(tmp_path) -> None:
    service = TicketProcessingService(
        settings=Settings(ticket_history_db_path=tmp_path / "history.sqlite3")
    )

    with pytest.raises(AppError) as exc_info:
        service.process_ticket(
            TicketProcessRequest(
                text=SAMPLE_TEXT,
                data_mode=DataMode.REAL,
            )
        )

    assert exc_info.value.code == "UNSUPPORTED_DATA_MODE"


def test_eval_priority_boundary_is_explicit() -> None:
    service_record = _payment_service_record()
    p1 = IntakeAgent().run(
        ticket_id="TCK-20260715-EVAL0003",
        text="线上支付服务出现超时告警，订单量从正常1000/min降到500/min",
        data_mode=DataMode.MOCK,
        observed_at="2026-07-15T00:00:00+00:00",
    )
    p2 = IntakeAgent().run(
        ticket_id="TCK-20260715-EVAL0004",
        text="线上支付服务出现超时告警，订单量从正常1000/min降到501/min",
        data_mode=DataMode.MOCK,
        observed_at="2026-07-15T00:00:00+00:00",
    )

    assert service_record["criticality"] == "business_critical"
    assert p1.classification is not None and p1.classification.priority == TicketPriority.P1
    assert p2.classification is not None and p2.classification.priority == TicketPriority.P2


def test_eval_routing_abstains_without_service_context() -> None:
    context = _payment_context().model_copy(update={"service": None})
    diagnosis = DiagnosisAgent().run(_classification(), context, DataMode.MOCK).diagnosis

    run = RoutingAgent().run(context, diagnosis, DataMode.MOCK)

    assert run.status == "abstained"
    assert run.routing.recommended_team is None
    assert "人工确认" in run.routing.escalation


def test_eval_llm_route_invalid_fails_closed() -> None:
    orchestrator = SupervisorOrchestrator(llm_client=InvalidRouteClient(), route_mode="llm")

    with pytest.raises(AppError) as exc_info:
        orchestrator.run(
            TicketProcessRequest(
                text=SAMPLE_TEXT,
                data_mode=DataMode.MOCK,
            ),
            ticket_id="TCK-20260715-EVAL0005",
            run_id="RUN-20260715-EVAL0005",
        )

    assert exc_info.value.code == "ORCHESTRATOR_INVALID_ROUTE"
