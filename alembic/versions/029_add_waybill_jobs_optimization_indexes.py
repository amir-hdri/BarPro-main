"""Add optimization indexes for waybill_jobs table.

This migration creates the three recommended indexes from CRITICAL_RULES.md section 20
for efficient job queue queries and status-based filtering.

Revision ID: 029
Revises: 028
Create Date: 2026-08-02

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "029"
down_revision = "028"
branch_labels = None
depends_on = None


def upgrade():
    """Create optimization indexes for waybill_jobs table."""
    # Composite index for efficient job queue queries (status + priority + created_at)
    op.create_index(
        "idx_wj_status_priority_created",
        "waybill_jobs",
        [sa.column("status"), sa.column("priority").desc(), sa.column("created_at")],
        unique=False,
        postgresql_concurrently=True,
    )

    # Index for retry scheduling
    op.create_index(
        "idx_wj_status_next_retry",
        "waybill_jobs",
        [sa.column("status"), sa.column("next_retry_at")],
        unique=False,
        postgresql_concurrently=True,
    )

    # Covering index for status-only queries
    op.create_index(
        "idx_wj_status_covering",
        "waybill_jobs",
        [sa.column("status")],
        unique=False,
        postgresql_include=[sa.column("id")],
        postgresql_concurrently=True,
    )


def downgrade():
    """Drop the optimization indexes."""
    op.drop_index("idx_wj_status_covering", table_name="waybill_jobs", postgresql_concurrently=True)
    op.drop_index("idx_wj_status_next_retry", table_name="waybill_jobs", postgresql_concurrently=True)
    op.drop_index("idx_wj_status_priority_created", table_name="waybill_jobs", postgresql_concurrently=True)
