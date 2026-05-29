"""add access_level to clients

Revision ID: 009_add_access_level
Revises: 008_add_sched_id_waybill_jobs
Create Date: 2025-05-04 22:30:00.000000

"""
import sqlalchemy as sa
import sqlmodel

from alembic import op

# revision identifiers, used by Alembic.
revision = '009_add_access_level'
down_revision = '008_add_sched_id_waybill_jobs'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # We already altered sqlite manually in case we're using sqlite,
    # but for production pg, we need this:
    try:
        op.add_column('clients', sa.Column('access_level', sqlmodel.sql.sqltypes.AutoString(length=50), server_default='standard', nullable=False))
    except Exception as e:
        print(f"Warning: {e}")

def downgrade() -> None:
    try:
        op.drop_column('clients', 'access_level')
    except Exception as e:
        print(f"Warning: {e}")
