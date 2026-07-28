from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from intelliticket_backend.errors import AppError
from intelliticket_backend.models import Team, User
from intelliticket_backend.repositories.tickets import TicketRepository
from intelliticket_backend.schemas.users import CurrentUser
from intelliticket_backend.schemas.workflow import (
    AssignTicketRequest,
    CancelTicketRequest,
    ConfirmTicketRequest,
    ReopenTicketRequest,
    ResolveTicketRequest,
    SlaBreachesResponse,
    TicketCommentCreateRequest,
    TicketCommentResponse,
    TicketCommentsResponse,
    TicketTimelineResponse,
    TicketWorkflowResponse,
    TriageCompleteRequest,
)


class TicketWorkflowService:
    """Explicit state machine for all human ticket actions."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = TicketRepository(session)

    @staticmethod
    def make_ticket_id() -> str:
        return f"TCK-{datetime.now(UTC):%Y%m%d}-{uuid4().hex[:8].upper()}"

    def submit(
        self,
        *,
        title: str,
        description: str,
        desk_id: str,
        data_mode: str,
        submitter: CurrentUser,
        priority: str = "P3",
    ) -> TicketWorkflowResponse:
        if submitter.id is None:
            raise AppError("AUTH_INVALID_TOKEN", "当前用户缺少数据库身份", 401, {})
        ticket = self.repository.create(
            ticket_id=self.make_ticket_id(),
            title=title,
            description=description,
            desk_id=desk_id,
            data_mode=data_mode,
            submitter_id=submitter.id,
            submitter=submitter.user_id,
            priority=priority,
        )
        return self.repository.to_workflow(ticket)

    def get(self, ticket_id: str, user: CurrentUser) -> TicketWorkflowResponse:
        ticket = self._ticket(ticket_id)
        self._ensure_visible(ticket.submitter_id, user)
        return self.repository.to_workflow(ticket)

    def triage_complete(
        self,
        ticket_id: str,
        request: TriageCompleteRequest,
        actor: CurrentUser,
    ) -> TicketWorkflowResponse:
        self._ensure_operator(actor)
        ticket = self._ticket(ticket_id)
        team_name = None
        if request.assigned_team_id:
            team = self.session.get(Team, request.assigned_team_id)
            if team is None or not team.is_active:
                raise AppError("TEAM_NOT_FOUND", "指定团队不存在或已停用", 404, {})
            team_name = team.name
        created_at = datetime.fromisoformat(ticket.created_at)
        response_due_at, resolution_due_at = self.repository.sla_deadlines(
            request.priority.value, created_at
        )
        updated = self.repository.transition(
            ticket_id=ticket_id,
            expected_version=request.version,
            allowed_statuses={"pending"},
            to_status="open",
            actor_id=self._actor_id(actor),
            event_type="triage_completed",
            changes={
                "category": request.category,
                "priority": request.priority.value,
                "assessed_priority": request.priority.value,
                "assigned_team_id": request.assigned_team_id,
                "assigned_team": team_name,
                "affected_service": request.affected_service,
                "response_due_at": response_due_at,
                "resolution_due_at": resolution_due_at,
                "sla_deadline": resolution_due_at,
            },
            payload={
                "category": request.category,
                "priority": request.priority.value,
                "assigned_team_id": request.assigned_team_id,
            },
        )
        return self.repository.to_workflow(updated)

    def claim(
        self, ticket_id: str, version: int, actor: CurrentUser
    ) -> TicketWorkflowResponse:
        self._ensure_operator(actor)
        now = datetime.now(UTC).isoformat()
        updated = self.repository.transition(
            ticket_id=ticket_id,
            expected_version=version,
            allowed_statuses={"pending", "open"},
            to_status="in_progress",
            actor_id=self._actor_id(actor),
            event_type="ticket_claimed",
            changes={
                "assignee_id": self._actor_id(actor),
                "claimed_by": actor.user_id,
                "claimed_at": now,
            },
            payload={"assignee_id": actor.id, "assignee": actor.user_id},
        )
        return self.repository.to_workflow(updated)

    def assign(
        self,
        ticket_id: str,
        request: AssignTicketRequest,
        actor: CurrentUser,
    ) -> TicketWorkflowResponse:
        if actor.role != "admin":
            raise AppError("AUTH_FORBIDDEN", "仅管理员可转派工单", 403, {})
        assignee = self.session.get(User, request.assignee_id)
        if assignee is None or not assignee.is_active or assignee.role not in {"operator", "admin"}:
            raise AppError("ASSIGNEE_NOT_FOUND", "指定处理人不存在或不可用", 404, {})
        team_name = None
        if request.assigned_team_id:
            team = self.session.get(Team, request.assigned_team_id)
            if team is None or not team.is_active:
                raise AppError("TEAM_NOT_FOUND", "指定团队不存在或已停用", 404, {})
            team_name = team.name
        now = datetime.now(UTC).isoformat()
        updated = self.repository.transition(
            ticket_id=ticket_id,
            expected_version=request.version,
            allowed_statuses={"pending", "open", "in_progress"},
            to_status="in_progress",
            actor_id=self._actor_id(actor),
            event_type="ticket_assigned",
            changes={
                "assignee_id": assignee.id,
                "claimed_by": assignee.username,
                "claimed_at": now,
                "assigned_team_id": request.assigned_team_id,
                "assigned_team": team_name,
            },
            payload={
                "assignee_id": assignee.id,
                "assignee": assignee.username,
                "assigned_team_id": request.assigned_team_id,
            },
        )
        return self.repository.to_workflow(updated)

    def add_comment(
        self,
        ticket_id: str,
        request: TicketCommentCreateRequest,
        actor: CurrentUser,
    ) -> TicketCommentResponse:
        ticket = self._ticket(ticket_id)
        self._ensure_visible(ticket.submitter_id, actor)
        if request.visibility == "internal" and actor.role not in {"operator", "admin"}:
            raise AppError("AUTH_FORBIDDEN", "员工不能添加内部备注", 403, {})
        comment = self.repository.add_comment(
            ticket=ticket,
            expected_version=request.version,
            author_id=self._actor_id(actor),
            visibility=request.visibility,
            body=request.body,
            mark_first_response=(
                request.visibility == "public" and actor.role in {"operator", "admin"}
            ),
        )
        return TicketCommentResponse(
            id=comment.id,
            ticket_id=comment.ticket_id,
            author_id=comment.author_id,
            author=actor.user_id,
            visibility=comment.visibility,
            body=comment.body,
            created_at=comment.created_at.isoformat(),
            updated_at=comment.updated_at.isoformat(),
        )

    def comments(self, ticket_id: str, actor: CurrentUser) -> TicketCommentsResponse:
        ticket = self._ticket(ticket_id)
        self._ensure_visible(ticket.submitter_id, actor)
        return TicketCommentsResponse(
            items=self.repository.comments(
                ticket_id, include_internal=actor.role in {"operator", "admin"}
            )
        )

    def timeline(self, ticket_id: str, actor: CurrentUser) -> TicketTimelineResponse:
        ticket = self._ticket(ticket_id)
        self._ensure_visible(ticket.submitter_id, actor)
        return TicketTimelineResponse(
            items=self.repository.events(
                ticket_id, include_internal=actor.role in {"operator", "admin"}
            )
        )

    def resolve(
        self,
        ticket_id: str,
        request: ResolveTicketRequest,
        actor: CurrentUser,
    ) -> TicketWorkflowResponse:
        self._ensure_operator(actor)
        ticket = self._ticket(ticket_id)
        if actor.role != "admin" and ticket.assignee_id != actor.id:
            raise AppError("AUTH_FORBIDDEN", "只有当前处理人可以解决工单", 403, {})
        now = datetime.now(UTC).isoformat()
        updated = self.repository.transition(
            ticket_id=ticket_id,
            expected_version=request.version,
            allowed_statuses={"in_progress"},
            to_status="resolved",
            actor_id=self._actor_id(actor),
            event_type="ticket_resolved",
            changes={
                "resolution_summary": request.resolution_summary,
                "root_cause": request.root_cause,
                "fix_action": request.fix_action,
                "verification": request.verification,
                "resolved_at": now,
            },
            payload={
                "resolution_summary": request.resolution_summary,
                "root_cause": request.root_cause,
                "fix_action": request.fix_action,
                "verification": request.verification,
            },
        )
        return self.repository.to_workflow(updated)

    def confirm(
        self,
        ticket_id: str,
        request: ConfirmTicketRequest,
        actor: CurrentUser,
    ) -> TicketWorkflowResponse:
        ticket = self._ticket(ticket_id)
        self._ensure_owner_or_admin(ticket.submitter_id, actor)
        updated = self.repository.transition(
            ticket_id=ticket_id,
            expected_version=request.version,
            allowed_statuses={"resolved"},
            to_status="closed",
            actor_id=self._actor_id(actor),
            event_type="ticket_closed",
            changes={"closed_at": datetime.now(UTC).isoformat()},
        )
        return self.repository.to_workflow(updated)

    def reopen(
        self,
        ticket_id: str,
        request: ReopenTicketRequest,
        actor: CurrentUser,
    ) -> TicketWorkflowResponse:
        ticket = self._ticket(ticket_id)
        self._ensure_owner_or_admin(ticket.submitter_id, actor)
        updated = self.repository.transition(
            ticket_id=ticket_id,
            expected_version=request.version,
            allowed_statuses={"resolved", "closed"},
            to_status="open",
            actor_id=self._actor_id(actor),
            event_type="ticket_reopened",
            changes={
                "assignee_id": None,
                "claimed_by": None,
                "claimed_at": None,
                "resolved_at": None,
                "closed_at": None,
            },
            payload={"reason": request.reason.strip()},
        )
        return self.repository.to_workflow(updated)

    def cancel(
        self,
        ticket_id: str,
        request: CancelTicketRequest,
        actor: CurrentUser,
    ) -> TicketWorkflowResponse:
        ticket = self._ticket(ticket_id)
        self._ensure_owner_or_admin(ticket.submitter_id, actor)
        updated = self.repository.transition(
            ticket_id=ticket_id,
            expected_version=request.version,
            allowed_statuses={"pending", "open"},
            to_status="cancelled",
            actor_id=self._actor_id(actor),
            event_type="ticket_cancelled",
            changes={"closed_at": datetime.now(UTC).isoformat()},
            payload={"reason": request.reason.strip()},
        )
        return self.repository.to_workflow(updated)

    def overdue(self, actor: CurrentUser) -> SlaBreachesResponse:
        self._ensure_operator(actor)
        return SlaBreachesResponse(items=self.repository.overdue())

    def _ticket(self, ticket_id: str):
        ticket = self.repository.get(ticket_id)
        if ticket is None:
            raise AppError("TICKET_NOT_FOUND", "工单不存在", 404, {"ticket_id": ticket_id})
        return ticket

    @staticmethod
    def _actor_id(actor: CurrentUser) -> str:
        if actor.id is None:
            raise AppError("AUTH_INVALID_TOKEN", "当前用户缺少数据库身份", 401, {})
        return actor.id

    @staticmethod
    def _ensure_operator(actor: CurrentUser) -> None:
        if actor.role not in {"operator", "admin"}:
            raise AppError("AUTH_FORBIDDEN", "仅运维人员可执行此操作", 403, {})

    @staticmethod
    def _ensure_visible(submitter_id: str | None, actor: CurrentUser) -> None:
        if actor.role in {"operator", "admin"} or submitter_id == actor.id:
            return
        raise AppError("TICKET_ACCESS_DENIED", "无权查看该工单", 403, {})

    @staticmethod
    def _ensure_owner_or_admin(submitter_id: str | None, actor: CurrentUser) -> None:
        if actor.role == "admin" or submitter_id == actor.id:
            return
        raise AppError("AUTH_FORBIDDEN", "只有提交人或管理员可执行此操作", 403, {})
