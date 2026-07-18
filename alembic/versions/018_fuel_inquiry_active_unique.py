"""enforce one active fuel inquiry per driver and period

Revision ID: 018_fuel_inquiry_active_unique
Revises: 017_fix_runtime_state_client_id
Create Date: 2026-07-18 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "018_fuel_inquiry_active_unique"
down_revision: str | None = "017_fix_runtime_state_client_id"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Preserve the oldest active request and terminate duplicates before adding
    # the constraint so existing production data cannot block deployment.
    op.execute(
        """
        UPDATE fuel_inquiries
        SET status = 'failed',
            error_message = 'legacy_missing_period_recreate'
        WHERE status IN ('pending', 'processing')
          AND (year IS NULL OR month IS NULL)
        """
    )
    op.execute(
        """
        WITH ranked AS (
            SELECT id,
                   row_number() OVER (
                       PARTITION BY client_id, driver_id, year, month
                       ORDER BY created_at ASC, id ASC
                   ) AS duplicate_rank
            FROM fuel_inquiries
            WHERE status IN ('pending', 'processing')
        )
        UPDATE fuel_inquiries
        SET status = 'failed',
            error_message = 'duplicate_active_inquiry_reconciled'
        WHERE id IN (SELECT id FROM ranked WHERE duplicate_rank > 1)
        """
    )
    op.create_index(
        "uq_fuel_inquiries_active_period",
        "fuel_inquiries",
        ["client_id", "driver_id", "year", "month"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending', 'processing')"),
    )


def downgrade() -> None:
    op.drop_index("uq_fuel_inquiries_active_period", table_name="fuel_inquiries")
