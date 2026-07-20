from __future__ import annotations

from threading import Event
from typing import Any

import pytest

from intelliticket_backend.errors import AppError
from intelliticket_backend.schemas.orchestration import RouteDecision
from intelliticket_backend.schemas.tickets import DataMode, TicketProcessRequest
from intelliticket_backend.services.agents.envelope import (
    AgentTaskError,
    InternalTaskRequest,
    InternalTaskResult,
)
from intelliticket_backend.services.agents.intake import IntakeAgent
from intelliticket_backend.services.llm import LlmClient, LlmClientError
from intelliticket_backend.services.orchestrator import (
    OrchestrationRunError,
    SupervisorOrchestrator,
)

SAMPLE_TEXT = "线上支付服务出现超时告警，订单量从正常1000/min降到300/min"


class QueueLlmClient(LlmClient):
    def __init__(self, decisions: list[Any]) -> None:
        self.decisions = decisions

    def structured_json_call(self, **_kwargs):  # type: ignore[no-untyped-def]
        if not self.decisions:
            raise AssertionError("No more queued decisions")
        return self.decisions.pop(0)


class FailingLlmClient(LlmClient):
    def structured_json_call(self, **_kwargs):  # type: ignore[no-untyped-def]
        raise LlmClientError("LLM_TIMEOUT", "timeout", {"provider": "deepseek"})


class FailingIntakeAgent(IntakeAgent):
    def handle_task(self, request: InternalTaskRequest) -> InternalTaskResult:
        return InternalTaskResult(
            task_id=request.task_id,
            ticket_id=request.ticket_id,
            run_id=request.run_id,
            agent_name=self.name,
            status="failed",
            error=AgentTaskError(
                code="INTAKE_FAILED",
                message="intake failed",
                details={},
            ),
        )


def decision(next_agent: str, evidence_ids: list[str] | None = None) -> RouteDecision:
    if next_agent in {"finish", "abstain"}:
        message_type = next_agent
    else:
        message_type = f"{next_agent}_request"
    return RouteDecision(
        next_agent=next_agent,
        message_type=message_type,
        reason_summary=f"选择 {next_agent}",
        evidence_ids=evidence_ids or [],
    )


def test_happy_path_routes_all_agents_and_finishes() -> None:
    orchestrator = SupervisorOrchestrator(route_mode="deterministic")

    result = orchestrator.run(
        TicketProcessRequest(text=SAMPLE_TEXT, data_mode=DataMode.MOCK),
        ticket_id="TCK-001",
        run_id="RUN-001",
    )

    assert result.ticket_id == "TCK-001"
    assert result.run_id == "RUN-001"
    assert result.classification.affected_service == "payment-service"
    assert result.diagnosis.candidate_root_causes
    assert result.routing.recommended_actions
    assert [item.step for item in result.agent_trace] == [
        "ticket_intake",
        "context_retrieval",
        "diagnosis",
        "routing",
        "review",
        "report",
    ]
    evidence_ids = {item.evidence_id for item in result.evidence}
    for trace in result.agent_trace:
        assert set(trace.evidence_ids) <= evidence_ids


def test_run_with_audit_returns_agent_runs_and_route_decisions() -> None:
    orchestrator = SupervisorOrchestrator(route_mode="deterministic")

    result = orchestrator.run_with_audit(
        TicketProcessRequest(text=SAMPLE_TEXT, data_mode=DataMode.MOCK),
        ticket_id="TCK-001",
        run_id="RUN-001",
    )

    assert result.response.ticket_id == "TCK-001"
    assert len(result.agent_runs) == 6
    assert len(result.route_decisions) == 7
    assert result.route_decisions[-1].next_agent == "finish"
    assert result.started_at
    assert result.completed_at


def test_llm_path_can_route_all_agents_and_finish() -> None:
    llm = QueueLlmClient(
        [
            decision("ticket_intake_agent"),
            decision("context_retrieval_agent"),
            decision("diagnosis_agent"),
            decision("routing_agent"),
            decision("reviewer_agent"),
            decision("report_agent"),
            decision("finish"),
        ]
    )
    orchestrator = SupervisorOrchestrator(llm_client=llm, route_mode="llm")

    result = orchestrator.run(
        TicketProcessRequest(text=SAMPLE_TEXT, data_mode=DataMode.MOCK),
        ticket_id="TCK-001",
        run_id="RUN-001",
    )

    assert result.classification.priority == "P1"
    assert result.report.recommendations


def test_invalid_route_fails_closed() -> None:
    orchestrator = SupervisorOrchestrator(
        llm_client=QueueLlmClient([{"next_agent": "missing_agent", "reason_summary": "bad"}]),
        route_mode="llm",
    )

    with pytest.raises(AppError) as exc_info:
        orchestrator.run(
            TicketProcessRequest(text=SAMPLE_TEXT, data_mode=DataMode.MOCK),
            ticket_id="TCK-001",
            run_id="RUN-001",
        )

    assert exc_info.value.code == "ORCHESTRATOR_INVALID_ROUTE"


