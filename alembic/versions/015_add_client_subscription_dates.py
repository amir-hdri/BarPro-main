"""add client subscription dates

Revision ID: 015_add_client_subscription_dates
Revises: 014_add_year_month_to_fuel_inquiries
Create Date: 2026-07-08 14:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '015_add_client_subscription_dates'
down_revision: str | None = '014_add_year_month_to_fuel_inquiries'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    columns = [col['name'] for col in inspector.get_columns('clients')]

    if 'subscription_start_date' not in columns:
        op.add_column('clients', sa.Column('subscription_start_date', sa.DateTime(timezone=False), nullable=True))
    if 'subscription_end_date' not in columns:
        op.add_column('clients', sa.Column('subscription_end_date', sa.DateTime(timezone=False), nullable=True))


def downgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    columns = [col['name'] for col in inspector.get_columns('clients')]

    if 'subscription_end_date' in columns:
        op.drop_column('clients', 'subscription_end_date')
    if 'subscription_start_date' in columns:
        op.drop_column('clients', 'subscription_start_date')
