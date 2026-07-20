from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fastapi import status
from pydantic import BaseModel, Field, ValidationError

from intelliticket_backend.errors import AppError
from intelliticket_backend.schemas.tickets import (
    DataMode,
    FinalReport,
    RecommendedAction,
    RoutingRecommendation,
    SupportTicketResult,
)
from intelliticket_backend.services.agents.base import AgentCapability, BaseAgent
from intelliticket_backend.services.agents.envelope import (
    AgentTaskError,
    InternalTaskRequest,
    InternalTaskResult,
    ReActStep,
)
from intelliticket_backend.services.llm import LlmClient, LlmClientError


class SupportReplyLlmOutput(BaseModel):
    """LLM 支持回复建议结构化输出 schema。"""

    reply_suggestions: list[str] = Field(..., min_length=1)
    report_title: str
    report_summary: str
    facts: list[str] = Field(default_factory=list)
    derived_findings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)

SUPPORT_TEAM = "内部支持服务台"


@dataclass(frozen=True)
class SupportReplyAgentRun:
    """Support Reply Agent 内部执行结果。"""

    agent_name: str
    status: str
    reply_suggestions: list[str] = field(default_factory=list)
    routing: RoutingRecommendation | None = None
    report: FinalReport | None = None
    support_result: SupportTicketResult | None = None
    evidence_ids: list[str] = field(default_factory=list)
    observations: list[str] = field(default_factory=list)
    react_steps: list[ReActStep] = field(default_factory=list)
    error: AgentTaskError | None = None


