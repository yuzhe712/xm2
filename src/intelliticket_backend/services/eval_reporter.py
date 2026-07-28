from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from typing import Any

from intelliticket_backend.config import Settings
from intelliticket_backend.errors import AppError
from intelliticket_backend.repositories.mock_ops_data import MockOpsDataRepository
from intelliticket_backend.schemas.evals import EvalCaseResult, EvalReport
from intelliticket_backend.schemas.tickets import (
    DataMode,
    HistoricalIncident,
    TicketCategory,
    TicketClassification,
    TicketPriority,
    TicketProcessRequest,
)
from intelliticket_backend.services.agents.context import ContextRetrievalAgent
from intelliticket_backend.services.agents.diagnosis import DiagnosisAgent
from intelliticket_backend.services.agents.envelope import AgentTaskError
from intelliticket_backend.services.agents.intake import IntakeAgent
from intelliticket_backend.services.agents.routing import RoutingAgent
from intelliticket_backend.services.llm import LlmClient
from intelliticket_backend.services.orchestrator import SupervisorOrchestrator
from intelliticket_backend.services.ticket_processing import TicketProcessingService

SAMPLE_TEXT = "线上支付服务出现超时告警，订单量从正常1000/min降到300/min"


@dataclass(frozen=True)
class EvalContext:
    """Eval case 运行上下文。"""

    history_db_path: Path

    def settings(self) -> Settings:
        return Settings(
            ticket_history_db_path=self.history_db_path,
            intake_agent_strategy="deterministic",
            diagnosis_agent_strategy="deterministic",
            support_reply_agent_strategy="deterministic",
            knowledge_provider="mock",
        )

    def repository(self) -> MockOpsDataRepository:
        return MockOpsDataRepository()


@dataclass(frozen=True)
class EvalCase:
    """内置 eval case 定义。"""

    case_id: str
    name: str
    run: Callable[[EvalContext], list[str]]


class InvalidRouteClient(LlmClient):
    def structured_json_call(self, **_kwargs: Any) -> dict[str, str]:
        return {"next_agent": "missing_agent", "message_type": "bad", "reason_summary": "bad"}


class MissingSopRepository(MockOpsDataRepository):
    def get_sops(self, service_name: str) -> list[dict[str, Any]]:
        return []


def available_eval_cases() -> list[EvalCase]:
    return [
        EvalCase(
            "unknown-service-abstains",
            "未知服务不生成虚假上下文或根因",
            _case_unknown_service_abstains,
        ),
        EvalCase(
            "service-alias-recognized",
            "服务别名可识别为 payment-service",
            _case_service_alias_recognized,
        ),
        EvalCase(
            "missing-required-metric-abstains-db-pool-cause",
            "缺失必要指标时不生成连接池耗尽根因",
            _case_missing_required_metric,
        ),
        EvalCase(
            "stale-metric-abstains-db-pool-cause",
            "过期指标不会支撑连接池耗尽根因",
            _case_stale_metric,
        ),
        EvalCase(
            "conflicting-incident-abstains-db-pool-cause",
            "冲突历史事件不会支撑连接池耗尽根因",
            _case_conflicting_incident,
        ),
        EvalCase(
            "missing-sop-keeps-routing-explainable",
            "缺失 SOP 时 routing 仍保持可解释",
            _case_missing_sop,
        ),
        EvalCase(
            "real-mode-excludes-mock-evidence",
            "real data mode 不混入 mock 证据",
            _case_real_mode_excludes_mock_evidence,
        ),
        EvalCase(
            "priority-boundary-p1-p2",
            "优先级边界 P1/P2 明确",
            _case_priority_boundary,
        ),
        EvalCase(
            "routing-abstains-without-service-context",
            "缺少服务上下文时 routing abstain",
            _case_routing_abstains_without_service_context,
        ),
        EvalCase(
            "invalid-llm-route-fails-closed",
            "非法 LLM route fail-closed",
            _case_invalid_llm_route,
        ),
    ]


def run_eval_report(
    *,
    case_ids: list[str] | None = None,
    history_db_path: Path | None = None,
) -> EvalReport:
    if history_db_path is not None:
        return _run_eval_report_with_db(case_ids=case_ids, history_db_path=history_db_path)
    with TemporaryDirectory(prefix="intelliticket-eval-", ignore_cleanup_errors=True) as temp_dir:
        return _run_eval_report_with_db(
            case_ids=case_ids,
            history_db_path=Path(temp_dir) / "eval.sqlite3",
        )


def _run_eval_report_with_db(
    *,
    case_ids: list[str] | None,
    history_db_path: Path,
) -> EvalReport:
    started = perf_counter()
    cases = _select_cases(case_ids)
    context = EvalContext(history_db_path=history_db_path)
    results = [_run_case(case, context) for case in cases]
    passed = sum(1 for result in results if result.status == "passed")
    failed = len(results) - passed
    return EvalReport(
        generated_at=datetime.now(UTC).isoformat(),
        data_mode=DataMode.MOCK,
        total=len(results),
        passed=passed,
        failed=failed,
        duration_ms=_elapsed_ms(started),
        cases=results,
    )


