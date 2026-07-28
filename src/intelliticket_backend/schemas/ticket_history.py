from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from intelliticket_backend.schemas.orchestration import RouteDecision
from intelliticket_backend.schemas.tickets import DataMode, DeskId, Evidence, TicketProcessResponse
from intelliticket_backend.services.agents.envelope import AgentTaskError, ReActStep

TICKET_ID_PATTERN = r"^TCK-\d{8}-[A-F0-9]{8}$"
RUN_ID_PATTERN = r"^RUN-\d{8}-[A-F0-9]{8}$"
RunStatus = Literal["queued", "running", "completed", "failed", "cancelled", "pending"]
TicketStatus = Literal["pending", "open", "in_progress", "resolved", "closed", "cancelled"]
SupportReplyDraftStatus = Literal["draft", "approved", "sent", "discarded"]


class SupportReplyDraftUpdateRequest(BaseModel):
    reply_text: str = Field(..., min_length=1, max_length=5000)
    report_summary: str | None = Field(default=None, max_length=1000)
    evidence_ids: list[str] = Field(default_factory=list)
    status: SupportReplyDraftStatus = "draft"
    editor: str | None = Field(default=None, max_length=120)

    @field_validator("reply_text")
    @classmethod
    def strip_reply_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("回复草稿不能为空")
        return stripped


class SupportReplyDraftResponse(BaseModel):
    draft_id: str
    ticket_id: str
    run_id: str
    source: str
    reply_text: str
    report_summary: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    status: SupportReplyDraftStatus
    editor: str | None = None
    created_at: str
    updated_at: str
    approved_at: str | None = None
    sent_at: str | None = None

    model_config = ConfigDict(extra="forbid")


class TicketLifecycleUpdateRequest(BaseModel):
    ticket_status: TicketStatus | None = None
    resolution_summary: str | None = Field(default=None, max_length=1000)
    root_cause: str | None = Field(default=None, max_length=2000)
    fix_action: str | None = Field(default=None, max_length=2000)
    verification: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def require_update(self) -> TicketLifecycleUpdateRequest:
        if (
            self.ticket_status is None
            and self.resolution_summary is None
            and self.root_cause is None
            and self.fix_action is None
            and self.verification is None
        ):
            raise ValueError("至少需要提供一个工单生命周期更新字段")
        if self.ticket_status == "resolved":
            missing = []
            if not (self.root_cause or "").strip():
                missing.append("root_cause（根因分析）")
            if not (self.fix_action or "").strip():
                missing.append("fix_action（修复动作）")
            if not (self.verification or "").strip():
                missing.append("verification（验证方式）")
            if missing:
                raise ValueError(
                    "标记已解决时必须填写："
                    + "、".join(missing)
                )
        return self


class TicketHistorySummary(BaseModel):
    ticket_id: str
    desk_id: DeskId
    latest_run_id: str | None = None
    created_at: str
    updated_at: str
    data_mode: DataMode
    status: RunStatus
    ticket_status: TicketStatus
    submitter: str | None = None
    assessed_priority: str | None = None
    assessed_priority_reason: str | None = None
    sla_deadline: str | None = None
    claimed_by: str | None = None
    claimed_at: str | None = None
    assigned_team: str | None = None
    resolution_summary: str | None = None
    closed_at: str | None = None
    summary: str | None = ""
    affected_service: str | None = None
    priority: str | None = None
    report_title: str | None = None
    version: int = 1
    assignee_id: str | None = None
    response_due_at: str | None = None
    resolution_due_at: str | None = None
    first_responded_at: str | None = None

    model_config = ConfigDict(extra="forbid")


class TicketHistoryListResponse(BaseModel):
    items: list[TicketHistorySummary] = Field(default_factory=list)
    limit: int
    offset: int
    total: int

    model_config = ConfigDict(extra="forbid")


class StoredAgentRun(BaseModel):
    sequence: int
    task_id: str
    agent_name: str
    step: str
    status: str
    route_decision: RouteDecision | None = None
    observations: list[str] = Field(default_factory=list)
    react_steps: list[ReActStep] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    error: AgentTaskError | None = None
    started_at: str
    completed_at: str | None = None

    model_config = ConfigDict(extra="forbid")


class StoredRunDetail(BaseModel):
    run_id: str
    status: RunStatus
    data_mode: DataMode
    route_mode: str
    started_at: str
    completed_at: str
    response: TicketProcessResponse | None = None
    error: AgentTaskError | None = None
    agent_runs: list[StoredAgentRun] = Field(default_factory=list)
    supervisor_decisions: list[RouteDecision] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class TicketHistoryDetailResponse(BaseModel):
    ticket_id: str
    desk_id: DeskId
    input_text: str
    data_mode: DataMode
    ticket_status: TicketStatus
    submitter: str | None = None
    assigned_team: str | None = None
    resolution_summary: str | None = None
    root_cause: str | None = None
    fix_action: str | None = None
    verification: str | None = None
    closed_at: str | None = None
    created_at: str
    updated_at: str
    support_reply_draft: SupportReplyDraftResponse | None = None
    latest_run: StoredRunDetail | None = None
    version: int = 1
    submitter_id: str | None = None
    assignee_id: str | None = None
    assigned_team_id: str | None = None
    claimed_by: str | None = None
    claimed_at: str | None = None
    priority: str | None = None
    category: str | None = None
    response_due_at: str | None = None
    resolution_due_at: str | None = None
    first_responded_at: str | None = None
    resolved_at: str | None = None
    ai_run_id: str | None = None
    ai_status: str | None = None
    ai_result: dict | None = None

    model_config = ConfigDict(extra="forbid")
