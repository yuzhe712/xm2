from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Select, and_, or_, select, update
from sqlalchemy.orm import Session, aliased

from intelliticket_backend.errors import AppError
from intelliticket_backend.models import AiRun, SlaPolicy, Ticket, TicketComment, TicketEvent, User
from intelliticket_backend.schemas.ticket_history import (
    TicketHistoryDetailResponse,
    TicketHistorySummary,
)
from intelliticket_backend.schemas.workflow import (
    SlaBreachResponse,
    TicketCommentResponse,
    TicketEventResponse,
    TicketWorkflowResponse,
)

DEFAULT_SLA_MINUTES = {
    "P1": (15, 240),
    "P2": (30, 480),
    "P3": (240, 1440),
    "P4": (480, 4320),
}


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(value: datetime | str | None) -> str | None:
    if value is None:
        return None
    return value.isoformat() if isinstance(value, datetime) else value


class TicketRepository:
    """SQLAlchemy repository for the human ticket workflow."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def sla_deadlines(self, priority: str, created_at: datetime | None = None) -> tuple[str, str]:
        policy = self.session.scalar(
            select(SlaPolicy).where(
                SlaPolicy.priority == priority,
                SlaPolicy.is_active.is_(True),
            )
        )
        response_minutes, resolution_minutes = (
            (policy.response_minutes, policy.resolution_minutes)
            if policy is not None
            else DEFAULT_SLA_MINUTES[priority]
        )
        base = created_at or _now()
        return (
            (base + timedelta(minutes=response_minutes)).isoformat(),
            (base + timedelta(minutes=resolution_minutes)).isoformat(),
        )

    def create(
        self,
        *,
        ticket_id: str,
        title: str,
        description: str,
        desk_id: str,
        data_mode: str,
        submitter_id: str,
        submitter: str,
        priority: str = "P3",
    ) -> Ticket:
        created_at = _now()
        response_due_at, resolution_due_at = self.sla_deadlines(priority, created_at)
        ticket = Ticket(
            ticket_id=ticket_id,
            title=title,
            description=description,
            input_text=description,
            desk_id=desk_id,
            data_mode=data_mode,
            ticket_status="pending",
            priority=priority,
            assessed_priority=priority,
            submitter_id=submitter_id,
            submitter=submitter,
            summary=title,
            response_due_at=response_due_at,
            resolution_due_at=resolution_due_at,
            sla_deadline=resolution_due_at,
            version=1,
            created_at=created_at.isoformat(),
            updated_at=created_at.isoformat(),
        )
        self.session.add(ticket)
        self.session.flush()
        self.add_event(
            ticket_id=ticket_id,
            actor_id=submitter_id,
            event_type="ticket_created",
            from_status=None,
            to_status="pending",
            visibility="public",
            payload={"title": title, "priority": priority},
        )
        return ticket

    def get(self, ticket_id: str) -> Ticket | None:
        return self.session.get(Ticket, ticket_id)

    def list_models(
        self,
        *,
        desk_id: str | None = None,
        submitter_id: str | None = None,
        statuses: set[str] | None = None,
    ) -> list[Ticket]:
        statement: Select[tuple[Ticket]] = select(Ticket)
        if desk_id is not None:
            statement = statement.where(Ticket.desk_id == desk_id)
        if submitter_id is not None:
            statement = statement.where(Ticket.submitter_id == submitter_id)
        if statuses:
            statement = statement.where(Ticket.ticket_status.in_(statuses))
        statement = statement.order_by(Ticket.updated_at.desc(), Ticket.ticket_id.desc())
        return list(self.session.scalars(statement).all())

    def transition(
        self,
        *,
        ticket_id: str,
        expected_version: int,
        allowed_statuses: set[str],
        to_status: str,
        actor_id: str,
        event_type: str,
        changes: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
        visibility: str = "public",
    ) -> Ticket:
        current = self.get(ticket_id)
        if current is None:
            raise AppError("TICKET_NOT_FOUND", "工单不存在", 404, {"ticket_id": ticket_id})
        from_status = current.ticket_status
        values = dict(changes or {})
        values.update(
            ticket_status=to_status,
            version=Ticket.version + 1,
            updated_at=_now().isoformat(),
        )
        result = self.session.execute(
            update(Ticket)
            .where(
                Ticket.ticket_id == ticket_id,
                Ticket.version == expected_version,
                Ticket.ticket_status.in_(allowed_statuses),
            )
            .values(**values)
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            self.session.expire_all()
            latest = self.get(ticket_id)
            if latest is None:
                raise AppError("TICKET_NOT_FOUND", "工单不存在", 404, {"ticket_id": ticket_id})
            if latest.version != expected_version:
                raise AppError(
                    "TICKET_VERSION_CONFLICT",
                    "工单已被其他用户更新",
                    409,
                    {"expected_version": expected_version, "current_version": latest.version},
                )
            raise AppError(
                "TICKET_INVALID_TRANSITION",
                "当前状态不允许执行该操作",
                409,
                {"status": latest.ticket_status, "allowed_statuses": sorted(allowed_statuses)},
            )
        self.add_event(
            ticket_id=ticket_id,
            actor_id=actor_id,
            event_type=event_type,
            from_status=from_status,
            to_status=to_status,
            visibility=visibility,
            payload=payload or {},
        )
        self.session.flush()
        self.session.expire_all()
        updated = self.get(ticket_id)
        assert updated is not None
        return updated

    def add_comment(
        self,
        *,
        ticket: Ticket,
        expected_version: int,
        author_id: str,
        visibility: str,
        body: str,
        mark_first_response: bool,
    ) -> TicketComment:
        now = _now()
        values: dict[str, Any] = {
            "version": Ticket.version + 1,
            "updated_at": now.isoformat(),
        }
        if mark_first_response and ticket.first_responded_at is None:
            values["first_responded_at"] = now.isoformat()
        result = self.session.execute(
            update(Ticket)
            .where(Ticket.ticket_id == ticket.ticket_id, Ticket.version == expected_version)
            .values(**values)
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            self.session.expire_all()
            latest = self.get(ticket.ticket_id)
            raise AppError(
                "TICKET_VERSION_CONFLICT",
                "工单已被其他用户更新",
                409,
                {
                    "expected_version": expected_version,
                    "current_version": latest.version if latest else None,
                },
            )
        comment = TicketComment(
            ticket_id=ticket.ticket_id,
            author_id=author_id,
            visibility=visibility,
            body=body,
            created_at=now,
            updated_at=now,
        )
        self.session.add(comment)
        self.session.flush()
        self.add_event(
            ticket_id=ticket.ticket_id,
            actor_id=author_id,
            event_type="comment_added" if visibility == "public" else "internal_note_added",
            from_status=ticket.ticket_status,
            to_status=ticket.ticket_status,
            visibility=visibility,
            payload={"comment_id": comment.id, "body": body},
        )
        self.session.flush()
        return comment

    def add_event(
        self,
        *,
        ticket_id: str,
        actor_id: str | None,
        event_type: str,
        from_status: str | None,
        to_status: str | None,
        visibility: str,
        payload: dict[str, Any],
    ) -> TicketEvent:
        event = TicketEvent(
            ticket_id=ticket_id,
            actor_id=actor_id,
            event_type=event_type,
            from_status=from_status,
            to_status=to_status,
            visibility=visibility,
            payload_json=payload,
        )
        self.session.add(event)
        self.session.flush()
        return event

    def comments(self, ticket_id: str, include_internal: bool) -> list[TicketCommentResponse]:
        author = aliased(User)
        statement = (
            select(TicketComment, author.username)
            .outerjoin(author, TicketComment.author_id == author.id)
            .where(TicketComment.ticket_id == ticket_id)
            .order_by(TicketComment.created_at, TicketComment.id)
        )
        if not include_internal:
            statement = statement.where(TicketComment.visibility == "public")
        return [
            TicketCommentResponse(
                id=comment.id,
                ticket_id=comment.ticket_id,
                author_id=comment.author_id,
                author=username or "unknown",
                visibility=comment.visibility,
                body=comment.body,
                created_at=comment.created_at.isoformat(),
                updated_at=comment.updated_at.isoformat(),
            )
            for comment, username in self.session.execute(statement).all()
        ]

    def events(self, ticket_id: str, include_internal: bool) -> list[TicketEventResponse]:
        actor = aliased(User)
        statement = (
            select(TicketEvent, actor.username)
            .outerjoin(actor, TicketEvent.actor_id == actor.id)
            .where(TicketEvent.ticket_id == ticket_id)
            .order_by(TicketEvent.created_at, TicketEvent.id)
        )
        if not include_internal:
            statement = statement.where(TicketEvent.visibility == "public")
        return [
            TicketEventResponse(
                id=event.id,
                ticket_id=event.ticket_id,
                actor_id=event.actor_id,
                actor=username,
                event_type=event.event_type,
                from_status=event.from_status,
                to_status=event.to_status,
                visibility=event.visibility,
                payload=event.payload_json,
                created_at=event.created_at.isoformat(),
            )
            for event, username in self.session.execute(statement).all()
        ]

    def overdue(self, now: datetime | None = None) -> list[SlaBreachResponse]:
        current = (now or _now()).isoformat()
        rows = self.session.scalars(
            select(Ticket).where(
                Ticket.ticket_status.not_in({"closed", "cancelled"}),
                or_(
                    and_(
                        Ticket.first_responded_at.is_(None),
                        Ticket.response_due_at.is_not(None),
                        Ticket.response_due_at < current,
                    ),
                    and_(
                        Ticket.resolution_due_at.is_not(None),
                        Ticket.resolution_due_at < current,
                    ),
                ),
            )
        ).all()
        return [
            SlaBreachResponse(
                ticket_id=ticket.ticket_id,
                status=ticket.ticket_status,
                priority=ticket.priority,
                response_overdue=bool(
                    ticket.first_responded_at is None
                    and ticket.response_due_at
                    and ticket.response_due_at < current
                ),
                resolution_overdue=bool(
                    ticket.resolution_due_at and ticket.resolution_due_at < current
                ),
                response_due_at=ticket.response_due_at,
                resolution_due_at=ticket.resolution_due_at,
            )
            for ticket in rows
        ]

    @staticmethod
    def to_workflow(ticket: Ticket) -> TicketWorkflowResponse:
        return TicketWorkflowResponse(
            ticket_id=ticket.ticket_id,
            title=ticket.title or ticket.summary or ticket.input_text[:120],
            description=ticket.description or ticket.input_text,
            desk_id=ticket.desk_id,
            data_mode=ticket.data_mode,
            status=ticket.ticket_status,
            priority=ticket.priority,
            category=ticket.category,
            submitter_id=ticket.submitter_id or "",
            submitter=ticket.submitter or "unknown",
            assigned_team_id=ticket.assigned_team_id,
            assigned_team=ticket.assigned_team,
            assignee_id=ticket.assignee_id,
            claimed_by=ticket.claimed_by,
            resolution_summary=ticket.resolution_summary,
            root_cause=ticket.root_cause,
            fix_action=ticket.fix_action,
            verification=ticket.verification,
            response_due_at=ticket.response_due_at,
            resolution_due_at=ticket.resolution_due_at,
            first_responded_at=ticket.first_responded_at,
            resolved_at=ticket.resolved_at,
            closed_at=ticket.closed_at,
            version=ticket.version,
            created_at=ticket.created_at,
            updated_at=ticket.updated_at,
        )

    @staticmethod
    def to_history_summary(ticket: Ticket, ai_status: str = "pending") -> TicketHistorySummary:
        return TicketHistorySummary(
            ticket_id=ticket.ticket_id,
            desk_id=ticket.desk_id,
            latest_run_id=ticket.latest_run_id,
            created_at=ticket.created_at,
            updated_at=ticket.updated_at,
            data_mode=ticket.data_mode,
            status=ai_status,
            ticket_status=ticket.ticket_status,
            submitter=ticket.submitter,
            assessed_priority=ticket.assessed_priority or ticket.priority,
            assessed_priority_reason=ticket.assessed_priority_reason,
            sla_deadline=ticket.resolution_due_at or ticket.sla_deadline,
            claimed_by=ticket.claimed_by,
            claimed_at=ticket.claimed_at,
            assigned_team=ticket.assigned_team,
            resolution_summary=ticket.resolution_summary,
            closed_at=ticket.closed_at,
            summary=ticket.summary,
            affected_service=ticket.affected_service,
            priority=ticket.priority,
            report_title=ticket.report_title,
            version=ticket.version,
            assignee_id=ticket.assignee_id,
            response_due_at=ticket.response_due_at,
            resolution_due_at=ticket.resolution_due_at,
            first_responded_at=ticket.first_responded_at,
        )

    @staticmethod
    def to_history_detail(
        ticket: Ticket, ai_run: AiRun | None = None
    ) -> TicketHistoryDetailResponse:
        return TicketHistoryDetailResponse(
            ticket_id=ticket.ticket_id,
            desk_id=ticket.desk_id,
            input_text=ticket.input_text,
            data_mode=ticket.data_mode,
            ticket_status=ticket.ticket_status,
            submitter=ticket.submitter,
            assigned_team=ticket.assigned_team,
            resolution_summary=ticket.resolution_summary,
            root_cause=ticket.root_cause,
            fix_action=ticket.fix_action,
            verification=ticket.verification,
            closed_at=ticket.closed_at,
            created_at=ticket.created_at,
            updated_at=ticket.updated_at,
            support_reply_draft=None,
            latest_run=None,
            version=ticket.version,
            submitter_id=ticket.submitter_id,
            assignee_id=ticket.assignee_id,
            assigned_team_id=ticket.assigned_team_id,
            claimed_by=ticket.claimed_by,
            claimed_at=ticket.claimed_at,
            priority=ticket.priority,
            category=ticket.category,
            response_due_at=ticket.response_due_at,
            resolution_due_at=ticket.resolution_due_at,
            first_responded_at=ticket.first_responded_at,
            resolved_at=ticket.resolved_at,
            ai_run_id=ai_run.id if ai_run else ticket.latest_run_id,
            ai_status=ai_run.status if ai_run else None,
            ai_result=ai_run.result_json if ai_run else None,
        )
