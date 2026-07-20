from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
from threading import Event
from uuid import uuid4

from fastapi import status

from intelliticket_backend.config import Settings, get_settings
from intelliticket_backend.errors import AppError
from intelliticket_backend.repositories.mock_ops_data import MockOpsDataRepository
from intelliticket_backend.repositories.ticket_history import TicketHistoryRepository
from intelliticket_backend.schemas.tickets import (
    DataMode,
    DeskId,
    TicketProcessRequest,
    TicketProcessResponse,
    TicketProcessWsAgentProgressEvent,
)
from intelliticket_backend.services.agents.context import ContextRetrievalAgent
from intelliticket_backend.services.agents.diagnosis import DiagnosisAgent
from intelliticket_backend.services.agents.intake import IntakeAgent
from intelliticket_backend.services.agents.report import ReportAgent
from intelliticket_backend.services.agents.reviewer import ReviewerAgent
from intelliticket_backend.services.agents.routing import RoutingAgent
from intelliticket_backend.services.case_retrieval import CaseRecord, CaseRetrieval, _tokenize
from intelliticket_backend.services.knowledge import KnowledgeService
from intelliticket_backend.services.llm import DeepSeekChatClient, LlmClient
from intelliticket_backend.services.notifications import (
    DingTalkNotifier,
    NotificationService,
)
from intelliticket_backend.services.orchestrator import (
    OrchestrationRunError,
    SupervisorOrchestrator,
)
from intelliticket_backend.services.support_workflow import SupportWorkflowService


