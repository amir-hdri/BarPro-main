"""add schedule_id and scheduled_by to waybill_jobs

Revision ID: 008_add_sched_id_waybill_jobs
Revises: 007_add_multi_level_system
Create Date: 2025-05-02 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '008_add_sched_id_waybill_jobs'
down_revision = '007_add_multi_level_system'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # `schedule_id` and `scheduled_by` along with FK and `scheduled_by` index
    # were already added in 007_add_multi_level_system.
    # This migration now only adds the missing index for `schedule_id`.
    op.create_index('idx_waybill_jobs_schedule_id', 'waybill_jobs', ['schedule_id'])


def downgrade() -> None:
    op.drop_index('idx_waybill_jobs_schedule_id', 'waybill_jobs')
