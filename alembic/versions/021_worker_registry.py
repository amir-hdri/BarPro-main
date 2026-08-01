"""create worker_registry table

Revision ID: 021_worker_registry
Revises: 020_dispatch_intents
Create Date: 2026-07-31 09:10:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "021_worker_registry"
down_revision: str | None = "020_dispatch_intents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    tables = inspector.get_table_names()

    if "worker_registry" not in tables:
        op.create_table(
            "worker_registry",
            sa.Column("id", sa.Integer(), nullable=False, primary_key=True),
            sa.Column("worker_id", sa.String(length=128), nullable=False),
            sa.Column("hostname", sa.String(length=256), nullable=False),
            sa.Column("capabilities_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("capacity", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
            sa.Column("last_heartbeat_at", sa.DateTime(timezone=False), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=False), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=False), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "uq_worker_registry_worker_id",
            "worker_registry",
            ["worker_id"],
            unique=True,
        )


def downgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    tables = inspector.get_table_names()

    if "worker_registry" in tables:
        op.drop_index("uq_worker_registry_worker_id", table_name="worker_registry")
        op.drop_table("worker_registry")
