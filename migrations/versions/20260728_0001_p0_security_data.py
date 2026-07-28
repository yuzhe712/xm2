"""P0 security and data foundation.

Revision ID: 20260728_0001
Revises:
Create Date: 2026-07-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from intelliticket_backend.models import Base

revision: str = "20260728_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LEGACY_TICKET_COLUMNS: dict[str, sa.Column] = {
    "title": sa.Column("title", sa.String(length=200), nullable=True),
    "description": sa.Column("description", sa.Text(), nullable=True),
    "desk_id": sa.Column(
        "desk_id", sa.String(length=20), nullable=False, server_default="ops"
    ),
    "category": sa.Column("category", sa.String(length=80), nullable=True),
    "ticket_status": sa.Column(
        "ticket_status", sa.String(length=20), nullable=False, server_default="open"
    ),
    "submitter": sa.Column("submitter", sa.String(length=60), nullable=True),
    "submitter_id": sa.Column("submitter_id", sa.String(length=36), nullable=True),
    "assigned_team": sa.Column("assigned_team", sa.String(length=120), nullable=True),
    "assigned_team_id": sa.Column("assigned_team_id", sa.String(length=36), nullable=True),
    "assignee_id": sa.Column("assignee_id", sa.String(length=36), nullable=True),
    "claimed_by": sa.Column("claimed_by", sa.String(length=60), nullable=True),
    "claimed_at": sa.Column("claimed_at", sa.String(length=64), nullable=True),
    "summary": sa.Column("summary", sa.Text(), nullable=True),
    "affected_service": sa.Column(
        "affected_service", sa.String(length=160), nullable=True
    ),
    "priority": sa.Column("priority", sa.String(length=10), nullable=True),
    "report_title": sa.Column("report_title", sa.String(length=240), nullable=True),
    "resolution_summary": sa.Column("resolution_summary", sa.Text(), nullable=True),
    "root_cause": sa.Column("root_cause", sa.Text(), nullable=True),
    "fix_action": sa.Column("fix_action", sa.Text(), nullable=True),
    "verification": sa.Column("verification", sa.Text(), nullable=True),
    "assessed_priority": sa.Column("assessed_priority", sa.String(length=10), nullable=True),
    "assessed_priority_reason": sa.Column(
        "assessed_priority_reason", sa.Text(), nullable=True
    ),
    "response_due_at": sa.Column("response_due_at", sa.String(length=64), nullable=True),
    "resolution_due_at": sa.Column("resolution_due_at", sa.String(length=64), nullable=True),
    "sla_deadline": sa.Column("sla_deadline", sa.String(length=64), nullable=True),
    "first_responded_at": sa.Column("first_responded_at", sa.String(length=64), nullable=True),
    "resolved_at": sa.Column("resolved_at", sa.String(length=64), nullable=True),
    "closed_at": sa.Column("closed_at", sa.String(length=64), nullable=True),
    "latest_run_id": sa.Column("latest_run_id", sa.String(length=64), nullable=True),
    "version": sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
}

RUNS_TABLE_SQL = """
CREATE TABLE runs (
    run_id TEXT PRIMARY KEY,
    ticket_id TEXT NOT NULL REFERENCES tickets(ticket_id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK (status IN ('completed', 'failed', 'cancelled')),
    data_mode TEXT NOT NULL CHECK (data_mode IN ('mock', 'demo', 'real')),
    route_mode TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT NOT NULL,
    response_json TEXT,
    error_json TEXT,
    agent_trace_json TEXT NOT NULL,
    supervisor_decisions_json TEXT NOT NULL
)
"""


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    had_legacy_tickets = inspector.has_table("tickets")

    if had_legacy_tickets:
        existing = {column["name"] for column in inspector.get_columns("tickets")}
        for name, column in LEGACY_TICKET_COLUMNS.items():
            if name not in existing:
                op.add_column("tickets", column)

    Base.metadata.create_all(bind=bind, checkfirst=True)
    if bind.dialect.name == "sqlite":
        _migrate_legacy_runs(bind)
        _migrate_legacy_auxiliary_tables(bind)


def _migrate_legacy_runs(bind: sa.Connection) -> None:
    inspector = sa.inspect(bind)
    if not inspector.has_table("runs"):
        return
    columns = {column["name"] for column in inspector.get_columns("runs")}
    table_sql = bind.execute(
        sa.text("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'runs'")
    ).scalar_one()
    if (
        "error_json" in columns
        and "'failed'" in table_sql
        and "'cancelled'" in table_sql
        and "RESPONSE_JSON TEXT NOT NULL" not in table_sql.upper()
    ):
        return

    bind.exec_driver_sql("PRAGMA foreign_keys = OFF")
    bind.exec_driver_sql("PRAGMA legacy_alter_table = ON")
    bind.exec_driver_sql("ALTER TABLE runs RENAME TO runs_old")
    bind.exec_driver_sql(RUNS_TABLE_SQL)
    bind.exec_driver_sql(
        """
        INSERT INTO runs (
            run_id, ticket_id, status, data_mode, route_mode, started_at,
            completed_at, response_json, error_json, agent_trace_json,
            supervisor_decisions_json
        )
        SELECT run_id, ticket_id, status, data_mode, route_mode, started_at,
               completed_at, response_json, NULL, agent_trace_json,
               supervisor_decisions_json
        FROM runs_old
        """
    )
    bind.exec_driver_sql("DROP TABLE runs_old")
    bind.exec_driver_sql("PRAGMA foreign_keys = ON")


def _migrate_legacy_auxiliary_tables(bind: sa.Connection) -> None:
    inspector = sa.inspect(bind)
    if inspector.has_table("agent_runs"):
        columns = {column["name"] for column in inspector.get_columns("agent_runs")}
        if "react_steps_json" not in columns:
            op.add_column(
                "agent_runs",
                sa.Column(
                    "react_steps_json", sa.Text(), nullable=False, server_default="[]"
                ),
            )
    if inspector.has_table("case_library"):
        columns = {column["name"] for column in inspector.get_columns("case_library")}
        additions = {
            "data_mode": sa.Column(
                "data_mode", sa.String(length=10), nullable=False, server_default="mock"
            ),
            "confirmed_root_cause": sa.Column(
                "confirmed_root_cause", sa.Text(), nullable=False, server_default=""
            ),
            "resolution": sa.Column(
                "resolution", sa.Text(), nullable=False, server_default=""
            ),
        }
        for name, column in additions.items():
            if name not in columns:
                op.add_column("case_library", column)


def downgrade() -> None:
    # Keep tickets because it can predate Alembic and may contain user data.
    for table_name in (
        "ai_runs",
        "ticket_comments",
        "ticket_events",
        "sla_policies",
        "users",
        "teams",
    ):
        op.execute(sa.text(f"DROP TABLE IF EXISTS {table_name}"))
