"""Add performance indexes for waybill_jobs queries.

Optimization:
- idx_wj_status_priority_created: covers scheduler's main query (filter by status, order by priority DESC, created_at ASC)
- idx_wj_status_next_retry: covers retry polling (WHERE status = 'waiting_retry' AND next_retry_at <= now())
- idx_wj_status_covering: covering index for queue_snapshot queries (SELECT COUNT)

Revision ID: 012_add_optimization_indexes
Revises: 5b6c7d8e9f0a_add_fuel_inquiries
Create Date: 2026-06-30
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "012_add_optimization_indexes"
down_revision: str | None = "5b6c7d8e9f0a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute('SET statement_timeout = 0')
    op.execute('COMMIT')
    op.execute(
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_wj_status_priority_created
        ON waybill_jobs (status, priority DESC, created_at ASC)
        """
    )
    op.execute(
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_wj_status_next_retry
        ON waybill_jobs (status, next_retry_at)
        """
    )
    op.execute(
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_wj_status_covering
        ON waybill_jobs (status) INCLUDE (id)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_wj_status_priority_created")
    op.execute("DROP INDEX IF EXISTS idx_wj_status_next_retry")
    op.execute("DROP INDEX IF EXISTS idx_wj_status_covering")
