from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from fastapi import status
from pydantic import BaseModel, Field, ValidationError, field_validator

from intelliticket_backend.errors import AppError
from intelliticket_backend.repositories.mock_ops_data import MockOpsDataRepository
from intelliticket_backend.schemas.tickets import (
    DataMode,
    Evidence,
    TicketCategory,
    TicketClassification,
    TicketPriority,
)
from intelliticket_backend.services.agents.base import AgentCapability, BaseAgent
from intelliticket_backend.services.agents.envelope import (
    AgentTaskError,
    InternalTaskRequest,
    InternalTaskResult,
    ReActStep,
)
from intelliticket_backend.services.llm import LlmClient, LlmClientError


class IntakeLlmClassification(BaseModel):
    """LLM 工单分类结构化输出 schema。"""

    category: TicketCategory
    summary: str
    affected_service: str | None
    symptoms: list[str]
    priority: TicketPriority
    priority_reason: str
    extracted_metrics: dict[str, Any] = Field(default_factory=dict)

    @field_validator("symptoms", mode="before")
    @classmethod
    def coerce_symptoms_to_list(cls, v: Any) -> list[str]:
        """若 LLM 返回字符串而非数组，按逗号或中文标点拆分。"""
        if isinstance(v, str):
            import re
            parts = re.split(r"[,，、；;]", v)
            return [p.strip() for p in parts if p.strip()]
        if isinstance(v, list):
            return [str(item) for item in v]
        return []


@dataclass(frozen=True)
class IntakeAgentLimits:
    """Intake Agent 执行边界。"""

    max_iterations: int = 1
    max_tool_calls: int = 1
    timeout_ms: int = 1000


@dataclass(frozen=True)
class IntakeAgentRun:
    """Intake Agent 内部执行结果。"""

    agent_name: str
    status: str
    classification: TicketClassification | None
    service_record: dict[str, Any] | None
    evidence: list[Evidence] = field(default_factory=list)
    observations: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    react_steps: list[ReActStep] = field(default_factory=list)
    iterations_used: int = 1
    max_iterations: int = 1
    max_tool_calls: int = 1


