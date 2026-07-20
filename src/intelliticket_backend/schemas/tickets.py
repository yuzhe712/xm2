from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class DataMode(StrEnum):
    MOCK = "mock"
    DEMO = "demo"
    REAL = "real"


class DeskId(StrEnum):
    OPS = "ops"
    SUPPORT = "support"


class TicketCategory(StrEnum):
    OPS_ALERT = "ops_alert"
    SUPPORT_REQUEST = "support_request"


class TicketPriority(StrEnum):
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    P4 = "P4"


class EvidenceRef(BaseModel):
    evidence_id: str


class Evidence(BaseModel):
    evidence_id: str
    source_type: str
    source_id: str
    source_name: str
    observed_at: str | None = None
    retrieved_at: str | None = None
    service: str | None = None
    metric_name: str | None = None
    value: Any | None = None
    unit: str | None = None
    quality: str
    data_mode: DataMode
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    summary: str
    trace_uri: str | None = None
    freshness: str | None = None
    quality_reason: str | None = None
    producer: str | None = None
    run_id: str | None = None


class TicketProcessRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)
    data_mode: DataMode = DataMode.MOCK
    desk_id: DeskId = DeskId.OPS
    submitter: str | None = None
    operator_id: str | None = None

    @field_validator("text")
    @classmethod
    def strip_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("工单内容不能为空")
        return stripped


class TicketSubmitRequest(BaseModel):
    """员工提交工单（只创建，不处理）。提交人由认证 token 确定。"""

    text: str = Field(..., min_length=1, max_length=2000)
    data_mode: DataMode = DataMode.MOCK
    desk_id: DeskId = DeskId.OPS

    @field_validator("text")
    @classmethod
    def strip_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("工单内容不能为空")
        return stripped


class TicketSubmitResponse(BaseModel):
    """工单提交结果。"""

    ticket_id: str
    status: str  # "pending"
    created_at: str
    text: str
    desk_id: DeskId
    submitter: str


class TicketClassification(BaseModel):
    category: TicketCategory
    summary: str
    affected_service: str | None
    symptoms: list[str]
    priority: TicketPriority
    priority_reason: str
    extracted_metrics: dict[str, Any] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)


class ServiceContext(BaseModel):
    service_id: str
    name: str
    display_name: str
    aliases: list[str]
    owner_team: str
    criticality: str
    dependencies: list[str] = Field(default_factory=list)
    data_mode: DataMode


class MetricSnapshot(BaseModel):
    evidence_id: str
    metric_name: str
    value: Any
    unit: str
    observed_at: str
    quality: str
    summary: str
    data_mode: DataMode


class DeploymentRecord(BaseModel):
    evidence_id: str
    version: str
    deployed_at: str
    author: str
    summary: str
    data_mode: DataMode


class HistoricalIncident(BaseModel):
    evidence_id: str
    incident_id: str
    root_cause: str
    summary: str
    data_mode: DataMode


class SopDocument(BaseModel):
    evidence_id: str
    sop_id: str
    title: str
    actions: list[str]
    data_mode: DataMode


class RetrievedContext(BaseModel):
    service: ServiceContext | None = None
    metrics: list[MetricSnapshot] = Field(default_factory=list)
    deployments: list[DeploymentRecord] = Field(default_factory=list)
    historical_incidents: list[HistoricalIncident] = Field(default_factory=list)
    sop_documents: list[SopDocument] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)


class CandidateRootCause(BaseModel):
    cause: str
    evidence_ids: list[str]
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning_summary: str


class RecommendedAction(BaseModel):
    action: str
    evidence_ids: list[str] = Field(default_factory=list)


class DiagnosisResult(BaseModel):
    candidate_root_causes: list[CandidateRootCause] = Field(default_factory=list)
    recommended_actions: list[RecommendedAction] = Field(default_factory=list)
    sop_refs: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    abstentions: list[str] = Field(default_factory=list)


