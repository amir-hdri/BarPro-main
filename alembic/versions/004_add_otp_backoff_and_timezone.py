"""add otp_backoff status and timezone-aware next_retry_at

Revision ID: 004_otp_backoff_tz
Revises: 003_waybill_job_corr_id
Create Date: 2026-04-11
"""
from alembic import op
import sqlalchemy as sa


revision = "004_otp_backoff_tz"
down_revision = "003_waybill_job_corr_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    columns = {column["name"] for column in inspector.get_columns("waybill_jobs")}

    # ── next_retry_at: upgrade from timezone-naive to timezone-aware ──
    # SQLite does not support ALTER COLUMN type changes.
    # For PostgreSQL (production), ALTER COLUMN is used.
    # For SQLite (development), the column is left as-is since SQLite
    # ignores timezone info anyway and the ORM handles conversions.
    dialect = bind.dialect.name

    if "next_retry_at" in columns and dialect == "postgresql":
        op.alter_column(
            "waybill_jobs",
            "next_retry_at",
            existing_type=sa.DateTime(),
            type_=sa.DateTime(timezone=True),
            existing_nullable=True,
        )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("waybill_jobs")}

    # Revert next_retry_at back to timezone-naive (PostgreSQL only)
    if "next_retry_at" in columns and dialect == "postgresql":
        op.alter_column(
            "waybill_jobs",
            "next_retry_at",
            existing_type=sa.DateTime(timezone=True),
            type_=sa.DateTime(timezone=False),
            existing_nullable=True,
        )