def _select_cases(case_ids: list[str] | None) -> list[EvalCase]:
    cases = available_eval_cases()
    if not case_ids:
        return cases
    by_id = {case.case_id: case for case in cases}
    missing = [case_id for case_id in case_ids if case_id not in by_id]
    if missing:
        raise ValueError(f"Unknown eval case: {', '.join(missing)}")
    return [by_id[case_id] for case_id in case_ids]


def _run_case(case: EvalCase, context: EvalContext) -> EvalCaseResult:
    started = perf_counter()
    try:
        observations = case.run(context)
        return EvalCaseResult(
            case_id=case.case_id,
            name=case.name,
            status="passed",
            data_mode=DataMode.MOCK,
            duration_ms=_elapsed_ms(started),
            observations=observations,
        )
    except AssertionError as exc:
        return _failed_case_result(case, started, "EVAL_ASSERTION_FAILED", str(exc))
    except Exception as exc:
        return _failed_case_result(case, started, "EVAL_CASE_ERROR", str(exc))


def _failed_case_result(
    case: EvalCase,
    started: float,
    code: str,
    message: str,
) -> EvalCaseResult:
    return EvalCaseResult(
        case_id=case.case_id,
        name=case.name,
        status="failed",
        data_mode=DataMode.MOCK,
        duration_ms=_elapsed_ms(started),
        observations=[],
        error=AgentTaskError(code=code, message=message or code, details={}),
    )


def _elapsed_ms(started: float) -> int:
    return max(0, round((perf_counter() - started) * 1000))


def _payment_service_record() -> dict[str, Any]:
    record = MockOpsDataRepository().resolve_service(SAMPLE_TEXT)
    _ensure(record is not None, "payment-service should resolve from sample text")
    return record


def _classification() -> TicketClassification:
    return TicketClassification(
        category=TicketCategory.OPS_ALERT,
        summary="payment-service 运维告警",
        affected_service="payment-service",
        symptoms=["timeout", "order_volume_drop"],
        priority=TicketPriority.P1,
        priority_reason="核心支付服务超时且订单量下降超过 50%。",
        extracted_metrics={"order_qps_before": 1000, "order_qps_after": 300},
        evidence_ids=["ev_ticket_input_001", "ev_service_payment_001"],
    )


def _payment_context():  # type: ignore[no-untyped-def]
    return ContextRetrievalAgent().run(_payment_service_record(), DataMode.MOCK).context


