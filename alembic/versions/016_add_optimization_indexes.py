"""add optimization indexes for waybill_jobs

Revision ID: 016_add_optimization_indexes
Revises: 015_add_client_sub_dates
Create Date: 2026-07-09 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '016_add_optimization_indexes'
down_revision: str | None = '015_add_client_sub_dates'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # CREATE INDEX CONCURRENTLY cannot run inside a transaction block
    # Use op.execute with autocommit to run outside transaction
    conn = op.get_bind()
    conn.execute(sa.text('COMMIT'))

    # Index for job scheduling queries: filter by status, order by priority DESC, created_at ASC
    conn.execute(sa.text(
        'CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_wj_status_priority_created '
        'ON waybill_jobs (status, priority DESC, created_at ASC)'
    ))

    # Index for stuck job cleanup: filter by status, order by next_retry_at
    conn.execute(sa.text(
        'CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_wj_status_next_retry '
        'ON waybill_jobs (status, next_retry_at)'
    ))

    # Covering index for queue depth queries (status + id)
    conn.execute(sa.text(
        'CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_wj_status_covering '
        'ON waybill_jobs (status) INCLUDE (id)'
    ))

    # Index for driver daily counter lookups
    conn.execute(sa.text(
        'CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_ddc_client_driver_business_date '
        'ON driver_daily_counters (client_id, driver_id, business_date)'
    ))

    # Index for runtime state lookups by driver
    conn.execute(sa.text(
        'CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_drs_driver_id '
        'ON driver_runtime_states (driver_id)'
    ))

    # Index for fuel inquiry queries by client + driver + status
    conn.execute(sa.text(
        'CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_fi_client_driver_status '
        'ON fuel_inquiries (client_id, driver_id, status)'
    ))

    conn.execute(sa.text('BEGIN'))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text('COMMIT'))

    conn.execute(sa.text('DROP INDEX CONCURRENTLY IF EXISTS idx_wj_status_priority_created'))
    conn.execute(sa.text('DROP INDEX CONCURRENTLY IF EXISTS idx_wj_status_next_retry'))
    conn.execute(sa.text('DROP INDEX CONCURRENTLY IF EXISTS idx_wj_status_covering'))
    conn.execute(sa.text('DROP INDEX CONCURRENTLY IF EXISTS idx_ddc_client_driver_business_date'))
    conn.execute(sa.text('DROP INDEX CONCURRENTLY IF EXISTS idx_drs_driver_id'))
    conn.execute(sa.text('DROP INDEX CONCURRENTLY IF EXISTS idx_fi_client_driver_status'))

    conn.execute(sa.text('BEGIN'))