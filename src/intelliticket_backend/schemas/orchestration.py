from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from intelliticket_backend.schemas.tickets import (
    DataMode,
    DiagnosisResult,
    Evidence,
    FinalReport,
    RetrievedContext,
    ReviewResult,
    RoutingRecommendation,
    TicketClassification,
    TicketProcessRequest,
    TicketProcessResponse,
)
from intelliticket_backend.services.agents.envelope import AgentTaskError, ReActStep

RouteNextAgent = Literal[
    "ticket_intake_agent",
    "context_retrieval_agent",
    "diagnosis_agent",
    "routing_agent",
    "reviewer_agent",
    "report_agent",
    "support_intake_service",
    "support_kb_retrieval_service",
    "support_kb_retrieval_agent",
    "support_routing_service",
    "support_reply_suggestion_service",
    "support_reply_agent",
    "finish",
    "abstain",
]

ALLOWED_NEXT_AGENTS: set[str] = {
    "ticket_intake_agent",
    "context_retrieval_agent",
    "diagnosis_agent",
    "routing_agent",
    "reviewer_agent",
    "report_agent",
    "support_intake_service",
    "support_kb_retrieval_service",
    "support_kb_retrieval_agent",
    "support_routing_service",
    "support_reply_suggestion_service",
    "support_reply_agent",
    "finish",
    "abstain",
}

PRIVATE_OR_UNSUPPORTED_ROUTE_FIELDS: set[str] = {
    "thought",
    "thoughts",
    "chain_of_thought",
    "reasoning",
    "private_reasoning",
    "hidden_reasoning",
    "scratchpad",
    "tool",
    "tool_name",
    "tool_call",
    "tool_calls",
    "function_call",
    "mcp",
    "mcp_tool",
    "mcp_server",
    "agent_payload",
    "classification",
    "context",
    "diagnosis",
    "routing",
    "report",
    "evidence",
    "fake_evidence",
}


class RouteDecision(BaseModel):
    """LLM Supervisor 只能返回的下一步路由决策。"""

    next_agent: RouteNextAgent
    message_type: str = Field(..., min_length=1, max_length=100)
    reason_summary: str = Field(..., min_length=1, max_length=500)
    required_inputs: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    requires_human_review: bool = False

    model_config = ConfigDict(extra="forbid")


class SupervisorAgentRun(BaseModel):
    """Supervisor 追加式 Agent 运行记录。"""

    task_id: str
    ticket_id: str
    run_id: str
    agent_name: str
    status: str
    route_decision: RouteDecision | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    observations: list[str] = Field(default_factory=list)
    react_steps: list[ReActStep] = Field(default_factory=list)
    error: AgentTaskError | None = None
    started_at: str
    completed_at: str | None = None

    model_config = ConfigDict(extra="forbid")


class SupervisorRunResult(BaseModel):
    """Supervisor 编排完成后的响应和审计数据。"""

    response: TicketProcessResponse
    agent_runs: list[SupervisorAgentRun] = Field(default_factory=list)
    route_decisions: list[RouteDecision] = Field(default_factory=list)
    started_at: str
    completed_at: str

    model_config = ConfigDict(extra="forbid")


class SupervisorRunFailure(BaseModel):
    """Supervisor 编排失败或取消后的审计快照。"""

    ticket_id: str
    run_id: str
    status: Literal["failed", "cancelled"]
    data_mode: DataMode
    error: AgentTaskError
    agent_runs: list[SupervisorAgentRun] = Field(default_factory=list)
    route_decisions: list[RouteDecision] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    started_at: str
    completed_at: str

    model_config = ConfigDict(extra="forbid")


class SupervisorState(BaseModel):
    """可序列化 Supervisor 编排状态。"""

    ticket_id: str
    run_id: str
    request: TicketProcessRequest
    status: Literal["running", "completed", "abstained", "failed", "cancelled"] = "running"
    current_step: int = 0
    max_steps: int
    agent_runs: list[SupervisorAgentRun] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    classification: TicketClassification | None = None
    service_record: dict[str, Any] | None = None
    context: RetrievedContext | None = None
    diagnosis: DiagnosisResult | None = None
    routing: RoutingRecommendation | None = None
    review: ReviewResult | None = None
    report: FinalReport | None = None
    similar_cases: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[AgentTaskError] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")
