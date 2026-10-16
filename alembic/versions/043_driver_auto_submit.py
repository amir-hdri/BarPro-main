"""Per-driver autonomous submission switch (default ON = current behavior).

Revision ID: 043_driver_auto_submit
Revises: 042_fuel_request_identity
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "043_driver_auto_submit"
down_revision: str | None = "042_fuel_request_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # server_default=True keeps every existing driver exactly as today:
    # autonomous submission stays enabled unless an operator flips it off.
    op.add_column(
        "drivers",
        sa.Column("auto_submit_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("drivers", "auto_submit_enabled")
