from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel

from intelliticket_backend.schemas.tickets import DataMode, DeskId


class KnowledgeDocument(BaseModel):
    """统一知识库文档结构，供不同知识库 Connector 输出。"""

    evidence_id: str
    source_type: str
    source_id: str
    source_name: str
    title: str
    summary: str
    actions: list[str]
    service: str | None = None
    desk_scope: DeskId | None = None
    retrieved_at: str
    updated_at: str | None = None
    quality: str
    data_mode: DataMode
    trace_uri: str | None = None
    article_id: str | None = None
    sop_id: str | None = None


class KnowledgeConnector(Protocol):
    """知识库 Connector 协议。"""

    def search_sops(
        self,
        *,
        query: str,
        service_name: str | None,
        limit: int,
    ) -> list[KnowledgeDocument]:
        """检索运维 SOP 文档。"""

    def search_support_articles(
        self,
        *,
        query: str,
        desk_id: DeskId,
        limit: int,
    ) -> list[KnowledgeDocument]:
        """检索内部支持知识库文章。"""
