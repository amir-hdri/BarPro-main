"""add ip_index to worker_registry for dead-worker routing filter

Revision ID: 032_worker_registry_ip_index
Revises: 031
Create Date: 2026-08-10 10:00:00.000000

Why:
The circuit-breaker router (get_next_ip_index*) must be able to tell which
queue suffix (IP index) belongs to which worker so it can stop routing to
queues whose worker is dead. This migration adds the nullable ``ip_index``
column and backfills it from existing rows using the same resolution
precedence as worker_lifecycle.resolve_ip_index:
  1. ``WORKER_ID`` when numeric (compose files set it to "1"/"2"/"3")
  2. trailing numeric suffix of ``hostname`` (e.g. worker-node-2)
Rows that cannot be resolved stay NULL — the router treats them as
unattributed and never removes an index from the pool on their behalf.
"""
from collections.abc import Sequence
import re

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "032_worker_registry_ip_index"
down_revision: str | None = "031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Same pattern as worker_lifecycle.resolve_ip_index
_IP_INDEX_RE = re.compile(r"(?:^|[-_])(\d+)$")


def _backfill_ip_index() -> None:
    """Fill ip_index from worker_id (numeric) or hostname suffix, when NULL."""
    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, worker_id, hostname FROM worker_registry WHERE ip_index IS NULL")
    ).fetchall()

    for row_id, worker_id, hostname in rows:
        value: int | None = None
        for candidate in (worker_id, hostname):
            match = _IP_INDEX_RE.search(str(candidate or "").strip())
            if match:
                parsed = int(match.group(1))
                if 1 <= parsed <= 999:
                    value = parsed
                    break
        if value is not None:
            bind.execute(
                sa.text("UPDATE worker_registry SET ip_index = :v WHERE id = :id"),
                {"v": value, "id": row_id},
            )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "worker_registry" not in tables:
        return

    columns = {col["name"] for col in inspector.get_columns("worker_registry")}
    if "ip_index" not in columns:
        op.add_column("worker_registry", sa.Column("ip_index", sa.Integer(), nullable=True))

    indexes = {idx["name"] for idx in inspector.get_indexes("worker_registry")}
    if "ix_worker_registry_ip_index" not in indexes:
        op.create_index("ix_worker_registry_ip_index", "worker_registry", ["ip_index"])

    _backfill_ip_index()


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "worker_registry" not in tables:
        return

    indexes = {idx["name"] for idx in inspector.get_indexes("worker_registry")}
    if "ix_worker_registry_ip_index" in indexes:
        op.drop_index("ix_worker_registry_ip_index", table_name="worker_registry")

    columns = {col["name"] for col in inspector.get_columns("worker_registry")}
    if "ip_index" in columns:
        op.drop_column("worker_registry", "ip_index")
