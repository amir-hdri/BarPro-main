"""Add performance indexes for common queries.

Revision ID: 006_add_performance_indexes
Revises: 005_fix_constraint_conflicts
Create Date: 2025-05-01 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = '006_add_performance_indexes'
down_revision = '005_fix_constraint_conflicts'
branch_labels = None
depends_on = None


def upgrade():
    """Add composite indexes for common query patterns."""
    
    # WaybillTask: Common query pattern (status + created_at for queue processing)
    op.create_index(
        'idx_waybilltask_status_created',
        'waybilltask',
        ['status', 'created_at'],
        unique=False
    )
    
    # WaybillTask: Worker assignment queries
    op.create_index(
        'idx_waybilltask_worker_status',
        'waybilltask',
        ['worker_id', 'status'],
        unique=False
    )
    
    # WaybillTask: Retry logic queries
    op.create_index(
        'idx_waybilltask_retryable_attempt',
        'waybilltask',
        ['retryable', 'attempt_count'],
        unique=False
    )
    
    # WaybillJob (multitenant): Client-specific queries
    op.create_index(
        'idx_waybilljob_client_status',
        'waybill_jobs',
        ['client_id', 'status'],
        unique=False,
        postgresql_where=sa.text("status IN ('pending', 'queued', 'in_progress')")
    )
    
    # WaybillJob: Driver assignment queries
    op.create_index(
        'idx_waybilljob_driver_status',
        'waybill_jobs',
        ['driver_id', 'status'],
        unique=False
    )
    
    # WaybillJob: Time-based queries for monitoring
    op.create_index(
        'idx_waybilljob_created_status',
        'waybill_jobs',
        ['created_at', 'status'],
        unique=False
    )
    
    # DomainEvent: Event log queries by client and time
    op.create_index(
        'idx_domainevent_client_timestamp',
        'domain_events',
        ['client_id', 'created_at'],
        unique=False
    )
    
    # DomainEvent: Event type filtering
    op.create_index(
        'idx_domainevent_event_type',
        'domain_events',
        ['event_type'],
        unique=False
    )
    
    # DriverRuntimeState: Active driver queries
    op.create_index(
        'idx_driverruntimestate_state',
        'driver_runtime_states',
        ['state'],
        unique=False
    )


def downgrade():
    """Remove performance indexes."""
    op.drop_index('idx_waybilltask_status_created', table_name='waybilltask')
    op.drop_index('idx_waybilltask_worker_status', table_name='waybilltask')
    op.drop_index('idx_waybilltask_retryable_attempt', table_name='waybilltask')
    op.drop_index('idx_waybilljob_client_status', table_name='waybill_jobs')
    op.drop_index('idx_waybilljob_driver_status', table_name='waybill_jobs')
    op.drop_index('idx_waybilljob_created_status', table_name='waybill_jobs')
    op.drop_index('idx_domainevent_client_timestamp', table_name='domain_events')
    op.drop_index('idx_domainevent_event_type', table_name='domain_events')
    op.drop_index('idx_driverruntimestate_state', table_name='driver_runtime_states')
