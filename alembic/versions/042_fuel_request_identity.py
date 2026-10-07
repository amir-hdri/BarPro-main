"""Preserve fuel request identity and execution timestamps without historical guesses.

Revision ID: 042_fuel_request_identity
Revises: 041_driver_plate_tracking_fields
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "042_fuel_request_identity"
down_revision: str | None = "041_driver_plate_tracking_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Current profile values and updated_at cannot prove historical identity or
    # execution timing. Leave old rows NULL instead of fabricating a backfill.
    op.add_column("fuel_inquiries", sa.Column("plate_number_snapshot", sa.String(50), nullable=True))
    op.add_column("fuel_inquiries", sa.Column("driver_name_snapshot", sa.String(255), nullable=True))
    op.add_column("fuel_inquiries", sa.Column("started_at", sa.DateTime(timezone=False), nullable=True))
    op.add_column("fuel_inquiries", sa.Column("finished_at", sa.DateTime(timezone=False), nullable=True))


def downgrade() -> None:
    for name in ("finished_at", "started_at", "driver_name_snapshot", "plate_number_snapshot"):
        op.drop_column("fuel_inquiries", name)