def _ensure(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _case_unknown_service_abstains(context: EvalContext) -> list[str]:
    service = TicketProcessingService(settings=context.settings())
    result = service.process_ticket(
        request=TicketProcessRequest(text="未知系统出现异常告警", data_mode=DataMode.MOCK),
    )
    _ensure(result.classification.affected_service is None, "affected_service should be None")
    _ensure(result.context.service is None, "context.service should be None")
    _ensure(result.diagnosis.candidate_root_causes == [], "root causes should be empty")
    _ensure(result.routing.recommended_team is None, "recommended_team should be None")
    return [
        "affected_service is None",
        "context.service is None",
        "candidate_root_causes is empty",
        "recommended_team is None",
    ]


def _case_service_alias_recognized(_context: EvalContext) -> list[str]:
    run = IntakeAgent().run(
        ticket_id="TCK-20260715-EVAL0002",
        text="payment 出现 timeout 告警",
        data_mode=DataMode.MOCK,
        observed_at="2026-07-15T00:00:00+00:00",
    )
    _ensure(run.classification is not None, "classification should exist")
    _ensure(
        run.classification.affected_service == "payment-service",
        "payment alias should resolve to payment-service",
    )
    return ["payment alias resolved to payment-service"]


def _case_missing_required_metric(_context: EvalContext) -> list[str]:
    context = _payment_context()
    context.metrics = [
        metric for metric in context.metrics if metric.metric_name != "db_connection_pool_usage"
    ]
    run = DiagnosisAgent().run(_classification(), context, DataMode.MOCK)
    _ensure(
        all("连接池耗尽" not in cause.cause for cause in run.diagnosis.candidate_root_causes),
        "db pool root cause should not be generated without required metric",
    )
    _ensure(bool(run.diagnosis.abstentions), "diagnosis should record abstentions")
    return ["db_connection_pool_usage removed", "db pool root cause was not generated"]


def _case_stale_metric(_context: EvalContext) -> list[str]:
    context = _payment_context()
    context.metrics = [
        metric.model_copy(update={"quality": "stale"})
        if metric.metric_name == "db_connection_pool_usage"
        else metric
        for metric in context.metrics
    ]
    run = DiagnosisAgent().run(_classification(), context, DataMode.MOCK)
    _ensure(
        all("连接池耗尽" not in cause.cause for cause in run.diagnosis.candidate_root_causes),
        "stale db pool metric should not support root cause",
    )
    _ensure(bool(run.diagnosis.abstentions), "diagnosis should record abstentions")
    return ["db pool metric marked stale", "db pool root cause was not generated"]


def _case_conflicting_incident(_context: EvalContext) -> list[str]:
    context = _payment_context()
    context.historical_incidents = [
        HistoricalIncident(
            evidence_id="ev_incident_conflict_001",
            incident_id="INC-CONFLICT",
            root_cause="网络抖动导致短暂超时",
            summary="历史相似工单指向网络抖动，而非连接池耗尽。",
            data_mode=DataMode.MOCK,
        )
    ]
    run = DiagnosisAgent().run(_classification(), context, DataMode.MOCK)
    _ensure(
        all("连接池耗尽" not in cause.cause for cause in run.diagnosis.candidate_root_causes),
        "conflicting incident should not support db pool root cause",
    )
    return ["historical incident conflicts with db pool cause", "db pool root cause absent"]


def _case_missing_sop(_context: EvalContext) -> list[str]:
    repository = MissingSopRepository()
    service_record = repository.resolve_service(SAMPLE_TEXT)
    _ensure(service_record is not None, "payment-service should resolve")
    context_run = ContextRetrievalAgent(repository=repository).run(service_record, DataMode.MOCK)
    diagnosis_run = DiagnosisAgent().run(_classification(), context_run.context, DataMode.MOCK)
    diagnosis = diagnosis_run.diagnosis
    run = RoutingAgent().run(context_run.context, diagnosis, DataMode.MOCK)
    _ensure(run.routing.recommended_team == "支付系统运维组", "recommended team should remain")
    _ensure(run.routing.sop_refs == [], "sop refs should be empty")
    _ensure(
        any("未发现 SOP" in observation for observation in run.observations),
        "observations should explain missing SOP",
    )
    return ["recommended_team remains 支付系统运维组", "sop_refs is empty"]


def _case_real_mode_excludes_mock_evidence(context: EvalContext) -> list[str]:
    service = TicketProcessingService(settings=context.settings())
    response = service.process_ticket(
        TicketProcessRequest(text=SAMPLE_TEXT, data_mode=DataMode.REAL)
    )
    _ensure(response.data_mode == DataMode.REAL, "response should remain in real mode")
    _ensure(bool(response.evidence), "real mode should return evidence")
    _ensure(
        all(item.data_mode == DataMode.REAL for item in response.evidence),
        "real mode must not contain mock evidence",
    )
    _ensure(
        all(not (item.trace_uri or "").startswith("mock_data/") for item in response.evidence),
        "real mode evidence must not reference mock_data",
    )
    return ["real mode completed", "all evidence is marked real"]


def _case_priority_boundary(_context: EvalContext) -> list[str]:
    service_record = _payment_service_record()
    p1 = IntakeAgent().run(
        ticket_id="TCK-20260715-EVAL0003",
        text="线上支付服务出现超时告警，订单量从正常1000/min降到500/min",
        data_mode=DataMode.MOCK,
        observed_at="2026-07-15T00:00:00+00:00",
    )
    p2 = IntakeAgent().run(
        ticket_id="TCK-20260715-EVAL0004",
        text="线上支付服务出现超时告警，订单量从正常1000/min降到501/min",
        data_mode=DataMode.MOCK,
        observed_at="2026-07-15T00:00:00+00:00",
    )
    _ensure(service_record["criticality"] == "business_critical", "service should be critical")
    _ensure(p1.classification is not None, "P1 classification should exist")
    _ensure(p2.classification is not None, "P2 classification should exist")
    _ensure(p1.classification.priority == TicketPriority.P1, "500/min boundary should be P1")
    _ensure(p2.classification.priority == TicketPriority.P2, "501/min boundary should be P2")
    return ["500/min classified P1", "501/min classified P2"]


def _case_routing_abstains_without_service_context(_context: EvalContext) -> list[str]:
    context = _payment_context().model_copy(update={"service": None})
    diagnosis = DiagnosisAgent().run(_classification(), context, DataMode.MOCK).diagnosis
    run = RoutingAgent().run(context, diagnosis, DataMode.MOCK)
    _ensure(run.status == "abstained", "routing should abstain")
    _ensure(run.routing.recommended_team is None, "recommended team should be None")
    _ensure("人工确认" in run.routing.escalation, "escalation should request human confirmation")
    return [
        "routing status abstained",
        "recommended_team is None",
        "escalation requests human confirmation",
    ]


def _case_invalid_llm_route(_context: EvalContext) -> list[str]:
    orchestrator = SupervisorOrchestrator(llm_client=InvalidRouteClient(), route_mode="llm")
    try:
        orchestrator.run(
            TicketProcessRequest(text=SAMPLE_TEXT, data_mode=DataMode.MOCK),
            ticket_id="TCK-20260715-EVAL0005",
            run_id="RUN-20260715-EVAL0005",
        )
    except AppError as exc:
        _ensure(
            exc.code == "ORCHESTRATOR_INVALID_ROUTE",
            "invalid route should fail with ORCHESTRATOR_INVALID_ROUTE",
        )
        return ["invalid LLM route rejected", "error code ORCHESTRATOR_INVALID_ROUTE"]
    raise AssertionError("invalid LLM route unexpectedly succeeded")
