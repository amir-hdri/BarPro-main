"""add year and month to fuel inquiries

Revision ID: 014_add_year_month_to_fuel_inquiries
Revises: 013_add_admin_driver_schedules
Create Date: 2026-07-07 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '014_add_year_month_to_fuel_inquiries'
down_revision: str | None = '013_add_admin_driver_schedules'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    columns = [col['name'] for col in inspector.get_columns('fuel_inquiries')]

    if 'year' not in columns:
        op.add_column('fuel_inquiries', sa.Column('year', sa.Integer(), nullable=True))
    if 'month' not in columns:
        op.add_column('fuel_inquiries', sa.Column('month', sa.Integer(), nullable=True))


def downgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    columns = [col['name'] for col in inspector.get_columns('fuel_inquiries')]

    if 'month' in columns:
        op.drop_column('fuel_inquiries', 'month')
    if 'year' in columns:
        op.drop_column('fuel_inquiries', 'year')
