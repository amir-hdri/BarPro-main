"""create executions table

Revision ID: 022_executions
Revises: 021_worker_registry
Create Date: 2026-07-31 09:20:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "022_executions"
down_revision: str | None = "021_worker_registry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    tables = inspector.get_table_names()

    if "executions" not in tables:
        op.create_table(
            "executions",
            sa.Column("id", sa.Integer(), nullable=False, primary_key=True),
            sa.Column("execution_id", sa.String(length=64), nullable=False),
            sa.Column("intent_id", sa.String(length=64), nullable=False),
            sa.Column("job_id", sa.String(length=100), nullable=False),
            sa.Column("attempt_no", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("operation", sa.String(length=32), nullable=False),
            sa.Column("worker_id", sa.String(length=128), nullable=False),
            sa.Column("fencing_token", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("lease_expires_at", sa.DateTime(timezone=False), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="running"),
            sa.Column("result_json", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=False), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=False), nullable=False),
            sa.ForeignKeyConstraint(["job_id"], ["waybill_jobs.job_id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "uq_executions_execution_id",
            "executions",
            ["execution_id"],
            unique=True,
        )
        op.create_index(
            "idx_executions_orphaned",
            "executions",
            ["status", "lease_expires_at"],
            unique=False,
        )


def downgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    tables = inspector.get_table_names()

    if "executions" in tables:
        op.drop_index("idx_executions_orphaned", table_name="executions")
        op.drop_index("uq_executions_execution_id", table_name="executions")
        op.drop_table("executions")