def test_prerequisite_missing_is_rejected() -> None:
    orchestrator = SupervisorOrchestrator(
        llm_client=QueueLlmClient([decision("diagnosis_agent")]),
        route_mode="llm",
    )

    with pytest.raises(AppError) as exc_info:
        orchestrator.run(
            TicketProcessRequest(text=SAMPLE_TEXT, data_mode=DataMode.MOCK),
            ticket_id="TCK-001",
            run_id="RUN-001",
        )

    assert exc_info.value.code == "ORCHESTRATOR_PREREQUISITE_MISSING"


def test_unknown_evidence_id_is_rejected() -> None:
    orchestrator = SupervisorOrchestrator(
        llm_client=QueueLlmClient([decision("ticket_intake_agent", ["ev_fake_001"])]),
        route_mode="llm",
    )

    with pytest.raises(AppError) as exc_info:
        orchestrator.run(
            TicketProcessRequest(text=SAMPLE_TEXT, data_mode=DataMode.MOCK),
            ticket_id="TCK-001",
            run_id="RUN-001",
        )

    assert exc_info.value.code == "ORCHESTRATOR_UNKNOWN_EVIDENCE_REF"


def test_private_thought_like_field_is_rejected() -> None:
    orchestrator = SupervisorOrchestrator(
        llm_client=QueueLlmClient(
            [
                {
                    "next_agent": "ticket_intake_agent",
                    "message_type": "ticket_intake_request",
                    "reason_summary": "bad",
                    "chain_of_thought": "secret",
                }
            ]
        ),
        route_mode="llm",
    )

    with pytest.raises(AppError) as exc_info:
        orchestrator.run(
            TicketProcessRequest(text=SAMPLE_TEXT, data_mode=DataMode.MOCK),
            ticket_id="TCK-001",
            run_id="RUN-001",
        )

    assert exc_info.value.code == "ORCHESTRATOR_PRIVATE_FIELD_REJECTED"


def test_llm_unavailable_does_not_fallback() -> None:
    orchestrator = SupervisorOrchestrator(llm_client=FailingLlmClient(), route_mode="llm")

    with pytest.raises(AppError) as exc_info:
        orchestrator.run(
            TicketProcessRequest(text=SAMPLE_TEXT, data_mode=DataMode.MOCK),
            ticket_id="TCK-001",
            run_id="RUN-001",
        )

    assert exc_info.value.code == "LLM_ROUTE_FAILED"


def test_max_step_limit_is_enforced() -> None:
    orchestrator = SupervisorOrchestrator(route_mode="deterministic", max_steps=1)

    with pytest.raises(AppError) as exc_info:
        orchestrator.run(
            TicketProcessRequest(text=SAMPLE_TEXT, data_mode=DataMode.MOCK),
            ticket_id="TCK-001",
            run_id="RUN-001",
        )

    assert exc_info.value.code == "ORCHESTRATOR_STEP_LIMIT_EXCEEDED"


def test_agent_failure_stops_orchestration() -> None:
    orchestrator = SupervisorOrchestrator(
        route_mode="deterministic",
        intake_agent=FailingIntakeAgent(),
    )

    with pytest.raises(AppError) as exc_info:
        orchestrator.run(
            TicketProcessRequest(text=SAMPLE_TEXT, data_mode=DataMode.MOCK),
            ticket_id="TCK-001",
            run_id="RUN-001",
        )

    assert exc_info.value.code == "AGENT_TASK_FAILED"
    assert isinstance(exc_info.value, OrchestrationRunError)
    assert exc_info.value.run_failure.status == "failed"
    assert exc_info.value.run_failure.agent_runs[0].status == "failed"
    assert exc_info.value.run_failure.agent_runs[0].error is not None


def test_cancelled_run_error_carries_audit_snapshot() -> None:
    cancel_event = Event()
    cancel_event.set()
    orchestrator = SupervisorOrchestrator(route_mode="deterministic")

    with pytest.raises(AppError) as exc_info:
        orchestrator.run(
            TicketProcessRequest(text=SAMPLE_TEXT, data_mode=DataMode.MOCK),
            ticket_id="TCK-001",
            run_id="RUN-001",
            cancel_event=cancel_event,
        )

    assert exc_info.value.code == "PROCESSING_CANCELLED"
    assert isinstance(exc_info.value, OrchestrationRunError)
    assert exc_info.value.run_failure.status == "cancelled"
    assert exc_info.value.run_failure.ticket_id == "TCK-001"
    assert exc_info.value.run_failure.run_id == "RUN-001"


def test_unknown_service_does_not_invent_context_or_root_cause() -> None:
    orchestrator = SupervisorOrchestrator(route_mode="deterministic")

    result = orchestrator.run(
        TicketProcessRequest(text="未知系统出现异常告警", data_mode=DataMode.MOCK),
        ticket_id="TCK-001",
        run_id="RUN-001",
    )

    assert result.classification.affected_service is None
    assert result.context.service is None
    assert result.diagnosis.candidate_root_causes == []
    assert result.routing.recommended_team is None
