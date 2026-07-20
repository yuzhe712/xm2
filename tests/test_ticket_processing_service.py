from __future__ import annotations

from threading import Event

import pytest

from intelliticket_backend.config import Settings
from intelliticket_backend.errors import AppError
from intelliticket_backend.repositories.ticket_history import TicketHistoryRepository
from intelliticket_backend.schemas.tickets import DataMode, DeskId, TicketProcessRequest
from intelliticket_backend.services.orchestrator import SupervisorOrchestrator
from intelliticket_backend.services.ticket_processing import TicketProcessingService

SAMPLE_TEXT = "线上支付服务出现超时告警，订单量从正常1000/min降到300/min"


def test_process_payment_timeout_ticket_returns_full_mvp_result() -> None:
    result = TicketProcessingService().process_ticket(
        TicketProcessRequest(text=SAMPLE_TEXT, data_mode=DataMode.MOCK)
    )

    assert result.ticket_id.startswith("TCK-")
    assert result.run_id.startswith("RUN-")
    assert result.data_mode == DataMode.MOCK
    assert result.classification.category == "ops_alert"
    assert result.classification.priority == "P1"
    assert result.classification.affected_service == "payment-service"
    assert "timeout" in result.classification.symptoms
    assert "order_volume_drop" in result.classification.symptoms
    assert result.context.service is not None
    assert result.context.service.owner_team == "支付系统运维组"
    assert result.diagnosis.candidate_root_causes
    assert result.routing.recommended_team == "支付系统运维组"
    assert result.routing.recommended_actions
    assert result.ops_result is not None
    assert result.ops_result.assigned_team == "支付系统运维组"
    assert result.ops_result.candidate_root_causes
    assert result.support_result is None
    assert result.report.recommendations
    assert [item.step for item in result.agent_trace] == [
        "ticket_intake",
        "context_retrieval",
        "diagnosis",
        "routing",
        "review",
        "report",
    ]
    intake_trace = next(item for item in result.agent_trace if item.step == "ticket_intake")
    assert "ticket_intake_agent completed" in intake_trace.summary
    context_trace = next(item for item in result.agent_trace if item.step == "context_retrieval")
    assert "context_retrieval_agent" in context_trace.summary
    assert context_trace.status in {"completed", "partial"}
    assert context_trace.evidence_ids
    diagnosis_trace = next(item for item in result.agent_trace if item.step == "diagnosis")
    assert "diagnosis_agent completed" in diagnosis_trace.summary
    routing_trace = next(item for item in result.agent_trace if item.step == "routing")
    assert "routing_agent completed" in routing_trace.summary
    report_trace = next(item for item in result.agent_trace if item.step == "report")
    assert "report_agent completed" in report_trace.summary
    assert report_trace.evidence_ids

    evidence_id_list = [item.evidence_id for item in result.evidence]
    assert len(evidence_id_list) == len(set(evidence_id_list))
    known_evidence_ids = set(evidence_id_list)
    referenced_ids = set(result.classification.evidence_ids)
    for cause in result.diagnosis.candidate_root_causes:
        referenced_ids.update(cause.evidence_ids)
    for action in result.routing.recommended_actions:
        referenced_ids.update(action.evidence_ids)
    for trace in result.agent_trace:
        referenced_ids.update(trace.evidence_ids)
    assert referenced_ids <= known_evidence_ids


