"""add driver plates table

Revision ID: 011_add_driver_plates
Revises: 010_add_missing_columns
Create Date: 2026-05-24 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '011_add_driver_plates'
down_revision = '010_add_missing_columns'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'driver_plates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('client_id', sa.Integer(), nullable=False),
        sa.Column('driver_id', sa.Integer(), nullable=False),
        sa.Column('plate_number', sa.String(length=20), nullable=False),
        sa.Column('vehicle_type', sa.String(length=100), nullable=True),
        sa.Column('status', sa.String(length=20), server_default='active', nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('client_id', 'plate_number', name='uq_driver_plate_client_plate'),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['driver_id'], ['drivers.id'], ondelete='CASCADE'),
    )
    op.create_index('idx_driver_plates_client_id', 'driver_plates', ['client_id'])
    op.create_index('idx_driver_plates_driver_id', 'driver_plates', ['driver_id'])
    op.create_index('idx_driver_plates_status', 'driver_plates', ['status'])


def downgrade() -> None:
    op.drop_index('idx_driver_plates_status', table_name='driver_plates')
    op.drop_index('idx_driver_plates_driver_id', table_name='driver_plates')
    op.drop_index('idx_driver_plates_client_id', table_name='driver_plates')
    op.drop_table('driver_plates')
