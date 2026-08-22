"""Add multi-route batch + route-template tables and distance/time columns.

Revision ID: 038_add_multiroute_batch_distance
Revises: 037_widen_status_columns
Create Date: 2026-08-22

Corrects the original roadmap (Phase 1): BarPro uses INTEGER primary keys
(not UUID), `payload_json` (not `payload`), and lowercase status values.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '038_add_multiroute_batch_distance'
down_revision: Union[str, None] = '037_widen_status_columns'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'waybill_route_template',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('client_id', sa.Integer(), sa.ForeignKey('clients.id'), nullable=False),
        sa.Column('name', sa.String(255), nullable=False, server_default=''),
        sa.Column('origin_province', sa.String(100), nullable=True),
        sa.Column('origin_city', sa.String(100), nullable=True),
        sa.Column('origin_address', sa.Text(), nullable=True),
        sa.Column('origin_lat', sa.Float(), nullable=True),
        sa.Column('origin_lng', sa.Float(), nullable=True),
        sa.Column('dest_province', sa.String(100), nullable=True),
        sa.Column('dest_city', sa.String(100), nullable=True),
        sa.Column('dest_address', sa.Text(), nullable=True),
        sa.Column('dest_lat', sa.Float(), nullable=True),
        sa.Column('dest_lng', sa.Float(), nullable=True),
        sa.Column('distance_km', sa.Float(), nullable=True),
        sa.Column('duration_min', sa.Float(), nullable=True),
        sa.Column('is_favorite', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=False), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=False), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('idx_rt_client_id', 'waybill_route_template', ['client_id'])
    op.create_index('idx_rt_client_favorite', 'waybill_route_template', ['client_id', 'is_favorite'])

    op.create_table(
        'waybill_batch',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('client_id', sa.Integer(), sa.ForeignKey('clients.id'), nullable=False),
        sa.Column('idempotency_key', sa.String(128), nullable=True),
        sa.Column('driver_id', sa.Integer(), sa.ForeignKey('drivers.id'), nullable=True),
        sa.Column('name', sa.String(255), nullable=True),
        sa.Column('route_template_ids', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('base_payload_json', sa.JSON(), nullable=True),
        sa.Column('target_count', sa.Integer(), nullable=False, server_default='15'),
        sa.Column('repeat_mode', sa.String(20), nullable=False, server_default='round_robin'),
        sa.Column('interval_minutes', sa.Integer(), nullable=False, server_default='40'),
        sa.Column('status', sa.String(20), nullable=False, server_default='active'),
        sa.Column('progress', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=False), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=False), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('idx_batch_client_driver', 'waybill_batch', ['client_id', 'driver_id'])
    op.create_index('idx_batch_status', 'waybill_batch', ['status'])
    op.create_unique_constraint('uq_waybill_batch_idempotency_key', 'waybill_batch', ['idempotency_key'])

    op.add_column('waybill_jobs', sa.Column('batch_id', sa.Integer(), nullable=True))
    op.add_column('waybill_jobs', sa.Column('route_template_id', sa.Integer(), nullable=True))
    op.add_column('waybill_jobs', sa.Column('sequence_index', sa.Integer(), nullable=True))
    op.add_column('waybill_jobs', sa.Column('distance_km', sa.Float(), nullable=True))
    op.add_column('waybill_jobs', sa.Column('duration_min', sa.Float(), nullable=True))

    op.create_foreign_key('fk_wj_batch_id', 'waybill_jobs', 'waybill_batch', ['batch_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key('fk_wj_route_template_id', 'waybill_jobs', 'waybill_route_template', ['route_template_id'], ['id'], ondelete='SET NULL')
    op.create_index('idx_wj_batch_id', 'waybill_jobs', ['batch_id'])
    op.create_index('idx_wj_route_template_id', 'waybill_jobs', ['route_template_id'])


def downgrade() -> None:
    op.drop_index('idx_wj_route_template_id', table_name='waybill_jobs')
    op.drop_index('idx_wj_batch_id', table_name='waybill_jobs')
    op.drop_constraint('fk_wj_route_template_id', 'waybill_jobs', type_='foreignkey')
    op.drop_constraint('fk_wj_batch_id', 'waybill_jobs', type_='foreignkey')
    op.drop_column('waybill_jobs', 'duration_min')
    op.drop_column('waybill_jobs', 'distance_km')
    op.drop_column('waybill_jobs', 'sequence_index')
    op.drop_column('waybill_jobs', 'route_template_id')
    op.drop_column('waybill_jobs', 'batch_id')

    op.drop_constraint('uq_waybill_batch_idempotency_key', 'waybill_batch', type_='unique')
    op.drop_index('idx_batch_status', table_name='waybill_batch')
    op.drop_index('idx_batch_client_driver', table_name='waybill_batch')
    op.drop_table('waybill_batch')

    op.drop_index('idx_rt_client_favorite', table_name='waybill_route_template')
    op.drop_index('idx_rt_client_id', table_name='waybill_route_template')
    op.drop_table('waybill_route_template')
