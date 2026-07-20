from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from threading import Event
from typing import Any

from intelliticket_backend.errors import AppError
from intelliticket_backend.repositories.mock_ops_data import MockOpsDataRepository
from intelliticket_backend.schemas.orchestration import (
    RouteDecision,
    SupervisorAgentRun,
    SupervisorRunResult,
)
from intelliticket_backend.schemas.tickets import (
    DataMode,
    DiagnosisResult,
    Evidence,
    EvidenceRef,
    RetrievedContext,
    ServiceContext,
    TicketCategory,
    TicketClassification,
    TicketPriority,
    TicketProcessRequest,
    TicketProcessResponse,
    TicketProcessWsAgentProgressEvent,
    WorkflowStepTrace,
)
from intelliticket_backend.services.agents.envelope import (
    AgentTaskError,
    InternalTaskRequest,
    InternalTaskResult,
)
from intelliticket_backend.services.agents.support_kb import SupportKbRetrievalAgent
from intelliticket_backend.services.agents.support_reply import SUPPORT_TEAM, SupportReplyAgent
from intelliticket_backend.services.knowledge import KnowledgeService
from intelliticket_backend.services.llm import LlmClient

SUPPORT_STEPS = [
    (
        "support_intake_service",
        "support_intake",
        "support intake 完成支持类请求识别",
    ),
    (
        "support_kb_retrieval_agent",
        "support_kb_retrieval",
        "support kb retrieval 完成知识库检索",
    ),
    (
        "support_routing_service",
        "support_routing",
        "support routing 完成内部支持分派",
    ),
    (
        "support_reply_agent",
        "support_reply_suggestion",
        "support reply suggestion 生成回复建议",
    ),
]


