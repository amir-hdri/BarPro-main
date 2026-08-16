"""add durable UTCMS night submission attempt counters

Revision ID: 034_night_submission_standby
Revises: 033_utcms_submission_gate_and_job_mutation
Create Date: 2026-08-16 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "034_night_submission_standby"
down_revision: str | None = "033_utcms_submission_gate_and_job_mutation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "waybill_jobs" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("waybill_jobs")}
    if "night_attempt_count" not in columns:
        op.add_column(
            "waybill_jobs",
            sa.Column("night_attempt_count", sa.Integer(), nullable=False, server_default="0"),
        )
    if "night_attempt_window" not in columns:
        op.add_column("waybill_jobs", sa.Column("night_attempt_window", sa.String(length=10), nullable=True))
        op.create_index("ix_waybill_jobs_night_attempt_window", "waybill_jobs", ["night_attempt_window"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "waybill_jobs" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("waybill_jobs")}
    indexes = {index["name"] for index in inspector.get_indexes("waybill_jobs")}
    if "ix_waybill_jobs_night_attempt_window" in indexes:
        op.drop_index("ix_waybill_jobs_night_attempt_window", table_name="waybill_jobs")
    if "night_attempt_window" in columns:
        op.drop_column("waybill_jobs", "night_attempt_window")
    if "night_attempt_count" in columns:
        op.drop_column("waybill_jobs", "night_attempt_count")