def test_process_support_ticket_uses_support_workflow_and_kb() -> None:
    result = TicketProcessingService().process_ticket(
        TicketProcessRequest(
            text="新入职同事无法访问支付服务只读监控面板，需要开通权限",
            data_mode=DataMode.MOCK,
            desk_id=DeskId.SUPPORT,
        )
    )

    assert result.data_mode == DataMode.MOCK
    assert result.classification.category == "support_request"
    assert result.classification.affected_service == "monitoring-console"
    assert result.routing.recommended_team == "内部支持服务台"
    assert result.diagnosis.candidate_root_causes == []
    assert result.diagnosis.abstentions == [
        "support desk 使用知识库回复建议流程，不生成运维根因诊断。"
    ]
    assert result.report.title.startswith("内部支持回复建议")
    assert result.support_result is not None
    assert result.support_result.recommended_team == "内部支持服务台"
    assert result.support_result.reply_suggestions
    assert result.ops_result is None
    assert [item.step for item in result.agent_trace] == [
        "support_intake",
        "support_kb_retrieval",
        "support_routing",
        "support_reply_suggestion",
    ]
    assert {item.source_type for item in result.evidence} == {"knowledge_article"}
    assert {item.producer for item in result.evidence} == {"support_kb_retrieval_agent"}
    assert {item.run_id for item in result.evidence} == {result.run_id}
    assert all(item.quality_reason for item in result.evidence)
    assert {item.evidence_id for item in result.evidence} >= set(
        result.routing.recommended_actions[0].evidence_ids
    )


def test_process_support_ticket_real_mode_completes_without_mock_knowledge() -> None:
    result = TicketProcessingService().process_ticket(
        TicketProcessRequest(
            text="新入职同事无法访问支付服务只读监控面板，需要开通权限",
            data_mode=DataMode.REAL,
            desk_id=DeskId.SUPPORT,
        )
    )

    assert result.data_mode == DataMode.REAL
    assert result.classification.category == "support_request"
    assert result.evidence == []
    assert result.support_result is not None
    assert result.support_result.matched_articles == []
    assert result.report.unknowns == ["未匹配到内部支持知识库文章，需人工补充上下文。"]
    assert "mock" not in " ".join(result.report.assumptions)
    assert {item.step for item in result.agent_trace} == {
        "support_intake",
        "support_kb_retrieval",
        "support_routing",
        "support_reply_suggestion",
    }


def test_process_ticket_persists_completed_result(tmp_path) -> None:
    db_path = tmp_path / "history.sqlite3"
    service = TicketProcessingService(
        settings=Settings(ticket_history_db_path=db_path),
    )

    result = service.process_ticket(
        TicketProcessRequest(text=SAMPLE_TEXT, data_mode=DataMode.MOCK)
    )

    detail = TicketHistoryRepository(db_path).get_ticket(result.ticket_id)
    assert detail is not None
    assert detail.latest_run.response.ticket_id == result.ticket_id
    assert detail.latest_run.response.data_mode == DataMode.MOCK
    assert detail.latest_run.agent_runs
    assert detail.latest_run.supervisor_decisions[-1].next_agent == "finish"


def test_process_support_ticket_persists_support_agent_runs(tmp_path) -> None:
    db_path = tmp_path / "history.sqlite3"
    service = TicketProcessingService(settings=Settings(ticket_history_db_path=db_path))

    result = service.process_ticket(
        TicketProcessRequest(
            text="办公网访问内部工单系统间歇性失败，部分用户反馈连接超时",
            data_mode=DataMode.MOCK,
            desk_id=DeskId.SUPPORT,
        )
    )

    detail = TicketHistoryRepository(db_path).get_ticket(result.ticket_id)
    assert detail is not None
    assert detail.desk_id == DeskId.SUPPORT
    assert detail.latest_run.response.classification.category == "support_request"
    assert [run.step for run in detail.latest_run.agent_runs] == [
        "support_intake",
        "support_kb_retrieval",
        "support_routing",
        "support_reply_suggestion",
    ]
    assert [run.agent_name for run in detail.latest_run.agent_runs] == [
        "support_intake_service",
        "support_kb_retrieval_agent",
        "support_routing_service",
        "support_reply_agent",
    ]
    assert detail.latest_run.supervisor_decisions[-1].next_agent == "finish"


def test_unsupported_support_workflow_strategy_fails_closed(tmp_path) -> None:
    service = TicketProcessingService(
        settings=Settings(
            ticket_history_db_path=tmp_path / "history.sqlite3",
            support_workflow_strategy="llm",
        )
    )

    with pytest.raises(AppError) as exc_info:
        service.process_ticket(
            TicketProcessRequest(
                text="无法访问监控面板",
                data_mode=DataMode.MOCK,
                desk_id=DeskId.SUPPORT,
            )
        )

    assert exc_info.value.code == "UNSUPPORTED_SUPPORT_WORKFLOW_STRATEGY"


