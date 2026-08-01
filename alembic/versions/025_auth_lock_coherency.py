"""add auth lock columns to driver_runtime_states

Revision ID: 025_auth_lock_coherency
Revises: 019_json_text_to_jsonb
Create Date: 2026-07-31 04:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "025_auth_lock_coherency"
down_revision: str | None = "024_admin_alerts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    columns = [col["name"] for col in inspector.get_columns("driver_runtime_states")]

    if "auth_lock_owner" not in columns:
        op.add_column(
            "driver_runtime_states",
            sa.Column("auth_lock_owner", sa.String(length=128), nullable=True),
        )
        op.create_index(
            "idx_driver_runtime_states_auth_lock_owner",
            "driver_runtime_states",
            ["auth_lock_owner"],
            unique=False,
        )
    if "auth_lock_acquired_at" not in columns:
        op.add_column(
            "driver_runtime_states",
            sa.Column("auth_lock_acquired_at", sa.DateTime(timezone=False), nullable=True),
        )
    if "auth_lock_ttl_seconds" not in columns:
        op.add_column(
            "driver_runtime_states",
            sa.Column("auth_lock_ttl_seconds", sa.Integer(), nullable=True),
        )


def downgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    columns = [col["name"] for col in inspector.get_columns("driver_runtime_states")]

    if "auth_lock_ttl_seconds" in columns:
        op.drop_column("driver_runtime_states", "auth_lock_ttl_seconds")
    if "auth_lock_acquired_at" in columns:
        op.drop_column("driver_runtime_states", "auth_lock_acquired_at")
    if "auth_lock_owner" in columns:
        op.drop_index("idx_driver_runtime_states_auth_lock_owner", table_name="driver_runtime_states")
        op.drop_column("driver_runtime_states", "auth_lock_owner")
