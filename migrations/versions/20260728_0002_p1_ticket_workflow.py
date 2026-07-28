"""P1 human ticket workflow and default SLA policies.

Revision ID: 20260728_0002
Revises: 20260728_0001
Create Date: 2026-07-28
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "20260728_0002"
down_revision: str | None = "20260728_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

POLICIES = (
    ("00000000-0000-0000-0000-000000000001", "P1 critical", "P1", 15, 240),
    ("00000000-0000-0000-0000-000000000002", "P2 high", "P2", 30, 480),
    ("00000000-0000-0000-0000-000000000003", "P3 normal", "P3", 240, 1440),
    ("00000000-0000-0000-0000-000000000004", "P4 low", "P4", 480, 4320),
)


def upgrade() -> None:
    bind = op.get_bind()
    policy_table = sa.table(
        "sla_policies",
        sa.column("id", sa.String),
        sa.column("name", sa.String),
        sa.column("priority", sa.String),
        sa.column("response_minutes", sa.Integer),
        sa.column("resolution_minutes", sa.Integer),
        sa.column("is_active", sa.Boolean),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    now = datetime.now(UTC)
    existing = set(
        bind.execute(sa.text("SELECT priority FROM sla_policies")).scalars().all()
    )
    op.bulk_insert(
        policy_table,
        [
            {
                "id": policy_id,
                "name": name,
                "priority": priority,
                "response_minutes": response_minutes,
                "resolution_minutes": resolution_minutes,
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            }
            for policy_id, name, priority, response_minutes, resolution_minutes in POLICIES
            if priority not in existing
        ],
    )


def downgrade() -> None:
    ids = ", ".join(f"'{policy_id}'" for policy_id, *_ in POLICIES)
    op.execute(sa.text(f"DELETE FROM sla_policies WHERE id IN ({ids})"))
