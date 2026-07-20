from __future__ import annotations

import pytest

from intelliticket_backend.errors import AppError
from intelliticket_backend.schemas.tickets import DataMode
from intelliticket_backend.services.ops_knowledge import OpsKnowledgeService

SAMPLE_TEXT = "线上支付服务出现超时告警，订单量从正常1000/min降到300/min"


def test_lookup_service_catalog_returns_mock_provenance() -> None:
    result = OpsKnowledgeService().lookup_service_catalog(SAMPLE_TEXT)

    assert result.tool_name == "lookup_service_catalog"
    assert result.data_mode == DataMode.MOCK
    assert result.records[0]["name"] == "payment-service"
    assert result.evidence_ids == ["ev_service_payment_001"]
    assert result.evidence[0].data_mode == DataMode.MOCK
    assert result.evidence[0].source_type == "service_catalog"


def test_lookup_service_catalog_rejects_unknown_service() -> None:
    with pytest.raises(AppError) as exc_info:
        OpsKnowledgeService().lookup_service_catalog("未知系统告警")

    assert exc_info.value.code == "MCP_SERVICE_NOT_FOUND"
    assert exc_info.value.details["query"] == "未知系统告警"


def test_get_metric_snapshots_returns_evidence() -> None:
    result = OpsKnowledgeService().get_metric_snapshots("payment-service")

    assert result.tool_name == "get_metric_snapshots"
    assert result.records
    assert "ev_metric_db_pool_001" in result.evidence_ids
    assert {item.data_mode for item in result.evidence} == {DataMode.MOCK}
    assert all(item.metric_name for item in result.evidence)


def test_get_incident_history_returns_evidence() -> None:
    result = OpsKnowledgeService().get_incident_history("payment-service")

    assert result.tool_name == "get_incident_history"
    assert result.records
    assert "ev_incident_payment_db_pool_001" in result.evidence_ids
    assert {item.source_type for item in result.evidence} == {"incident_history"}


def test_get_sop_documents_returns_evidence() -> None:
    result = OpsKnowledgeService().get_sop_documents("payment-service")

    assert result.tool_name == "get_sop_documents"
    assert result.records
    assert "ev_sop_payment_timeout_001" in result.evidence_ids
    assert {item.source_type for item in result.evidence} == {"sop_document"}


def test_service_scoped_lookup_rejects_unknown_service() -> None:
    with pytest.raises(AppError) as exc_info:
        OpsKnowledgeService().get_metric_snapshots("unknown-service")

    assert exc_info.value.code == "MCP_SERVICE_NOT_FOUND"
    assert exc_info.value.details["service_name"] == "unknown-service"
