"""Add ordered route-chain scheduling flag to waybill batches.

Revision ID: 039_add_route_chain_scheduling
Revises: 038_add_multiroute_batch_distance
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "039_add_route_chain_scheduling"
down_revision: Union[str, None] = "038_add_multiroute_batch_distance"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "waybill_batch",
        sa.Column("route_chain", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("waybill_batch", "route_chain")
