from __future__ import annotations

import pytest

from intelliticket_backend.errors import AppError
from intelliticket_backend.repositories.mock_ops_data import MockOpsDataRepository
from intelliticket_backend.schemas.tickets import DataMode
from intelliticket_backend.services.agents.context import (
    ContextRetrievalAgent,
    ContextRetrievalAgentLimits,
)
from intelliticket_backend.services.agents.envelope import InternalTaskRequest

SAMPLE_TEXT = "线上支付服务出现超时告警，订单量从正常1000/min降到300/min"


class FakeRealKnowledgeService:
    def search_sops(self, *, query: str, service_name: str | None, data_mode: DataMode, limit: int | None = None) -> list[dict]:
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


def _payment_service_record() -> dict:
    repository = MockOpsDataRepository()
    service_record = repository.resolve_service(SAMPLE_TEXT)
    assert service_record is not None
    return service_record


def test_context_retrieval_agent_returns_payment_context_with_provenance() -> None:
    service_record = _payment_service_record()

    run = ContextRetrievalAgent().run(service_record, DataMode.MOCK)

    assert run.agent_name == "context_retrieval_agent"
    assert run.status == "partial"
    assert run.iterations_used <= run.max_iterations
    assert run.max_tool_calls == 4
    assert run.context.service is not None
    assert run.context.service.owner_team == "支付系统运维组"
    assert run.context.metrics == []
    assert run.context.deployments == []
    assert run.context.historical_incidents
    assert run.context.sop_documents
    assert "未接入真实监控系统" in run.context.unknowns[0]
    assert "ev_service_payment_001" in run.evidence_ids
    assert "ev_metric_db_pool_001" not in run.evidence_ids
    assert run.evidence_ids == [item.evidence_id for item in run.evidence]
    assert {item.data_mode for item in run.evidence} == {DataMode.MOCK}
    assert [step.action for step in run.react_steps] == [
        "validate_service_record",
        "skip_mock_operational_facts",
        "retrieve_knowledge_context",
        "finish",
    ]


def test_context_retrieval_agent_abstains_without_service_record() -> None:
    run = ContextRetrievalAgent().run(None, DataMode.MOCK)

    assert run.status == "abstained"
    assert run.context.service is None
    assert run.evidence == []
    assert run.evidence_ids == []
    assert "未能从工单文本识别影响服务" in run.context.unknowns[0]


def test_context_retrieval_agent_real_mode_queries_real_knowledge_without_mock_context() -> None:
    run = ContextRetrievalAgent(knowledge_service=FakeRealKnowledgeService()).run(
        _payment_service_record(), DataMode.REAL, SAMPLE_TEXT
    )

    assert run.status == "partial"
    assert run.context.service is None
    assert run.context.sop_documents
    assert run.evidence
    assert {item.data_mode for item in run.evidence} == {DataMode.REAL}
    assert all(not (item.trace_uri or "").startswith("mock_data/") for item in run.evidence)
    assert "未接入真实 CMDB/监控/部署系统" in run.context.unknowns[0]


def test_context_retrieval_agent_rejects_malformed_service_record() -> None:
    service_record = dict(_payment_service_record())
    del service_record["evidence_id"]

    with pytest.raises(AppError) as exc_info:
        ContextRetrievalAgent().run(service_record, DataMode.MOCK)

    assert exc_info.value.code == "CONTEXT_EVIDENCE_INVALID"
    assert exc_info.value.details["missing"] == ["evidence_id"]


def test_context_retrieval_agent_rejects_non_mock_service_record() -> None:
    service_record = dict(_payment_service_record())
    service_record["data_mode"] = "real"

    with pytest.raises(AppError) as exc_info:
        ContextRetrievalAgent().run(service_record, DataMode.MOCK)

    assert exc_info.value.code == "CONTEXT_EVIDENCE_INVALID"
    assert exc_info.value.details["data_mode"] == "real"


def test_context_retrieval_agent_abstains_when_tool_call_limit_is_too_low() -> None:
    service_record = _payment_service_record()
    agent = ContextRetrievalAgent(limits=ContextRetrievalAgentLimits(max_tool_calls=1))

    run = agent.run(service_record, DataMode.MOCK)

    assert run.status == "abstained"
    assert run.context.service is None
    assert run.evidence == []
    assert "工具调用上限不足" in run.context.unknowns[0]


class SopFailureRepository(MockOpsDataRepository):
    def get_sops(self, service_name: str) -> list[dict]:
        raise AppError("MOCK_DATA_LOAD_ERROR", "SOP mock 数据不可用")


def test_context_retrieval_agent_returns_partial_context_for_optional_source_failure() -> None:
    repository = SopFailureRepository()
    service_record = repository.resolve_service(SAMPLE_TEXT)
    assert service_record is not None

    run = ContextRetrievalAgent(repository=repository).run(service_record, DataMode.MOCK)

    assert run.status == "partial"
    assert run.context.service is not None
    assert run.context.metrics == []
    assert run.context.sop_documents == []
    assert run.context.unknowns
    assert any("SOP 文档" in unknown for unknown in run.context.unknowns)
    assert "ev_service_payment_001" in run.evidence_ids
    assert "ev_sop_payment_timeout_001" not in run.evidence_ids


def _context_task_request(payload: dict) -> InternalTaskRequest:
    return InternalTaskRequest(
        task_id="task-context-001",
        ticket_id="TCK-TEST-001",
        run_id="RUN-TEST-001",
        from_agent="ticket_intake_agent",
        to_agent="context_retrieval_agent",
        message_type="context_request",
        payload=payload,
        evidence_ids=["ev_service_payment_001"],
        idempotency_key="TCK-TEST-001:context",
    )


def test_context_retrieval_agent_handle_task_returns_internal_result() -> None:
    service_record = _payment_service_record()
    request = _context_task_request(
        {"service_record": service_record, "data_mode": DataMode.MOCK.value}
    )

    result = ContextRetrievalAgent().handle_task(request)

    assert result.status == "partial"
    assert result.error is None
    assert result.payload["context"]["service"]["name"] == "payment-service"
    assert result.payload["evidence"]
    assert "ev_service_payment_001" in result.evidence_ids
    assert result.react_steps
    assert all("thought" not in step.model_dump() for step in result.react_steps)


def test_context_retrieval_agent_handle_task_rejects_wrong_target() -> None:
    request = _context_task_request({"service_record": None, "data_mode": DataMode.MOCK.value})
    request = request.model_copy(update={"to_agent": "routing_agent"})

    result = ContextRetrievalAgent().handle_task(request)

    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "INVALID_AGENT_TARGET"


def test_context_retrieval_agent_handle_task_rejects_malformed_payload() -> None:
    request = _context_task_request({"service_record": []})

    result = ContextRetrievalAgent().handle_task(request)

    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "INVALID_TASK_PAYLOAD"
