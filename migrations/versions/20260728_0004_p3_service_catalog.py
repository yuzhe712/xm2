"""P3 administrator-managed service catalog.

Revision ID: 20260728_0004
Revises: 20260728_0003
Create Date: 2026-07-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260728_0004"
down_revision: str | None = "20260728_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table("service_catalog"):
        return
    op.create_table(
        "service_catalog",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("service_key", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("desk_id", sa.String(length=20), nullable=False),
        sa.Column("team_id", sa.String(length=36), nullable=True),
        sa.Column("keywords_json", sa.JSON(), nullable=False),
        sa.Column("default_category", sa.String(length=80), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "desk_id IN ('ops', 'support')",
            name="ck_service_catalog_desk_id_values",
        ),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("service_key"),
    )
    op.create_index(
        op.f("ix_service_catalog_service_key"),
        "service_catalog",
        ["service_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_service_catalog_service_key"), table_name="service_catalog")
    op.drop_table("service_catalog")
