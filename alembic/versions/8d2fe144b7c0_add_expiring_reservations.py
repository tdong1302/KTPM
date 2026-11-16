"""Add expiring reservations.

Revision ID: 8d2fe144b7c0
Revises: e7b4a9c21d60
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "8d2fe144b7c0"
down_revision: str | None = "e7b4a9c21d60"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "reservations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "event_id", sa.Integer(), sa.ForeignKey("events.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("booking_id", sa.Integer(), sa.ForeignKey("bookings.id"), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("quantity > 0 AND quantity <= 10", name="ck_reservations_quantity"),
        sa.CheckConstraint("created_at < expires_at", name="ck_reservations_time_order"),
        sa.CheckConstraint(
            "status IN ('RESERVED', 'CONFIRMED', 'EXPIRED', 'CANCELLED')",
            name="ck_reservations_status",
        ),
        sa.CheckConstraint(
            "(status = 'CONFIRMED' AND booking_id IS NOT NULL) OR "
            "(status <> 'CONFIRMED' AND booking_id IS NULL)",
            name="ck_reservations_booking_status",
        ),
    )
    op.create_index(
        "ix_reservations_status_expires_at_id", "reservations", ["status", "expires_at", "id"]
    )
    op.create_index("ix_reservations_event_id", "reservations", ["event_id"])
    op.create_index("ix_reservations_booking_id", "reservations", ["booking_id"], unique=True)


def downgrade() -> None:
    # Older application versions cannot release inventory held by active reservations.
    # Fail closed unless active holds have been reclaimed before the downgrade.
    reservations = sa.table("reservations", sa.column("status"))
    active_hold = sa.select(1).where(reservations.c.status == "RESERVED").limit(1)
    if op.get_bind().scalar(active_hold) is not None:
        raise RuntimeError("reclaim active reservations before downgrading")
    op.drop_table("reservations")
