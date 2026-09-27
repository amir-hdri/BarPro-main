"""Add road polyline snapshot to waybill route templates (Phase 16).

Revision ID: 040_add_route_template_polyline
Revises: 039_add_route_chain_scheduling
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "040_add_route_template_polyline"
down_revision: Union[str, None] = "039_add_route_chain_scheduling"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("waybill_route_template", sa.Column("route_polyline", sa.Text(), nullable=True))
    op.add_column("waybill_route_template", sa.Column("route_source", sa.String(32), nullable=True))
    op.add_column("waybill_route_template", sa.Column("route_distance_km", sa.Float(), nullable=True))
    op.add_column("waybill_route_template", sa.Column("route_duration_s", sa.Float(), nullable=True))
    op.add_column("waybill_route_template", sa.Column("anchor_hash", sa.String(32), nullable=True))


def downgrade() -> None:
    op.drop_column("waybill_route_template", "anchor_hash")
    op.drop_column("waybill_route_template", "route_duration_s")
    op.drop_column("waybill_route_template", "route_distance_km")
    op.drop_column("waybill_route_template", "route_source")
    op.drop_column("waybill_route_template", "route_polyline")