class TicketProcessingService:
    """工单处理服务，内部委托受控 Supervisor 编排。"""

    def __init__(
        self,
        repository: MockOpsDataRepository | None = None,
        intake_agent: IntakeAgent | None = None,
        context_agent: ContextRetrievalAgent | None = None,
        diagnosis_agent: DiagnosisAgent | None = None,
        routing_agent: RoutingAgent | None = None,
        reviewer_agent: ReviewerAgent | None = None,
        report_agent: ReportAgent | None = None,
        settings: Settings | None = None,
        llm_client: LlmClient | None = None,
        orchestrator: SupervisorOrchestrator | None = None,
        support_workflow: SupportWorkflowService | None = None,
        history_repository: TicketHistoryRepository | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.repository = repository or MockOpsDataRepository()
        self.knowledge_service = KnowledgeService(
            settings=self.settings,
            repository=self.repository,
        )
        self.llm_client = llm_client or self._build_llm_client()
        self.intake_agent = intake_agent or IntakeAgent(
            repository=self.repository,
            llm_client=self.llm_client,
            strategy=self.settings.intake_agent_strategy,
        )
        self.context_agent = context_agent or ContextRetrievalAgent(
            repository=self.repository,
            knowledge_service=self.knowledge_service,
        )
        self.diagnosis_agent = diagnosis_agent or DiagnosisAgent(
            llm_client=self.llm_client,
            strategy=self.settings.diagnosis_agent_strategy,
        )
        self.routing_agent = routing_agent or RoutingAgent()
        self.reviewer_agent = reviewer_agent or ReviewerAgent(
            llm_client=self.llm_client,
        )
        self.report_agent = report_agent or ReportAgent()
        self.support_workflow = support_workflow or SupportWorkflowService(
            repository=self.repository,
            knowledge_service=self.knowledge_service,
            llm_client=self.llm_client,
            reply_strategy=self.settings.support_reply_agent_strategy,
        )
        self.history_repository = history_repository or TicketHistoryRepository(
            self.settings.ticket_history_db_path
        )
        self.case_retrieval = self._build_case_retrieval()
        self.notification_service = self._build_notification_service()
        self.orchestrator = orchestrator or SupervisorOrchestrator(
            llm_client=self.llm_client,
            intake_agent=self.intake_agent,
            context_agent=self.context_agent,
            diagnosis_agent=self.diagnosis_agent,
            routing_agent=self.routing_agent,
            reviewer_agent=self.reviewer_agent,
            report_agent=self.report_agent,
            max_steps=self.settings.orchestrator_max_steps,
            route_mode=self.settings.orchestrator_route_mode,
            llm_temperature=self.settings.llm_temperature,
            case_retrieval=self.case_retrieval,
        )

    def process_ticket_preview(
        self,
        request: TicketProcessRequest,
        progress_sink: Callable[[TicketProcessWsAgentProgressEvent], None] | None = None,
        cancel_event: Event | None = None,
        ticket_id: str | None = None,
        run_id: str | None = None,
    ) -> TicketProcessResponse:
        """处理工单但不持久化，用于人工确认前的重处理预览。"""
        if request.data_mode not in {DataMode.MOCK, DataMode.REAL}:
            raise AppError(
                "UNSUPPORTED_DATA_MODE",
                "当前仅支持 mock 或 real 数据模式",
                status.HTTP_400_BAD_REQUEST,
                {
                    "requested_data_mode": request.data_mode.value,
                    "supported": [DataMode.MOCK.value, DataMode.REAL.value],
                },
            )
        if (
            request.desk_id == DeskId.SUPPORT
            and self.settings.support_workflow_strategy != "deterministic"
        ):
            raise AppError(
                "UNSUPPORTED_SUPPORT_WORKFLOW_STRATEGY",
                "support workflow 当前仅支持 deterministic 策略，不能静默降级或初始化未实现策略",
                status.HTTP_400_BAD_REQUEST,
                {
                    "requested_strategy": self.settings.support_workflow_strategy,
                    "supported": ["deterministic"],
                },
            )

        ticket_id = ticket_id or self._make_id("TCK")
        run_id = run_id or self._make_id("RUN")
        self._prepare_case_retrieval(request.data_mode)
        if request.desk_id == DeskId.SUPPORT:
            run_result = self.support_workflow.run_with_audit(
                request,
                progress_sink=progress_sink,
                cancel_event=cancel_event,
                ticket_id=ticket_id,
                run_id=run_id,
            )
        else:
            run_result = self.orchestrator.run_with_audit(
                request,
                progress_sink=progress_sink,
                cancel_event=cancel_event,
                ticket_id=ticket_id,
                run_id=run_id,
            )
        return run_result.response

    def process_ticket(
        self,
        request: TicketProcessRequest,
        progress_sink: Callable[[TicketProcessWsAgentProgressEvent], None] | None = None,
        cancel_event: Event | None = None,
        ticket_id: str | None = None,
        run_id: str | None = None,
    ) -> TicketProcessResponse:
        if request.data_mode not in {DataMode.MOCK, DataMode.REAL}:
            raise AppError(
                "UNSUPPORTED_DATA_MODE",
                "当前仅支持 mock 或 real 数据模式",
                status.HTTP_400_BAD_REQUEST,
                {
                    "requested_data_mode": request.data_mode.value,
                    "supported": [DataMode.MOCK.value, DataMode.REAL.value],
                },
            )
        if (
            request.desk_id == DeskId.SUPPORT
            and self.settings.support_workflow_strategy != "deterministic"
        ):
            raise AppError(
                "UNSUPPORTED_SUPPORT_WORKFLOW_STRATEGY",
                "support workflow 当前仅支持 deterministic 策略，不能静默降级或初始化未实现策略",
                status.HTTP_400_BAD_REQUEST,
                {
                    "requested_strategy": self.settings.support_workflow_strategy,
                    "supported": ["deterministic"],
                },
            )

        ticket_id = ticket_id or self._make_id("TCK")
        run_id = run_id or self._make_id("RUN")
        self._prepare_case_retrieval(request.data_mode)
        try:
            if request.desk_id == DeskId.SUPPORT:
                run_result = self.support_workflow.run_with_audit(
                    request,
                    progress_sink=progress_sink,
                    cancel_event=cancel_event,
                    ticket_id=ticket_id,
                    run_id=run_id,
                )
            else:
                run_result = self.orchestrator.run_with_audit(
                    request,
                    progress_sink=progress_sink,
                    cancel_event=cancel_event,
                    ticket_id=ticket_id,
                    run_id=run_id,
                )
        except OrchestrationRunError as exc:
            try:
                self.history_repository.save_failed_run(
                    request=request,
                    run_failure=exc.run_failure,
                    route_mode=self.settings.orchestrator_route_mode,
                )
            except Exception as save_exc:
                raise AppError(
                    "TICKET_HISTORY_SAVE_FAILED",
                    "工单处理终态保存失败，未返回假成功",
                    status.HTTP_500_INTERNAL_SERVER_ERROR,
                    {
                        "error": str(save_exc),
                        "original_error_code": exc.code,
                        "original_error_message": exc.message,
                    },
                ) from save_exc
            raise
        try:
            self.history_repository.save_completed_run(
                request=request,
                run_result=run_result,
                route_mode=self.settings.orchestrator_route_mode,
            )
        except Exception as exc:
            raise AppError(
                "TICKET_HISTORY_SAVE_FAILED",
                "工单处理结果保存失败，未返回假成功",
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                {"error": str(exc)},
            ) from exc
        return run_result.response

    def _prepare_case_retrieval(self, data_mode: DataMode) -> None:
        self.case_retrieval = self._build_case_retrieval(data_mode)
        self.orchestrator.case_retrieval = self.case_retrieval

    def _build_case_retrieval(self, data_mode: DataMode | None = None) -> CaseRetrieval:
        retrieval = CaseRetrieval()
        cases = self.history_repository.load_all_cases(
            data_mode.value if data_mode is not None else None
        )
        for case_data in cases:
            import json as _json
            symptoms = (
                _json.loads(case_data["symptoms_json"])
                if isinstance(case_data.get("symptoms_json"), str)
                else (case_data.get("symptoms_json") or [])
            )
            record = CaseRecord(
                ticket_id=case_data["ticket_id"],
                text=case_data["input_text"],
                symptoms=symptoms,
                data_mode=case_data.get("data_mode", "mock"),
                root_cause=case_data.get("root_cause", ""),
                confirmed_root_cause=case_data.get("confirmed_root_cause", ""),
                resolution=case_data.get("resolution", ""),
            )
            record.token_counts = Counter(
                _tokenize(case_data["input_text"])
                + [t for s in symptoms for t in _tokenize(s)]
            )
            retrieval.index(record)
        retrieval.rebuild()
        return retrieval

    def _build_notification_service(self) -> NotificationService:
        notifiers = []
        if self.settings.dingtalk_enabled:
            if (
                self.settings.dingtalk_operator_webhook_url is not None
            ):
                notifiers.append(
                    DingTalkNotifier(
                        webhook_url=self.settings.dingtalk_operator_webhook_url
                    )
                )
            if (
                self.settings.dingtalk_employee_webhook_url is not None
            ):
                notifiers.append(
                    DingTalkNotifier(
                        webhook_url=self.settings.dingtalk_employee_webhook_url
                    )
                )
        return NotificationService(notifiers=notifiers)

    def _notify(self, response: TicketProcessResponse) -> None:
        try:
            p = response.classification.priority.value

            if p == "P4":
                response.notification = {"channels": []}
                return

            # Use the LLM's actual diagnosis text
            if response.diagnosis.candidate_root_causes:
                top = response.diagnosis.candidate_root_causes[0]
                diag_text = top.reasoning_summary or top.cause
            elif response.diagnosis.abstentions:
                diag_text = response.diagnosis.abstentions[0]
            else:
                diag_text = "请查看 IntelliTicket 详情"

            svc = response.classification.affected_service or ""
            title = (
                f"🔴 [P1] {response.ticket_id} {svc}"
                if p == "P1"
                else f"[{p}] {response.ticket_id} {svc}"
            )

            payload = self.notification_service.build_payload(
                ticket_id=response.ticket_id,
                title=title,
                summary=diag_text,
                priority=p,
                affected_service=response.classification.affected_service,
                recommended_actions=response.report.recommendations if response.report else [],
                ticket_url=None,
                is_at_all=(p == "P1"),
            )
            results = self.notification_service.send(payload)
            response.notification = {
                "channels": [
                    {"channel": r.channel, "status": r.status, "message": r.message}
                    for r in results
                ]
            }
        except Exception:
            pass

    def _build_llm_client(self) -> LlmClient | None:
        api_key = self.settings.resolved_deepseek_api_key
        if api_key is None or not api_key.get_secret_value().strip():
            return None
        if self.settings.llm_provider != "deepseek":
            raise AppError(
                "UNSUPPORTED_LLM_PROVIDER",
                "不支持的 LLM provider",
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                {"llm_provider": self.settings.llm_provider},
            )
        return DeepSeekChatClient(
            api_key=self.settings.resolved_deepseek_api_key,
            base_url=self.settings.deepseek_base_url,
            model=self.settings.llm_model,
            timeout_seconds=self.settings.llm_timeout_seconds,
            max_retries=self.settings.llm_max_retries,
            retry_backoff_seconds=self.settings.llm_retry_backoff_seconds,
            temperature=self.settings.llm_temperature,
        )

    def _make_id(self, prefix: str) -> str:
        date_part = datetime.now(UTC).strftime("%Y%m%d")
        return f"{prefix}-{date_part}-{uuid4().hex[:8].upper()}"
