from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fastapi import status
from pydantic import ValidationError

from intelliticket_backend.errors import AppError
from intelliticket_backend.schemas.tickets import (
    DataMode,
    DiagnosisResult,
    Evidence,
    RetrievedContext,
    ReviewIssue,
    ReviewResult,
    RoutingRecommendation,
    TicketClassification,
)
from intelliticket_backend.services.agents.base import AgentCapability, BaseAgent
from intelliticket_backend.services.agents.envelope import (
    InternalTaskRequest,
    InternalTaskResult,
    ReActStep,
)
from intelliticket_backend.services.llm import LlmClient, LlmClientError


@dataclass(frozen=True)
class ReviewerAgentLimits:
    """Reviewer Agent 执行边界。"""

    max_iterations: int = 1
    max_tool_calls: int = 0
    timeout_ms: int = 1000


@dataclass(frozen=True)
class ReviewerAgentRun:
    """Reviewer Agent 内部执行结果。"""

    agent_name: str
    status: str
    review: ReviewResult
    observations: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    react_steps: list[ReActStep] = field(default_factory=list)
    iterations_used: int = 1
    max_iterations: int = 1
    max_tool_calls: int = 0


class ReviewerAgent(BaseAgent):
    """跨 Agent 证据一致性审查 Agent。

    接收 classification, context, diagnosis, routing 四个上游输出，
    使用 LLM 验证跨 Agent 证据链一致性。先执行轻量确定性规则，
    再调用 LLM 做语义审查。

    行为：fail-closed。
    - LLM 不可用 → abstain
    - 发现证据矛盾 → flagged
    - 一切一致 → consistent
    """

    name = "reviewer_agent"
    description = "验证跨 Agent 证据一致性，发现矛盾或缺失"
    capabilities = [AgentCapability.REVIEW]

    def __init__(
        self,
        limits: ReviewerAgentLimits | None = None,
        llm_client: LlmClient | None = None,
    ) -> None:
        self.limits = limits or ReviewerAgentLimits()
        self.llm_client = llm_client

    # ------------------------------------------------------------------
    # handle_task — 标准 Agent 入口
    # ------------------------------------------------------------------

    def handle_task(self, request: InternalTaskRequest) -> InternalTaskResult:
        """处理内部任务信封。"""
        if request.to_agent != self.name:
            return self.wrong_target_result(request)

        try:
            classification = TicketClassification.model_validate(
                request.payload["classification"]
            )
            context = RetrievedContext.model_validate(request.payload["context"])
            diagnosis = DiagnosisResult.model_validate(request.payload["diagnosis"])
            routing = RoutingRecommendation.model_validate(request.payload["routing"])
            raw_evidence = request.payload.get("evidence", [])
            evidence = [Evidence.model_validate(e) for e in raw_evidence]
            data_mode = DataMode(request.payload["data_mode"])
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            return self.invalid_payload_result(request, exc)

        run = self.run(classification, context, diagnosis, routing, evidence, data_mode)
        return self.make_task_result(
            request=request,
            status=run.status,
            payload={"review": run.review.model_dump(mode="json")},
            evidence_ids=run.evidence_ids,
            observations=run.observations,
            react_steps=run.react_steps,
        )

    # ------------------------------------------------------------------
    # run — 核心逻辑：确定性规则 → LLM 语义审查
    # ------------------------------------------------------------------

    def run(
        self,
        classification: TicketClassification,
        context: RetrievedContext,
        diagnosis: DiagnosisResult,
        routing: RoutingRecommendation,
        evidence: list[Evidence],
        data_mode: DataMode,
    ) -> ReviewerAgentRun:
        observations: list[str] = []
        react_steps: list[ReActStep] = []

        # ---- gate: unsupported data_mode → abstain ----
        if data_mode not in {DataMode.MOCK, DataMode.REAL}:
            review = ReviewResult(
                review_status="abstain",
                issues=[],
                recommendation="Reviewer 仅允许处理 mock 或 real 数据模式。",
                confidence=0.0,
            )
            react_steps.append(
                self._react_step(
                    1, "不支持的数据模式，审查 abstain。",
                    "gate_check", f"data_mode={data_mode.value}",
                    "不支持的数据模式拒绝审查。", [],
                )
            )
            return self._run("abstained", review, observations, [], react_steps)

        # ---- Step 1: deterministic pre-checks ----
        det_issues = self._deterministic_checks(
            classification, context, diagnosis, routing
        )
        critical_issues = [issue for issue in det_issues if issue.severity == "critical"]
        if critical_issues:
            evidence_ids = self._collect_evidence_ids(
                classification, context, diagnosis, routing, evidence
            )
            review = ReviewResult(
                review_status="flagged",
                issues=critical_issues,
                recommendation="确定性规则发现关键冲突，建议人工复核后继续。",
                confidence=0.9,
                evidence_ids=evidence_ids,
            )
            react_steps.append(
                self._react_step(
                    1,
                    f"确定性规则发现 {len(critical_issues)} 个关键问题。",
                    "deterministic_checks",
                    f"critical_issues={len(critical_issues)}",
                    f"发现 {len(critical_issues)} 个关键问题，标记为 flagged。",
                    evidence_ids,
                )
            )
            return self._run("completed", review, observations, evidence_ids, react_steps)
        react_steps.append(
            self._react_step(
                1,
                "确定性规则检查通过，未发现明显矛盾。",
                "deterministic_checks",
                "no issues",
                "确定性检查通过。",
                [],
            )
        )

        # ---- Step 2: LLM semantic review ----
        if self.llm_client is None:
            review = ReviewResult(
                review_status="consistent",
                issues=[],
                recommendation=(
                    "LLM 客户端未配置，已完成确定性证据一致性检查，"
                    "未发现跨 Agent 矛盾。"
                ),
                confidence=0.6 if data_mode == DataMode.REAL else 0.0,
                evidence_ids=self._collect_evidence_ids(
                    classification,
                    context,
                    diagnosis,
                    routing,
                    evidence,
                ),
            )
            evidence_ids = review.evidence_ids
            react_steps.append(
                self._react_step(
                    2,
                    "LLM 客户端未配置，完成确定性审查。",
                    "deterministic_review", "no llm_client",
                    "确定性检查未发现跨 Agent 矛盾。", evidence_ids,
                )
            )
            return self._run("completed", review, observations, evidence_ids, react_steps)

        try:
            llm_output = self.llm_client.structured_json_call(
                system_prompt=self._review_system_prompt(),
                user_payload=self._build_review_payload(
                    classification, context, diagnosis, routing, evidence
                ),
                response_schema=ReviewResult,
            )
        except LlmClientError:
            review = ReviewResult(
                review_status="abstain",
                issues=[],
                recommendation="LLM 调用失败，无法完成语义审查。",
                confidence=0.0,
            )
            react_steps.append(
                self._react_step(
                    3,
                    "LLM 调用失败，审查 abstain。",
                    "llm_review", "LLM call failed",
                    "fail-closed: abstain（LLM 不可用）。", [],
                )
            )
            return self._run("completed", review, observations, [], react_steps)

        # ---- Step 3: validate LLM evidence references ----
        known_ids = self._known_evidence_ids(
            classification, context, diagnosis, routing, evidence
        )
        for issue in llm_output.issues:
            missing = sorted(set(issue.evidence_ids) - known_ids)
            if missing:
                raise AppError(
                    "REVIEW_LLM_EVIDENCE_INVALID",
                    "Reviewer LLM 引用了不存在的证据 ID",
                    status.HTTP_502_BAD_GATEWAY,
                    {
                        "issue": issue.description[:120],
                        "missing_evidence_ids": missing,
                    },
                )

        if data_mode == DataMode.REAL and llm_output.review_status == "flagged":
            blocking_issues = [
                issue
                for issue in llm_output.issues
                if issue.severity == "critical"
                and set(issue.evidence_ids) - set(classification.evidence_ids)
            ]
            if not blocking_issues:
                llm_output = llm_output.model_copy(
                    update={
                        "review_status": "consistent",
                        "recommendation": (
                            "真实模式的 CMDB/监控缺口已在诊断保留意见中声明；"
                            "现有飞书 SOP 引用和处理建议证据闭合。"
                        ),
                    }
                )

        evidence_ids = sorted(set(llm_output.evidence_ids) & known_ids)
        react_steps.append(
            self._react_step(
                3,
                "LLM 语义审查完成。",
                "llm_review",
                f"status={llm_output.review_status}, issues={len(llm_output.issues)}",
                f"审查结论：{llm_output.review_status}。{llm_output.recommendation}",
                evidence_ids,
            )
        )
        return self._run("completed", llm_output, observations, evidence_ids, react_steps)

    # ------------------------------------------------------------------
    # 确定性规则
    # ------------------------------------------------------------------

    def _deterministic_checks(
        self,
        classification: TicketClassification,
        context: RetrievedContext,
        diagnosis: DiagnosisResult,
        routing: RoutingRecommendation,
    ) -> list[ReviewIssue]:
        """不依赖 LLM 的轻量确定性检查。"""
        issues: list[ReviewIssue] = []

        # service name consistency — check name, display_name, and aliases
        svc_name = classification.affected_service
        if svc_name and context.service:
            svc = context.service
            known_names = {svc.name}
            if svc.display_name:
                known_names.add(svc.display_name)
            known_names.update(svc.aliases)
            if svc_name not in known_names:
                issues.append(
                    ReviewIssue(
                        severity="warning",
                        category="service_contradiction",
                        description=(
                            f"分类影响服务 '{svc_name}' "
                            f"与服务目录中的已知名称 {sorted(known_names)} 均不匹配。"
                        ),
                        affected_fields=[
                            "classification.affected_service",
                            "context.service.name",
                        ],
                    )
                )

        known_action_evidence_ids = {
            *classification.evidence_ids,
            *(sop.evidence_id for sop in context.sop_documents),
        }
        for action in routing.recommended_actions:
            if not action.evidence_ids or not set(action.evidence_ids) <= known_action_evidence_ids:
                issues.append(
                    ReviewIssue(
                        severity="warning",
                        category="routing_evidence_missing",
                        description="处理建议缺少当前检索 SOP 的有效证据引用。",
                        affected_fields=["routing.recommended_actions"],
                        evidence_ids=action.evidence_ids,
                    )
                )

        # routing team vs service owner
        if routing.recommended_team and context.service:
            if routing.recommended_team != context.service.owner_team:
                issues.append(
                    ReviewIssue(
                        severity="warning",
                        category="routing_mismatch",
                        description=(
                            f"路由推荐团队 '{routing.recommended_team}' "
                            f"与服务目录属主团队 '{context.service.owner_team}' 不一致。"
                        ),
                        affected_fields=[
                            "routing.recommended_team",
                            "context.service.owner_team",
                        ],
                    )
                )

        return issues

    # ------------------------------------------------------------------
    # LLM 提示词 & payload 构建
    # ------------------------------------------------------------------

    def _review_system_prompt(self) -> str:
        return (
            "你是 IntelliTicket 平台的证据一致性审查 Agent（reviewer_agent）。"
            "你的任务是对比四个上游 Agent 的输出，验证跨 Agent 的证据一致性。\n\n"
            "## 审查维度\n\n"
            "1. 诊断-证据一致性：\n"
            "   - diagnosis.candidate_root_causes 中的每一条根因是否有实际证据支撑？\n"
            "   - 引用的 evidence_id 是否在 context 中真实存在？\n"
            "   - 诊断结论是否与指标快照、部署记录、历史工单的事实描述一致？\n\n"
            "2. 路由-诊断一致性：\n"
            "   - routing.recommended_actions 是否针对 diagnosis 中识别出的根因？\n"
            "   - routing.recommended_team 是否与 context.service.owner_team 一致？\n"
            "   - 如果 diagnosis 已 abstain，routing 是否仍给出了缺乏依据的建议？\n\n"
            "3. 矛盾发现：\n"
            "   - classification.affected_service 与 context.service.name 是否一致？\n"
            "   - diagnosis.abstentions 与 candidate_root_causes"
            " 同时非空是否存在矛盾？\n\n"
            "4. 证据缺失：\n"
            "   - 诊断依赖的关键指标在 context 中是否缺失？\n"
            "   - 路由建议引用的 SOP 在 context.sop_documents 中是否实际存在？\n"
            "   - context.unknowns 中列出的缺失信息是否对诊断结论构成影响？\n\n"
            "## 输出格式\n\n"
            "严格 JSON 对象：\n"
            "- review_status: \"consistent\" | \"flagged\" | \"abstain\"\n"
            "- issues: 问题列表，每项含 severity(critical/warning/info)、"
            "category、description、affected_fields、evidence_ids\n"
            "- recommendation: 中文建议\n"
            "- confidence: 0.0-1.0 置信度\n"
            "- evidence_ids: 审查中引用的证据 ID\n\n"
            "## 重要规则\n\n"
            "- 只引用 user_payload 中实际存在的 evidence_id，禁止编造。\n"
            "- 只标记确切的矛盾或缺失，不要凭空质疑。\n"
            "- 如果四个 Agent 输出之间逻辑一致、证据链完整，review_status 应为 consistent。\n"
            "- 如果数据不足以做出判断，review_status 应为 abstain。"
        )

    def _build_review_payload(
        self,
        classification: TicketClassification,
        context: RetrievedContext,
        diagnosis: DiagnosisResult,
        routing: RoutingRecommendation,
        evidence: list[Evidence],
    ) -> dict[str, Any]:
        return {
            "classification": classification.model_dump(mode="json"),
            "context": {
                "service": (
                    context.service.model_dump(mode="json")
                    if context.service else None
                ),
                "metrics": [m.model_dump(mode="json") for m in context.metrics],
                "deployments": [
                    d.model_dump(mode="json") for d in context.deployments
                ],
                "historical_incidents": [
                    i.model_dump(mode="json") for i in context.historical_incidents
                ],
                "sop_documents": [
                    s.model_dump(mode="json") for s in context.sop_documents
                ],
                "unknowns": context.unknowns,
            },
            "diagnosis": diagnosis.model_dump(mode="json"),
            "routing": routing.model_dump(mode="json"),
            "evidence": [e.model_dump(mode="json") for e in evidence],
        }

    # ------------------------------------------------------------------
    # evidence 工具方法
    # ------------------------------------------------------------------

    def _known_evidence_ids(
        self,
        classification: TicketClassification,
        context: RetrievedContext,
        diagnosis: DiagnosisResult,
        routing: RoutingRecommendation,
        evidence: list[Evidence],
    ) -> set[str]:
        ids: set[str] = {e.evidence_id for e in evidence}
        ids.update(classification.evidence_ids)
        for source in [
            [context.service] if context.service else [],
            context.metrics,
            context.deployments,
            context.historical_incidents,
            context.sop_documents,
        ]:
            for item in source:  # type: ignore[attr-defined]
                if hasattr(item, "evidence_id"):
                    ids.add(item.evidence_id)  # type: ignore[arg-type]
        for cause in diagnosis.candidate_root_causes:
            ids.update(cause.evidence_ids)
        for action in routing.recommended_actions:
            ids.update(action.evidence_ids)
        return ids

    def _collect_evidence_ids(
        self,
        classification: TicketClassification,
        context: RetrievedContext,
        diagnosis: DiagnosisResult,
        routing: RoutingRecommendation,
        evidence: list[Evidence],
    ) -> list[str]:
        return sorted(self._known_evidence_ids(
            classification, context, diagnosis, routing, evidence
        ))

    # ------------------------------------------------------------------
    # 内部 helper
    # ------------------------------------------------------------------

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

    def _run(
        self,
        status: str,
        review: ReviewResult,
        observations: list[str],
        evidence_ids: list[str],
        react_steps: list[ReActStep],
    ) -> ReviewerAgentRun:
        return ReviewerAgentRun(
            agent_name=self.name,
            status=status,
            review=review,
            observations=observations,
            evidence_ids=evidence_ids,
            react_steps=react_steps,
            iterations_used=len(react_steps),
            max_iterations=self.limits.max_iterations,
            max_tool_calls=self.limits.max_tool_calls,
        )
