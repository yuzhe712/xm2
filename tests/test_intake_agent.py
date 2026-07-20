from __future__ import annotations

import pytest

from intelliticket_backend.errors import AppError
from intelliticket_backend.repositories.mock_ops_data import MockOpsDataRepository
from intelliticket_backend.schemas.tickets import DataMode
from intelliticket_backend.services.agents.envelope import InternalTaskRequest
from intelliticket_backend.services.agents.intake import IntakeAgent

SAMPLE_TEXT = "线上支付服务出现超时告警，订单量从正常1000/min降到300/min"
OBSERVED_AT = "2026-07-14T10:16:00+08:00"


def test_intake_agent_classifies_payment_timeout_ticket() -> None:
    run = IntakeAgent().run(
        ticket_id="TCK-TEST-001",
        text=SAMPLE_TEXT,
        data_mode=DataMode.MOCK,
        observed_at=OBSERVED_AT,
    )

    assert run.agent_name == "ticket_intake_agent"
    assert run.status == "completed"
    assert run.iterations_used <= run.max_iterations
    assert run.max_tool_calls == 1
    assert run.classification is not None
    assert run.classification.affected_service == "payment-service"
    assert run.classification.priority == "P1"
    assert "timeout" in run.classification.symptoms
    assert "order_volume_drop" in run.classification.symptoms
    assert run.classification.extracted_metrics == {
        "order_qps_before": 1000,
        "order_qps_after": 300,
    }
    assert run.service_record is not None
    assert run.evidence_ids == ["ev_ticket_input_001", "ev_service_payment_001"]
    assert {item.evidence_id for item in run.evidence} == set(run.evidence_ids)
    assert all(item.data_mode == DataMode.MOCK for item in run.evidence)
    assert [step.action for step in run.react_steps] == [
        "validate_input",
        "resolve_service",
        "classify_priority",
        "finish",
    ]


def test_intake_agent_unknown_service_does_not_invent_context() -> None:
    run = IntakeAgent().run(
        ticket_id="TCK-TEST-002",
        text="未知系统出现异常告警",
        data_mode=DataMode.MOCK,
        observed_at=OBSERVED_AT,
    )

    assert run.status == "completed"
    assert run.classification is not None
    assert run.classification.affected_service is None
    assert run.classification.priority == "P3"
    assert run.service_record is None
    assert run.evidence_ids == ["ev_ticket_input_001"]
    assert run.classification.evidence_ids == ["ev_ticket_input_001"]


def test_intake_agent_real_mode_classifies_from_ticket_input_only() -> None:
    run = IntakeAgent().run(
        ticket_id="TCK-TEST-003",
        text=SAMPLE_TEXT,
        data_mode=DataMode.REAL,
        observed_at=OBSERVED_AT,
    )

    assert run.status == "completed"
    assert run.classification is not None
    assert run.service_record is None
    assert {item.data_mode for item in run.evidence} == {DataMode.REAL}
    assert run.evidence_ids == ["ev_ticket_input_001"]
    assert any("跳过 mock 服务目录" in observation for observation in run.observations)


def test_intake_agent_does_not_create_partial_metrics_from_one_min_value() -> None:
    run = IntakeAgent().run(
        ticket_id="TCK-TEST-004",
        text="线上支付服务出现超时告警，订单量约1000/min",
        data_mode=DataMode.MOCK,
        observed_at=OBSERVED_AT,
    )

    assert run.classification is not None
    assert run.classification.extracted_metrics == {}
    assert run.classification.priority == "P2"


class MalformedServiceRepository:
    def resolve_service(self, _text: str) -> dict:
        service = MockOpsDataRepository().resolve_service(SAMPLE_TEXT)
        assert service is not None
        service = dict(service)
        service["data_mode"] = "real"
        return service


def test_intake_agent_rejects_malformed_service_record() -> None:
    agent = IntakeAgent(repository=MalformedServiceRepository())

    with pytest.raises(AppError) as exc_info:
        agent.run(
            ticket_id="TCK-TEST-005",
            text=SAMPLE_TEXT,
            data_mode=DataMode.MOCK,
            observed_at=OBSERVED_AT,
        )

    assert exc_info.value.code == "INTAKE_EVIDENCE_INVALID"


def _intake_task_request(payload: dict) -> InternalTaskRequest:
    return InternalTaskRequest(
        task_id="task-intake-001",
        ticket_id="TCK-TEST-006",
        run_id="RUN-TEST-001",
        from_agent="ticket_processing_service",
        to_agent="ticket_intake_agent",
        message_type="intake_request",
        payload=payload,
        idempotency_key="TCK-TEST-006:intake",
    )


def test_intake_agent_handle_task_returns_internal_result() -> None:
    request = _intake_task_request(
        {
            "text": SAMPLE_TEXT,
            "data_mode": DataMode.MOCK.value,
            "observed_at": OBSERVED_AT,
        }
    )

    result = IntakeAgent().handle_task(request)

    assert result.status == "completed"
    assert result.error is None
    assert result.payload["classification"]["affected_service"] == "payment-service"
    assert result.payload["service_record"]["name"] == "payment-service"
    assert result.evidence_ids == ["ev_ticket_input_001", "ev_service_payment_001"]
    assert result.react_steps
    assert all("thought" not in step.model_dump() for step in result.react_steps)
    assert all("chain_of_thought" not in step.model_dump() for step in result.react_steps)


def test_intake_agent_handle_task_rejects_wrong_target() -> None:
    request = _intake_task_request({"text": SAMPLE_TEXT, "data_mode": DataMode.MOCK.value})
    request = request.model_copy(update={"to_agent": "diagnosis_agent"})

    result = IntakeAgent().handle_task(request)

    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "INVALID_AGENT_TARGET"


def test_intake_agent_handle_task_rejects_malformed_payload() -> None:
    request = _intake_task_request({"data_mode": DataMode.MOCK.value})

    result = IntakeAgent().handle_task(request)

    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "INVALID_TASK_PAYLOAD"
