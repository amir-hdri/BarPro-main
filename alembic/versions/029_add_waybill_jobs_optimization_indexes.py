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
down_revision = "028_submission_unconfirmed_category"
branch_labels = None
depends_on = None


def upgrade():
    """Create optimization indexes for waybill_jobs table."""
    # CREATE INDEX CONCURRENTLY cannot run inside a transaction block
    # Use op.execute with autocommit to run outside transaction
    op.execute("SET statement_timeout = '300s'")
    op.execute("COMMIT")

    # Composite index for efficient job queue queries (status + priority + created_at)
    op.execute(
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_wj_status_priority_created
        ON waybill_jobs (status, priority DESC, created_at ASC)
        """
    )

    # Index for retry scheduling
    op.execute(
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_wj_status_next_retry
        ON waybill_jobs (status, next_retry_at)
        """
    )

    # Covering index for status-only queries
    op.execute(
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_wj_status_covering
        ON waybill_jobs (status) INCLUDE (id)
        """
    )


def downgrade():
    """Drop the optimization indexes."""
    op.drop_index("idx_wj_status_covering", table_name="waybill_jobs", postgresql_concurrently=True)
    op.drop_index("idx_wj_status_next_retry", table_name="waybill_jobs", postgresql_concurrently=True)
    op.drop_index("idx_wj_status_priority_created", table_name="waybill_jobs", postgresql_concurrently=True)
