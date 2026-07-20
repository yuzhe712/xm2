from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from intelliticket_backend.repositories.mock_ops_data import MockOpsDataRepository
from intelliticket_backend.schemas.tickets import DataMode, DeskId
from intelliticket_backend.services.knowledge.connectors.base import KnowledgeDocument


class MockKnowledgeConnector:
    """将本地 mock SOP/support KB 包装为统一知识库 Connector。"""

    source_name = "Local Mock Knowledge Base"

    def __init__(self, repository: MockOpsDataRepository | None = None) -> None:
        self.repository = repository or MockOpsDataRepository()

    def search_sops(
        self,
        *,
        query: str,
        service_name: str | None,
        limit: int,
    ) -> list[KnowledgeDocument]:
        if not service_name:
            return []
        records = self.repository.get_sops(service_name)
        return [self._sop_document(record) for record in records[:limit]]

    def search_support_articles(
        self,
        *,
        query: str,
        desk_id: DeskId,
        limit: int,
    ) -> list[KnowledgeDocument]:
        records = self.repository.get_knowledge_articles(desk_id)
        selected = records if not query.strip() else self._select_articles(query, records)
        return [self._support_document(record) for record in selected[:limit]]

    def _sop_document(self, record: dict[str, Any]) -> KnowledgeDocument:
        return KnowledgeDocument(
            evidence_id=record["evidence_id"],
            source_type=record["source_type"],
            source_id=record["source_id"],
            source_name=record["source_name"],
            title=record["title"],
            summary=record["summary"],
            actions=list(record.get("actions", [])),
            service=record.get("service"),
            retrieved_at=record.get("retrieved_at") or self._now(),
            quality=record["quality"],
            data_mode=DataMode.MOCK,
            trace_uri=f"mock_data/sop_docs.json#{record.get('sop_id')}",
            sop_id=record.get("sop_id"),
        )

    def _support_document(self, record: dict[str, Any]) -> KnowledgeDocument:
        return KnowledgeDocument(
            evidence_id=record["evidence_id"],
            source_type=record["source_type"],
            source_id=record["source_id"],
            source_name=record["source_name"],
            title=record["title"],
            summary=record["summary"],
            actions=list(record.get("actions", [])),
            service=record.get("service"),
            desk_scope=DeskId(record["desk_scope"]),
            retrieved_at=record.get("retrieved_at") or self._now(),
            quality=record["quality"],
            data_mode=DataMode.MOCK,
            trace_uri=f"mock_data/support_kb.json#{record.get('article_id')}",
            article_id=record.get("article_id"),
        )

    def _select_articles(self, text: str, articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized = text.lower()
        scored: list[tuple[int, dict[str, Any]]] = []
        for article in articles:
            haystack = " ".join(
                [
                    article.get("service", ""),
                    article.get("title", ""),
                    article.get("summary", ""),
                    *article.get("actions", []),
                ]
            ).lower()
            score = sum(1 for token in self._tokens(normalized) if token in haystack)
            if score > 0:
                scored.append((score, article))
        if not scored:
            return articles[:1]
        scored.sort(key=lambda item: item[0], reverse=True)
        top_score = scored[0][0]
        return [article for score, article in scored if score == top_score]

    def _tokens(self, normalized_text: str) -> list[str]:
        tokens = [
            token
            for token in normalized_text.replace("，", " ").replace("。", " ").split()
            if token
        ]
        keywords: list[str] = []
        keyword_expansions = {
            "网络": ["网络", "vpn", "dns"],
            "vpn": ["vpn"],
            "dns": ["dns"],
            "账号": ["账号", "权限", "角色", "permission"],
            "权限": ["账号", "权限", "角色", "permission"],
            "访问": ["访问"],
            "监控": ["monitoring", "console", "账号", "权限"],
            "工单": ["工单"],
        }
        for keyword, expanded in keyword_expansions.items():
            if keyword in normalized_text:
                keywords.extend(expanded)
        return tokens + keywords

    def _now(self) -> str:
        return datetime.now(UTC).isoformat()
