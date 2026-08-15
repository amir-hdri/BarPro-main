"""add utcms_system_observations and waybill_jobs mutation tracking

Revision ID: 033_utcms_submission_gate_and_job_mutation
Revises: 032_worker_registry_ip_index
Create Date: 2026-08-15 12:00:00.000000

Why:
1. Adds `utcms_system_observations` table for storing UTCMS submission gate
   states (otp_free, otp_required, unknown, degraded), probe observations,
   validity windows, and sanitized evidence.
2. Adds mutation safety and tracking columns to `waybill_jobs`
   (request_digest, document_id, mutation_status, mutation_at, reconciled_at)
   to ensure durable idempotency and support reconciliation.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "033_utcms_submission_gate_and_job_mutation"
down_revision: str | None = "032_worker_registry_ip_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    # 1. Create utcms_system_observations table if not exists
    if "utcms_system_observations" not in tables:
        op.create_table(
            "utcms_system_observations",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("state", sa.String(length=32), nullable=False, server_default="unknown"),
            sa.Column("observed_at", sa.DateTime(timezone=False), nullable=False),
            sa.Column("valid_until", sa.DateTime(timezone=False), nullable=True),
            sa.Column("next_probe_at", sa.DateTime(timezone=False), nullable=True),
            sa.Column("source", sa.String(length=64), nullable=False, server_default="passive_probe"),
            sa.Column("worker_id", sa.String(length=128), nullable=True),
            sa.Column("evidence_json", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=False), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=False), nullable=False),
        )
        op.create_index("idx_utcms_obs_state", "utcms_system_observations", ["state"])
        op.create_index("idx_utcms_obs_observed_at", "utcms_system_observations", ["observed_at"])
        op.create_index("idx_utcms_obs_valid_until", "utcms_system_observations", ["valid_until"])

    # 2. Add mutation and tracking columns to waybill_jobs if not exists
    if "waybill_jobs" in tables:
        columns = {col["name"] for col in inspector.get_columns("waybill_jobs")}

        if "request_digest" not in columns:
            op.add_column("waybill_jobs", sa.Column("request_digest", sa.String(length=128), nullable=True))
            op.create_index("ix_waybill_jobs_request_digest", "waybill_jobs", ["request_digest"])

        if "document_id" not in columns:
            op.add_column("waybill_jobs", sa.Column("document_id", sa.String(length=64), nullable=True))
            op.create_index("ix_waybill_jobs_document_id", "waybill_jobs", ["document_id"])

        if "mutation_status" not in columns:
            op.add_column("waybill_jobs", sa.Column("mutation_status", sa.String(length=32), nullable=True))
            op.create_index("ix_waybill_jobs_mutation_status", "waybill_jobs", ["mutation_status"])

        if "mutation_at" not in columns:
            op.add_column("waybill_jobs", sa.Column("mutation_at", sa.DateTime(timezone=False), nullable=True))

        if "reconciled_at" not in columns:
            op.add_column("waybill_jobs", sa.Column("reconciled_at", sa.DateTime(timezone=False), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "waybill_jobs" in tables:
        columns = {col["name"] for col in inspector.get_columns("waybill_jobs")}
        indexes = {idx["name"] for idx in inspector.get_indexes("waybill_jobs")}

        if "ix_waybill_jobs_mutation_status" in indexes:
            op.drop_index("ix_waybill_jobs_mutation_status", table_name="waybill_jobs")
        if "mutation_status" in columns:
            op.drop_column("waybill_jobs", "mutation_status")

        if "ix_waybill_jobs_document_id" in indexes:
            op.drop_index("ix_waybill_jobs_document_id", table_name="waybill_jobs")
        if "document_id" in columns:
            op.drop_column("waybill_jobs", "document_id")

        if "ix_waybill_jobs_request_digest" in indexes:
            op.drop_index("ix_waybill_jobs_request_digest", table_name="waybill_jobs")
        if "request_digest" in columns:
            op.drop_column("waybill_jobs", "request_digest")

        if "mutation_at" in columns:
            op.drop_column("waybill_jobs", "mutation_at")

        if "reconciled_at" in columns:
            op.drop_column("waybill_jobs", "reconciled_at")

    if "utcms_system_observations" in tables:
        indexes = {idx["name"] for idx in inspector.get_indexes("utcms_system_observations")}
        if "idx_utcms_obs_valid_until" in indexes:
            op.drop_index("idx_utcms_obs_valid_until", table_name="utcms_system_observations")
        if "idx_utcms_obs_observed_at" in indexes:
            op.drop_index("idx_utcms_obs_observed_at", table_name="utcms_system_observations")
        if "idx_utcms_obs_state" in indexes:
            op.drop_index("idx_utcms_obs_state", table_name="utcms_system_observations")
        op.drop_table("utcms_system_observations")
