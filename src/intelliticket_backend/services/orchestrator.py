from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from threading import Event
from typing import Any

from fastapi import status
from pydantic import ValidationError

from intelliticket_backend.errors import AppError
from intelliticket_backend.schemas.orchestration import (
    ALLOWED_NEXT_AGENTS,
    PRIVATE_OR_UNSUPPORTED_ROUTE_FIELDS,
    RouteDecision,
    SupervisorAgentRun,
    SupervisorRunFailure,
    SupervisorRunResult,
    SupervisorState,
)
from intelliticket_backend.schemas.tickets import (
    DiagnosisResult,
    Evidence,
    EvidenceRef,
    FinalReport,
    OpsTicketResult,
    RetrievedContext,
    ReviewResult,
    RoutingRecommendation,
    TicketClassification,
    TicketProcessRequest,
    TicketProcessResponse,
    TicketProcessWsAgentProgressEvent,
    WorkflowStepTrace,
)
from intelliticket_backend.services.agents.context import ContextRetrievalAgent
from intelliticket_backend.services.agents.diagnosis import DiagnosisAgent
from intelliticket_backend.services.agents.envelope import AgentTaskError, InternalTaskRequest
from intelliticket_backend.services.agents.intake import IntakeAgent
from intelliticket_backend.services.agents.report import ReportAgent
from intelliticket_backend.services.agents.reviewer import ReviewerAgent
from intelliticket_backend.services.agents.routing import RoutingAgent
from intelliticket_backend.services.llm import LlmClient, LlmClientError

SUPERVISOR_AGENT_NAME = "supervisor_orchestrator"

AGENT_TO_STEP = {
    "ticket_intake_agent": "ticket_intake",
    "context_retrieval_agent": "context_retrieval",
    "diagnosis_agent": "diagnosis",
    "routing_agent": "routing",
    "reviewer_agent": "review",
    "report_agent": "report",
}

DEFAULT_MESSAGE_TYPES = {
    "ticket_intake_agent": "ticket_intake_request",
    "context_retrieval_agent": "context_retrieval_request",
    "diagnosis_agent": "diagnosis_request",
    "routing_agent": "routing_request",
    "reviewer_agent": "review_request",
    "report_agent": "report_request",
    "support_intake_service": "support_intake_service_request",
    "support_kb_retrieval_service": "support_kb_retrieval_service_request",
    "support_routing_service": "support_routing_service_request",
    "support_reply_suggestion_service": "support_reply_suggestion_service_request",
    "finish": "finish",
    "abstain": "abstain",
}

REQUIRED_COMPLETED_AGENTS = {
    "ticket_intake_agent": [],
    "context_retrieval_agent": ["ticket_intake_agent"],
    "diagnosis_agent": ["ticket_intake_agent", "context_retrieval_agent"],
    "routing_agent": [
        "ticket_intake_agent",
        "context_retrieval_agent",
        "diagnosis_agent",
    ],
    "reviewer_agent": [
        "ticket_intake_agent",
        "context_retrieval_agent",
        "diagnosis_agent",
        "routing_agent",
    ],
    "report_agent": [
        "ticket_intake_agent",
        "context_retrieval_agent",
        "diagnosis_agent",
        "routing_agent",
        "reviewer_agent",
    ],
    "support_intake_service": [],
    "support_kb_retrieval_service": ["support_intake_service"],
    "support_routing_service": ["support_intake_service", "support_kb_retrieval_service"],
    "support_reply_suggestion_service": [
        "support_intake_service",
        "support_kb_retrieval_service",
        "support_routing_service",
    ],
    "finish": [
        "ticket_intake_agent",
        "context_retrieval_agent",
        "diagnosis_agent",
        "routing_agent",
        "reviewer_agent",
    ],
    "abstain": [],
}


