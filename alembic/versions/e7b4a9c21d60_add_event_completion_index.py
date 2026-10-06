"""add index for ordered event-completion batches

Revision ID: e7b4a9c21d60
Revises: c4d2f3a1b890
Create Date: 2026-10-06 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "e7b4a9c21d60"
down_revision: str | None = "c4d2f3a1b890"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_events_status_end_time_id",
        "events",
        ["status", "end_time", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_events_status_end_time_id", table_name="events")
