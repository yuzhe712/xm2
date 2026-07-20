from __future__ import annotations

import pytest
from pydantic import ValidationError

from intelliticket_backend.schemas.orchestration import (
    RouteDecision,
    SupervisorState,
)
from intelliticket_backend.schemas.tickets import DataMode, TicketProcessRequest


def test_route_decision_accepts_valid_route() -> None:
    decision = RouteDecision(
        next_agent="ticket_intake_agent",
        message_type="ticket_intake_request",
        reason_summary="先执行 intake。",
        required_inputs=[],
        evidence_ids=[],
        requires_human_review=False,
    )

    assert decision.next_agent == "ticket_intake_agent"
    assert decision.message_type == "ticket_intake_request"


def test_route_decision_rejects_invalid_agent() -> None:
    with pytest.raises(ValidationError):
        RouteDecision(
            next_agent="missing_agent",
            message_type="missing_request",
            reason_summary="非法 Agent。",
        )


@pytest.mark.parametrize(
    "field_name",
    ["chain_of_thought", "tool_call", "diagnosis"],
)
def test_route_decision_rejects_private_tool_or_business_fields(field_name: str) -> None:
    payload = {
        "next_agent": "ticket_intake_agent",
        "message_type": "ticket_intake_request",
        "reason_summary": "先执行 intake。",
        field_name: "not allowed",
    }

    with pytest.raises(ValidationError):
        RouteDecision.model_validate(payload)


def test_supervisor_state_is_json_serializable() -> None:
    state = SupervisorState(
        ticket_id="TCK-001",
        run_id="RUN-001",
        request=TicketProcessRequest(text="线上支付服务出现超时告警", data_mode=DataMode.MOCK),
        max_steps=8,
    )

    dumped = state.model_dump(mode="json")

    assert dumped["ticket_id"] == "TCK-001"
    assert dumped["request"]["data_mode"] == "mock"
    assert dumped["agent_runs"] == []
