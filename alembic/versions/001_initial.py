"""Initial migration - create bot_stats and waybill_tasks tables

Revision ID: 001_initial
Revises:
Create Date: 2026-04-05 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '001_initial'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create bot_stats table
    op.create_table(
        'botstats',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('report_date', sa.Date(), nullable=False),
        sa.Column('total_requests', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('successful_waybills', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('failed_attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('map_google', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('map_openlayers', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('map_leaflet', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('map_mapbox', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('map_unknown', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('map_none', sa.Integer(), nullable=False, server_default='0'),
        sa.UniqueConstraint('report_date', name='uq_botstats_report_date'),
    )
    op.create_index('ix_botstats_report_date', 'botstats', ['report_date'])

    # Create waybilltask table (legacy single-tenant model)
    op.create_table(
        'waybilltask',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('task_id', sa.String(), nullable=False),
        sa.Column('idempotency_key', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='queued'),
        sa.Column('payload_json', sa.Text(), nullable=False, server_default='{}'),
        sa.Column('result_json', sa.Text(), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('error_category', sa.String(), nullable=True),
        sa.Column('attempt_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('max_retries', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('retryable', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('celery_task_id', sa.String(), nullable=True),
        sa.Column('worker_id', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('task_id', name='uq_waybill_task_task_id'),
        sa.UniqueConstraint('idempotency_key', name='uq_waybill_task_idempotency_key'),
    )
    op.create_index('ix_waybilltask_task_id', 'waybilltask', ['task_id'])
    op.create_index('ix_waybilltask_idempotency_key', 'waybilltask', ['idempotency_key'])
    op.create_index('ix_waybilltask_status', 'waybilltask', ['status'])
    op.create_index('ix_waybilltask_error_category', 'waybilltask', ['error_category'])
    op.create_index('ix_waybilltask_celery_task_id', 'waybilltask', ['celery_task_id'])
    op.create_index('ix_waybilltask_worker_id', 'waybilltask', ['worker_id'])


def downgrade() -> None:
    op.drop_table('waybilltask')
    op.drop_table('botstats')
