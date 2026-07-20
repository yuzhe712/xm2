from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from fastapi import status
from pydantic import ValidationError

from intelliticket_backend.errors import AppError
from intelliticket_backend.repositories.mock_ops_data import MockOpsDataRepository
from intelliticket_backend.schemas.tickets import (
    DataMode,
    DeploymentRecord,
    Evidence,
    HistoricalIncident,
    MetricSnapshot,
    RetrievedContext,
    ServiceContext,
    SopDocument,
)
from intelliticket_backend.services.agents.base import AgentCapability, BaseAgent
from intelliticket_backend.services.agents.envelope import (
    AgentTaskError,
    InternalTaskRequest,
    InternalTaskResult,
    ReActStep,
)
from intelliticket_backend.services.knowledge import KnowledgeService


@dataclass(frozen=True)
class ContextRetrievalAgentLimits:
    """Context Retrieval Agent 执行边界。"""

    max_iterations: int = 1
    max_tool_calls: int = 4
    timeout_ms: int = 1000


@dataclass(frozen=True)
class ContextRetrievalAgentRun:
    """Context Retrieval Agent 内部执行结果。"""

    agent_name: str
    status: str
    context: RetrievedContext
    evidence: list[Evidence] = field(default_factory=list)
    observations: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    react_steps: list[ReActStep] = field(default_factory=list)
    iterations_used: int = 1
    max_iterations: int = 1
    max_tool_calls: int = 4


