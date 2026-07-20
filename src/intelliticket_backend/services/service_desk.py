from __future__ import annotations

from fastapi import status

from intelliticket_backend.errors import AppError
from intelliticket_backend.repositories.mock_ops_data import MockOpsDataRepository
from intelliticket_backend.schemas.service_desk import (
    CatalogItem,
    CatalogResponse,
    KnowledgeArticle,
    KnowledgeResponse,
)
from intelliticket_backend.schemas.tickets import DataMode, DeskId
from intelliticket_backend.services.knowledge import KnowledgeService


class ServiceDeskService:
    """Desk-scoped service catalog and knowledge access."""

    def __init__(
        self,
        repository: MockOpsDataRepository | None = None,
        knowledge_service: KnowledgeService | None = None,
    ) -> None:
        self.repository = repository or MockOpsDataRepository()
        self.knowledge_service = knowledge_service or KnowledgeService(repository=self.repository)

    def get_catalog(self, desk_id: DeskId) -> CatalogResponse:
        records = self.repository.get_catalog_items(desk_id)
        if not records:
            raise AppError(
                "DESK_CATALOG_EMPTY",
                "服务台目录 mock 数据为空，未返回假成功",
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                {"desk_id": desk_id.value},
            )
        return CatalogResponse(
            desk_id=desk_id,
            data_mode=DataMode.MOCK,
            items=[CatalogItem.model_validate(record) for record in records],
        )

    def get_knowledge(
        self,
        desk_id: DeskId,
        data_mode: DataMode | None = DataMode.MOCK,
    ) -> KnowledgeResponse:
        records = self.knowledge_service.search_support_articles(
            query="",
            desk_id=desk_id,
            data_mode=data_mode,
        )
        if not records:
            if data_mode == DataMode.REAL:
                return KnowledgeResponse(desk_id=desk_id, data_mode=DataMode.REAL, items=[])
            raise AppError(
                "DESK_KNOWLEDGE_EMPTY",
                "服务台知识库数据为空，未返回假成功",
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                {"desk_id": desk_id.value},
            )
        has_real_knowledge = any(
            record.get("data_mode") == DataMode.REAL.value for record in records
        )
        data_mode = DataMode.REAL if has_real_knowledge else DataMode.MOCK
        return KnowledgeResponse(
            desk_id=desk_id,
            data_mode=data_mode,
            items=[KnowledgeArticle.model_validate(record) for record in records],
        )
