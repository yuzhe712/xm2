from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from intelliticket_backend.schemas.ticket_history import TicketStatus
from intelliticket_backend.schemas.tickets import DataMode, DeskId, TicketPriority

CommentVisibility = Literal["public", "internal"]


class VersionedCommand(BaseModel):
    version: int = Field(..., ge=1)


class TriageCompleteRequest(VersionedCommand):
    category: str = Field(..., min_length=1, max_length=80)
    priority: TicketPriority
    assigned_team_id: str | None = Field(default=None, max_length=36)
    affected_service: str | None = Field(default=None, max_length=160)


class ClaimTicketRequest(VersionedCommand):
    pass


class AssignTicketRequest(VersionedCommand):
    assignee_id: str = Field(..., min_length=1, max_length=36)
    assigned_team_id: str | None = Field(default=None, max_length=36)


class TicketCommentCreateRequest(VersionedCommand):
    visibility: CommentVisibility = "public"
    body: str = Field(..., min_length=1, max_length=5000)

    @field_validator("body")
    @classmethod
    def strip_body(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("评论内容不能为空")
        return stripped


class ResolveTicketRequest(VersionedCommand):
    resolution_summary: str = Field(..., min_length=1, max_length=2000)
    root_cause: str = Field(..., min_length=1, max_length=2000)
    fix_action: str = Field(..., min_length=1, max_length=2000)
    verification: str = Field(..., min_length=1, max_length=2000)

    @field_validator("resolution_summary", "root_cause", "fix_action", "verification")
    @classmethod
    def strip_resolution_field(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("解决信息不能为空")
        return stripped


class ConfirmTicketRequest(VersionedCommand):
    pass


class ReopenTicketRequest(VersionedCommand):
    reason: str = Field(..., min_length=1, max_length=1000)


class CancelTicketRequest(VersionedCommand):
    reason: str = Field(..., min_length=1, max_length=1000)


class TicketWorkflowResponse(BaseModel):
    ticket_id: str
    title: str
    description: str
    desk_id: DeskId
    data_mode: DataMode
    status: TicketStatus
    priority: str | None = None
    category: str | None = None
    submitter_id: str
    submitter: str
    assigned_team_id: str | None = None
    assigned_team: str | None = None
    assignee_id: str | None = None
    claimed_by: str | None = None
    resolution_summary: str | None = None
    root_cause: str | None = None
    fix_action: str | None = None
    verification: str | None = None
    response_due_at: str | None = None
    resolution_due_at: str | None = None
    first_responded_at: str | None = None
    resolved_at: str | None = None
    closed_at: str | None = None
    version: int
    created_at: str
    updated_at: str

    model_config = ConfigDict(extra="forbid")


class TicketCommentResponse(BaseModel):
    id: str
    ticket_id: str
    author_id: str
    author: str
    visibility: CommentVisibility
    body: str
    created_at: str
    updated_at: str

    model_config = ConfigDict(extra="forbid")


class TicketEventResponse(BaseModel):
    id: str
    ticket_id: str
    actor_id: str | None = None
    actor: str | None = None
    event_type: str
    from_status: TicketStatus | None = None
    to_status: TicketStatus | None = None
    visibility: CommentVisibility
    payload: dict
    created_at: str

    model_config = ConfigDict(extra="forbid")


class TicketTimelineResponse(BaseModel):
    items: list[TicketEventResponse]


class TicketCommentsResponse(BaseModel):
    items: list[TicketCommentResponse]


class SlaBreachResponse(BaseModel):
    ticket_id: str
    status: TicketStatus
    priority: str | None = None
    response_overdue: bool
    resolution_overdue: bool
    response_due_at: str | None = None
    resolution_due_at: str | None = None


class SlaBreachesResponse(BaseModel):
    items: list[SlaBreachResponse]
