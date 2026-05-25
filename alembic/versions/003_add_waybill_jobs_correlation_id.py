"""add correlation_id to waybill_jobs for batch tracking

Revision ID: 003_waybill_job_corr_id
Revises: 002_phase1_rpa_backend
Create Date: 2026-04-09
"""
from alembic import op
import sqlalchemy as sa


revision = "003_waybill_job_corr_id"
down_revision = "002_phase1_rpa_backend"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    columns = {column["name"] for column in inspector.get_columns("waybill_jobs")}
    indexes = {index["name"] for index in inspector.get_indexes("waybill_jobs")}

    if "correlation_id" not in columns:
        op.add_column("waybill_jobs", sa.Column("correlation_id", sa.String(length=128), nullable=True))

    if "ix_waybill_jobs_correlation_id" not in indexes:
        op.create_index("ix_waybill_jobs_correlation_id", "waybill_jobs", ["correlation_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    columns = {column["name"] for column in inspector.get_columns("waybill_jobs")}
    indexes = {index["name"] for index in inspector.get_indexes("waybill_jobs")}

    if "ix_waybill_jobs_correlation_id" in indexes:
        op.drop_index("ix_waybill_jobs_correlation_id", table_name="waybill_jobs")

    if "correlation_id" in columns:
        op.drop_column("waybill_jobs", "correlation_id")
