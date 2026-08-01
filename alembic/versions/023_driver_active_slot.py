"""add active_execution_id to driver_runtime_states and index

Revision ID: 023_driver_active_slot
Revises: 022_executions
Create Date: 2026-07-31 10:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "023_driver_active_slot"
down_revision: str | None = "022_executions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    columns = [col["name"] for col in inspector.get_columns("driver_runtime_states")]

    if "active_execution_id" not in columns:
        op.add_column(
            "driver_runtime_states",
            sa.Column("active_execution_id", sa.String(length=64), nullable=True),
        )
        op.create_index(
            "idx_driver_active_execution_unique",
            "driver_runtime_states",
            ["active_execution_id"],
            unique=True,
            postgresql_where=sa.text("active_execution_id IS NOT NULL"),
        )


def downgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    columns = [col["name"] for col in inspector.get_columns("driver_runtime_states")]

    if "active_execution_id" in columns:
        op.drop_index("idx_driver_active_execution_unique", table_name="driver_runtime_states")
        op.drop_column("driver_runtime_states", "active_execution_id")
