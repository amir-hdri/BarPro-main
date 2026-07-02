"""add admin_driver_schedules table

Revision ID: 013_add_admin_driver_schedules
Revises: 012_add_optimization_indexes
Create Date: 2026-07-02

This migration creates the admin_driver_schedules table that was defined
in app/models/admin.py but was missing from the migration chain.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "013_add_admin_driver_schedules"
down_revision: str | None = "012_add_optimization_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Check if table already exists (idempotent guard)
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "admin_driver_schedules" in inspector.get_table_names():
        return

    op.create_table(
        "admin_driver_schedules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("driver_id", sa.Integer(), nullable=False),
        # Schedule settings
        sa.Column("schedule_type", sa.String(length=20), nullable=False),  # daily, weekly, monthly, custom
        sa.Column("schedule_time", sa.String(), nullable=False),  # HH:MM format
        sa.Column("schedule_days", sa.JSON(), nullable=True),
        # Waybill template (JSON blob)
        sa.Column("waybill_template", sa.JSON(), nullable=False),
        # Status
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_run_at", sa.DateTime(), nullable=True),
        sa.Column("next_run_at", sa.DateTime(), nullable=True),
        # Stats
        sa.Column("total_runs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("successful_runs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_runs", sa.Integer(), nullable=False, server_default="0"),
        # Timestamps
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["driver_id"], ["drivers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_admin_driver_schedules_driver_id", "admin_driver_schedules", ["driver_id"])
    op.create_index("ix_admin_driver_schedules_is_active", "admin_driver_schedules", ["is_active"])
    op.create_index("ix_admin_driver_schedules_next_run_at", "admin_driver_schedules", ["next_run_at"])


def downgrade() -> None:
    op.drop_index("ix_admin_driver_schedules_next_run_at", table_name="admin_driver_schedules")
    op.drop_index("ix_admin_driver_schedules_is_active", table_name="admin_driver_schedules")
    op.drop_index("ix_admin_driver_schedules_driver_id", table_name="admin_driver_schedules")
    op.drop_table("admin_driver_schedules")
