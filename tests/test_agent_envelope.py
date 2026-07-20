from __future__ import annotations

import pytest
from pydantic import ValidationError

from intelliticket_backend.services.agents.diagnosis import DiagnosisAgent
from intelliticket_backend.services.agents.envelope import (
    AgentTaskError,
    InternalTaskRequest,
    InternalTaskResult,
    ReActStep,
)


def test_internal_task_request_requires_core_fields() -> None:
    request = InternalTaskRequest(
        task_id="task-001",
        ticket_id="TCK-001",
        run_id="RUN-001",
        from_agent="context_retrieval_agent",
        to_agent="diagnosis_agent",
        message_type="diagnosis_request",
        payload={"data_mode": "mock"},
        evidence_ids=["ev_service_payment_001"],
        idempotency_key="TCK-001:diagnosis",
    )

    assert request.to_agent == "diagnosis_agent"
    assert request.idempotency_key == "TCK-001:diagnosis"
    assert request.evidence_ids == ["ev_service_payment_001"]
    assert request.created_at


def test_internal_task_request_rejects_missing_required_fields() -> None:
    with pytest.raises(ValidationError):
        InternalTaskRequest(
            task_id="task-001",
            ticket_id="TCK-001",
            run_id="RUN-001",
            from_agent="context_retrieval_agent",
            to_agent="diagnosis_agent",
            message_type="diagnosis_request",
            payload={},
        )


def test_react_step_serializes_without_private_thought_fields() -> None:
    step = ReActStep(
        step_index=1,
        decision_summary="校验上下文。",
        action="validate_context",
        action_input_summary="service=payment-service",
        observation_summary="服务上下文可用。",
        evidence_ids=["ev_service_payment_001"],
    )

    dumped = step.model_dump()

    assert dumped["action"] == "validate_context"
    assert "thought" not in dumped
    assert "chain_of_thought" not in dumped
    assert "reasoning" not in dumped


def test_internal_task_result_carries_structured_error() -> None:
    result = InternalTaskResult(
        task_id="task-001",
        ticket_id="TCK-001",
        run_id="RUN-001",
        agent_name="diagnosis_agent",
        status="failed",
        error=AgentTaskError(
            code="INVALID_TASK_PAYLOAD",
            message="payload 无法通过 schema 校验",
            details={"field": "context"},
        ),
    )

    assert result.error is not None
    assert result.error.code == "INVALID_TASK_PAYLOAD"
    assert result.payload == {}
    assert result.react_steps == []


def test_base_agent_result_helpers_create_structured_errors() -> None:
    request = InternalTaskRequest(
        task_id="task-001",
        ticket_id="TCK-001",
        run_id="RUN-001",
        from_agent="routing_agent",
        to_agent="report_agent",
        message_type="diagnosis_request",
        payload={},
        idempotency_key="TCK-001:diagnosis",
    )

    wrong_target = DiagnosisAgent().wrong_target_result(request)
    invalid_payload = DiagnosisAgent().invalid_payload_result(request, ValueError("bad"))

    assert wrong_target.status == "failed"
    assert wrong_target.error is not None
    assert wrong_target.error.code == "INVALID_AGENT_TARGET"
    assert invalid_payload.status == "failed"
    assert invalid_payload.error is not None
    assert invalid_payload.error.code == "INVALID_TASK_PAYLOAD"
