"""Add driver-tracking fields to driver_plates (target count, round-trip, in-transport).

Revision ID: 041_driver_plate_tracking_fields
Revises: 040_add_route_template_polyline
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "041_driver_plate_tracking_fields"
down_revision: str | None = "040_add_route_template_polyline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "driver_plates",
        sa.Column("target_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "driver_plates",
        sa.Column("round_trip", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "driver_plates",
        sa.Column("in_transport", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("driver_plates", "in_transport")
    op.drop_column("driver_plates", "round_trip")
    op.drop_column("driver_plates", "target_count")
