from __future__ import annotations

from typing import Any

from intelliticket_backend.errors import AppError
from intelliticket_backend.repositories.mock_ops_data import MockOpsDataRepository
from intelliticket_backend.schemas.mcp_tools import OpsKnowledgeToolResult
from intelliticket_backend.schemas.tickets import DataMode, Evidence


class OpsKnowledgeService:
    """面向 MCP adapter 的 mock 运维知识查询服务。"""

    def __init__(self, repository: MockOpsDataRepository | None = None) -> None:
        self.repository = repository or MockOpsDataRepository()

    def lookup_service_catalog(self, query: str) -> OpsKnowledgeToolResult:
        service_record = self.repository.resolve_service(query)
        if service_record is None:
            raise AppError(
                "MCP_SERVICE_NOT_FOUND",
                "未从 mock 服务目录识别到服务",
                details={"query": query},
            )
        evidence = [self._record_to_evidence(service_record)]
        return OpsKnowledgeToolResult(
            tool_name="lookup_service_catalog",
            records=[self._public_record(service_record)],
            evidence=evidence,
            evidence_ids=[item.evidence_id for item in evidence],
        )

    def get_metric_snapshots(self, service_name: str) -> OpsKnowledgeToolResult:
        canonical_service_name = self._canonical_service_name(service_name)
        return self._service_scoped_result(
            tool_name="get_metric_snapshots",
            records=self.repository.get_metrics(canonical_service_name),
        )

    def get_incident_history(self, service_name: str) -> OpsKnowledgeToolResult:
        canonical_service_name = self._canonical_service_name(service_name)
        return self._service_scoped_result(
            tool_name="get_incident_history",
            records=self.repository.get_incidents(canonical_service_name),
        )

    def get_sop_documents(self, service_name: str) -> OpsKnowledgeToolResult:
        canonical_service_name = self._canonical_service_name(service_name)
        return self._service_scoped_result(
            tool_name="get_sop_documents",
            records=self.repository.get_sops(canonical_service_name),
        )

    def _service_scoped_result(
        self,
        tool_name: str,
        records: list[dict[str, Any]],
    ) -> OpsKnowledgeToolResult:
        evidence = [self._record_to_evidence(record) for record in records]
        return OpsKnowledgeToolResult(
            tool_name=tool_name,
            records=[self._public_record(record) for record in records],
            evidence=evidence,
            evidence_ids=[item.evidence_id for item in evidence],
            unknowns=[] if records else [f"mock 数据中没有对应的 {tool_name} 记录。"],
        )

    def _canonical_service_name(self, service_name: str) -> str:
        services = self.repository.load_all()["services"]
        for service in services:
            if (
                service.get("name") == service_name
                or service_name in service.get("aliases", [])
                or service.get("display_name") == service_name
            ):
                return str(service["name"])
        raise AppError(
            "MCP_SERVICE_NOT_FOUND",
            "mock 服务目录中不存在该服务",
            details={"service_name": service_name},
        )

    def _record_to_evidence(self, record: dict[str, Any]) -> Evidence:
        try:
            return Evidence(
                evidence_id=record["evidence_id"],
                source_type=record["source_type"],
                source_id=record["source_id"],
                source_name=record["source_name"],
                observed_at=record.get("observed_at"),
                retrieved_at=record.get("retrieved_at"),
                service=record.get("service"),
                metric_name=record.get("metric_name"),
                value=record.get("value"),
                unit=record.get("unit"),
                quality=record["quality"],
                data_mode=DataMode.MOCK,
                confidence=record.get("confidence"),
                summary=record["summary"],
            )
        except KeyError as exc:
            raise AppError(
                "MCP_MOCK_DATA_INVALID",
                "mock 数据缺少 MCP 输出所需的证据字段",
                details={"missing": str(exc)},
            ) from exc

    def _public_record(self, record: dict[str, Any]) -> dict[str, Any]:
        public = dict(record)
        public["data_mode"] = DataMode.MOCK.value
        return public
