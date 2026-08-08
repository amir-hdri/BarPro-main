"""Add submission_fingerprint to waybill_jobs

Revision ID: 031
Revises: 030
Create Date: 2026-08-08 00:00:00.000000

The worker stores a deterministic SHA-256 fingerprint derived from the waybill
payload (national code, plate, origin/destination, cargo weight, business
date) on first execution. This is an audit helper for the reconciliation
flow — the authoritative UTCMS verification remains the multi-field row
matching in the reconciliation scraper.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "031"
down_revision: str | None = "030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "waybill_jobs",
        sa.Column("submission_fingerprint", sa.String(128), nullable=True),
    )
    op.create_index(
        "ix_waybill_jobs_submission_fingerprint",
        "waybill_jobs",
        ["submission_fingerprint"],
    )


def downgrade() -> None:
    op.drop_index("ix_waybill_jobs_submission_fingerprint", table_name="waybill_jobs")
    op.drop_column("waybill_jobs", "submission_fingerprint")