class OrchestrationRunError(AppError):
    """携带终态审计快照的编排错误。"""

    def __init__(self, original: AppError, run_failure: SupervisorRunFailure) -> None:
        super().__init__(original.code, original.message, original.status_code, original.details)
        self.run_failure = run_failure


class SupervisorOrchestrator:
    """受控 Supervisor 编排器：LLM 只能选择下一步 Agent。"""

    def __init__(
        self,
        *,
        llm_client: LlmClient | None = None,
        intake_agent: IntakeAgent | None = None,
        context_agent: ContextRetrievalAgent | None = None,
        diagnosis_agent: DiagnosisAgent | None = None,
        routing_agent: RoutingAgent | None = None,
        reviewer_agent: ReviewerAgent | None = None,
        report_agent: ReportAgent | None = None,
        max_steps: int = 8,
        route_mode: str = "deterministic",
        llm_temperature: float | None = 0.0,
        case_retrieval: Any | None = None,
    ) -> None:
        self.llm_client = llm_client
        self.max_steps = max_steps
        self.route_mode = route_mode
        self.llm_temperature = llm_temperature
        self.case_retrieval = case_retrieval
        self.agents = {
            "ticket_intake_agent": intake_agent or IntakeAgent(),
            "context_retrieval_agent": context_agent or ContextRetrievalAgent(),
            "diagnosis_agent": diagnosis_agent or DiagnosisAgent(),
            "routing_agent": routing_agent or RoutingAgent(),
            "reviewer_agent": reviewer_agent or ReviewerAgent(),
            "report_agent": report_agent or ReportAgent(),
        }

    def run(
        self,
        request: TicketProcessRequest,
        *,
        ticket_id: str,
        run_id: str,
        progress_sink: Callable[[TicketProcessWsAgentProgressEvent], None] | None = None,
        cancel_event: Event | None = None,
    ) -> TicketProcessResponse:
        return self.run_with_audit(
            request,
            ticket_id=ticket_id,
            run_id=run_id,
            progress_sink=progress_sink,
            cancel_event=cancel_event,
        ).response

    def run_with_audit(
        self,
        request: TicketProcessRequest,
        *,
        ticket_id: str,
        run_id: str,
        progress_sink: Callable[[TicketProcessWsAgentProgressEvent], None] | None = None,
        cancel_event: Event | None = None,
    ) -> SupervisorRunResult:
        state = SupervisorState(
            ticket_id=ticket_id,
            run_id=run_id,
            request=request,
            max_steps=self.max_steps,
        )
        trace: list[WorkflowStepTrace] = []
        route_decisions: list[RouteDecision] = []
        started_at = self._now()

        try:
            while state.status == "running":
                self._check_cancelled(cancel_event, ticket_id, run_id)
                if state.current_step >= state.max_steps:
                    state.status = "failed"
                    raise AppError(
                        "ORCHESTRATOR_STEP_LIMIT_EXCEEDED",
                        "Supervisor 编排超过最大步骤限制",
                        status.HTTP_500_INTERNAL_SERVER_ERROR,
                        {"max_steps": state.max_steps},
                    )

                state.current_step += 1
                route = self._next_route(state)
                self._validate_route(route, state)
                route_decisions.append(route)

                if route.next_agent == "finish":
                    self._validate_ready_to_finish(state)
                    self._validate_evidence_refs(state, trace)
                    state.status = "completed"
                    completed_at = self._now()
                    report = state.report or FinalReport(
                        title="审查标记，报告暂停",
                        summary=(
                            "ReviewerAgent 标记了证据链问题，"
                            "已跳过自动报告生成，请人工复核。"
                        ),
                        facts=[],
                        derived_findings=[],
                        assumptions=[],
                        unknowns=[],
                        recommendations=["人工复核 Reviewer 标记的问题后手动生成报告。"],
                    )
                    response = TicketProcessResponse(
                        ticket_id=ticket_id,
                        run_id=run_id,
                        data_mode=request.data_mode,
                        classification=state.classification,
                        context=state.context,
                        diagnosis=state.diagnosis,
                        routing=state.routing,
                        review=state.review,
                        report=report,
                        agent_trace=trace,
                        evidence=state.evidence,
                        similar_cases=state.similar_cases,
                        ops_result=OpsTicketResult(
                            affected_service=state.classification.affected_service,
                            candidate_root_causes=state.diagnosis.candidate_root_causes,
                            recommended_actions=state.routing.recommended_actions,
                            assigned_team=state.routing.recommended_team,
                            sop_refs=state.routing.sop_refs,
                            evidence_ids=[item.evidence_id for item in state.evidence],
                        ),
                    )
                    return SupervisorRunResult(
                        response=response,
                        agent_runs=state.agent_runs,
                        route_decisions=route_decisions,
                        started_at=started_at,
                        completed_at=completed_at,
                    )

                if route.next_agent == "abstain":
                    state.status = "abstained"
                    raise AppError(
                        "ORCHESTRATOR_ABSTAINED",
                        "Supervisor 选择 abstain，未生成部分响应以避免伪造完整结果",
                        status.HTTP_502_BAD_GATEWAY,
                        {"reason_summary": route.reason_summary},
                    )

                agent = self.agents.get(route.next_agent)
                if agent is None:
                    raise AppError(
                        "ORCHESTRATOR_INVALID_ROUTE",
                        "Supervisor 选择了不存在的 Agent",
                        status.HTTP_502_BAD_GATEWAY,
                        {"next_agent": route.next_agent, "known_agents": sorted(self.agents)},
                    )

                task_request = self._build_task_request(state, route)
                agent_started_at = self._now()
                result = agent.handle_task(task_request)
                agent_run = SupervisorAgentRun(
                    task_id=task_request.task_id,
                    ticket_id=ticket_id,
                    run_id=run_id,
                    agent_name=result.agent_name,
                    status=result.status,
                    route_decision=route,
                    evidence_ids=result.evidence_ids,
                    observations=result.observations,
                    react_steps=result.react_steps,
                    error=result.error,
                    started_at=agent_started_at,
                    completed_at=result.completed_at,
                )
                state.agent_runs.append(agent_run)

                if result.status == "failed":
                    state.status = "failed"
                    if result.error is not None:
                        state.errors.append(result.error)
                    raise AppError(
                        "AGENT_TASK_FAILED",
                        "Agent 执行失败，Supervisor 已停止编排",
                        status.HTTP_500_INTERNAL_SERVER_ERROR,
                        {
                            "agent_name": result.agent_name,
                            "error": result.error.model_dump(mode="json") if result.error else {},
                        },
                    )

                self._merge_result(state, route.next_agent, result.payload)
                self._validate_agent_output_evidence(state, route.next_agent)
                step_trace = self._trace_for_result(
                    route.next_agent,
                    result.status,
                    result.evidence_ids,
                )
                trace.append(step_trace)
                self._emit_progress(
                    progress_sink,
                    cancel_event,
                    ticket_id,
                    run_id,
                    len(trace),
                    step_trace,
                    result.agent_name,
                )

            raise AppError(
                "ORCHESTRATOR_FAILED",
                "Supervisor 编排未能生成结果",
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                {"status": state.status},
            )
        except OrchestrationRunError:
            raise
        except AppError as exc:
            raise self._run_error_from_app_error(exc, state, route_decisions, started_at) from exc

    def _run_error_from_app_error(
        self,
        exc: AppError,
        state: SupervisorState,
        route_decisions: list[RouteDecision],
        started_at: str,
    ) -> OrchestrationRunError:
        run_status = "cancelled" if exc.code == "PROCESSING_CANCELLED" else "failed"
        state.status = run_status
        run_failure = SupervisorRunFailure(
            ticket_id=state.ticket_id,
            run_id=state.run_id,
            status=run_status,
            data_mode=state.request.data_mode,
            error=AgentTaskError(code=exc.code, message=exc.message, details=exc.details),
            agent_runs=state.agent_runs,
            route_decisions=route_decisions,
            evidence=state.evidence,
            started_at=started_at,
            completed_at=self._now(),
        )
        return OrchestrationRunError(exc, run_failure)

    def _next_route(self, state: SupervisorState) -> RouteDecision:
        if self.route_mode == "deterministic":
            return self._deterministic_next_route(state)
        if self.route_mode != "llm":
            raise AppError(
                "ORCHESTRATOR_ROUTE_MODE_INVALID",
                "Supervisor route_mode 无效",
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                {"route_mode": self.route_mode},
            )
        if self.llm_client is None:
            raise AppError(
                "LLM_ROUTE_FAILED",
                "LLM routing 已启用但未配置 LLM client",
                status.HTTP_502_BAD_GATEWAY,
                {"route_mode": self.route_mode},
            )
        try:
            raw_decision = self.llm_client.structured_json_call(
                system_prompt=self._route_system_prompt(),
                user_payload=self._route_user_payload(state),
                response_schema=RouteDecision,
                temperature=self.llm_temperature,
            )
        except LlmClientError as exc:
            raise AppError(
                "LLM_ROUTE_FAILED",
                "LLM 路由失败，未执行静默降级",
                status.HTTP_502_BAD_GATEWAY,
                {"llm_error_code": exc.code, "details": exc.details},
            ) from exc
        return self._normalize_route_decision(raw_decision)

    def _normalize_route_decision(self, raw_decision: Any) -> RouteDecision:
        if isinstance(raw_decision, RouteDecision):
            return raw_decision
        if isinstance(raw_decision, dict):
            private_fields = sorted(PRIVATE_OR_UNSUPPORTED_ROUTE_FIELDS & set(raw_decision))
            if private_fields:
                raise AppError(
                    "ORCHESTRATOR_PRIVATE_FIELD_REJECTED",
                    "LLM route 包含不允许的私有推理、工具或业务输出字段",
                    status.HTTP_502_BAD_GATEWAY,
                    {"fields": private_fields},
                )
            try:
                return RouteDecision.model_validate(raw_decision)
            except ValidationError as exc:
                raise AppError(
                    "ORCHESTRATOR_INVALID_ROUTE",
                    "LLM route 未通过 schema 校验",
                    status.HTTP_502_BAD_GATEWAY,
                    {"errors": self._safe_validation_errors(exc)},
                ) from exc
        raise AppError(
            "ORCHESTRATOR_INVALID_ROUTE",
            "LLM route 不是 JSON 对象",
            status.HTTP_502_BAD_GATEWAY,
            {"type": type(raw_decision).__name__},
        )

    def _deterministic_next_route(self, state: SupervisorState) -> RouteDecision:
        completed = self._completed_agents(state)
        # If reviewer flagged, skip report → finish early
        if "reviewer_agent" in completed and state.review is not None:
            if state.review.review_status == "flagged":
                return RouteDecision(
                    next_agent="finish",
                    message_type="finish",
                    reason_summary=(
                        "ReviewerAgent 标记了严重问题，跳过 ReportAgent 直接 finish。"
                    ),
                    required_inputs=[],
                    evidence_ids=[],
                    requires_human_review=True,
                )
        for agent_name in [
            "ticket_intake_agent",
            "context_retrieval_agent",
            "diagnosis_agent",
            "routing_agent",
            "reviewer_agent",
            "report_agent",
        ]:
            if agent_name not in completed:
                return RouteDecision(
                    next_agent=agent_name,
                    message_type=DEFAULT_MESSAGE_TYPES[agent_name],
                    reason_summary=f"deterministic route 选择 {agent_name}。",
                    required_inputs=REQUIRED_COMPLETED_AGENTS[agent_name],
                    evidence_ids=[],
                    requires_human_review=False,
                )
        return RouteDecision(
            next_agent="finish",
            message_type="finish",
            reason_summary="deterministic route 已完成全部 Agent，进入 finish。",
            required_inputs=REQUIRED_COMPLETED_AGENTS["finish"],
            evidence_ids=[],
            requires_human_review=False,
        )

    def _validate_route(self, route: RouteDecision, state: SupervisorState) -> None:
        if route.next_agent not in ALLOWED_NEXT_AGENTS:
            raise AppError(
                "ORCHESTRATOR_INVALID_ROUTE",
                "Supervisor 选择了不在 allowlist 内的下一步",
                status.HTTP_502_BAD_GATEWAY,
                {"next_agent": route.next_agent, "allowed": sorted(ALLOWED_NEXT_AGENTS)},
            )

        completed = self._completed_agents(state)
        if route.next_agent in completed:
            raise AppError(
                "ORCHESTRATOR_INVALID_ROUTE",
                "Supervisor 不能重复调用已完成的 Agent",
                status.HTTP_502_BAD_GATEWAY,
                {"next_agent": route.next_agent},
            )

        missing_prerequisites = [
            agent_name
            for agent_name in REQUIRED_COMPLETED_AGENTS[route.next_agent]
            if agent_name not in completed
        ]
        if missing_prerequisites:
            raise AppError(
                "ORCHESTRATOR_PREREQUISITE_MISSING",
                "Supervisor route 跳过了必要前置 Agent",
                status.HTTP_502_BAD_GATEWAY,
                {
                    "next_agent": route.next_agent,
                    "missing_prerequisites": missing_prerequisites,
                },
            )

        known_evidence_ids = {item.evidence_id for item in state.evidence}
        unknown_evidence_ids = sorted(set(route.evidence_ids) - known_evidence_ids)
        if unknown_evidence_ids:
            raise AppError(
                "ORCHESTRATOR_UNKNOWN_EVIDENCE_REF",
                "Supervisor route 引用了未知证据",
                status.HTTP_502_BAD_GATEWAY,
                {"unknown_evidence_ids": unknown_evidence_ids},
            )

    def _build_task_request(
        self,
        state: SupervisorState,
        route: RouteDecision,
    ) -> InternalTaskRequest:
        payload: dict[str, Any]
        if route.next_agent == "ticket_intake_agent":
            payload = {
                "text": state.request.text,
                "data_mode": state.request.data_mode.value,
                "observed_at": self._now(),
            }
        elif route.next_agent == "context_retrieval_agent":
            payload = {
                "service_record": state.service_record,
                "ticket_text": state.request.text,
                "data_mode": state.request.data_mode.value,
            }
        elif route.next_agent == "diagnosis_agent":
            if state.classification is None or state.context is None:
                self._raise_internal_prerequisite_error(route.next_agent)
            # Search similar cases for knowledge-informed diagnosis
            if self.case_retrieval is not None:
                similar = self.case_retrieval.search(
                    text=state.request.text,
                    symptoms=state.classification.symptoms,
                    top_k=3,
                )
                state.similar_cases = [
                    {
                        "ticket_id": tid,
                        "score": round(score, 3),
                        **(
                            {
                                "data_mode": c.data_mode,
                                "root_cause": c.root_cause,
                                "confirmed": bool(c.confirmed_root_cause),
                                "confirmed_root_cause": c.confirmed_root_cause,
                                "resolution": c.resolution,
                            }
                            if (c := self.case_retrieval.get_case(tid))
                            else {}
                        ),
                    }
                    for tid, score in similar
                ]
            payload = {
                "classification": state.classification.model_dump(mode="json"),
                "context": state.context.model_dump(mode="json"),
                "data_mode": state.request.data_mode.value,
                "ticket_text": state.request.text,
                "similar_cases": state.similar_cases,
            }
        elif route.next_agent == "routing_agent":
            if state.context is None or state.diagnosis is None:
                self._raise_internal_prerequisite_error(route.next_agent)
            payload = {
                "context": state.context.model_dump(mode="json"),
                "diagnosis": state.diagnosis.model_dump(mode="json"),
                "data_mode": state.request.data_mode.value,
            }
        elif route.next_agent == "reviewer_agent":
            if (
                state.classification is None
                or state.context is None
                or state.diagnosis is None
                or state.routing is None
            ):
                self._raise_internal_prerequisite_error(route.next_agent)
            payload = {
                "classification": state.classification.model_dump(mode="json"),
                "context": state.context.model_dump(mode="json"),
                "diagnosis": state.diagnosis.model_dump(mode="json"),
                "routing": state.routing.model_dump(mode="json"),
                "evidence": [e.model_dump(mode="json") for e in state.evidence],
                "data_mode": state.request.data_mode.value,
            }
        elif route.next_agent == "report_agent":
            if (
                state.classification is None
                or state.context is None
                or state.diagnosis is None
                or state.routing is None
            ):
                self._raise_internal_prerequisite_error(route.next_agent)
            payload = {
                "classification": state.classification.model_dump(mode="json"),
                "context": state.context.model_dump(mode="json"),
                "diagnosis": state.diagnosis.model_dump(mode="json"),
                "routing": state.routing.model_dump(mode="json"),
                "data_mode": state.request.data_mode.value,
            }
        else:
            raise AppError(
                "ORCHESTRATOR_INVALID_ROUTE",
                "无法为非 Agent route 构造任务",
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                {"next_agent": route.next_agent},
            )

        return InternalTaskRequest(
            task_id=f"TASK-{state.run_id}-{state.current_step:02d}",
            ticket_id=state.ticket_id,
            run_id=state.run_id,
            from_agent=SUPERVISOR_AGENT_NAME,
            to_agent=route.next_agent,
            message_type=route.message_type or DEFAULT_MESSAGE_TYPES[route.next_agent],
            payload=payload,
            evidence_ids=route.evidence_ids,
            idempotency_key=f"{state.run_id}:{state.current_step}:{route.next_agent}",
        )

    def _merge_result(
        self,
        state: SupervisorState,
        agent_name: str,
        payload: dict[str, Any],
    ) -> None:
        try:
            if agent_name == "ticket_intake_agent":
                classification = TicketClassification.model_validate(payload["classification"])
                state.classification = classification
                service_record = payload.get("service_record")
                if service_record is not None and not isinstance(service_record, dict):
                    raise TypeError("service_record 必须是对象或 null")
                state.service_record = service_record
                self._merge_evidence(state, payload.get("evidence", []))
            elif agent_name == "context_retrieval_agent":
                state.context = RetrievedContext.model_validate(payload["context"])
                self._merge_evidence(state, payload.get("evidence", []))
            elif agent_name == "diagnosis_agent":
                state.diagnosis = DiagnosisResult.model_validate(payload["diagnosis"])
            elif agent_name == "routing_agent":
                state.routing = RoutingRecommendation.model_validate(payload["routing"])
            elif agent_name == "reviewer_agent":
                state.review = ReviewResult.model_validate(payload["review"])
            elif agent_name == "report_agent":
                state.report = FinalReport.model_validate(payload["report"])
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            raise AppError(
                "ORCHESTRATOR_AGENT_PAYLOAD_INVALID",
                "Agent 返回 payload 未通过 Supervisor 校验",
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                {"agent_name": agent_name, "error": str(exc)},
            ) from exc

    def _merge_evidence(self, state: SupervisorState, raw_evidence: list[Any]) -> None:
        known = {item.evidence_id: item for item in state.evidence}
        for raw_item in raw_evidence:
            item = Evidence.model_validate(raw_item)
            existing = known.get(item.evidence_id)
            if existing is not None:
                if existing.model_dump(mode="json") != item.model_dump(mode="json"):
                    raise AppError(
                        "EVIDENCE_CONFLICT",
                        "不同 Agent 返回了相同 evidence_id 但内容不一致",
                        status.HTTP_500_INTERNAL_SERVER_ERROR,
                        {"evidence_id": item.evidence_id},
                    )
                continue
            state.evidence.append(item)
            known[item.evidence_id] = item

    def _validate_agent_output_evidence(
        self,
        state: SupervisorState,
        agent_name: str,
    ) -> None:
        known = {item.evidence_id for item in state.evidence}
        referenced: set[str] = set()
        if state.classification is not None:
            referenced.update(state.classification.evidence_ids)
        if agent_name == "diagnosis_agent" and state.diagnosis is not None:
            for cause in state.diagnosis.candidate_root_causes:
                referenced.update(cause.evidence_ids)
        if agent_name == "routing_agent" and state.routing is not None:
            for action in state.routing.recommended_actions:
                referenced.update(action.evidence_ids)
        missing = sorted(referenced - known)
        if missing:
            raise AppError(
                "INSUFFICIENT_EVIDENCE",
                "Agent 输出引用了不存在的证据",
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                {"agent_name": agent_name, "missing_evidence_ids": missing},
            )

    def _trace_for_result(
        self,
        agent_name: str,
        run_status: str,
        evidence_ids: list[str],
    ) -> WorkflowStepTrace:
        now = self._now()
        summary: str
        if agent_name == "ticket_intake_agent":
            summary = f"{agent_name} {run_status}，完成工单分类定级"
        elif agent_name == "context_retrieval_agent":
            summary = f"{agent_name} {run_status}，检索到 {len(evidence_ids)} 条上下文证据"
        elif agent_name == "diagnosis_agent":
            summary = f"{agent_name} {run_status}，生成候选根因"
        elif agent_name == "routing_agent":
            summary = f"{agent_name} {run_status}，生成分派建议"
        elif agent_name == "reviewer_agent":
            summary = f"{agent_name} {run_status}，跨 Agent 证据一致性审查完成"
        elif agent_name == "report_agent":
            summary = f"{agent_name} {run_status}，生成最终处理报告"
        else:
            summary = f"{agent_name} {run_status}"
        return WorkflowStepTrace(
            step=AGENT_TO_STEP[agent_name],
            status=run_status,
            started_at=now,
            completed_at=now,
            summary=summary,
            evidence_ids=evidence_ids,
        )

    def _emit_progress(
        self,
        progress_sink: Callable[[TicketProcessWsAgentProgressEvent], None] | None,
        cancel_event: Event | None,
        ticket_id: str,
        run_id: str,
        sequence: int,
        trace: WorkflowStepTrace,
        agent_name: str,
    ) -> None:
        if progress_sink:
            progress_sink(
                TicketProcessWsAgentProgressEvent(
                    ticket_id=ticket_id,
                    run_id=run_id,
                    sequence=sequence,
                    agent_name=agent_name,
                    step=trace.step,
                    status=trace.status,
                    summary=trace.summary,
                    evidence_refs=[EvidenceRef(evidence_id=eid) for eid in trace.evidence_ids],
                )
            )
        self._check_cancelled(cancel_event, ticket_id, run_id)

    def _validate_ready_to_finish(self, state: SupervisorState) -> None:
        reviewer_flagged = (
            state.review is not None and state.review.review_status == "flagged"
        )
        missing = []
        if state.classification is None:
            missing.append("classification")
        if state.context is None:
            missing.append("context")
        if state.diagnosis is None:
            missing.append("diagnosis")
        if state.routing is None:
            missing.append("routing")
        if state.review is None:
            missing.append("review")
        # Allow skipping report if reviewer flagged
        if state.report is None and not reviewer_flagged:
            missing.append("report")
        if missing:
            raise AppError(
                "ORCHESTRATOR_PREREQUISITE_MISSING",
                "Supervisor finish 缺少必要输出",
                status.HTTP_502_BAD_GATEWAY,
                {"missing_outputs": missing},
            )

    def _validate_evidence_refs(
        self,
        state: SupervisorState,
        trace: list[WorkflowStepTrace],
    ) -> None:
        self._validate_ready_to_finish(state)
        known_ids = {item.evidence_id for item in state.evidence}
        referenced = set(state.classification.evidence_ids)
        for step in trace:
            referenced.update(step.evidence_ids)
        for run in state.agent_runs:
            referenced.update(run.evidence_ids)
            if run.route_decision:
                referenced.update(run.route_decision.evidence_ids)
        for cause in state.diagnosis.candidate_root_causes:
            referenced.update(cause.evidence_ids)
        for action in state.routing.recommended_actions:
            referenced.update(action.evidence_ids)
        missing = sorted(referenced - known_ids)
        if missing:
            raise AppError(
                "INSUFFICIENT_EVIDENCE",
                "工单处理结果引用了不存在的证据",
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                {"missing_evidence_ids": missing},
            )

    def _completed_agents(self, state: SupervisorState) -> set[str]:
        completed_statuses = {"completed", "partial", "abstained"}
        return {run.agent_name for run in state.agent_runs if run.status in completed_statuses}

    def _route_system_prompt(self) -> str:
        return (
            "你是 IntelliTicket Supervisor，只能选择下一步 Agent。"
            "必须返回 JSON 对象，字段只能包含 next_agent、message_type、reason_summary、"
            "required_inputs、evidence_ids、requires_human_review。"
            "不能输出 chain-of-thought/private reasoning，不能调用工具或 MCP，"
            "不能生成 classification/context/diagnosis/routing/report/evidence。"
            "next_agent 必须来自 allowlist，不能跳过前置 Agent，不能引用未知 evidence。"
        )

    def _route_user_payload(self, state: SupervisorState) -> dict[str, Any]:
        return {
            "ticket_id": state.ticket_id,
            "run_id": state.run_id,
            "step": state.current_step,
            "max_steps": state.max_steps,
            "allowed_next_agents": sorted(ALLOWED_NEXT_AGENTS),
            "completed_agents": sorted(self._completed_agents(state)),
            "available_outputs": {
                "classification": state.classification is not None,
                "service_record": state.service_record is not None,
                "context": state.context is not None,
                "diagnosis": state.diagnosis is not None,
                "routing": state.routing is not None,
                "report": state.report is not None,
            },
            "known_evidence_ids": [item.evidence_id for item in state.evidence],
            "last_agent_status": state.agent_runs[-1].status if state.agent_runs else None,
            "ticket_summary": {
                "data_mode": state.request.data_mode.value,
                "text": state.request.text,
            },
        }

    def _check_cancelled(
        self,
        cancel_event: Event | None,
        ticket_id: str,
        run_id: str,
    ) -> None:
        if cancel_event and cancel_event.is_set():
            raise AppError(
                "PROCESSING_CANCELLED",
                "工单处理已被客户端取消",
                499,
                {"ticket_id": ticket_id, "run_id": run_id},
            )

    def _raise_internal_prerequisite_error(self, next_agent: str) -> None:
        raise AppError(
            "ORCHESTRATOR_PREREQUISITE_MISSING",
            "Supervisor 内部状态缺少必要输入",
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            {"next_agent": next_agent},
        )

    def _safe_validation_errors(self, exc: ValidationError) -> list[dict[str, Any]]:
        errors: list[dict[str, Any]] = []
        for error in exc.errors():
            item = dict(error)
            if "ctx" in item:
                item["ctx"] = {key: str(value) for key, value in item["ctx"].items()}
            errors.append(item)
        return errors

    def _now(self) -> str:
        return datetime.now(UTC).isoformat()
