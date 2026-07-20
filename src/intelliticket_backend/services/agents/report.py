from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import ValidationError

from intelliticket_backend.schemas.tickets import (
    DataMode,
    DiagnosisResult,
    FinalReport,
    RetrievedContext,
    RoutingRecommendation,
    TicketClassification,
)
from intelliticket_backend.services.agents.base import AgentCapability, BaseAgent
from intelliticket_backend.services.agents.envelope import (
    InternalTaskRequest,
    InternalTaskResult,
    ReActStep,
)


@dataclass(frozen=True)
class ReportAgentLimits:
    """Report Agent 执行边界。"""

    max_iterations: int = 1
    max_tool_calls: int = 0
    timeout_ms: int = 1000


@dataclass(frozen=True)
class ReportAgentRun:
    """Report Agent 内部执行结果。"""

    agent_name: str
    status: str
    report: FinalReport
    observations: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    react_steps: list[ReActStep] = field(default_factory=list)
    iterations_used: int = 1
    max_iterations: int = 1
    max_tool_calls: int = 0


class ReportAgent(BaseAgent):
    """基于分类、上下文、诊断和路由结果的轻量报告 Agent。"""

    name = "report_agent"
    description = "汇总最终报告，保留证据、链路和未确认事项"
    capabilities = [AgentCapability.REPORT]

    def __init__(self, limits: ReportAgentLimits | None = None) -> None:
        self.limits = limits or ReportAgentLimits()

    def handle_task(self, request: InternalTaskRequest) -> InternalTaskResult:
        """处理内部任务信封，不代表正式 A2A 协议兼容。"""
        if request.to_agent != self.name:
            return self.wrong_target_result(request)

        try:
            classification = TicketClassification.model_validate(
                request.payload["classification"]
            )
            context = RetrievedContext.model_validate(request.payload["context"])
            diagnosis = DiagnosisResult.model_validate(request.payload["diagnosis"])
            routing = RoutingRecommendation.model_validate(request.payload["routing"])
            data_mode = DataMode(request.payload["data_mode"])
            run = self.run(classification, context, diagnosis, routing, data_mode)
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            return self.invalid_payload_result(request, exc)

        return self.make_task_result(
            request=request,
            status=run.status,
            payload={"report": run.report.model_dump(mode="json")},
            evidence_ids=run.evidence_ids,
            observations=run.observations,
            react_steps=run.react_steps,
        )

    def run(
        self,
        classification: TicketClassification,
        context: RetrievedContext,
        diagnosis: DiagnosisResult,
        routing: RoutingRecommendation,
        data_mode: DataMode,
    ) -> ReportAgentRun:
        observations = [
            f"执行边界：max_iterations={self.limits.max_iterations}, "
            f"max_tool_calls={self.limits.max_tool_calls}, timeout_ms={self.limits.timeout_ms}",
        ]
        react_steps: list[ReActStep] = [
            self._react_step(
                1,
                "校验报告输入数据模式和证据。",
                "validate_report_inputs",
                f"data_mode={data_mode.value}",
                "进入报告生成流程。",
                classification.evidence_ids,
            )
        ]

        if data_mode not in {DataMode.MOCK, DataMode.REAL}:
            report = self._conservative_report(
                classification=classification,
                context=context,
                diagnosis=diagnosis,
                routing=routing,
                extra_unknown="当前报告 Agent 仅允许处理 mock 或 real 数据模式。",
                assumption="数据模式不受支持，拒绝生成确定性处理报告。",
            )
            react_steps[-1] = self._react_step(
                1,
                "校验报告输入，发现不支持的数据模式。",
                "validate_report_inputs",
                f"data_mode={data_mode.value}",
                "生成保守报告。",
                [],
            )
            react_steps.append(
                self._react_step(
                    2,
                    "构造保守报告。",
                    "build_conservative_report",
                    "unsupported_data_mode",
                    "拒绝生成确定性处理报告。",
                    [],
                )
            )
            return self._run("abstained", report, observations, [], react_steps)

        evidence_ids = self._collect_evidence_ids(classification, context, diagnosis, routing)
        react_steps.append(
            self._react_step(
                2,
                "收集报告引用证据。",
                "collect_report_evidence",
                "classification + context + diagnosis + routing",
                f"收集到 {len(evidence_ids)} 条证据引用。",
                evidence_ids,
            )
        )
        if not classification.evidence_ids:
            report = self._conservative_report(
                classification=classification,
                context=context,
                diagnosis=diagnosis,
                routing=routing,
                extra_unknown="缺少工单输入证据，无法生成可信报告。",
                assumption="报告缺少原始工单证据，仅能保守展示已知信息。",
            )
            react_steps.append(
                self._react_step(
                    3,
                    "缺少分类证据，构造保守报告。",
                    "build_conservative_report",
                    "classification.evidence_ids=[]",
                    "证据不足，报告 abstain。",
                    evidence_ids,
                )
            )
            return self._run("abstained", report, observations, evidence_ids, react_steps)

        report = self._build_report(classification, context, diagnosis, routing)
        observations.append("已基于分类、上下文、诊断和路由结果生成最终报告。")
        react_steps.append(
            self._react_step(
                3,
                "构造最终报告。",
                "build_report",
                f"service={classification.affected_service or 'unknown'}",
                "生成事实、推导、未知项和建议。",
                evidence_ids,
            )
        )
        react_steps.append(
            self._react_step(
                4,
                "完成报告生成。",
                "finish",
                f"recommendations={len(report.recommendations)}",
                "返回最终报告和证据引用。",
                evidence_ids,
            )
        )
        return self._run("completed", report, observations, evidence_ids, react_steps)

    def _build_report(
        self,
        classification: TicketClassification,
        context: RetrievedContext,
        diagnosis: DiagnosisResult,
        routing: RoutingRecommendation,
    ) -> FinalReport:
        service_name = classification.affected_service or "未知服务"
        top_cause = (
            diagnosis.candidate_root_causes[0].cause
            if diagnosis.candidate_root_causes
            else "证据不足，暂不判断根因"
        )
        top_summary = (
            diagnosis.candidate_root_causes[0].reasoning_summary
            if diagnosis.candidate_root_causes
            else ""
        )

        facts = [
            f"工单类型：{classification.category.value}",
            f"紧急程度：{classification.priority.value}",
            f"影响服务：{service_name}",
        ]
        before = classification.extracted_metrics.get("order_qps_before")
        after = classification.extracted_metrics.get("order_qps_after")
        if isinstance(before, int | float) and isinstance(after, int | float) and before > 0:
            drop_rate = round((before - after) / before * 100)
            facts.append(
                f"用户提交事实：订单量从 {before}/min 降至 {after}/min，"
                f"下降约 {drop_rate}%。"
            )
        facts.extend(metric.summary for metric in context.metrics)
        facts.extend(deployment.summary for deployment in context.deployments)

        recommendations = [action.action for action in routing.recommended_actions]
        if routing.escalation:
            recommendations.append(routing.escalation)

        unknowns = list(
            dict.fromkeys([*diagnosis.unknowns, *diagnosis.abstentions, *context.unknowns])
        )

        return FinalReport(
            title=f"{service_name} 运维告警处理报告",
            summary=top_summary or top_cause,
            facts=facts,
            derived_findings=[
                cause.reasoning_summary for cause in diagnosis.candidate_root_causes
            ],
            assumptions=[self._report_assumption(context)],
            unknowns=unknowns,
            recommendations=recommendations,
        )

    def _report_assumption(self, context: RetrievedContext) -> str:
        if any(sop.data_mode == DataMode.REAL for sop in context.sop_documents):
            return (
                "当前结论基于用户提交内容和飞书真实知识库 SOP；"
                "未接入真实 CMDB、监控或部署事实。"
            )
        return (
            "当前结论基于用户提交内容、服务目录、历史案例和 SOP；"
            "未把 mock 指标作为当前故障事实。"
        )

    def _conservative_report(
        self,
        classification: TicketClassification,
        context: RetrievedContext,
        diagnosis: DiagnosisResult,
        routing: RoutingRecommendation,
        extra_unknown: str,
        assumption: str,
    ) -> FinalReport:
        report = self._build_report(classification, context, diagnosis, routing)
        return report.model_copy(
            update={
                "summary": "证据不足，暂不生成确定性处理报告。",
                "assumptions": [*report.assumptions, assumption],
                "unknowns": [*report.unknowns, extra_unknown],
            }
        )

    def _collect_evidence_ids(
        self,
        classification: TicketClassification,
        context: RetrievedContext,
        diagnosis: DiagnosisResult,
        routing: RoutingRecommendation,
    ) -> list[str]:
        evidence_ids = set(classification.evidence_ids)
        evidence_ids.update(metric.evidence_id for metric in context.metrics)
        evidence_ids.update(deployment.evidence_id for deployment in context.deployments)
        evidence_ids.update(incident.evidence_id for incident in context.historical_incidents)
        evidence_ids.update(sop.evidence_id for sop in context.sop_documents)
        for cause in diagnosis.candidate_root_causes:
            evidence_ids.update(cause.evidence_ids)
        for action in routing.recommended_actions:
            evidence_ids.update(action.evidence_ids)
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
        report: FinalReport,
        observations: list[str],
        evidence_ids: list[str],
        react_steps: list[ReActStep],
    ) -> ReportAgentRun:
        return ReportAgentRun(
            agent_name=self.name,
            status=status,
            report=report,
            observations=observations,
            evidence_ids=evidence_ids,
            react_steps=react_steps,
            iterations_used=min(1, self.limits.max_iterations),
            max_iterations=self.limits.max_iterations,
            max_tool_calls=self.limits.max_tool_calls,
        )
