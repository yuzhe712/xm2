from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, Boolean, CheckConstraint, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from intelliticket_backend.models.base import Base, TimestampMixin


def _id() -> str:
    return str(uuid4())


class Ticket(Base):
    """P0 transition model; legacy columns remain until the P1 repository cutover."""

    __tablename__ = "tickets"
    __table_args__ = (
        CheckConstraint(
            "ticket_status IN "
            "('pending', 'open', 'in_progress', 'resolved', 'closed', 'cancelled')",
            name="status_values",
        ),
        CheckConstraint("data_mode IN ('mock', 'real')", name="data_mode_values"),
        Index("ix_tickets_updated_at", "updated_at"),
    )

    ticket_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    input_text: Mapped[str] = mapped_column(Text)
    desk_id: Mapped[str] = mapped_column(String(20), default="ops", nullable=False)
    category: Mapped[str | None] = mapped_column(String(80))
    data_mode: Mapped[str] = mapped_column(String(10), nullable=False)
    ticket_status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    priority: Mapped[str | None] = mapped_column(String(10))
    submitter: Mapped[str | None] = mapped_column(String(60), index=True)
    submitter_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    assigned_team: Mapped[str | None] = mapped_column(String(120))
    assigned_team_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("teams.id", ondelete="SET NULL")
    )
    claimed_by: Mapped[str | None] = mapped_column(String(60))
    assignee_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL")
    )
    claimed_at: Mapped[str | None] = mapped_column(String(64))
    summary: Mapped[str | None] = mapped_column(Text)
    affected_service: Mapped[str | None] = mapped_column(String(160))
    report_title: Mapped[str | None] = mapped_column(String(240))
    resolution_summary: Mapped[str | None] = mapped_column(Text)
    root_cause: Mapped[str | None] = mapped_column(Text)
    fix_action: Mapped[str | None] = mapped_column(Text)
    verification: Mapped[str | None] = mapped_column(Text)
    assessed_priority: Mapped[str | None] = mapped_column(String(10))
    assessed_priority_reason: Mapped[str | None] = mapped_column(Text)
    response_due_at: Mapped[str | None] = mapped_column(String(64))
    resolution_due_at: Mapped[str | None] = mapped_column(String(64))
    sla_deadline: Mapped[str | None] = mapped_column(String(64))
    first_responded_at: Mapped[str | None] = mapped_column(String(64))
    resolved_at: Mapped[str | None] = mapped_column(String(64))
    closed_at: Mapped[str | None] = mapped_column(String(64))
    latest_run_id: Mapped[str | None] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[str] = mapped_column(
        String(64), default=lambda: datetime.now(UTC).isoformat(), nullable=False
    )
    updated_at: Mapped[str] = mapped_column(
        String(64),
        default=lambda: datetime.now(UTC).isoformat(),
        onupdate=lambda: datetime.now(UTC).isoformat(),
        nullable=False,
    )


class TicketEvent(Base):
    __tablename__ = "ticket_events"
    __table_args__ = (
        CheckConstraint("visibility IN ('public', 'internal')", name="visibility_values"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    ticket_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tickets.ticket_id", ondelete="CASCADE"), index=True
    )
    actor_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL")
    )
    event_type: Mapped[str] = mapped_column(String(80))
    from_status: Mapped[str | None] = mapped_column(String(20))
    to_status: Mapped[str | None] = mapped_column(String(20))
    visibility: Mapped[str] = mapped_column(String(20), default="public", nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC), nullable=False
    )


class TicketComment(TimestampMixin, Base):
    __tablename__ = "ticket_comments"
    __table_args__ = (
        CheckConstraint("visibility IN ('public', 'internal')", name="visibility_values"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    ticket_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tickets.ticket_id", ondelete="CASCADE"), index=True
    )
    author_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT")
    )
    visibility: Mapped[str] = mapped_column(String(20), default="public", nullable=False)
    body: Mapped[str] = mapped_column(Text)


class AiRun(Base):
    __tablename__ = "ai_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed', 'cancelled')",
            name="status_values",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    ticket_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tickets.ticket_id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(20), default="queued", nullable=False)
    celery_task_id: Mapped[str | None] = mapped_column(String(80), index=True)
    stage: Mapped[str] = mapped_column(String(40), default="queued", nullable=False)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pipeline_version: Mapped[str] = mapped_column(String(40))
    provider: Mapped[str] = mapped_column(String(60))
    model: Mapped[str] = mapped_column(String(120))
    prompt_version: Mapped[str] = mapped_column(String(40))
    input_hash: Mapped[str] = mapped_column(String(64), index=True)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    evidence_json: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    confidence: Mapped[float | None]
    error_code: Mapped[str | None] = mapped_column(String(120))
    error_message: Mapped[str | None] = mapped_column(Text)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duration_ms: Mapped[int | None]
    decision: Mapped[str | None] = mapped_column(String(20))
    decision_note: Mapped[str | None] = mapped_column(Text)
    modified_result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    decided_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL")
    )
    decided_at: Mapped[datetime | None]
    started_at: Mapped[datetime | None]
    completed_at: Mapped[datetime | None]
    heartbeat_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )


class SlaPolicy(TimestampMixin, Base):
    __tablename__ = "sla_policies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    priority: Mapped[str] = mapped_column(String(10), unique=True)
    response_minutes: Mapped[int] = mapped_column(Integer)
    resolution_minutes: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
