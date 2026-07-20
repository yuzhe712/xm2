from __future__ import annotations

from intelliticket_backend.config import Settings, get_settings
from intelliticket_backend.errors import AppError
from intelliticket_backend.repositories.mock_ops_data import MockOpsDataRepository
from intelliticket_backend.schemas.tickets import DataMode, DeskId
from intelliticket_backend.services.knowledge.connectors.base import (
    KnowledgeConnector,
    KnowledgeDocument,
)
from intelliticket_backend.services.knowledge.connectors.feishu import (
    FeishuKnowledgeConnector,
)
from intelliticket_backend.services.knowledge.connectors.mock import (
    MockKnowledgeConnector,
)


class KnowledgeService:
    """统一知识库检索服务，封装 mock/飞书 Connector 选择。"""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        repository: MockOpsDataRepository | None = None,
        connector: KnowledgeConnector | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.repository = repository or MockOpsDataRepository()
        self.mock_connector = MockKnowledgeConnector(self.repository)
        self.connector = connector or self._build_connector()
        self.provider = self.settings.knowledge_provider

    def search_sops(
        self,
        *,
        query: str,
        service_name: str | None,
        limit: int | None = None,
        data_mode: DataMode | None = None,
    ) -> list[dict]:
        connector = self._connector_for_data_mode(data_mode)
        documents = connector.search_sops(
            query=query,
            service_name=service_name,
            limit=limit or self.settings.feishu_max_results,
        )
        if data_mode is not None:
            documents = [document for document in documents if document.data_mode == data_mode]
        return [self._document_to_sop_record(document) for document in documents]

    def search_support_articles(
        self,
        *,
        query: str,
        desk_id: DeskId,
        limit: int | None = None,
        data_mode: DataMode | None = None,
    ) -> list[dict]:
        connector = self._connector_for_data_mode(data_mode)
        documents = connector.search_support_articles(
            query=query,
            desk_id=desk_id,
            limit=limit or self.settings.feishu_max_results,
        )
        if data_mode is not None:
            documents = [document for document in documents if document.data_mode == data_mode]
        return [self._document_to_support_record(document, desk_id) for document in documents]

    def _connector_for_data_mode(self, data_mode: DataMode | None) -> KnowledgeConnector:
        if data_mode == DataMode.MOCK:
            return self.mock_connector
        return self.connector

    def _build_connector(self) -> KnowledgeConnector:
        if self.settings.knowledge_provider != "feishu":
            return self.mock_connector
        if not (
            self.settings.feishu_app_id
            and self.settings.feishu_app_secret
            and (
                self.settings.feishu_drive_folder_url
                or self.settings.feishu_drive_folder_token
            )
        ):
            raise AppError(
                "FEISHU_KB_NOT_CONFIGURED",
                "已选择飞书知识库，但飞书应用凭证或 Drive 文件夹配置不完整",
                500,
                {"provider": "feishu", "fallback": "disabled"},
            )
        return FeishuKnowledgeConnector(
            app_id=self.settings.feishu_app_id,
            app_secret=self.settings.feishu_app_secret,
            base_url=self.settings.feishu_base_url,
            wiki_space_id=self.settings.feishu_wiki_space_id,
            drive_folder_url=self.settings.feishu_drive_folder_url,
            drive_folder_token=self.settings.feishu_drive_folder_token,
            timeout_seconds=self.settings.feishu_timeout_seconds,
            max_results=self.settings.feishu_max_results,
        )

    def _document_to_sop_record(self, document: KnowledgeDocument) -> dict:
        return {
            "evidence_id": document.evidence_id,
            "source_type": document.source_type,
            "source_id": document.source_id,
            "source_name": document.source_name,
            "retrieved_at": document.retrieved_at,
            "service": document.service or "external-knowledge",
            "sop_id": document.sop_id or document.article_id or document.source_id,
            "title": document.title,
            "actions": document.actions,
            "quality": document.quality,
            "data_mode": document.data_mode.value,
            "summary": document.summary,
            "trace_uri": document.trace_uri,
            "quality_reason": self._quality_reason(document),
        }

    def _document_to_support_record(self, document: KnowledgeDocument, desk_id: DeskId) -> dict:
        return {
            "evidence_id": document.evidence_id,
            "source_type": document.source_type,
            "source_id": document.source_id,
            "source_name": document.source_name,
            "retrieved_at": document.retrieved_at,
            "desk_scope": (document.desk_scope or desk_id).value,
            "service": document.service or "internal-support",
            "article_id": document.article_id or document.sop_id or document.source_id,
            "title": document.title,
            "actions": document.actions,
            "quality": document.quality,
            "data_mode": document.data_mode.value,
            "summary": document.summary,
            "trace_uri": document.trace_uri,
            "quality_reason": (
                "来自本地 mock support_kb.json，data_mode=mock。"
                if document.data_mode == DataMode.MOCK
                else self._quality_reason(document)
            ),
        }

    def _quality_reason(self, document: KnowledgeDocument) -> str:
        if document.data_mode == DataMode.REAL:
            return "来自飞书 Drive 文件夹读取的真实知识文档，作为知识参考，不代表当前故障事实。"
        return "来自本地 mock 知识库，data_mode=mock。"
