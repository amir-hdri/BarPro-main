"""Fix constraint name conflicts between legacy tables.

Revision ID: 005_constraint_conflicts
Revises: 004_otp_backoff_tz
Create Date: 2026-04-23 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005_fix_constraint_conflicts"
down_revision: Union[str, None] = "004_otp_backoff_tz"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Rename legacy constraints if they still use the old names."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    if "waybill_tasks_legacy" in tables:
        constraints = {
            constraint["name"]
            for constraint in inspector.get_unique_constraints("waybill_tasks_legacy")
        }

        if "uq_waybill_task_task_id" in constraints:
            op.drop_constraint(
                "uq_waybill_task_task_id",
                "waybill_tasks_legacy",
                type_="unique",
            )
            op.create_unique_constraint(
                "uq_waybill_tasks_legacy_task_id",
                "waybill_tasks_legacy",
                ["task_id"],
            )

        if "uq_waybill_task_idempotency_key" in constraints:
            op.drop_constraint(
                "uq_waybill_task_idempotency_key",
                "waybill_tasks_legacy",
                type_="unique",
            )
            op.create_unique_constraint(
                "uq_waybill_tasks_legacy_idempotency_key",
                "waybill_tasks_legacy",
                ["idempotency_key"],
            )


def downgrade() -> None:
    """Restore the original legacy constraint names if needed."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    if "waybill_tasks_legacy" in tables:
        constraints = {
            constraint["name"]
            for constraint in inspector.get_unique_constraints("waybill_tasks_legacy")
        }

        if "uq_waybill_tasks_legacy_task_id" in constraints:
            op.drop_constraint(
                "uq_waybill_tasks_legacy_task_id",
                "waybill_tasks_legacy",
                type_="unique",
            )
            op.create_unique_constraint(
                "uq_waybill_task_task_id",
                "waybill_tasks_legacy",
                ["task_id"],
            )

        if "uq_waybill_tasks_legacy_idempotency_key" in constraints:
            op.drop_constraint(
                "uq_waybill_tasks_legacy_idempotency_key",
                "waybill_tasks_legacy",
                type_="unique",
            )
            op.create_unique_constraint(
                "uq_waybill_task_idempotency_key",
                "waybill_tasks_legacy",
                ["idempotency_key"],
            )