class IntakeAgent(BaseAgent):
    """基于工单文本和 mock 服务目录的轻量 Intake Agent。"""

    name = "ticket_intake_agent"
    description = "理解工单输入，提取服务、症状、指标、类型和优先级"
    capabilities = [AgentCapability.TICKET_INTAKE]

    REQUIRED_SERVICE_FIELDS = {
        "evidence_id",
        "source_type",
        "source_id",
        "source_name",
        "quality",
        "data_mode",
        "summary",
        "name",
        "criticality",
    }

    def __init__(
        self,
        repository: MockOpsDataRepository | None = None,
        limits: IntakeAgentLimits | None = None,
        llm_client: LlmClient | None = None,
        strategy: str = "deterministic",
    ) -> None:
        self.repository = repository or MockOpsDataRepository()
        self.limits = limits or IntakeAgentLimits()
        self.llm_client = llm_client
        self.strategy = strategy

    def handle_task(self, request: InternalTaskRequest) -> InternalTaskResult:
        """处理内部任务信封，不代表正式 A2A 协议兼容。"""
        if request.to_agent != self.name:
            return self.wrong_target_result(request)

        try:
            text = request.payload["text"]
            data_mode = DataMode(request.payload["data_mode"])
            observed_at = request.payload.get("observed_at", request.created_at)
            if not isinstance(text, str) or not isinstance(observed_at, str):
                raise TypeError("text 和 observed_at 必须是字符串")
            run = self.run(
                ticket_id=request.ticket_id,
                text=text,
                data_mode=data_mode,
                observed_at=observed_at,
            )
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            return self.invalid_payload_result(request, exc)
        except AppError as exc:
            return self._app_error_result(request, exc)

        return self.make_task_result(
            request=request,
            status=run.status,
            payload={
                "classification": (
                    run.classification.model_dump(mode="json")
                    if run.classification is not None
                    else None
                ),
                "service_record": run.service_record,
                "evidence": [item.model_dump(mode="json") for item in run.evidence],
            },
            evidence_ids=run.evidence_ids,
            observations=run.observations,
            react_steps=run.react_steps,
        )

    def run(
        self,
        ticket_id: str,
        text: str,
        data_mode: DataMode,
        observed_at: str,
    ) -> IntakeAgentRun:
        observations = [
            f"执行边界：max_iterations={self.limits.max_iterations}, "
            f"max_tool_calls={self.limits.max_tool_calls}, timeout_ms={self.limits.timeout_ms}",
        ]
        react_steps = [
            self._react_step(
                1,
                "校验工单输入和数据模式。",
                "validate_input",
                f"ticket_id={ticket_id}, data_mode={data_mode.value}",
                "工单输入已进入 intake 流程。",
                [],
            )
        ]

        if self.strategy not in {"deterministic", "llm"}:
            raise AppError(
                "INTAKE_STRATEGY_INVALID",
                "intake agent 策略无效，仅支持 deterministic 或 llm",
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                {"strategy": self.strategy},
            )

        evidence = [self._ticket_input_evidence(ticket_id, text, data_mode, observed_at)]

        if data_mode != DataMode.MOCK:
            observations.append("data_mode 非 mock，跳过 mock 服务目录，仅基于工单文本分类。")
            if self.strategy == "llm":
                return self._llm_run(
                    ticket_id=ticket_id,
                    text=text,
                    data_mode=data_mode,
                    observed_at=observed_at,
                    evidence=evidence,
                    observations=observations,
                    react_steps=react_steps,
                    service_record=None,
                )
            symptoms = self._extract_symptoms(text)
            extracted_metrics = self._extract_metrics(text)
            priority, priority_reason = self._classify_priority(
                service_record=None,
                symptoms=symptoms,
                extracted_metrics=extracted_metrics,
            )
            evidence_ids = [item.evidence_id for item in evidence]
            classification = TicketClassification(
                category=TicketCategory.OPS_ALERT,
                summary=self._make_summary(text, None),
                affected_service=None,
                symptoms=symptoms,
                priority=priority,
                priority_reason=priority_reason,
                extracted_metrics=extracted_metrics,
                evidence_ids=evidence_ids,
            )
            react_steps.append(
                self._react_step(
                    2,
                    "跳过 mock 服务目录，基于工单文本完成分类定级。",
                    "classify_from_ticket_text",
                    f"symptoms={len(symptoms)}, metrics={list(extracted_metrics)}",
                    f"优先级：{priority.value}。",
                    evidence_ids,
                )
            )
            return self._run("completed", classification, None, evidence, observations, react_steps)

        if self.strategy == "llm":
            service_record = self.repository.resolve_service(text)
            if service_record:
                self._validate_service_record(service_record)
                service_evidence = self._record_to_evidence(service_record)
                evidence.append(service_evidence)
                observations.append(f"通过 mock 服务目录识别服务：{service_record['name']}。")
            return self._llm_run(
                ticket_id=ticket_id,
                text=text,
                data_mode=data_mode,
                observed_at=observed_at,
                evidence=evidence,
                observations=observations,
                react_steps=react_steps,
                service_record=service_record,
            )

        service_record = self.repository.resolve_service(text)
        symptoms = self._extract_symptoms(text)
        extracted_metrics = self._extract_metrics(text)
        affected_service = service_record["name"] if service_record else None

        if service_record:
            self._validate_service_record(service_record)
            service_evidence = self._record_to_evidence(service_record)
            evidence.append(service_evidence)
            observations.append(f"通过 mock 服务目录识别服务：{affected_service}。")
            react_steps.append(
                self._react_step(
                    2,
                    "查询 mock 服务目录并识别影响服务。",
                    "resolve_service",
                    "service_catalog lookup",
                    f"识别服务：{affected_service}。",
                    [service_evidence.evidence_id],
                )
            )
        else:
            observations.append("未能从 mock 服务目录识别影响服务。")
            react_steps.append(
                self._react_step(
                    2,
                    "查询 mock 服务目录但未识别影响服务。",
                    "resolve_service",
                    "service_catalog lookup",
                    "未识别服务，不编造服务上下文。",
                    [],
                )
            )

        priority, priority_reason = self._classify_priority(
            service_record=service_record,
            symptoms=symptoms,
            extracted_metrics=extracted_metrics,
        )
        evidence_ids = [item.evidence_id for item in evidence]
        react_steps.append(
            self._react_step(
                3,
                "基于服务等级、症状和指标摘要计算优先级。",
                "classify_priority",
                f"symptoms={len(symptoms)}, metrics={list(extracted_metrics)}",
                f"优先级：{priority.value}。",
                evidence_ids,
            )
        )
        classification = TicketClassification(
            category=TicketCategory.OPS_ALERT,
            summary=self._make_summary(text, affected_service),
            affected_service=affected_service,
            symptoms=symptoms,
            priority=priority,
            priority_reason=priority_reason,
            extracted_metrics=extracted_metrics,
            evidence_ids=evidence_ids,
        )
        self._validate_classification_evidence(classification, evidence)
        observations.append(f"完成分类定级：{classification.priority.value}。")
        react_steps.append(
            self._react_step(
                4,
                "汇总 intake 分类结果。",
                "finish",
                f"affected_service={affected_service or 'unknown'}",
                "返回分类、服务记录和 intake 证据。",
                evidence_ids,
            )
        )
        return self._run(
            "completed",
            classification,
            service_record,
            evidence,
            observations,
            react_steps,
        )

    def _llm_run(
        self,
        ticket_id: str,
        text: str,
        data_mode: DataMode,
        observed_at: str,
        evidence: list[Evidence],
        observations: list[str],
        react_steps: list[ReActStep],
        service_record: dict[str, Any] | None,
    ) -> IntakeAgentRun:
        """LLM 驱动的工单分类路径。"""
        if self.llm_client is None:
            raise AppError(
                "INTAKE_LLM_CLIENT_MISSING",
                "intake agent 策略为 llm 但未注入 LlmClient，拒绝执行",
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                {"strategy": self.strategy},
            )
        react_steps.append(
            self._react_step(
                2,
                "调用 LLM 进行工单分类定级。",
                "llm_classify",
                f"text_len={len(text)}",
                "LLM 结构化分类已返回。",
                [],
            )
        )
        observations.append("已通过 LLM 完成工单分类定级。")
        try:
            llm_output = self.llm_client.structured_json_call(
                system_prompt=self._intake_llm_system_prompt(),
                user_payload={"text": text, "data_mode": data_mode.value},
                response_schema=IntakeLlmClassification,
            )
        except LlmClientError as exc:
            raise AppError(
                "INTAKE_LLM_FAILED",
                "LLM 工单分类调用失败，已阻止生成假结果",
                status.HTTP_502_BAD_GATEWAY,
                {"llm_error_code": exc.code, "details": exc.details},
            ) from exc

        known_ids = {item.evidence_id for item in evidence}
        evidence_ids = [eid for eid in [item.evidence_id for item in evidence] if eid in known_ids]
        react_steps.append(
            self._react_step(
                3,
                "基于 LLM 分类结果和服务目录证据，汇总 intake 输出。",
                "finish",
                f"affected_service={llm_output.affected_service or 'unknown'}",
                f"返回 LLM 分类结果，优先级 {llm_output.priority.value}。",
                evidence_ids,
            )
        )
        classification = TicketClassification(
            category=llm_output.category,
            summary=llm_output.summary,
            affected_service=llm_output.affected_service,
            symptoms=llm_output.symptoms,
            priority=llm_output.priority,
            priority_reason=llm_output.priority_reason,
            extracted_metrics=llm_output.extracted_metrics,
            evidence_ids=evidence_ids,
        )
        self._validate_classification_evidence(classification, evidence)
        return self._run(
            "completed",
            classification,
            service_record,
            evidence,
            observations,
            react_steps,
        )

    def _intake_llm_system_prompt(self) -> str:
        return (
            "你是 IntelliTicket 平台的工单分类 Agent（ticket_intake_agent）。"
            "你的任务是根据用户输入的工单文本，输出结构化的工单分类结果。"
            "只能输出 JSON 对象，字段包括 category、summary、affected_service、symptoms、"
            "priority、priority_reason、extracted_metrics。"
            "category 必须是 ops_alert（运维告警）或 support_request（支持请求）。"
            "priority 必须是 P1、P2、P3 或 P4，需给出明确理由。"
            "affected_service 必须使用纯英文服务标识名（如 payment-service），不要用中文名。"
            "symptoms 必须是字符串数组 []，如 [\"timeout\", \"order_volume_drop\"]，"
            "每个元素是一个关键词，不要写成一段长文本。"
            "如果从文本中提取到数值指标（如订单量、超时率），填入 extracted_metrics。"
            "不要编造信息——如果文本中没有明确线索，相应字段留空或使用合理默认值。"
        )

    def _ticket_input_evidence(
        self,
        ticket_id: str,
        text: str,
        data_mode: DataMode,
        observed_at: str,
    ) -> Evidence:
        return Evidence(
            evidence_id="ev_ticket_input_001",
            source_type="ticket_input",
            source_id=ticket_id,
            source_name="用户输入工单",
            observed_at=observed_at,
            retrieved_at=observed_at,
            service=None,
            quality="user_provided",
            data_mode=data_mode,
            summary=text,
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
            data_mode=DataMode.MOCK,
            summary=record["summary"],
        )

    def _validate_service_record(self, service_record: dict[str, Any]) -> None:
        missing = sorted(self.REQUIRED_SERVICE_FIELDS - set(service_record))
        if missing:
            raise AppError(
                "INTAKE_EVIDENCE_INVALID",
                "服务目录记录缺少必要溯源字段",
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                {"missing": missing},
            )
        if service_record.get("data_mode") != DataMode.MOCK.value:
            raise AppError(
                "INTAKE_EVIDENCE_INVALID",
                "服务目录记录 data_mode 非 mock",
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                {"data_mode": service_record.get("data_mode")},
            )

    def _validate_classification_evidence(
        self,
        classification: TicketClassification,
        evidence: list[Evidence],
    ) -> None:
        known_ids = {item.evidence_id for item in evidence}
        missing = sorted(set(classification.evidence_ids) - known_ids)
        if missing:
            raise AppError(
                "INTAKE_EVIDENCE_INVALID",
                "工单分类引用了不存在的 intake 证据",
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                {"missing_evidence_ids": missing},
            )
        evidence_modes = {item.data_mode for item in evidence}
        if len(evidence_modes) > 1:
            raise AppError(
                "INTAKE_EVIDENCE_INVALID",
                "intake 证据混用了不同 data_mode",
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                {"data_modes": sorted(mode.value for mode in evidence_modes)},
            )

    def _extract_symptoms(self, text: str) -> list[str]:
        symptoms: list[str] = []
        if "超时" in text or "timeout" in text.lower():
            symptoms.append("timeout")
        if "订单量" in text and ("降" in text or "下降" in text):
            symptoms.append("order_volume_drop")
        if "告警" in text:
            symptoms.append("alert")
        return symptoms or ["unknown_symptom"]

    def _extract_metrics(self, text: str) -> dict[str, int]:
        numbers = [int(value) for value in re.findall(r"(\d+)\s*/?\s*min", text)]
        if len(numbers) >= 2:
            return {"order_qps_before": numbers[0], "order_qps_after": numbers[1]}
        return {}

    def _classify_priority(
        self,
        service_record: dict[str, Any] | None,
        symptoms: list[str],
        extracted_metrics: dict[str, int],
    ) -> tuple[TicketPriority, str]:
        before = extracted_metrics.get("order_qps_before")
        after = extracted_metrics.get("order_qps_after")
        severe_drop = bool(
            before and after is not None and before > 0 and after / before <= 0.5
        )
        critical_service = (
            service_record and service_record.get("criticality") == "business_critical"
        )
        if critical_service and "timeout" in symptoms and severe_drop:
            return TicketPriority.P1, "核心支付服务超时且订单量下降超过 50%。"
        if critical_service and "timeout" in symptoms:
            return TicketPriority.P2, "核心支付服务出现超时，但缺少严重业务量下降证据。"
        return TicketPriority.P3, "未识别到核心业务服务的严重影响证据。"

    def _make_summary(self, text: str, affected_service: str | None) -> str:
        if affected_service:
            return f"{affected_service} 出现运维告警：{text}"
        return f"未识别服务的运维告警：{text}"

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
        classification: TicketClassification | None,
        service_record: dict[str, Any] | None,
        evidence: list[Evidence],
        observations: list[str],
        react_steps: list[ReActStep],
    ) -> IntakeAgentRun:
        return IntakeAgentRun(
            agent_name=self.name,
            status=status,
            classification=classification,
            service_record=service_record,
            evidence=evidence,
            observations=observations,
            evidence_ids=[item.evidence_id for item in evidence],
            react_steps=react_steps,
            iterations_used=min(1, self.limits.max_iterations),
            max_iterations=self.limits.max_iterations,
            max_tool_calls=self.limits.max_tool_calls,
        )
