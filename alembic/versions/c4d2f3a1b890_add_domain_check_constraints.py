"""add database checks for core domain invariants

Revision ID: c4d2f3a1b890
Revises: a9ddd8888f24
Create Date: 2026-10-05 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op


revision: str = "c4d2f3a1b890"
down_revision: str | None = "a9ddd8888f24"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_users_role", "users", "role IN ('USER', 'ORGANIZER', 'ADMIN')"
    )
    op.create_check_constraint(
        "ck_events_total_tickets_positive", "events", "total_tickets > 0"
    )
    op.create_check_constraint(
        "ck_events_available_nonnegative", "events", "available_tickets >= 0"
    )
    op.create_check_constraint(
        "ck_events_available_within_total", "events", "available_tickets <= total_tickets"
    )
    op.create_check_constraint("ck_events_price_nonnegative", "events", "price >= 0")
    op.create_check_constraint("ck_events_time_order", "events", "start_time < end_time")
    op.create_check_constraint(
        "ck_events_status",
        "events",
        "status IN ('DRAFT', 'PUBLISHED', 'CANCELLED', 'COMPLETED')",
    )
    op.create_check_constraint(
        "ck_bookings_quantity", "bookings", "quantity > 0 AND quantity <= 10"
    )
    op.create_check_constraint(
        "ck_bookings_unit_price_nonnegative", "bookings", "unit_price >= 0"
    )
    op.create_check_constraint(
        "ck_bookings_status", "bookings", "status IN ('CONFIRMED', 'CANCELLED')"
    )


def downgrade() -> None:
    op.drop_constraint("ck_bookings_status", "bookings", type_="check")
    op.drop_constraint("ck_bookings_unit_price_nonnegative", "bookings", type_="check")
    op.drop_constraint("ck_bookings_quantity", "bookings", type_="check")
    op.drop_constraint("ck_events_status", "events", type_="check")
    op.drop_constraint("ck_events_time_order", "events", type_="check")
    op.drop_constraint("ck_events_price_nonnegative", "events", type_="check")
    op.drop_constraint("ck_events_available_within_total", "events", type_="check")
    op.drop_constraint("ck_events_available_nonnegative", "events", type_="check")
    op.drop_constraint("ck_events_total_tickets_positive", "events", type_="check")
    op.drop_constraint("ck_users_role", "users", type_="check")