class SupportWorkflowService:
    """内部支持服务台 deterministic 工单处理 workflow。"""

    def __init__(
        self,
        repository: MockOpsDataRepository | None = None,
        kb_agent: SupportKbRetrievalAgent | None = None,
        reply_agent: SupportReplyAgent | None = None,
        knowledge_service: KnowledgeService | None = None,
        llm_client: LlmClient | None = None,
        reply_strategy: str = "deterministic",
    ) -> None:
        self.repository = repository or MockOpsDataRepository()
        self.knowledge_service = knowledge_service or KnowledgeService(repository=self.repository)
        self.kb_agent = kb_agent or SupportKbRetrievalAgent(
            repository=self.repository,
            knowledge_service=self.knowledge_service,
        )
        self.reply_agent = reply_agent or SupportReplyAgent(
            llm_client=llm_client,
            strategy=reply_strategy,
        )

    def run_with_audit(
        self,
        request: TicketProcessRequest,
        *,
        ticket_id: str,
        run_id: str,
        progress_sink: Callable[[TicketProcessWsAgentProgressEvent], None] | None = None,
        cancel_event: Event | None = None,
    ) -> SupervisorRunResult:
        started_at = self._now()
        self._check_cancelled(cancel_event, ticket_id, run_id)

        agent_runs: list[SupervisorAgentRun] = []
        route_decisions: list[RouteDecision] = []
        trace: list[WorkflowStepTrace] = []

        self._append_step(
            agent_runs=agent_runs,
            route_decisions=route_decisions,
            trace=trace,
            progress_sink=progress_sink,
            cancel_event=cancel_event,
            ticket_id=ticket_id,
            run_id=run_id,
            sequence=1,
            agent_name="support_intake_service",
            step="support_intake",
            summary="support intake 完成支持类请求识别",
            evidence_ids=[],
        )

        kb_result = self.kb_agent.handle_task(
            self._task_request(
                task_id=f"TASK-{run_id}-02",
                ticket_id=ticket_id,
                run_id=run_id,
                from_agent="support_intake_service",
                to_agent="support_kb_retrieval_agent",
                message_type="support_kb_retrieval_request",
                payload={
                    "text": request.text,
                    "desk_id": request.desk_id.value,
                    "data_mode": request.data_mode.value,
                },
                evidence_ids=[],
            )
        )
        self._ensure_agent_completed(kb_result)
        matched_articles = list(kb_result.payload["matched_articles"])
        evidence = [Evidence.model_validate(item) for item in kb_result.payload["evidence"]]
        evidence_ids = list(kb_result.evidence_ids)
        self._append_agent_result_step(
            agent_runs=agent_runs,
            route_decisions=route_decisions,
            trace=trace,
            progress_sink=progress_sink,
            cancel_event=cancel_event,
            ticket_id=ticket_id,
            run_id=run_id,
            sequence=2,
            result=kb_result,
            step="support_kb_retrieval",
            summary="support kb retrieval 完成知识库检索",
        )

        self._append_step(
            agent_runs=agent_runs,
            route_decisions=route_decisions,
            trace=trace,
            progress_sink=progress_sink,
            cancel_event=cancel_event,
            ticket_id=ticket_id,
            run_id=run_id,
            sequence=3,
            agent_name="support_routing_service",
            step="support_routing",
            summary="support routing 完成内部支持分派",
            evidence_ids=evidence_ids,
        )

        reply_result = self.reply_agent.handle_task(
            self._task_request(
                task_id=f"TASK-{run_id}-04",
                ticket_id=ticket_id,
                run_id=run_id,
                from_agent="support_routing_service",
                to_agent="support_reply_agent",
                message_type="support_reply_request",
                payload={
                    "text": request.text,
                    "matched_articles": matched_articles,
                    "evidence_ids": evidence_ids,
                    "data_mode": request.data_mode.value,
                },
                evidence_ids=evidence_ids,
            )
        )
        self._ensure_agent_completed(reply_result)
        self._append_agent_result_step(
            agent_runs=agent_runs,
            route_decisions=route_decisions,
            trace=trace,
            progress_sink=progress_sink,
            cancel_event=cancel_event,
            ticket_id=ticket_id,
            run_id=run_id,
            sequence=4,
            result=reply_result,
            step="support_reply_suggestion",
            summary="support reply suggestion 生成回复建议",
        )

        primary_article = matched_articles[0] if matched_articles else None
        service_name = primary_article["service"] if primary_article else "internal-support"
        title = primary_article["title"] if primary_article else "内部支持请求处理建议"
        classification = TicketClassification(
            category=TicketCategory.SUPPORT_REQUEST,
            summary=self._summary(request.text),
            affected_service=service_name,
            symptoms=self._support_symptoms(request.text),
            priority=TicketPriority.P3,
            priority_reason="内部支持请求默认按 P3 处理；如影响范围扩大需人工升级。",
            extracted_metrics={},
            evidence_ids=evidence_ids,
        )
        context = RetrievedContext(
            service=ServiceContext(
                service_id=service_name,
                name=service_name,
                display_name=title,
                aliases=[],
                owner_team=SUPPORT_TEAM,
                criticality="medium",
                dependencies=[],
                data_mode=request.data_mode,
            ),
            unknowns=[] if evidence else ["未匹配到内部支持知识库文章，需人工补充上下文。"],
        )
        diagnosis = DiagnosisResult(
            candidate_root_causes=[],
            unknowns=context.unknowns,
            abstentions=["support desk 使用知识库回复建议流程，不生成运维根因诊断。"],
        )
        response = TicketProcessResponse(
            ticket_id=ticket_id,
            run_id=run_id,
            data_mode=request.data_mode,
            classification=classification,
            context=context,
            diagnosis=diagnosis,
            routing=reply_result.payload["routing"],
            report=reply_result.payload["report"],
            agent_trace=trace,
            evidence=evidence,
            support_result=reply_result.payload["support_result"],
        )
        route_decisions.append(
            RouteDecision(
                next_agent="finish",
                message_type="finish",
                reason_summary="support deterministic route 已完成回复建议流程，进入 finish。",
                required_inputs=[agent_name for agent_name, _, _ in SUPPORT_STEPS],
                evidence_ids=evidence_ids,
                requires_human_review=False,
            )
        )
        completed_at = self._now()
        return SupervisorRunResult(
            response=response,
            agent_runs=agent_runs,
            route_decisions=route_decisions,
            started_at=started_at,
            completed_at=completed_at,
        )

    def _task_request(
        self,
        *,
        task_id: str,
        ticket_id: str,
        run_id: str,
        from_agent: str,
        to_agent: str,
        message_type: str,
        payload: dict[str, Any],
        evidence_ids: list[str],
    ) -> InternalTaskRequest:
        return InternalTaskRequest(
            task_id=task_id,
            ticket_id=ticket_id,
            run_id=run_id,
            from_agent=from_agent,
            to_agent=to_agent,
            message_type=message_type,
            payload=payload,
            evidence_ids=evidence_ids,
            idempotency_key=f"{run_id}:{task_id}",
        )

    def _append_agent_result_step(
        self,
        *,
        agent_runs: list[SupervisorAgentRun],
        route_decisions: list[RouteDecision],
        trace: list[WorkflowStepTrace],
        progress_sink: Callable[[TicketProcessWsAgentProgressEvent], None] | None,
        cancel_event: Event | None,
        ticket_id: str,
        run_id: str,
        sequence: int,
        result: InternalTaskResult,
        step: str,
        summary: str,
    ) -> None:
        self._append_step(
            agent_runs=agent_runs,
            route_decisions=route_decisions,
            trace=trace,
            progress_sink=progress_sink,
            cancel_event=cancel_event,
            ticket_id=ticket_id,
            run_id=run_id,
            sequence=sequence,
            agent_name=result.agent_name,
            step=step,
            summary=summary,
            evidence_ids=result.evidence_ids,
            observations=result.observations or [summary],
            error=result.error,
            status=result.status,
        )

    def _append_step(
        self,
        *,
        agent_runs: list[SupervisorAgentRun],
        route_decisions: list[RouteDecision],
        trace: list[WorkflowStepTrace],
        progress_sink: Callable[[TicketProcessWsAgentProgressEvent], None] | None,
        cancel_event: Event | None,
        ticket_id: str,
        run_id: str,
        sequence: int,
        agent_name: str,
        step: str,
        summary: str,
        evidence_ids: list[str],
        observations: list[str] | None = None,
        error: AgentTaskError | None = None,
        status: str = "completed",
    ) -> None:
        self._check_cancelled(cancel_event, ticket_id, run_id)
        now = self._now()
        route = RouteDecision(
            next_agent=agent_name,
            message_type=f"{agent_name}_request",
            reason_summary=f"support deterministic route 选择 {agent_name}。",
            required_inputs=[],
            evidence_ids=evidence_ids,
            requires_human_review=False,
        )
        route_decisions.append(route)
        agent_runs.append(
            SupervisorAgentRun(
                task_id=f"TASK-{run_id}-{sequence:02d}",
                ticket_id=ticket_id,
                run_id=run_id,
                agent_name=agent_name,
                status=status,
                route_decision=route,
                evidence_ids=evidence_ids,
                observations=observations or [summary],
                error=error,
                started_at=now,
                completed_at=now,
            )
        )
        step_trace = WorkflowStepTrace(
            step=step,
            status=status,
            started_at=now,
            completed_at=now,
            summary=summary,
            evidence_ids=evidence_ids,
        )
        trace.append(step_trace)
        self._emit_progress(
            progress_sink,
            cancel_event,
            ticket_id,
            run_id,
            sequence,
            step_trace,
            agent_name,
        )

    def _ensure_agent_completed(self, result: InternalTaskResult) -> None:
        if result.status == "completed":
            return
        code = result.error.code if result.error else "SUPPORT_AGENT_FAILED"
        message = result.error.message if result.error else "support agent 执行失败"
        details = result.error.details if result.error else {"agent_name": result.agent_name}
        raise AppError(code, message, 400, details)

    def _support_symptoms(self, text: str) -> list[str]:
        symptoms = []
        for keyword, symptom in [
            ("网络", "network_access_issue"),
            ("vpn", "vpn_access_issue"),
            ("账号", "account_issue"),
            ("权限", "permission_issue"),
            ("访问", "access_issue"),
        ]:
            if keyword in text.lower():
                symptoms.append(symptom)
        return symptoms or ["internal_support_request"]

    def _summary(self, text: str) -> str:
        compact = " ".join(text.split())
        return compact if len(compact) <= 120 else f"{compact[:117]}..."

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

    def _now(self) -> str:
        return datetime.now(UTC).isoformat()
