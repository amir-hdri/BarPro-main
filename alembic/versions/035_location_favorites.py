"""add location_favorites table for client saved addresses

Revision ID: 035_location_favorites
Revises: 034_night_submission_standby
Create Date: 2026-08-16 23:35:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "035_location_favorites"
down_revision: str | None = "034_night_submission_standby"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "location_favorites" not in inspector.get_table_names():
        op.create_table(
            "location_favorites",
            sa.Column("id", sa.Integer(), nullable=False, primary_key=True, autoincrement=True),
            sa.Column("client_id", sa.Integer(), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("province", sa.String(length=100), nullable=False),
            sa.Column("city", sa.String(length=100), nullable=False),
            sa.Column("district", sa.String(length=100), nullable=True),
            sa.Column("address", sa.Text(), nullable=False),
            sa.Column("latitude", sa.Float(), nullable=True),
            sa.Column("longitude", sa.Float(), nullable=True),
            sa.Column("is_origin", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("is_destination", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("idx_loc_fav_client_id", "location_favorites", ["client_id"])
        op.create_index("idx_loc_fav_title", "location_favorites", ["client_id", "title"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "location_favorites" in inspector.get_table_names():
        op.drop_table("location_favorites")