class RoutingRecommendation(BaseModel):
    recommended_team: str | None
    recommended_actions: list[RecommendedAction]
    escalation: str | None = None
    sop_refs: list[str] = Field(default_factory=list)


class FinalReport(BaseModel):
    title: str
    summary: str
    facts: list[str]
    derived_findings: list[str]
    assumptions: list[str]
    unknowns: list[str]
    recommendations: list[str]


class ReviewIssue(BaseModel):
    """ReviewerAgent 发现的具体问题。"""

    severity: Literal["critical", "warning", "info"]
    category: str
    description: str
    affected_fields: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class ReviewResult(BaseModel):
    """ReviewerAgent 跨 Agent 证据一致性审查结果。"""

    review_status: Literal["consistent", "flagged", "abstain"]
    issues: list[ReviewIssue] = Field(default_factory=list)
    recommendation: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[str] = Field(default_factory=list)


class ReActToolDecision(BaseModel):
    """ReAct 循环中 LLM 的工具调用决策（伪工具调用）。"""

    action: Literal[
        "get_metrics", "get_deployments", "get_incidents", "get_sops", "finish"
    ]
    action_input: dict[str, Any] = Field(default_factory=dict)
    thought: str


class WorkflowStepTrace(BaseModel):
    step: str
    status: str
    started_at: str
    completed_at: str
    summary: str
    evidence_ids: list[str] = Field(default_factory=list)


class OpsTicketResult(BaseModel):
    affected_service: str | None
    candidate_root_causes: list[CandidateRootCause] = Field(default_factory=list)
    recommended_actions: list[RecommendedAction] = Field(default_factory=list)
    assigned_team: str | None
    sop_refs: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class SupportTicketResult(BaseModel):
    request_type: str
    matched_articles: list[str] = Field(default_factory=list)
    reply_suggestions: list[str] = Field(default_factory=list)
    recommended_team: str | None
    escalation: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class TicketProcessResponse(BaseModel):
    ticket_id: str
    run_id: str
    data_mode: DataMode
    classification: TicketClassification
    context: RetrievedContext
    diagnosis: DiagnosisResult
    routing: RoutingRecommendation
    review: ReviewResult | None = None
    report: FinalReport
    agent_trace: list[WorkflowStepTrace]
    evidence: list[Evidence]
    ops_result: OpsTicketResult | None = None
    support_result: SupportTicketResult | None = None
    similar_cases: list[dict[str, Any]] = Field(default_factory=list)
    notification: dict[str, Any] | None = None


class TicketProcessWsStartRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)
    data_mode: DataMode = DataMode.MOCK
    desk_id: DeskId = DeskId.OPS

    @field_validator("text")
    @classmethod
    def strip_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("工单内容不能为空")
        return stripped


class TicketProcessWsStartMessage(BaseModel):
    type: Literal["start"]
    request: TicketProcessWsStartRequest


class TicketProcessWsCancelMessage(BaseModel):
    type: Literal["cancel"]
    reason: str | None = None


class TicketProcessWsEvent(BaseModel):
    type: str
    ticket_id: str
    run_id: str
    sequence: int
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class TicketProcessWsStartedEvent(TicketProcessWsEvent):
    type: Literal["started"] = "started"


class TicketProcessWsAgentProgressEvent(TicketProcessWsEvent):
    type: Literal["agent_progress"] = "agent_progress"
    agent_name: str
    step: str
    status: str
    summary: str
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)


class TicketProcessWsHeartbeatEvent(TicketProcessWsEvent):
    type: Literal["heartbeat"] = "heartbeat"


class TicketProcessWsCompletedEvent(TicketProcessWsEvent):
    type: Literal["completed"] = "completed"
    result: TicketProcessResponse


class TicketProcessWsCancelledEvent(TicketProcessWsEvent):
    type: Literal["cancelled"] = "cancelled"
    reason: str = "client_cancelled"


class TicketProcessWsErrorEvent(TicketProcessWsEvent):
    type: Literal["error"] = "error"
    error: dict[str, Any]
