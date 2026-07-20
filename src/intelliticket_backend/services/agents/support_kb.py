from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from intelliticket_backend.repositories.mock_ops_data import MockOpsDataRepository
from intelliticket_backend.schemas.tickets import DataMode, DeskId, Evidence
from intelliticket_backend.services.agents.base import AgentCapability, BaseAgent
from intelliticket_backend.services.agents.envelope import (
    AgentTaskError,
    InternalTaskRequest,
    InternalTaskResult,
    ReActStep,
)
from intelliticket_backend.services.knowledge import KnowledgeService


@dataclass(frozen=True)
class SupportKbRetrievalAgentRun:
    """Support KB Retrieval Agent 内部执行结果。"""

    agent_name: str
    status: str
    matched_articles: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    observations: list[str] = field(default_factory=list)
    react_steps: list[ReActStep] = field(default_factory=list)
    error: AgentTaskError | None = None


class SupportKbRetrievalAgent(BaseAgent):
    """基于 support 知识库的 deterministic 检索边界。"""

    name = "support_kb_retrieval_agent"
    description = "检索内部支持知识库并返回可追溯 evidence"
    capabilities = [AgentCapability.SUPPORT_KB_RETRIEVAL]

    def __init__(
        self,
        repository: MockOpsDataRepository | None = None,
        knowledge_service: KnowledgeService | None = None,
    ) -> None:
        self.repository = repository or MockOpsDataRepository()
        self.knowledge_service = knowledge_service or KnowledgeService(repository=self.repository)

    def handle_task(self, request: InternalTaskRequest) -> InternalTaskResult:
        """处理内部任务信封，不代表正式 A2A 协议兼容。"""
        if request.to_agent != self.name:
            return self.wrong_target_result(request)

        try:
            text = str(request.payload["text"])
            desk_id = DeskId(request.payload["desk_id"])
            data_mode = DataMode(request.payload["data_mode"])
            run = self.run(text=text, desk_id=desk_id, data_mode=data_mode, run_id=request.run_id)
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            return self.invalid_payload_result(request, exc)

        return self.make_task_result(
            request=request,
            status=run.status,
            payload={
                "matched_articles": run.matched_articles,
                "evidence": [item.model_dump(mode="json") for item in run.evidence],
                "evidence_ids": run.evidence_ids,
            },
            evidence_ids=run.evidence_ids,
            observations=run.observations,
            react_steps=run.react_steps,
            error=run.error,
        )

    def run(
        self,
        *,
        text: str,
        desk_id: DeskId,
        data_mode: DataMode,
        run_id: str,
    ) -> SupportKbRetrievalAgentRun:
        observations = [
            "执行边界：deterministic support KB 检索，max_iterations=1, max_tool_calls=1。"
        ]
        react_steps: list[ReActStep] = []
        if data_mode not in {DataMode.MOCK, DataMode.REAL}:
            error = AgentTaskError(
                code="UNSUPPORTED_SUPPORT_KB_DATA_MODE",
                message="support KB 检索仅允许 mock 或 real 数据模式",
                details={"data_mode": data_mode.value},
            )
            observations.append("data_mode 非 mock/real，拒绝执行 support KB 检索。")
            react_steps.append(
                self._react_step(
                    1,
                    "校验 support KB 检索数据模式失败。",
                    "validate_support_kb_request",
                    f"data_mode={data_mode.value}",
                    "拒绝生成检索结果。",
                    [],
                )
            )
            return SupportKbRetrievalAgentRun(
                agent_name=self.name,
                status="failed",
                observations=observations,
                react_steps=react_steps,
                error=error,
            )

        selected_articles = self.knowledge_service.search_support_articles(
            query=text,
            desk_id=desk_id,
            data_mode=data_mode,
        )
        selected_articles = [
            article for article in selected_articles if article.get("data_mode") == data_mode.value
        ]
        evidence = [self._evidence_from_article(article, run_id) for article in selected_articles]
        evidence_ids = [item.evidence_id for item in evidence]
        observations.append(f"已从内部支持知识库匹配 {len(selected_articles)} 篇文章。")
        react_steps.append(
            self._react_step(
                1,
                "根据用户文本检索内部支持知识库。",
                "retrieve_support_kb",
                f"desk_id={desk_id.value}, data_mode={data_mode.value}",
                f"匹配 {len(selected_articles)} 篇 support KB 文章。",
                evidence_ids,
            )
        )
        return SupportKbRetrievalAgentRun(
            agent_name=self.name,
            status="completed",
            matched_articles=selected_articles,
            evidence=evidence,
            evidence_ids=evidence_ids,
            observations=observations,
            react_steps=react_steps,
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

    def _evidence_from_article(self, article: dict[str, Any], run_id: str) -> Evidence:
        data_mode = article.get("data_mode")
        trace_uri = article.get("trace_uri")
        if not trace_uri:
            trace_uri = (
                f"mock_data/support_kb.json#{article.get('article_id')}"
                if data_mode == DataMode.MOCK.value
                else f"knowledge/support#{article.get('article_id') or article.get('source_id')}"
            )
        return Evidence.model_validate(article).model_copy(
            update={
                "freshness": article.get("quality"),
                "quality_reason": article.get("quality_reason") or "来自内部支持知识库。",
                "producer": self.name,
                "run_id": run_id,
                "trace_uri": trace_uri,
            }
        )

    def _react_step(
        self,
        step_index: int,
        decision_summary: str,
        action: str,
        action_input_summary: str,
        observation_summary: str,
        evidence_ids: list[str],
    ) -> ReActStep:
        return ReActStep(
            step_index=step_index,
            decision_summary=decision_summary,
            action=action,
            action_input_summary=action_input_summary,
            observation_summary=observation_summary,
            evidence_ids=evidence_ids,
        )
