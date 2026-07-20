from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import ValidationError

from intelliticket_backend.schemas.tickets import (
    DataMode,
    DiagnosisResult,
    RecommendedAction,
    RetrievedContext,
    RoutingRecommendation,
)
from intelliticket_backend.services.agents.base import AgentCapability, BaseAgent
from intelliticket_backend.services.agents.envelope import (
    InternalTaskRequest,
    InternalTaskResult,
    ReActStep,
)


@dataclass(frozen=True)
class RoutingAgentLimits:
    """Routing Agent 执行边界。"""

    max_iterations: int = 1
    max_tool_calls: int = 0
    timeout_ms: int = 1000


@dataclass(frozen=True)
class RoutingAgentRun:
    """Routing Agent 内部执行结果。"""

    agent_name: str
    status: str
    routing: RoutingRecommendation
    observations: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    react_steps: list[ReActStep] = field(default_factory=list)
    iterations_used: int = 1
    max_iterations: int = 1
    max_tool_calls: int = 0


class RoutingAgent(BaseAgent):
    """基于上下文和诊断结果的轻量分派 Agent。"""

    name = "routing_agent"
    description = "推荐处理团队、行动项、升级策略和 SOP 引用"
    capabilities = [AgentCapability.ROUTING]

    def __init__(self, limits: RoutingAgentLimits | None = None) -> None:
        self.limits = limits or RoutingAgentLimits()

    def handle_task(self, request: InternalTaskRequest) -> InternalTaskResult:
        """处理内部任务信封，不代表正式 A2A 协议兼容。"""
        if request.to_agent != self.name:
            return self.wrong_target_result(request)

        try:
            context = RetrievedContext.model_validate(request.payload["context"])
            diagnosis = DiagnosisResult.model_validate(request.payload["diagnosis"])
            data_mode = DataMode(request.payload["data_mode"])
            run = self.run(context, diagnosis, data_mode)
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            return self.invalid_payload_result(request, exc)

        return self.make_task_result(
            request=request,
            status=run.status,
            payload={"routing": run.routing.model_dump(mode="json")},
            evidence_ids=run.evidence_ids,
            observations=run.observations,
            react_steps=run.react_steps,
        )

    def run(
        self,
        context: RetrievedContext,
        diagnosis: DiagnosisResult,
        data_mode: DataMode,
    ) -> RoutingAgentRun:
        observations = [
            f"执行边界：max_iterations={self.limits.max_iterations}, "
            f"max_tool_calls={self.limits.max_tool_calls}, timeout_ms={self.limits.timeout_ms}",
        ]
        react_steps: list[ReActStep] = []

        if data_mode == DataMode.REAL:
            return self._real_knowledge_run(context, observations, react_steps, diagnosis)

        if not context.service:
            observations.append("缺少服务目录上下文，转人工确认影响系统。")
            routing = RoutingRecommendation(
                recommended_team=None,
                recommended_actions=[],
                escalation="服务未知，建议人工确认影响系统后再分派。",
                sop_refs=[],
            )
            react_steps.append(
                self._react_step(
                    1,
                    "校验服务上下文，发现服务未知。",
                    "validate_context",
                    "context.service=None",
                    "转人工确认影响系统后再分派。",
                    [],
                )
            )
            return self._run("abstained", routing, observations, [], react_steps)

        mode_errors = self._non_mock_context_errors(context)
        if mode_errors:
            observations.extend(mode_errors)
            routing = RoutingRecommendation(
                recommended_team=None,
                recommended_actions=[],
                escalation="上下文数据模式不可信，建议人工确认后再分派。",
                sop_refs=[],
            )
            react_steps.append(
                self._react_step(
                    1,
                    "校验上下文数据模式，发现非 mock SOP 或服务上下文。",
                    "validate_context",
                    f"errors={len(mode_errors)}",
                    "上下文不可信，路由 abstain。",
                    [],
                )
            )
            return self._run("abstained", routing, observations, [], react_steps)

        react_steps.append(
            self._react_step(
                1,
                "校验路由上下文通过。",
                "validate_context",
                f"service={context.service.name}",
                "服务归属和 SOP 上下文可用于路由。",
                [],
            )
        )

        actions: list[RecommendedAction] = []
        sop_refs: list[str] = []
        for sop in context.sop_documents:
            sop_refs.append(sop.sop_id)
            for action in sop.actions:
                if action not in {item.action for item in actions}:
                    actions.append(
                        RecommendedAction(action=action, evidence_ids=[sop.evidence_id])
                    )
        # Cap SOP actions to avoid dumping every matched SOP indiscriminately
        actions = actions[:6]
        react_steps.append(
            self._react_step(
                2,
                "从 SOP 文档收集处理动作。",
                "collect_sop_actions",
                f"sops={len(context.sop_documents)}",
                f"生成 {len(actions)} 个 SOP 动作。",
                [sop.evidence_id for sop in context.sop_documents],
            )
        )

        diagnosis_evidence_ids = [
            evidence_id
            for cause in diagnosis.candidate_root_causes
            for evidence_id in cause.evidence_ids
        ]
        react_steps.append(
            self._react_step(
                3,
                "结合候选根因调整处理动作顺序。",
                "apply_diagnosis_actions",
                f"candidate_root_causes={len(diagnosis.candidate_root_causes)}",
                f"最终动作数：{len(actions)}。",
                diagnosis_evidence_ids,
            )
        )

        if context.sop_documents:
            observations.append("已根据 SOP 文档生成处理动作。")
        else:
            observations.append("未发现 SOP 文档，仅根据服务归属和诊断结果生成分派建议。")

        routing = RoutingRecommendation(
            recommended_team=context.service.owner_team,
            recommended_actions=actions,
            escalation=None,
            sop_refs=sop_refs,
        )
        evidence_ids = self._collect_evidence_ids(routing)
        react_steps.append(
            self._react_step(
                4,
                "汇总分派建议。",
                "finish",
                f"team={routing.recommended_team}",
                "返回推荐团队、处理动作和升级策略。",
                evidence_ids,
            )
        )
        return self._run("completed", routing, observations, evidence_ids, react_steps)

    def _real_knowledge_run(
        self,
        context: RetrievedContext,
        observations: list[str],
        react_steps: list[ReActStep],
        diagnosis: DiagnosisResult | None = None,
    ) -> RoutingAgentRun:
        diagnosis = diagnosis or DiagnosisResult()
        actions = diagnosis.recommended_actions[:6]
        sop_refs = diagnosis.sop_refs
        routing = RoutingRecommendation(
            recommended_team="待人工确认",
            recommended_actions=actions,
            escalation=(
                "真实服务目录和监控未接入；请按已验证的飞书 SOP 建议排查，"
                "并由值班人员确认影响服务和责任团队。"
            ),
            sop_refs=sop_refs,
        )
        evidence_ids = self._collect_evidence_ids(routing)
        observations.append(f"真实模式下使用 {len(actions)} 条经 LLM 验证的 RAG 处理建议。")
        react_steps.append(
            self._react_step(
                1,
                "真实模式下收集飞书 SOP 处理动作。",
                "collect_real_sop_actions",
                f"selected_sops={len(sop_refs)}",
                f"使用 {len(actions)} 个经 LLM 验证的知识库动作。",
                evidence_ids,
            )
        )
        react_steps.append(
            self._react_step(
                2,
                "汇总真实模式分派建议。",
                "finish",
                "team=pending_manual_confirmation",
                "返回飞书 SOP 建议和人工确认升级策略。",
                evidence_ids,
            )
        )
        return self._run(
            "completed" if actions else "abstained",
            routing,
            observations,
            evidence_ids,
            react_steps,
        )

    def _non_mock_context_errors(self, context: RetrievedContext) -> list[str]:
        errors: list[str] = []
        if context.service and context.service.data_mode != DataMode.MOCK:
            errors.append("服务目录上下文 data_mode 非 mock。")
        # SOP/知识库文档允许来自真实外部知识库；路由仅把它们作为处理建议来源。
        return errors

    def _collect_evidence_ids(self, routing: RoutingRecommendation) -> list[str]:
        evidence_ids = {
            evidence_id
            for action in routing.recommended_actions
            for evidence_id in action.evidence_ids
        }
        return sorted(evidence_ids)

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
        routing: RoutingRecommendation,
        observations: list[str],
        evidence_ids: list[str],
        react_steps: list[ReActStep],
    ) -> RoutingAgentRun:
        return RoutingAgentRun(
            agent_name=self.name,
            status=status,
            routing=routing,
            observations=observations,
            evidence_ids=evidence_ids,
            react_steps=react_steps,
            iterations_used=min(1, self.limits.max_iterations),
            max_iterations=self.limits.max_iterations,
            max_tool_calls=self.limits.max_tool_calls,
        )
