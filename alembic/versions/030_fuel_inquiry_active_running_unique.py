"""include 'running' in the active fuel inquiry unique period

Revision ID: 030
Revises: 029
Create Date: 2026-08-05 00:00:00.000000

The app-level de-duplication in ``FuelInquiryService.create_inquiry`` already
treats ``pending`` / ``processing`` / ``running`` as mutually exclusive active
states, but the partial unique index created in 018 only covered ``pending`` and
``processing``. Rebuild it to include ``running`` so the database layer enforces
the same rule and a directly-inserted ``running`` row cannot silently duplicate
an active period.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "030"
down_revision: str | None = "029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_WHERE = sa.text("status IN ('pending', 'processing')")
NEW_WHERE = sa.text("status IN ('pending', 'processing', 'running')")


def upgrade() -> None:
    # Reconcile any pre-existing duplicate active rows (pending/processing/running)
    # before redefining the constraint so production data cannot block the rebuild.
    op.execute(
        """
        UPDATE fuel_inquiries
        SET status = 'failed',
            error_message = 'duplicate_active_inquiry_reconciled'
        WHERE status IN ('pending', 'processing', 'running')
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
            WHERE status IN ('pending', 'processing', 'running')
        )
        UPDATE fuel_inquiries
        SET status = 'failed',
            error_message = 'duplicate_active_inquiry_reconciled'
        WHERE id IN (SELECT id FROM ranked WHERE duplicate_rank > 1)
        """
    )

    op.drop_index("uq_fuel_inquiries_active_period", table_name="fuel_inquiries")
    op.create_index(
        "uq_fuel_inquiries_active_period",
        "fuel_inquiries",
        ["client_id", "driver_id", "year", "month"],
        unique=True,
        postgresql_where=NEW_WHERE,
    )


def downgrade() -> None:
    op.drop_index("uq_fuel_inquiries_active_period", table_name="fuel_inquiries")
    op.create_index(
        "uq_fuel_inquiries_active_period",
        "fuel_inquiries",
        ["client_id", "driver_id", "year", "month"],
        unique=True,
        postgresql_where=OLD_WHERE,
    )
