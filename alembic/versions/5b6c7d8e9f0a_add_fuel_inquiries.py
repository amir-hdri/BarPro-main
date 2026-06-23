"""add fuel inquiries table

Revision ID: 5b6c7d8e9f0a
Revises: 4a5b6c7d8e9f
Create Date: 2026-06-18 12:00:00.000000

"""
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '5b6c7d8e9f0a'
down_revision: str | None = '4a5b6c7d8e9f'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'fuel_inquiries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('client_id', sa.Integer(), nullable=False),
        sa.Column('driver_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=20), server_default='pending', nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('quota_data_json', sa.Text(), nullable=True),
        sa.Column('screenshot_url', sa.Text(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['driver_id'], ['drivers.id'], ondelete='CASCADE'),
    )
    op.create_index('idx_fuel_inquiries_client_id', 'fuel_inquiries', ['client_id'])
    op.create_index('idx_fuel_inquiries_driver_id', 'fuel_inquiries', ['driver_id'])
    op.create_index('idx_fuel_inquiries_status', 'fuel_inquiries', ['status'])


def downgrade() -> None:
    op.drop_index('idx_fuel_inquiries_status', table_name='fuel_inquiries')
    op.drop_index('idx_fuel_inquiries_driver_id', table_name='fuel_inquiries')
    op.drop_index('idx_fuel_inquiries_client_id', table_name='fuel_inquiries')
    op.drop_table('fuel_inquiries')
