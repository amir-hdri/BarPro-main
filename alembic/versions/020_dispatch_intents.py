"""create dispatch_intents table

Revision ID: 020_dispatch_intents
Revises: 019_json_text_to_jsonb
Create Date: 2026-07-31 09:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "020_dispatch_intents"
down_revision: str | None = "019_json_text_to_jsonb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    tables = inspector.get_table_names()

    if "dispatch_intents" not in tables:
        op.create_table(
            "dispatch_intents",
            sa.Column("id", sa.Integer(), nullable=False, primary_key=True),
            sa.Column("intent_id", sa.String(length=64), nullable=False),
            sa.Column("client_id", sa.Integer(), nullable=False),
            sa.Column("job_id", sa.String(length=100), nullable=False),
            sa.Column("attempt_no", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("operation", sa.String(length=32), nullable=False),
            sa.Column("fencing_token", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
            sa.Column("created_at", sa.DateTime(timezone=False), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=False), nullable=False),
            sa.ForeignKeyConstraint(["client_id"], ["clients.id"]),
            sa.ForeignKeyConstraint(["job_id"], ["waybill_jobs.job_id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "uq_dispatch_intents_intent_id",
            "dispatch_intents",
            ["intent_id"],
            unique=True,
        )
        op.create_index(
            "idx_dispatch_intents_queue_pending",
            "dispatch_intents",
            ["status", "created_at"],
            unique=False,
        )


def downgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    tables = inspector.get_table_names()

    if "dispatch_intents" in tables:
        op.drop_index("idx_dispatch_intents_queue_pending", table_name="dispatch_intents")
        op.drop_index("uq_dispatch_intents_intent_id", table_name="dispatch_intents")
        op.drop_table("dispatch_intents")
