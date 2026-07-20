from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from fastapi import status
from pydantic import ValidationError

from intelliticket_backend.errors import AppError
from intelliticket_backend.schemas.tickets import (
    CandidateRootCause,
    DataMode,
    DiagnosisResult,
    HistoricalIncident,
    MetricSnapshot,
    RetrievedContext,
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
class DiagnosisAgentLimits:
    """Diagnosis Agent 执行边界。"""

    max_iterations: int = 5
    max_tool_calls: int = 4
    timeout_ms: int = 30000


@dataclass(frozen=True)
class DiagnosisAgentRun:
    """Diagnosis Agent 内部执行结果。"""

    agent_name: str
    status: str
    diagnosis: DiagnosisResult
    observations: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    react_steps: list[ReActStep] = field(default_factory=list)
    iterations_used: int = 1
    max_iterations: int = 1
    max_tool_calls: int = 0


class DiagnosisAgent(BaseAgent):
    """基于已检索上下文的轻量诊断 Agent。

    当前版本不调用外部工具、不访问仓库、不使用 LLM，只对已验证的上下文证据做
    bounded 诊断和 abstention。
    """

    name = "diagnosis_agent"
    description = "生成候选根因、证据链、置信度和不确定性"
    capabilities = [AgentCapability.DIAGNOSIS]

    def __init__(
        self,
        limits: DiagnosisAgentLimits | None = None,
        llm_client: LlmClient | None = None,
        strategy: str = "deterministic",
    ) -> None:
        self.limits = limits or DiagnosisAgentLimits()
        self.llm_client = llm_client
        self.strategy = strategy

    def handle_task(self, request: InternalTaskRequest) -> InternalTaskResult:
        """处理内部任务信封，不代表正式 A2A 协议兼容。"""
        if request.to_agent != self.name:
            return self.wrong_target_result(request)

        try:
            classification = TicketClassification.model_validate(
                request.payload["classification"]
            )
            context = RetrievedContext.model_validate(request.payload["context"])
            data_mode = DataMode(request.payload["data_mode"])
            ticket_text = str(request.payload.get("ticket_text", ""))
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            return self.invalid_payload_result(request, exc)

        run = self.run(
            classification,
            context,
            data_mode,
            similar_cases=request.payload.get("similar_cases", []),
            ticket_text=ticket_text,
        )
        return self.make_task_result(
            request=request,
            status=run.status,
            payload={"diagnosis": run.diagnosis.model_dump(mode="json")},
            evidence_ids=run.evidence_ids,
            observations=run.observations,
            react_steps=run.react_steps,
        )

    def run(
        self,
        classification: TicketClassification,
        context: RetrievedContext,
        data_mode: DataMode,
        similar_cases: list[dict[str, Any]] | None = None,
        ticket_text: str = "",
    ) -> DiagnosisAgentRun:
        observations = [
            f"执行边界：max_iterations={self.limits.max_iterations}, "
            f"max_tool_calls={self.limits.max_tool_calls}, timeout_ms={self.limits.timeout_ms}",
        ]
        react_steps: list[ReActStep] = []

        if self.strategy not in {"deterministic", "llm", "react"}:
            raise AppError(
                "DIAGNOSIS_STRATEGY_INVALID",
                "diagnosis agent 策略无效，仅支持 deterministic、llm 或 react",
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                {"strategy": self.strategy},
            )

        if data_mode == DataMode.REAL:
            if self.strategy == "llm":
                return self._llm_run(
                    classification=classification,
                    context=context,
                    data_mode=data_mode,
                    observations=observations,
                    react_steps=react_steps,
                    similar_cases=similar_cases,
                    ticket_text=ticket_text,
                )
            return self._real_knowledge_run(
                classification=classification,
                context=context,
                observations=observations,
                react_steps=react_steps,
            )

        if not context.service:
            diagnosis = DiagnosisResult(
                unknowns=["影响服务未知"],
                abstentions=["缺少服务目录证据，无法生成可信根因诊断。"],
            )
            react_steps.append(
                self._react_step(
                    1,
                    "校验服务上下文，发现服务目录证据缺失。",
                    "validate_context",
                    "context.service=None",
                    "缺少服务目录证据，诊断 abstain。",
                    [],
                )
            )
            return self._run("abstained", diagnosis, observations, [], react_steps)

        mode_errors = self._non_mock_context_errors(context)
        if mode_errors:
            diagnosis = DiagnosisResult(unknowns=mode_errors, abstentions=mode_errors)
            react_steps.append(
                self._react_step(
                    1,
                    "校验上下文数据模式，发现非 mock 证据。",
                    "validate_context",
                    f"errors={len(mode_errors)}",
                    "上下文数据模式不可信，诊断 abstain。",
                    [],
                )
            )
            return self._run("abstained", diagnosis, observations, [], react_steps)

        react_steps.append(
            self._react_step(
                1,
                "校验 mock 服务上下文通过。",
                "validate_context",
                f"service={context.service.name}",
                "服务目录和上下文数据模式可用于诊断。",
                [],
            )
        )

        if self.strategy == "react":
            return self._react_run(
                classification=classification,
                context=context,
                data_mode=data_mode,
                observations=observations,
                react_steps=react_steps,
            )

        if self.strategy == "llm":
            return self._llm_run(
                classification=classification,
                context=context,
                data_mode=data_mode,
                observations=observations,
                react_steps=react_steps,
                similar_cases=similar_cases,
            )

        metric_by_name = {metric.metric_name: metric for metric in context.metrics}
        db_pool = metric_by_name.get("db_connection_pool_usage")
        timeout_rate = metric_by_name.get("timeout_rate")
        similar_incident = self._usable_similar_incident(context.historical_incidents)

        causes: list[CandidateRootCause] = []
        abstentions: list[str] = []

        if self._is_usable_required_metric(db_pool) and similar_incident:
            evidence_ids = [db_pool.evidence_id, similar_incident.evidence_id]
            if timeout_rate and timeout_rate.data_mode == DataMode.MOCK:
                evidence_ids.append(timeout_rate.evidence_id)
            causes.append(
                CandidateRootCause(
                    cause="数据库连接池耗尽导致支付服务超时",
                    evidence_ids=evidence_ids,
                    confidence=0.82,
                    reasoning_summary=(
                        "连接池使用率达到 96%，且历史相似工单曾由连接池耗尽导致；"
                        "该结论基于 mock 指标和历史工单，不代表真实生产监控。"
                    ),
                )
            )
            observations.append("连接池指标与历史相似工单同时存在，生成连接池根因候选。")
            react_steps.append(
                self._react_step(
                    2,
                    "评估连接池根因所需指标和历史工单。",
                    "evaluate_db_pool_cause",
                    "db_connection_pool_usage + historical_incident",
                    "证据充足，生成连接池根因候选。",
                    evidence_ids,
                )
            )
        elif similar_incident:
            causes.append(
                CandidateRootCause(
                    cause="历史案例提示需优先排查数据库连接池或下游依赖",
                    evidence_ids=[similar_incident.evidence_id],
                    confidence=0.45,
                    reasoning_summary=(
                        "历史相似工单存在连接池相关根因，可作为排查方向；"
                        "当前未接入真实监控指标，不能确认连接池使用率或当前根因。"
                    ),
                )
            )
            abstentions.append(
                "未接入真实监控指标，不能确认 db_connection_pool_usage、timeout_rate 等当前状态。"
            )
            react_steps.append(
                self._react_step(
                    2,
                    "评估连接池根因所需指标和历史工单。",
                    "evaluate_db_pool_cause",
                    "historical_incident_only",
                    "仅作为排查方向生成低置信候选，不确认当前根因。",
                    [similar_incident.evidence_id],
                )
            )
        else:
            abstentions.append(
                "缺少真实监控指标和历史相似工单，"
                "不生成数据库连接池耗尽根因。"
            )
            react_steps.append(
                self._react_step(
                    2,
                    "评估连接池根因所需指标和历史工单。",
                    "evaluate_db_pool_cause",
                    "db_connection_pool_usage + historical_incident",
                    "证据不足，不生成连接池根因候选。",
                    [],
                )
            )

        if context.deployments:
            deployment = context.deployments[0]
            if deployment.data_mode == DataMode.MOCK:
                causes.append(
                    CandidateRootCause(
                        cause="最近发布版本可能引入性能退化或连接泄漏",
                        evidence_ids=[deployment.evidence_id],
                        confidence=0.58,
                        reasoning_summary=(
                            "告警窗口附近存在新版本发布，需要结合真实发布 diff 和监控"
                            "进一步确认。"
                        ),
                    )
                )
                observations.append("存在近期发布记录，生成发布相关候选根因。")
                react_steps.append(
                    self._react_step(
                        3,
                        "评估近期发布记录。",
                        "evaluate_deployment_cause",
                        f"deployment={deployment.version}",
                        "存在 mock 发布证据，生成发布相关候选根因。",
                        [deployment.evidence_id],
                    )
                )
        else:
            observations.append("未发现近期发布记录，不生成发布相关候选根因。")
            react_steps.append(
                self._react_step(
                    3,
                    "评估近期发布记录。",
                    "evaluate_deployment_cause",
                    "deployments=0",
                    "未发现近期发布记录，不生成发布相关候选根因。",
                    [],
                )
            )

        if not causes:
            diagnosis = DiagnosisResult(
                unknowns=["缺少连接池、超时率、部署记录或历史相似工单证据"],
                abstentions=abstentions or ["现有证据不足以支持候选根因。"],
            )
            react_steps.append(
                self._react_step(
                    4,
                    "汇总候选根因评估结果。",
                    "finish",
                    "candidate_root_causes=0",
                    "无可信候选根因，诊断 abstain。",
                    [],
                )
            )
            return self._run("abstained", diagnosis, observations, [], react_steps)

        evidence_ids = sorted(
            evidence_id for cause in causes for evidence_id in cause.evidence_ids
        )
        diagnosis = DiagnosisResult(
            candidate_root_causes=causes,
            unknowns=[
                "未接入真实监控指标，无法确认当前超时率、连接池使用率、错误率或依赖耗时。"
            ],
            abstentions=abstentions,
        )
        react_steps.append(
            self._react_step(
                4,
                "汇总候选根因评估结果。",
                "finish",
                f"candidate_root_causes={len(causes)}",
                "返回带证据引用的候选根因。",
                evidence_ids,
            )
        )
        return self._run("completed", diagnosis, observations, evidence_ids, react_steps)

    def _real_knowledge_run(
        self,
        *,
        classification: TicketClassification,
        context: RetrievedContext,
        observations: list[str],
        react_steps: list[ReActStep],
    ) -> DiagnosisAgentRun:
        real_sops = [sop for sop in context.sop_documents if sop.data_mode == DataMode.REAL]
        evidence_ids = [sop.evidence_id for sop in real_sops]
        react_steps.append(
            self._react_step(
                1,
                "真实模式下校验外部知识库证据。",
                "validate_real_knowledge_context",
                f"real_sops={len(real_sops)}",
                "仅将真实 SOP 作为排查方向，不当作当前故障事实。",
                evidence_ids,
            )
        )
        unknowns = list(context.unknowns)
        unknowns.append("未接入真实监控指标、CMDB 或部署系统，无法确认当前根因。")
        if not real_sops:
            diagnosis = DiagnosisResult(
                unknowns=unknowns,
                abstentions=["未检索到真实 SOP 证据，仅保留工单输入事实，需人工补充上下文。"],
            )
            react_steps.append(
                self._react_step(
                    2,
                    "汇总真实知识库诊断结果。",
                    "finish",
                    "real_sops=0",
                    "证据不足，诊断 abstain。",
                    [],
                )
            )
            return self._run("abstained", diagnosis, observations, [], react_steps)

        titles = "、".join(sop.title for sop in real_sops[:3])
        cause = CandidateRootCause(
            cause="真实知识库提示需按匹配 SOP 排查相关故障方向",
            evidence_ids=evidence_ids[:3],
            confidence=0.35,
            reasoning_summary=(
                f"飞书知识库匹配到 {len(real_sops)} 篇 SOP（{titles}），可作为排查方向；"
                "但缺少真实监控、服务目录和部署事实，不能确认当前根因。"
            ),
        )
        diagnosis = DiagnosisResult(
            candidate_root_causes=[cause],
            unknowns=unknowns,
            abstentions=["真实 SOP 只能提供排查方向，不能替代当前监控或 CMDB 事实。"],
        )
        observations.append(f"已基于 {len(real_sops)} 篇真实 SOP 生成低置信排查方向。")
        react_steps.append(
            self._react_step(
                2,
                "汇总真实知识库诊断结果。",
                "finish",
                f"real_sops={len(real_sops)}",
                "返回低置信排查方向和保留意见。",
                cause.evidence_ids,
            )
        )
        return self._run("completed", diagnosis, observations, cause.evidence_ids, react_steps)

    def _llm_run(
        self,
        classification: TicketClassification,
        context: RetrievedContext,
        data_mode: DataMode,
        observations: list[str],
        react_steps: list[ReActStep],
        similar_cases: list[dict[str, Any]] | None = None,
        ticket_text: str = "",
    ) -> DiagnosisAgentRun:
        """LLM 驱动的根因诊断路径。"""
        if self.llm_client is None:
            raise AppError(
                "DIAGNOSIS_LLM_CLIENT_MISSING",
                "diagnosis agent 策略为 llm 但未注入 LlmClient，拒绝执行",
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                {"strategy": self.strategy},
            )
        react_steps.append(
            self._react_step(
                2,
                "调用 LLM 进行根因诊断推理。",
                "llm_diagnose",
                (
                    f"metrics={len(context.metrics)}, "
                    f"incidents={len(context.historical_incidents)}, "
                    f"similar_cases={len(similar_cases or [])}"
                ),
                "LLM 结构化诊断已返回。",
                [],
            )
        )
        observations.append("已通过 LLM 完成根因诊断。")
        diagnosis_payload = {
            "ticket_text": ticket_text,
            "classification": classification.model_dump(mode="json"),
            "context": {
                "service": context.service.model_dump(mode="json") if context.service else None,
                "metrics": [m.model_dump(mode="json") for m in context.metrics],
                "deployments": [d.model_dump(mode="json") for d in context.deployments],
                "historical_incidents": [
                    i.model_dump(mode="json") for i in context.historical_incidents
                ],
                "sop_documents": [
                    s.model_dump(mode="json") for s in context.sop_documents
                ],
                "unknowns": context.unknowns,
            },
            "similar_cases": [] if data_mode == DataMode.REAL else (similar_cases or []),
            "data_mode": data_mode.value,
        }
        try:
            llm_output = self.llm_client.structured_json_call(
                system_prompt=self._diagnosis_llm_system_prompt(),
                user_payload=diagnosis_payload,
                response_schema=DiagnosisResult,
            )
        except LlmClientError as exc:
            raise AppError(
                "DIAGNOSIS_LLM_FAILED",
                "LLM 根因诊断调用失败，已阻止生成假结果",
                status.HTTP_502_BAD_GATEWAY,
                {"llm_error_code": exc.code, "details": exc.details},
            ) from exc

        known_ids = {
            item.evidence_id
            for source in [
                [context.service] if context.service else [],
                context.metrics,
                context.deployments,
                context.historical_incidents,
                context.sop_documents,
            ]
            for item in source
            if hasattr(item, "evidence_id")
        }
        # Also allow evidence IDs from the classification (intake agent)
        known_ids.update(classification.evidence_ids)
        for cause in llm_output.candidate_root_causes:
            missing = sorted(set(cause.evidence_ids) - known_ids)
            if missing:
                raise AppError(
                    "DIAGNOSIS_LLM_EVIDENCE_INVALID",
                    "LLM 诊断引用了不存在的证据 ID",
                    status.HTTP_502_BAD_GATEWAY,
                    {"cause": cause.cause, "missing_evidence_ids": missing},
                )
        for action in llm_output.recommended_actions:
            missing = sorted(set(action.evidence_ids) - known_ids)
            if missing:
                raise AppError(
                    "DIAGNOSIS_LLM_EVIDENCE_INVALID",
                    "LLM 建议引用了不存在的证据 ID",
                    status.HTTP_502_BAD_GATEWAY,
                    {"action": action.action, "missing_evidence_ids": missing},
                )
            if self._is_raw_knowledge_line(action.action, context):
                raise AppError(
                    "DIAGNOSIS_LLM_ACTION_INVALID",
                    "LLM 将知识库原文标题或章节直接作为处理建议",
                    status.HTTP_502_BAD_GATEWAY,
                    {"action": action.action[:120]},
                )
        known_sop_refs = {sop.sop_id for sop in context.sop_documents}
        missing_sop_refs = sorted(set(llm_output.sop_refs) - known_sop_refs)
        if missing_sop_refs:
            raise AppError(
                "DIAGNOSIS_LLM_SOP_REF_INVALID",
                "LLM 引用了不存在的 SOP",
                status.HTTP_502_BAD_GATEWAY,
                {"missing_sop_refs": missing_sop_refs},
            )
        if data_mode == DataMode.REAL:
            real_sop_ids = {
                sop.evidence_id for sop in context.sop_documents if sop.data_mode == DataMode.REAL
            }
            selected_causes = [
                cause.model_copy(update={"confidence": min(cause.confidence, 0.49)})
                for cause in llm_output.candidate_root_causes
                if set(cause.evidence_ids) & real_sop_ids
            ]
            selected_actions = [
                action
                for action in llm_output.recommended_actions
                if set(action.evidence_ids) & real_sop_ids
            ]
            used_sop_evidence_ids = {
                evidence_id
                for item in [*selected_causes, *selected_actions]
                for evidence_id in item.evidence_ids
                if evidence_id in real_sop_ids
            }
            selected_sop_refs = [
                sop.sop_id
                for sop in context.sop_documents
                if sop.evidence_id in used_sop_evidence_ids
            ]
            llm_output = llm_output.model_copy(
                update={
                    "candidate_root_causes": selected_causes,
                    "recommended_actions": selected_actions,
                    "sop_refs": selected_sop_refs,
                }
            )

        if not context.metrics:
            llm_output = self._sanitize_no_metric_diagnosis(llm_output)

        evidence_ids = sorted(
            {eid for cause in llm_output.candidate_root_causes for eid in cause.evidence_ids}
        )
        react_steps.append(
            self._react_step(
                4,
                "汇总 LLM 诊断结果。",
                "finish",
                f"candidate_root_causes={len(llm_output.candidate_root_causes)}",
                "返回 LLM 生成的候选根因。",
                evidence_ids,
            )
        )
        return self._run("completed", llm_output, observations, evidence_ids, react_steps)

    # ------------------------------------------------------------------
    # ReAct 伪工具调用循环
    # ------------------------------------------------------------------

    _REACT_TOOLS: dict[str, tuple[str, str]] = {
        "get_incidents": (
            "查询指定服务的历史工单", "service_name: 服务名"
        ),
        "get_sops": (
            "查询指定服务的 SOP 文档", "service_name: 服务名"
        ),
    }

    def _react_run(
        self,
        classification: TicketClassification,
        context: RetrievedContext,
        data_mode: DataMode,
        observations: list[str],
        react_steps: list[ReActStep],
    ) -> DiagnosisAgentRun:
        """ReAct 伪工具调用循环 —— LLM 决定每步调用工具还是 finish。"""
        if self.llm_client is None:
            raise AppError(
                "DIAGNOSIS_LLM_CLIENT_MISSING",
                "diagnosis agent 策略为 react 但未注入 LlmClient，拒绝执行",
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                {"strategy": self.strategy},
            )

        service_name = classification.affected_service or ""
        if not service_name:
            diagnosis = DiagnosisResult(
                unknowns=["影响服务未知"],
                abstentions=["缺少服务名，无法执行 ReAct 工具查询。"],
            )
            return self._run("abstained", diagnosis, observations, [], react_steps)

        from intelliticket_backend.repositories.mock_ops_data import (
            MockOpsDataRepository,
        )
        repo = MockOpsDataRepository()

        tool_executors: dict[str, Any] = {
            "get_incidents": repo.get_incidents,
            "get_sops": repo.get_sops,
        }

        from intelliticket_backend.schemas.tickets import ReActToolDecision

        tool_results: dict[str, list[dict[str, Any]]] = {}
        final_diagnosis: DiagnosisResult | None = None
        iteration = 0
        tool_calls_count = 0
        all_evidence_ids: list[str] = []

        max_iter = self.limits.max_iterations
        max_tools = self.limits.max_tool_calls

        # Build conversation as accumulated payload
        conversation: list[dict[str, Any]] = [
            {
                "role": "user",
                "content": (
                    f"工单分类：{classification.model_dump(mode='json')}\n"
                    f"影响服务：{service_name}\n"
                    f"已有上下文：{context.model_dump(mode='json')}"
                ),
            }
        ]

        while iteration < max_iter:
            iteration += 1

            if tool_calls_count >= max_tools:
                conversation.append({
                    "role": "user",
                    "content": "已达到工具调用上限，必须立即 finish 并输出当前最优诊断。",
                })

            try:
                decision = self.llm_client.structured_json_call(
                    system_prompt=self._react_system_prompt(max_tools),
                    user_payload={
                        "conversation": conversation,
                        "iteration": iteration,
                        "max_iterations": max_iter,
                        "available_tools": [
                            {"name": n, "description": d, "input": i}
                            for n, (d, i) in self._REACT_TOOLS.items()
                        ],
                    },
                    response_schema=ReActToolDecision,
                )
            except LlmClientError as exc:
                react_steps.append(
                    self._react_step(
                        iteration,
                        f"LLM 调用失败（{exc.code}），诊断中止。",
                        "react_error",
                        f"iteration={iteration}",
                        f"LLM 错误：{exc.code}。",
                        [],
                    )
                )
                final_diagnosis = DiagnosisResult(
                    unknowns=["LLM 调用失败"],
                    abstentions=["ReAct 循环因 LLM 错误中止。"],
                )
                break

            react_steps.append(
                self._react_step(
                    iteration,
                    decision.thought,
                    decision.action,
                    str(decision.action_input)[:200],
                    "",
                    [],
                )
            )

            if decision.action == "finish":
                try:
                    final_diagnosis = DiagnosisResult.model_validate(
                        decision.action_input
                    )
                except Exception as exc:
                    raise AppError(
                        "DIAGNOSIS_REACT_FINISH_INVALID",
                        "ReAct finish 动作未包含合法的 DiagnosisResult",
                        status.HTTP_502_BAD_GATEWAY,
                        {"error": str(exc)},
                    ) from exc
                react_steps[-1] = self._react_step(
                    iteration,
                    decision.thought,
                    "finish",
                    f"candidate_root_causes={len(final_diagnosis.candidate_root_causes)}",
                    "ReAct 诊断完成。",
                    all_evidence_ids,
                )
                break

            executor = tool_executors.get(decision.action)
            if executor is None:
                observation_text = f"未知工具 '{decision.action}'。可用工具：{list(tool_executors)}"
            else:
                tool_calls_count += 1
                service_arg = decision.action_input.get(
                    "service_name", service_name
                )
                try:
                    raw_result = executor(service_arg)
                except Exception as exc:
                    raw_result = []
                    observation_text = f"工具调用失败：{exc}"
                else:
                    tool_results[decision.action] = raw_result
                    for item in raw_result:
                        if isinstance(item, dict) and "evidence_id" in item:
                            all_evidence_ids.append(item["evidence_id"])
                    import json as _json

                    observation_text = (
                        f"工具 {decision.action}(service_name='{service_arg}') "
                        f"返回 {len(raw_result)} 条记录。\n"
                        f"{_json.dumps(raw_result, ensure_ascii=False, indent=2)}"
                    )

            conversation.append({
                "role": "assistant",
                "content": (
                    f"Action: {decision.action}\n"
                    f"Thought: {decision.thought}"
                ),
            })
            conversation.append({
                "role": "user",
                "content": f"OBSERVATION:\n{observation_text}",
            })

        if final_diagnosis is None:
            final_diagnosis = DiagnosisResult(
                unknowns=["ReAct 循环达到最大迭代上限"],
                abstentions=["未能完成诊断，循环超出限制。"],
            )
            react_steps.append(
                self._react_step(
                    iteration,
                    "达到最大迭代/工具上限，诊断中止。",
                    "max_limit_reached",
                    f"iterations={iteration}/{max_iter}, tools={tool_calls_count}/{max_tools}",
                    "超出限制，诊断中止。",
                    [],
                )
            )

        final_diagnosis = self._sanitize_no_metric_diagnosis(final_diagnosis)

        evidence_ids = all_evidence_ids
        for cause in final_diagnosis.candidate_root_causes:
            evidence_ids.extend(cause.evidence_ids)
        return self._run(
            "completed", final_diagnosis, observations, evidence_ids, react_steps
        )

    def _is_raw_knowledge_line(
        self,
        action: str,
        context: RetrievedContext,
    ) -> bool:
        normalized = action.strip().lower()
        if not normalized:
            return True
        if re.fullmatch(r"\d+(?:\.\d+)*\s*适用场景", normalized) or normalized == "适用场景":
            return True
        raw_lines = {
            line.strip().lower()
            for sop in context.sop_documents
            for line in [sop.title, *sop.actions]
            if line.strip()
        }
        return normalized in raw_lines

    def _sanitize_no_metric_diagnosis(self, diagnosis: DiagnosisResult) -> DiagnosisResult:
        sanitized_causes: list[CandidateRootCause] = []
        for cause in diagnosis.candidate_root_causes:
            summary = cause.reasoning_summary
            if re.search(r"\d+(?:\.\d+)?\s*%", summary):
                summary = re.sub(
                    r"[^。；;]*\d+(?:\.\d+)?\s*%[^。；;]*(?:[。；;]|$)",
                    "",
                    summary,
                ).strip() or (
                    "基于用户提交事实和知识类上下文给出排查方向；"
                    "未接入真实监控指标，不能确认当前指标数值。"
                )
            sanitized_causes.append(cause.model_copy(update={"reasoning_summary": summary}))
        return diagnosis.model_copy(
            update={
                "candidate_root_causes": sanitized_causes,
                "unknowns": [
                    *diagnosis.unknowns,
                    "未接入真实监控指标，无法确认当前超时率、连接池使用率、错误率或依赖耗时。",
                ],
                "abstentions": [
                    *diagnosis.abstentions,
                    "当前诊断只能作为排查方向，不能把历史案例或 SOP 当作当前故障事实。",
                ],
            }
        )

    def _react_system_prompt(self, max_tool_calls: int) -> str:
        tools_desc = "\n".join(
            f"- {n}: {d}。输入：{i}"
            for n, (d, i) in self._REACT_TOOLS.items()
        )
        return (
            "你是 IntelliTicket 平台的 ReAct 根因诊断 Agent（diagnosis_agent）。"
            "你可以通过调用工具查询运维数据来辅助生成诊断结论。\n\n"
            "## 可用工具\n"
            f"{tools_desc}\n\n"
            "## 输出格式（严格 JSON）\n"
            '{"action": "get_incidents"|"get_sops"|"finish",'
            ' "action_input": {}, "thought": "推理摘要"}\n\n'
            "### 工具调用 action_input：\n"
            '{"service_name": "payment-service"}\n\n'
            "### finish action_input（完整 DiagnosisResult）：\n"
            '{"candidate_root_causes": [{"cause": "...", "evidence_ids": [...],'
            ' "confidence": 0.82, "reasoning_summary": "..."}],'
            ' "unknowns": [...], "abstentions": [...]}\n\n'
            "## 规则\n"
            "- 每轮选择一个知识类工具或 finish；不要查询或生成当前实时监控指标。\n"
            f"- 最多调用 {max_tool_calls} 次工具。\n"
            "- 只引用工具返回中实际存在的 evidence_id，禁止编造。\n"
            "- thought 字段必须包含推理摘要（会被记录到审计日志）。\n"
            "- 证据充足后调用 finish 输出诊断；证据不足在 abstentions 中说明缺什么。"
        )

    def _diagnosis_llm_system_prompt(self) -> str:
        return (
            "你是 IntelliTicket 平台的根因诊断 Agent（diagnosis_agent）。"
            "你的任务是根据工单分类结果、已检索的上下文证据、以及历史相似案例，"
            "生成候选根因分析。\n\n"
            "## 输出格式\n"
            "JSON 对象，字段包括 candidate_root_causes、recommended_actions、sop_refs、"
            "unknowns、abstentions。\n"
            "candidate_root_causes 中每一项必须有 cause（根因描述）、"
            "evidence_ids（引用的证据 ID 列表）、confidence（0-1 的置信度）、"
            "reasoning_summary（推理摘要）。"
            "recommended_actions 必须是对象数组，每项严格为 "
            '{"action": "具体可执行动作", "evidence_ids": ["ev_..."]}，不能输出字符串数组。'
            "sop_refs 必须是字符串数组。\n\n"
            "## 使用历史案例\n"
            "user_payload 中的 similar_cases 是历史相似工单。"
            "如果某个案例的 confirmed 为 true，说明其根因已经人工确认，应给予更高权重。"
            "在 reasoning_summary 中引用相关案例的 ticket_id。\n\n"
            "## RAG 规则\n"
            "先根据 ticket_text 和 classification 判断每篇候选 SOP 的相关性；候选召回不等于采用。"
            "candidate_root_causes 和 recommended_actions 只能引用被选中的相关 SOP evidence_id。"
            "recommended_actions 必须是你综合工单和 SOP 后生成的具体可执行动作，"
            "禁止直接复制 SOP 标题、章节号、‘适用场景’或候选正文整句。"
            "sop_refs 只能填写 context.sop_documents 中实际存在的 sop_id。"
            "只能引用 user_payload 中实际存在的 evidence_id，不能编造。"
            "不要把历史案例、SOP 或服务目录写成当前故障事实。"
            "真实模式且缺少指标/CMDB/部署事实时，候选根因置信度不得超过 0.49。"
            "如果 context.metrics 为空，禁止生成具体当前指标数值"
            "（如超时率、连接池使用率、错误率），"
            "只能基于用户输入事实和历史知识给出排查方向，并在 abstentions 中说明缺少真实监控指标。"
            "证据不足时在 abstentions 中说明。"
            "unknowns 列出当前无法确定的关键信息。"
            "即使没有服务目录上下文，也可以基于症状和相关 SOP 给出有证据的低置信排查方向。"
        )

    def _run(
        self,
        status: str,
        diagnosis: DiagnosisResult,
        observations: list[str],
        evidence_ids: list[str],
        react_steps: list[ReActStep],
    ) -> DiagnosisAgentRun:
        return DiagnosisAgentRun(
            agent_name=self.name,
            status=status,
            diagnosis=diagnosis,
            observations=observations,
            evidence_ids=evidence_ids,
            react_steps=react_steps,
            iterations_used=min(1, self.limits.max_iterations),
            max_iterations=self.limits.max_iterations,
            max_tool_calls=self.limits.max_tool_calls,
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

    def _non_mock_context_errors(self, context: RetrievedContext) -> list[str]:
        errors: list[str] = []
        if context.service and context.service.data_mode != DataMode.MOCK:
            errors.append("服务目录上下文 data_mode 非 mock。")
        for metric in context.metrics:
            if metric.data_mode != DataMode.MOCK:
                errors.append(f"指标 {metric.metric_name} data_mode 非 mock。")
        for deployment in context.deployments:
            if deployment.data_mode != DataMode.MOCK:
                errors.append(f"部署记录 {deployment.version} data_mode 非 mock。")
        for incident in context.historical_incidents:
            if incident.data_mode != DataMode.MOCK:
                errors.append(f"历史工单 {incident.incident_id} data_mode 非 mock。")
        # SOP/知识库文档允许来自真实外部知识库；它们是知识参考，不是当前故障事实。
        return errors

    def _usable_similar_incident(
        self,
        incidents: list[HistoricalIncident],
    ) -> HistoricalIncident | None:
        for incident in incidents:
            normalized_root_cause = incident.root_cause.lower()
            is_connection_pool = (
                "连接池" in incident.root_cause or "connection pool" in normalized_root_cause
            )
            if incident.data_mode == DataMode.MOCK and is_connection_pool:
                return incident
        return None

    def _is_usable_required_metric(self, metric: MetricSnapshot | None) -> bool:
        if metric is None:
            return False
        if metric.data_mode != DataMode.MOCK:
            return False
        if metric.quality not in {"fresh", "historical"}:
            return False
        return bool(metric.evidence_id)
