"""create admin_alerts table with dedupe_key unique index

Revision ID: 024_admin_alerts
Revises: 026_error_category_backfill
Create Date: 2026-07-31 14:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "024_admin_alerts"
down_revision: str | None = "023_driver_active_slot"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    tables = inspector.get_table_names()

    if "admin_alerts" not in tables:
        op.create_table(
            "admin_alerts",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=True),
            sa.Column("severity", sa.String(length=20), nullable=False),
            sa.Column("category", sa.String(length=50), nullable=False),
            sa.Column("message", sa.String(length=1000), nullable=False),
            sa.Column("dedupe_key", sa.String(length=255), nullable=False),
            sa.Column("details", sa.JSON(), nullable=True),
            sa.Column("is_acknowledged", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("acknowledged_at", sa.DateTime(timezone=False), nullable=True),
            sa.Column("acknowledged_by", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=False), nullable=False),
            sa.ForeignKeyConstraint(["tenant_id"], ["clients.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "idx_admin_alerts_dedupe_key_unique",
            "admin_alerts",
            ["dedupe_key"],
            unique=True,
        )
        op.create_index(
            "idx_admin_alerts_tenant_id",
            "admin_alerts",
            ["tenant_id"],
            unique=False,
        )
        op.create_index(
            "idx_admin_alerts_severity",
            "admin_alerts",
            ["severity"],
            unique=False,
        )
        op.create_index(
            "idx_admin_alerts_is_acknowledged",
            "admin_alerts",
            ["is_acknowledged"],
            unique=False,
        )


def downgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    tables = inspector.get_table_names()

    if "admin_alerts" in tables:
        op.drop_index("idx_admin_alerts_is_acknowledged", table_name="admin_alerts")
        op.drop_index("idx_admin_alerts_severity", table_name="admin_alerts")
        op.drop_index("idx_admin_alerts_tenant_id", table_name="admin_alerts")
        op.drop_index("idx_admin_alerts_dedupe_key_unique", table_name="admin_alerts")
        op.drop_table("admin_alerts")