def test_process_ops_ticket_real_mode_does_not_return_mock_evidence() -> None:
    result = TicketProcessingService().process_ticket(
        TicketProcessRequest(text=SAMPLE_TEXT, data_mode=DataMode.REAL)
    )

    assert result.data_mode == DataMode.REAL
    assert result.classification.category == "ops_alert"
    assert {item.data_mode for item in result.evidence} == {DataMode.REAL}
    assert all(not (item.trace_uri or "").startswith("mock_data/") for item in result.evidence)


def test_real_mode_persists_without_mock_evidence(tmp_path) -> None:
    db_path = tmp_path / "history.sqlite3"
    service = TicketProcessingService(settings=Settings(ticket_history_db_path=db_path))

    result = service.process_ticket(TicketProcessRequest(text=SAMPLE_TEXT, data_mode=DataMode.REAL))
    detail = TicketHistoryRepository(db_path).get_ticket(result.ticket_id)

    assert detail is not None
    assert detail.latest_run.response.data_mode == DataMode.REAL
    assert all(
        item.data_mode == DataMode.REAL for item in detail.latest_run.response.evidence
    )


def test_process_ticket_persists_failed_run(tmp_path) -> None:
    db_path = tmp_path / "history.sqlite3"
    service = TicketProcessingService(
        settings=Settings(ticket_history_db_path=db_path),
        orchestrator=SupervisorOrchestrator(route_mode="deterministic", max_steps=1),
    )

    with pytest.raises(AppError) as exc_info:
        service.process_ticket(TicketProcessRequest(text=SAMPLE_TEXT, data_mode=DataMode.MOCK))

    listing = TicketHistoryRepository(db_path).list_tickets(limit=20, offset=0)
    detail = TicketHistoryRepository(db_path).get_ticket(listing.items[0].ticket_id)

    assert exc_info.value.code == "ORCHESTRATOR_STEP_LIMIT_EXCEEDED"
    assert listing.total == 1
    assert listing.items[0].status == "failed"
    assert detail is not None
    assert detail.latest_run.status == "failed"
    assert detail.latest_run.response is None
    assert detail.latest_run.error is not None
    assert detail.latest_run.error.code == "ORCHESTRATOR_STEP_LIMIT_EXCEEDED"


def test_process_ticket_persists_cancelled_run(tmp_path) -> None:
    db_path = tmp_path / "history.sqlite3"
    service = TicketProcessingService(settings=Settings(ticket_history_db_path=db_path))
    cancel_event = Event()
    cancel_event.set()

    with pytest.raises(AppError) as exc_info:
        service.process_ticket(
            TicketProcessRequest(text=SAMPLE_TEXT, data_mode=DataMode.MOCK),
            cancel_event=cancel_event,
            ticket_id="TCK-20260715-ABCDEF12",
            run_id="RUN-20260715-1234ABCD",
        )

    detail = TicketHistoryRepository(db_path).get_ticket("TCK-20260715-ABCDEF12")

    assert exc_info.value.code == "PROCESSING_CANCELLED"
    assert detail is not None
    assert detail.latest_run.status == "cancelled"
    assert detail.latest_run.response is None
    assert detail.latest_run.error is not None
    assert detail.latest_run.error.code == "PROCESSING_CANCELLED"


def test_unknown_service_does_not_invent_context_or_root_cause() -> None:
    result = TicketProcessingService().process_ticket(
        TicketProcessRequest(text="未知系统出现异常告警", data_mode=DataMode.MOCK)
    )

    assert result.classification.affected_service is None
    assert result.context.service is None
    assert result.diagnosis.candidate_root_causes == []
    assert result.diagnosis.abstentions
    assert result.routing.recommended_team is None
