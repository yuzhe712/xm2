"""P4 attachment and notification reliability.

Revision ID: 20260728_0005
Revises: 20260728_0004
Create Date: 2026-07-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260728_0005"
down_revision: str | None = "20260728_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("attachments"):
        op.create_table(
            "attachments",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("ticket_id", sa.String(length=64), nullable=False),
            sa.Column("uploader_id", sa.String(length=36), nullable=False),
            sa.Column("original_name", sa.String(length=255), nullable=False),
            sa.Column("storage_key", sa.String(length=80), nullable=False),
            sa.Column("content_type", sa.String(length=120), nullable=False),
            sa.Column("size_bytes", sa.Integer(), nullable=False),
            sa.Column("sha256", sa.String(length=64), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["ticket_id"], ["tickets.ticket_id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["uploader_id"], ["users.id"], ondelete="RESTRICT"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("storage_key"),
        )
        op.create_index(op.f("ix_attachments_ticket_id"), "attachments", ["ticket_id"])
    if not sa.inspect(bind).has_table("notification_deliveries"):
        op.create_table(
            "notification_deliveries",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("ticket_id", sa.String(length=64), nullable=False),
            sa.Column("channel", sa.String(length=30), nullable=False),
            sa.Column("target", sa.String(length=20), nullable=False),
            sa.Column("event_type", sa.String(length=60), nullable=False),
            sa.Column("payload_json", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("attempts", sa.Integer(), nullable=False),
            sa.Column("celery_task_id", sa.String(length=80), nullable=True),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint(
                "status IN ('queued', 'sending', 'sent', 'failed', 'skipped')",
                name=op.f("ck_notification_deliveries_status_values"),
            ),
            sa.CheckConstraint(
                "target IN ('operator', 'employee')",
                name=op.f("ck_notification_deliveries_target_values"),
            ),
            sa.ForeignKeyConstraint(["ticket_id"], ["tickets.ticket_id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            op.f("ix_notification_deliveries_status"),
            "notification_deliveries",
            ["status"],
        )
        op.create_index(
            op.f("ix_notification_deliveries_ticket_id"),
            "notification_deliveries",
            ["ticket_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table("notification_deliveries"):
        op.drop_index(
            op.f("ix_notification_deliveries_ticket_id"),
            table_name="notification_deliveries",
        )
        op.drop_index(
            op.f("ix_notification_deliveries_status"),
            table_name="notification_deliveries",
        )
        op.drop_table("notification_deliveries")
    if sa.inspect(bind).has_table("attachments"):
        op.drop_index(op.f("ix_attachments_ticket_id"), table_name="attachments")
        op.drop_table("attachments")