class SupportReplyAgent(BaseAgent):
    """将 support KB 匹配结果转为回复建议（deterministic 或 LLM）。"""

    name = "support_reply_agent"
    description = "基于内部支持知识库生成回复建议和报告草稿种子"
    capabilities = [AgentCapability.SUPPORT_REPLY]

    def __init__(
        self,
        llm_client: LlmClient | None = None,
        strategy: str = "deterministic",
    ) -> None:
        self.llm_client = llm_client
        self.strategy = strategy

    def handle_task(self, request: InternalTaskRequest) -> InternalTaskResult:
        """处理内部任务信封，不代表正式 A2A 协议兼容。"""
        if request.to_agent != self.name:
            return self.wrong_target_result(request)

        try:
            text = str(request.payload["text"])
            matched_articles = request.payload["matched_articles"]
            evidence_ids = list(request.payload["evidence_ids"])
            data_mode = DataMode(request.payload["data_mode"])
            if not isinstance(matched_articles, list) or not all(
                isinstance(item, dict) for item in matched_articles
            ):
                raise TypeError("matched_articles 必须是对象数组")
            run = self.run(
                text=text,
                matched_articles=matched_articles,
                evidence_ids=evidence_ids,
                data_mode=data_mode,
            )
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            return self.invalid_payload_result(request, exc)

        return self.make_task_result(
            request=request,
            status=run.status,
            payload={
                "reply_suggestions": run.reply_suggestions,
                "routing": run.routing.model_dump(mode="json") if run.routing else None,
                "report": run.report.model_dump(mode="json") if run.report else None,
                "support_result": run.support_result.model_dump(mode="json")
                if run.support_result
                else None,
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
        matched_articles: list[dict[str, Any]],
        evidence_ids: list[str],
        data_mode: DataMode,
    ) -> SupportReplyAgentRun:
        observations = [
            f"执行边界：support 回复生成，strategy={self.strategy}，max_iterations=1。"
        ]
        react_steps: list[ReActStep] = []

        if self.strategy not in {"deterministic", "llm"}:
            raise AppError(
                "SUPPORT_REPLY_STRATEGY_INVALID",
                "support reply agent 策略无效，仅支持 deterministic 或 llm",
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                {"strategy": self.strategy},
            )

        if data_mode not in {DataMode.MOCK, DataMode.REAL}:
            error = AgentTaskError(
                code="UNSUPPORTED_SUPPORT_REPLY_DATA_MODE",
                message="support 回复建议仅允许 mock 或 real 数据模式",
                details={"data_mode": data_mode.value},
            )
            observations.append("data_mode 非 mock/real，拒绝生成 support 回复建议。")
            react_steps.append(
                self._react_step(
                    1,
                    "校验 support reply 数据模式失败。",
                    "validate_support_reply_request",
                    f"data_mode={data_mode.value}",
                    "拒绝生成回复建议。",
                    [],
                )
            )
            return SupportReplyAgentRun(
                agent_name=self.name,
                status="failed",
                observations=observations,
                react_steps=react_steps,
                error=error,
            )

        if self.strategy == "llm":
            return self._llm_run(
                text=text,
                matched_articles=matched_articles,
                evidence_ids=evidence_ids,
                data_mode=data_mode,
                observations=observations,
                react_steps=react_steps,
            )

        primary_article = matched_articles[0] if matched_articles else None
        service_name = primary_article["service"] if primary_article else "internal-support"
        title = primary_article["title"] if primary_article else "内部支持请求处理建议"
        actions = self._actions_from_articles(matched_articles)
        if not actions:
            actions = ["记录用户问题并交由内部支持服务台人工确认"]

        routing = RoutingRecommendation(
            recommended_team=SUPPORT_TEAM,
            recommended_actions=[
                RecommendedAction(action=action, evidence_ids=evidence_ids) for action in actions
            ],
            escalation="若影响多人、关键系统不可用或权限涉及高危角色，升级给内部支持负责人复核。",
            sop_refs=[article["article_id"] for article in matched_articles],
        )
        report = FinalReport(
            title=f"内部支持回复建议：{title}",
            summary="已基于 support 服务台知识库生成回复建议。",
            facts=[f"用户请求：{text}", f"匹配知识库文章数：{len(matched_articles)}"],
            derived_findings=[f"建议由{SUPPORT_TEAM}处理，优先级 P3。"],
            assumptions=[self._knowledge_assumption(data_mode)],
            unknowns=[] if matched_articles else ["未匹配到内部支持知识库文章，需人工补充上下文。"],
            recommendations=actions,
        )
        support_result = SupportTicketResult(
            request_type="internal_support_request",
            matched_articles=[article["article_id"] for article in matched_articles],
            reply_suggestions=actions,
            recommended_team=SUPPORT_TEAM,
            escalation=routing.escalation,
            evidence_ids=evidence_ids,
        )
        observations.append(
            f"已基于 {len(matched_articles)} 篇 KB 文章生成 {len(actions)} 条回复建议。"
        )
        react_steps.append(
            self._react_step(
                1,
                "将 KB actions 转为客服回复建议和本地报告草稿种子。",
                "compose_support_reply",
                f"service={service_name}",
                f"生成 {len(actions)} 条 deterministic 回复建议。",
                evidence_ids,
            )
        )
        return SupportReplyAgentRun(
            agent_name=self.name,
            status="completed",
            reply_suggestions=actions,
            routing=routing,
            report=report,
            support_result=support_result,
            evidence_ids=evidence_ids,
            observations=observations,
            react_steps=react_steps,
        )

    def _llm_run(
        self,
        *,
        text: str,
        matched_articles: list[dict[str, Any]],
        evidence_ids: list[str],
        data_mode: DataMode,
        observations: list[str],
        react_steps: list[ReActStep],
    ) -> SupportReplyAgentRun:
        """LLM 驱动的支持回复生成路径。"""
        if self.llm_client is None:
            raise AppError(
                "SUPPORT_REPLY_LLM_CLIENT_MISSING",
                "support reply agent 策略为 llm 但未注入 LlmClient，拒绝执行",
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                {"strategy": self.strategy},
            )
        llm_payload = {
            "user_request": text,
            "kb_articles": [
                {
                    "article_id": a.get("article_id", ""),
                    "title": a.get("title", ""),
                    "service": a.get("service", ""),
                    "summary": a.get("summary", ""),
                    "actions": a.get("actions", []),
                    "category": a.get("category", ""),
                }
                for a in matched_articles
            ],
        }
        react_steps.append(
            self._react_step(
                1,
                "调用 LLM 生成支持回复建议和报告草稿。",
                "llm_compose_reply",
                f"kb_articles={len(matched_articles)}",
                "LLM 结构化回复已返回。",
                evidence_ids,
            )
        )
        observations.append(
            f"已通过 LLM 基于 {len(matched_articles)} 篇 KB 文章生成回复建议。"
        )
        try:
            llm_output = self.llm_client.structured_json_call(
                system_prompt=self._reply_llm_system_prompt(),
                user_payload=llm_payload,
                response_schema=SupportReplyLlmOutput,
            )
        except LlmClientError as exc:
            raise AppError(
                "SUPPORT_REPLY_LLM_FAILED",
                "LLM 支持回复生成调用失败，已阻止生成假结果",
                status.HTTP_502_BAD_GATEWAY,
                {"llm_error_code": exc.code, "details": exc.details},
            ) from exc

        routing = RoutingRecommendation(
            recommended_team=SUPPORT_TEAM,
            recommended_actions=[
                RecommendedAction(action=action, evidence_ids=evidence_ids)
                for action in llm_output.recommendations
            ],
            escalation="若影响多人、关键系统不可用或权限涉及高危角色，升级给内部支持负责人复核。",
            sop_refs=[article["article_id"] for article in matched_articles],
        )
        report = FinalReport(
            title=llm_output.report_title,
            summary=llm_output.report_summary,
            facts=llm_output.facts,
            derived_findings=llm_output.derived_findings,
            assumptions=[self._knowledge_assumption(data_mode)],
            unknowns=[] if matched_articles else ["未匹配到内部支持知识库文章，需人工补充上下文。"],
            recommendations=llm_output.recommendations,
        )
        support_result = SupportTicketResult(
            request_type="internal_support_request",
            matched_articles=[article["article_id"] for article in matched_articles],
            reply_suggestions=llm_output.reply_suggestions,
            recommended_team=SUPPORT_TEAM,
            escalation=routing.escalation,
            evidence_ids=evidence_ids,
        )
        return SupportReplyAgentRun(
            agent_name=self.name,
            status="completed",
            reply_suggestions=llm_output.reply_suggestions,
            routing=routing,
            report=report,
            support_result=support_result,
            evidence_ids=evidence_ids,
            observations=observations,
            react_steps=react_steps,
        )

    def _knowledge_assumption(self, data_mode: DataMode) -> str:
        if data_mode == DataMode.REAL:
            return "当前结果来自真实知识库检索，仅作为支持回复参考；审批和权限变更仍需按企业流程确认。"
        return "当前结果来自本地 mock 知识库，不代表真实企业知识库或审批系统。"

    def _reply_llm_system_prompt(self) -> str:
        return (
            "你是企业内部 IT 支持服务台的客服回复 Agent（support_reply_agent）。"
            "你的任务是根据用户的支持请求和匹配到的知识库文章，生成专业、有帮助的回复建议。"
            "只能输出 JSON 对象，字段包括 reply_suggestions、report_title、report_summary、"
            "facts、derived_findings、recommendations。"
            "reply_suggestions 是面向用户的回复建议列表，语气应专业、友好，包含具体操作指引。"
            "每个建议应引用知识库文章中的具体步骤，而非笼统描述。"
            "recommendations 是处理动作列表，每条应具体可执行。"
            "如果知识库文章信息不足，在回复中诚实说明需要进一步确认。"
            "不要编造不存在的系统名、链接或联系方式。"
        )

    def _actions_from_articles(self, articles: list[dict[str, Any]]) -> list[str]:
        actions: list[str] = []
        for article in articles:
            for action in article.get("actions", []):
                if action not in actions:
                    actions.append(action)
        return actions

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
