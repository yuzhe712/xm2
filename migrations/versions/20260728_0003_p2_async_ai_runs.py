"""P2 persistent asynchronous AI task fields.

Revision ID: 20260728_0003
Revises: 20260728_0002
Create Date: 2026-07-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260728_0003"
down_revision: str | None = "20260728_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("ai_runs")}
    additions = {
        "celery_task_id": sa.Column("celery_task_id", sa.String(80), nullable=True),
        "stage": sa.Column(
            "stage", sa.String(40), nullable=False, server_default="queued"
        ),
        "progress": sa.Column(
            "progress", sa.Integer(), nullable=False, server_default="0"
        ),
        "evidence_json": sa.Column("evidence_json", sa.JSON(), nullable=True),
        "confidence": sa.Column("confidence", sa.Float(), nullable=True),
        "duration_ms": sa.Column("duration_ms", sa.Integer(), nullable=True),
        "decision": sa.Column("decision", sa.String(20), nullable=True),
        "decision_note": sa.Column("decision_note", sa.Text(), nullable=True),
        "modified_result_json": sa.Column("modified_result_json", sa.JSON(), nullable=True),
        "decided_by": sa.Column("decided_by", sa.String(36), nullable=True),
        "decided_at": sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        "heartbeat_at": sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        "updated_at": sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    }
    for name, column in additions.items():
        if name not in columns:
            op.add_column("ai_runs", column)
    bind = op.get_bind()
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("ai_runs")}
    if "ix_ai_runs_celery_task_id" not in indexes:
        op.create_index("ix_ai_runs_celery_task_id", "ai_runs", ["celery_task_id"])


def downgrade() -> None:
    bind = op.get_bind()
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("ai_runs")}
    if "ix_ai_runs_celery_task_id" in indexes:
        op.drop_index("ix_ai_runs_celery_task_id", table_name="ai_runs")
    columns = {column["name"] for column in sa.inspect(bind).get_columns("ai_runs")}
    for name in (
        "updated_at",
        "heartbeat_at",
        "decided_at",
        "decided_by",
        "modified_result_json",
        "decision_note",
        "decision",
        "duration_ms",
        "confidence",
        "evidence_json",
        "progress",
        "stage",
        "celery_task_id",
    ):
        if name in columns:
            op.drop_column("ai_runs", name)
