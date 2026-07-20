from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import status

from intelliticket_backend.config import get_settings
from intelliticket_backend.errors import AppError
from intelliticket_backend.schemas.tickets import DeskId


class MockOpsDataRepository:
    """本地 mock 运维数据仓库。"""

    FILES = {
        "services": "services.json",
        "metrics": "metrics.json",
        "deployments": "deploy_records.json",
        "incidents": "incidents.json",
        "sops": "sop_docs.json",
        "catalog_items": "catalog_items.json",
        "support_kb": "support_kb.json",
    }

    REQUIRED_EVIDENCE_FIELDS = {
        "evidence_id",
        "source_type",
        "source_id",
        "source_name",
        "quality",
        "data_mode",
        "summary",
    }

    def __init__(self, data_dir: Path | None = None) -> None:
        settings = get_settings()
        configured_dir = data_dir or settings.mock_data_dir
        self.data_dir = (
            configured_dir if configured_dir.is_absolute() else Path.cwd() / configured_dir
        )

    def load_all(self) -> dict[str, list[dict[str, Any]]]:
        return {name: self._load_file(filename) for name, filename in self.FILES.items()}

    def resolve_service(self, text: str) -> dict[str, Any] | None:
        normalized_text = text.lower()
        for service in self._load_file(self.FILES["services"]):
            names = [service["name"], service.get("display_name", ""), *service.get("aliases", [])]
            if any(name and name.lower() in normalized_text for name in names):
                return service
        return None

    def get_metrics(self, service_name: str) -> list[dict[str, Any]]:
        return self._filter_by_service("metrics", service_name)

    def get_deployments(self, service_name: str) -> list[dict[str, Any]]:
        return self._filter_by_service("deployments", service_name)

    def get_incidents(self, service_name: str) -> list[dict[str, Any]]:
        return self._filter_by_service("incidents", service_name)

    def get_sops(self, service_name: str) -> list[dict[str, Any]]:
        return self._filter_by_service("sops", service_name)

    def get_catalog_items(self, desk_id: DeskId) -> list[dict[str, Any]]:
        return self._filter_by_desk("catalog_items", desk_id)

    def get_knowledge_articles(self, desk_id: DeskId) -> list[dict[str, Any]]:
        return self._filter_by_desk("support_kb", desk_id)

    def _filter_by_service(self, key: str, service_name: str) -> list[dict[str, Any]]:
        return [
            record
            for record in self._load_file(self.FILES[key])
            if record.get("service") == service_name
        ]

    def _filter_by_desk(self, key: str, desk_id: DeskId) -> list[dict[str, Any]]:
        return [
            record
            for record in self._load_file(self.FILES[key])
            if record.get("desk_scope") == desk_id.value
        ]

    def _load_file(self, filename: str) -> list[dict[str, Any]]:
        path = self.data_dir / filename
        try:
            with path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except FileNotFoundError as exc:
            raise AppError(
                "MOCK_DATA_LOAD_ERROR",
                f"mock 数据文件不存在: {filename}",
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                {"path": str(path)},
            ) from exc
        except json.JSONDecodeError as exc:
            raise AppError(
                "MOCK_DATA_LOAD_ERROR",
                f"mock 数据文件不是合法 JSON: {filename}",
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                {"path": str(path)},
            ) from exc

        if not isinstance(data, list):
            raise AppError(
                "MOCK_DATA_LOAD_ERROR",
                f"mock 数据文件必须是数组: {filename}",
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                {"path": str(path)},
            )

        for index, record in enumerate(data):
            self._validate_record(filename, index, record)
        return data

    def _validate_record(self, filename: str, index: int, record: Any) -> None:
        if not isinstance(record, dict):
            raise AppError(
                "MOCK_DATA_LOAD_ERROR",
                "mock 数据记录必须是对象",
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                {"file": filename, "index": index},
            )

        missing = sorted(field for field in self.REQUIRED_EVIDENCE_FIELDS if field not in record)
        if missing:
            raise AppError(
                "MOCK_DATA_LOAD_ERROR",
                "mock 数据缺少必要溯源字段",
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                {"file": filename, "index": index, "missing": missing},
            )

        if record.get("data_mode") != "mock":
            raise AppError(
                "MOCK_DATA_LOAD_ERROR",
                "mock 数据必须显式标记 data_mode=mock",
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                {"file": filename, "index": index, "data_mode": record.get("data_mode")},
            )

        if not (record.get("observed_at") or record.get("retrieved_at")):
            raise AppError(
                "MOCK_DATA_LOAD_ERROR",
                "mock 数据必须包含 observed_at 或 retrieved_at",
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                {"file": filename, "index": index},
            )

        if filename in {self.FILES["catalog_items"], self.FILES["support_kb"]}:
            desk_scope = record.get("desk_scope")
            if desk_scope not in {DeskId.OPS.value, DeskId.SUPPORT.value}:
                raise AppError(
                    "MOCK_DATA_LOAD_ERROR",
                    "服务台 mock 数据必须包含合法 desk_scope",
                    status.HTTP_500_INTERNAL_SERVER_ERROR,
                    {"file": filename, "index": index, "desk_scope": desk_scope},
                )