class ContextRetrievalAgent(BaseAgent):
    """基于已识别服务的轻量上下文检索 Agent。"""

    name = "context_retrieval_agent"
    description = "查询服务目录、历史工单和 SOP，不默认注入模拟实时指标"
    capabilities = [AgentCapability.CONTEXT_RETRIEVAL]

    REQUIRED_SERVICE_FIELDS = {
        "evidence_id",
        "source_type",
        "source_id",
        "source_name",
        "quality",
        "data_mode",
        "summary",
        "service_id",
        "name",
        "display_name",
        "owner_team",
        "criticality",
    }

    REQUIRED_TOOLS = 4

    def __init__(
        self,
        repository: MockOpsDataRepository | None = None,
        limits: ContextRetrievalAgentLimits | None = None,
        knowledge_service: KnowledgeService | None = None,
    ) -> None:
        self.repository = repository or MockOpsDataRepository()
        self.limits = limits or ContextRetrievalAgentLimits()
        self.knowledge_service = knowledge_service or KnowledgeService(repository=self.repository)

    def handle_task(self, request: InternalTaskRequest) -> InternalTaskResult:
        """处理内部任务信封，不代表正式 A2A 协议兼容。"""
        if request.to_agent != self.name:
            return self.wrong_target_result(request)

        try:
            service_record = request.payload.get("service_record")
            ticket_text = request.payload.get("ticket_text", "")
            data_mode = DataMode(request.payload["data_mode"])
            if service_record is not None and not isinstance(service_record, dict):
                raise TypeError("service_record 必须是对象或 null")
            if not isinstance(ticket_text, str):
                raise TypeError("ticket_text 必须是字符串")
            run = self.run(service_record, data_mode, ticket_text)
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            return self.invalid_payload_result(request, exc)
        except AppError as exc:
            return self._app_error_result(request, exc)

        return self.make_task_result(
            request=request,
            status=run.status,
            payload={
                "context": run.context.model_dump(mode="json"),
                "evidence": [item.model_dump(mode="json") for item in run.evidence],
            },
            evidence_ids=run.evidence_ids,
            observations=run.observations,
            react_steps=run.react_steps,
        )

    def run(
        self,
        service_record: dict[str, Any] | None,
        data_mode: DataMode,
        ticket_text: str = "",
    ) -> ContextRetrievalAgentRun:
        observations = [
            f"执行边界：max_iterations={self.limits.max_iterations}, "
            f"max_tool_calls={self.limits.max_tool_calls}, timeout_ms={self.limits.timeout_ms}",
        ]
        react_steps: list[ReActStep] = []

        limit_error = self._limit_error()
        if limit_error:
            observations.append(limit_error)
            context = RetrievedContext(unknowns=[limit_error])
            react_steps.append(
                self._react_step(
                    1,
                    "校验上下文检索执行边界失败。",
                    "validate_service_record",
                    "limits",
                    limit_error,
                    [],
                )
            )
            return self._run(
                "abstained", context, [], observations, react_steps, iterations_used=0
            )

        if data_mode != DataMode.MOCK:
            observations.append("data_mode 非 mock，跳过 mock 服务目录，仅查询真实知识源。")
            sops = self._get_optional_records(
                source_name="SOP 文档",
                loader=lambda: self.knowledge_service.search_sops(
                    query=ticket_text,
                    service_name=None,
                    data_mode=data_mode,
                ),
                observations=observations,
                unknowns=[],
            )
            unknowns = [
                "未接入真实 CMDB/监控/部署系统，未补充服务目录、指标或发布事实。"
            ]
            context = RetrievedContext(
                sop_documents=[
                    SopDocument(
                        evidence_id=record["evidence_id"],
                        sop_id=record["sop_id"],
                        title=record["title"],
                        actions=record["actions"],
                        data_mode=DataMode(record.get("data_mode", data_mode.value)),
                    )
                    for record in sops
                ],
                unknowns=unknowns,
            )
            evidence = [self._record_to_evidence(record) for record in sops]
            react_steps.append(
                self._react_step(
                    1,
                    "真实模式下跳过 mock 上下文，仅查询外部知识源。",
                    "retrieve_real_knowledge_context",
                    f"query_len={len(ticket_text)}",
                    f"检索到 {len(sops)} 条 SOP 证据。",
                    [item.evidence_id for item in evidence],
                )
            )
            return self._run("partial", context, evidence, observations, react_steps)

        if not service_record:
            observations.append("缺少服务目录记录，未执行上下文检索。")
            context = RetrievedContext(
                unknowns=["未能从工单文本识别影响服务，因此未查询服务上下文。"]
            )
            react_steps.append(
                self._react_step(
                    1,
                    "校验服务目录记录，发现服务未知。",
                    "validate_service_record",
                    "service_record=None",
                    "不查询上下文，避免编造服务数据。",
                    [],
                )
            )
            return self._run("abstained", context, [], observations, react_steps)

        self._validate_service_record(service_record)
        service_name = service_record["name"]
        react_steps.append(
            self._react_step(
                1,
                "校验服务目录记录和 mock 数据模式。",
                "validate_service_record",
                f"service={service_name}",
                "服务目录记录可用于上下文检索。",
                [service_record["evidence_id"]],
            )
        )

        metrics: list[dict[str, Any]] = []
        deployments: list[dict[str, Any]] = []
        unknowns: list[str] = [
            "未接入真实监控系统，未自动补充模拟指标作为当前故障事实。"
        ]
        observations.append(
            "默认员工工单流程不查询 mock 指标或 mock 部署记录，避免把模拟数据当作当前事实。"
        )
        react_steps.append(
            self._react_step(
                2,
                "跳过模拟实时上下文。",
                "skip_mock_operational_facts",
                f"service={service_name}",
                "未查询 mock metrics / mock deployments，仅保留用户输入事实和知识类上下文。",
                [],
            )
        )

        incidents = self._get_optional_records(
            source_name="历史工单",
            loader=lambda: self.repository.get_incidents(service_name),
            observations=observations,
            unknowns=unknowns,
        )
        sops = self._get_optional_records(
            source_name="SOP 文档",
            loader=lambda: self.knowledge_service.search_sops(
                query=service_record.get("summary", service_name),
                service_name=service_name,
                data_mode=data_mode,
            ),
            observations=observations,
            unknowns=unknowns,
        )
        optional_evidence_ids = [
            record["evidence_id"] for record in [*deployments, *incidents, *sops]
        ]
        react_steps.append(
            self._react_step(
                3,
                "查询知识类上下文数据源。",
                "retrieve_knowledge_context",
                "historical incidents + sops",
                f"检索到 {len(optional_evidence_ids)} 条历史案例/SOP 证据。",
                optional_evidence_ids,
            )
        )

        context = self._build_context(
            service_record,
            metrics,
            deployments,
            incidents,
            sops,
            unknowns,
        )
        evidence = [
            self._record_to_evidence(record)
            for record in [service_record, *metrics, *deployments, *incidents, *sops]
        ]
        observations.append(
            f"完成 {service_name} 上下文检索：metrics={len(metrics)}, "
            f"deployments={len(deployments)}, incidents={len(incidents)}, sops={len(sops)}。"
        )
        status_value = "partial" if unknowns else "completed"
        react_steps.append(
            self._react_step(
                4,
                "汇总上下文检索结果。",
                "finish",
                f"status={status_value}",
                f"返回 {len(evidence)} 条上下文证据。",
                [item.evidence_id for item in evidence],
            )
        )
        return self._run(status_value, context, evidence, observations, react_steps)

    def _limit_error(self) -> str | None:
        if self.limits.max_iterations < 1:
            return "Context Retrieval Agent 迭代次数上限不足，拒绝执行。"
        if self.limits.timeout_ms < 1:
            return "Context Retrieval Agent timeout_ms 非法，拒绝执行。"
        if self.limits.max_tool_calls < self.REQUIRED_TOOLS:
            return "Context Retrieval Agent 工具调用上限不足，无法检索必要上下文。"
        return None

    def _validate_service_record(self, service_record: dict[str, Any]) -> None:
        missing = sorted(self.REQUIRED_SERVICE_FIELDS - set(service_record))
        if missing:
            raise AppError(
                "CONTEXT_EVIDENCE_INVALID",
                "服务目录记录缺少必要上下文字段",
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                {"missing": missing},
            )
        if service_record.get("data_mode") != DataMode.MOCK.value:
            raise AppError(
                "CONTEXT_EVIDENCE_INVALID",
                "服务目录记录 data_mode 非 mock",
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                {"data_mode": service_record.get("data_mode")},
            )

    def _get_optional_records(
        self,
        source_name: str,
        loader: Callable[[], list[dict[str, Any]]],
        observations: list[str],
        unknowns: list[str],
    ) -> list[dict[str, Any]]:
        try:
            records = loader()
        except AppError as exc:
            message = f"可选{source_name}检索失败：{exc.code}。"
            observations.append(message)
            unknowns.append(message)
            return []
        observations.append(f"已查询可选{source_name}：{len(records)} 条。")
        return records

    def _build_context(
        self,
        service_record: dict[str, Any],
        metrics: list[dict[str, Any]],
        deployments: list[dict[str, Any]],
        incidents: list[dict[str, Any]],
        sops: list[dict[str, Any]],
        unknowns: list[str],
    ) -> RetrievedContext:
        return RetrievedContext(
            service=ServiceContext(
                service_id=service_record["service_id"],
                name=service_record["name"],
                display_name=service_record["display_name"],
                aliases=service_record.get("aliases", []),
                owner_team=service_record["owner_team"],
                criticality=service_record["criticality"],
                dependencies=service_record.get("dependencies", []),
                data_mode=DataMode.MOCK,
            ),
            metrics=[
                MetricSnapshot(
                    evidence_id=record["evidence_id"],
                    metric_name=record["metric_name"],
                    value=record["value"],
                    unit=record["unit"],
                    observed_at=record["observed_at"],
                    quality=record["quality"],
                    summary=record["summary"],
                    data_mode=DataMode.MOCK,
                )
                for record in metrics
            ],
            deployments=[
                DeploymentRecord(
                    evidence_id=record["evidence_id"],
                    version=record["version"],
                    deployed_at=record["deployed_at"],
                    author=record["author"],
                    summary=record["summary"],
                    data_mode=DataMode.MOCK,
                )
                for record in deployments
            ],
            historical_incidents=[
                HistoricalIncident(
                    evidence_id=record["evidence_id"],
                    incident_id=record["incident_id"],
                    root_cause=record["root_cause"],
                    summary=record["summary"],
                    data_mode=DataMode.MOCK,
                )
                for record in incidents
            ],
            sop_documents=[
                SopDocument(
                    evidence_id=record["evidence_id"],
                    sop_id=record["sop_id"],
                    title=record["title"],
                    actions=record["actions"],
                    data_mode=DataMode(record.get("data_mode", DataMode.MOCK.value)),
                )
                for record in sops
            ],
            unknowns=unknowns,
        )

    def _record_to_evidence(self, record: dict[str, Any]) -> Evidence:
        return Evidence(
            evidence_id=record["evidence_id"],
            source_type=record["source_type"],
            source_id=record["source_id"],
            source_name=record["source_name"],
            observed_at=record.get("observed_at"),
            retrieved_at=record.get("retrieved_at"),
            service=record.get("service"),
            metric_name=record.get("metric_name"),
            value=record.get("value"),
            unit=record.get("unit"),
            quality=record["quality"],
            data_mode=DataMode(record.get("data_mode", DataMode.MOCK.value)),
            summary=record["summary"],
            trace_uri=record.get("trace_uri"),
            quality_reason=record.get("quality_reason"),
        )

    def _app_error_result(
        self,
        request: InternalTaskRequest,
        exc: AppError,
    ) -> InternalTaskResult:
        return self.make_task_result(
            request=request,
            status="failed",
            error=AgentTaskError(
                code=exc.code,
                message=exc.message,
                details=exc.details,
            ),
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

    def _run(
        self,
        status: str,
        context: RetrievedContext,
        evidence: list[Evidence],
        observations: list[str],
        react_steps: list[ReActStep],
        iterations_used: int = 1,
    ) -> ContextRetrievalAgentRun:
        return ContextRetrievalAgentRun(
            agent_name=self.name,
            status=status,
            context=context,
            evidence=evidence,
            observations=observations,
            evidence_ids=[item.evidence_id for item in evidence],
            react_steps=react_steps,
            iterations_used=min(iterations_used, self.limits.max_iterations),
            max_iterations=self.limits.max_iterations,
            max_tool_calls=self.limits.max_tool_calls,
        )
