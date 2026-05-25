"""add missing columns + fix driver_schedules schema drift

Revision ID: 010_add_missing_columns
Revises: 009_add_access_level
Create Date: 2026-05-23 00:00:00.000000

Fixes:
1. drivers.default_payload_json missing from DB (causes stats 500)
2. driver_schedules table has completely wrong schema from migration 007
   — migration 007 created (schedule_type, schedule_time, schedule_days, waybill_template, ...)
   — SQLModel expects (client_id, title, frequency, run_time, run_times_csv, payload_template_json, ...)
"""
from alembic import op
import sqlalchemy as sa

revision = '010_add_missing_columns'
down_revision = '009_add_access_level'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    # 1. Add default_payload_json to drivers table (missing column — causes stats 500)
    if 'drivers' in tables:
        columns = {col['name'] for col in inspector.get_columns('drivers')}
        if 'default_payload_json' not in columns:
            op.add_column('drivers', sa.Column('default_payload_json', sa.Text(), nullable=True))

    # 2. Rebuild driver_schedules table to match the SQLModel
    #    The current table was created by migration 007 with a completely different schema.
    rebuild_schedules = 'driver_schedules' in tables
    if rebuild_schedules:
        # Drop FK from waybill_jobs if it exists (migration 007 added it)
        # The model does NOT define a FK for schedule_id.
        if 'waybill_jobs' in tables:
            fks = inspector.get_foreign_keys('waybill_jobs')
            for fk in fks:
                if fk.get('constrained_columns') == ['schedule_id']:
                    fk_name = fk.get('name')
                    if fk_name:
                        op.drop_constraint(fk_name, 'waybill_jobs', type_='foreignkey')

        # Drop old driver_schedules table
        op.drop_table('driver_schedules')

    # Create driver_schedules with the correct model schema
    # (unconditionally — either it never existed, or we just dropped the old one)
    op.create_table(
        'driver_schedules',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('client_id', sa.Integer(), sa.ForeignKey('clients.id'), nullable=False, index=True),
        sa.Column('driver_id', sa.Integer(), sa.ForeignKey('drivers.id'), nullable=False, index=True),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('frequency', sa.String(length=20), nullable=False, server_default='daily'),
        sa.Column('run_time', sa.String(length=5), nullable=False, server_default='08:00'),
        sa.Column('run_times_csv', sa.String(length=256), nullable=True),
        sa.Column('weekdays_csv', sa.String(length=32), nullable=True),
        sa.Column('specific_dates_csv', sa.String(length=1024), nullable=True),
        sa.Column('start_date', sa.String(length=10), nullable=True),
        sa.Column('end_date', sa.String(length=10), nullable=True),
        sa.Column('timezone', sa.String(length=64), nullable=False, server_default='Asia/Tehran'),
        sa.Column('payload_template_json', sa.Text(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('last_run_at', sa.DateTime(), nullable=True),
        sa.Column('next_run_at', sa.DateTime(), nullable=True),
        sa.Column('last_run_signature', sa.String(length=64), nullable=True, index=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )
    op.create_index('idx_driver_schedules_client_id', 'driver_schedules', ['client_id'])
    op.create_index('idx_driver_schedules_driver_id', 'driver_schedules', ['driver_id'])
    op.create_index('idx_driver_schedules_is_active', 'driver_schedules', ['is_active'])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    # Drop the corrected driver_schedules
    if 'driver_schedules' in tables:
        op.drop_table('driver_schedules')

    # Recreate old driver_schedules (from migration 007)
    if 'driver_schedules' not in tables:
        op.create_table(
            'driver_schedules',
            sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
            sa.Column('driver_id', sa.Integer(), sa.ForeignKey('drivers.id'), nullable=False),
            sa.Column('schedule_type', sa.String(length=20), nullable=False),
            sa.Column('schedule_time', sa.Time(), nullable=False),
            sa.Column('schedule_days', sa.dialects.postgresql.JSONB(), nullable=True),
            sa.Column('waybill_template', sa.dialects.postgresql.JSONB(), nullable=False),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('last_run_at', sa.DateTime(), nullable=True),
            sa.Column('next_run_at', sa.DateTime(), nullable=True),
            sa.Column('total_runs', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('successful_runs', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('failed_runs', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
        )

        # Re-add FK to waybill_jobs
        if 'waybill_jobs' in tables:
            columns = {col['name'] for col in inspector.get_columns('waybill_jobs')}
            if 'schedule_id' in columns:
                op.create_foreign_key(
                    'fk_waybill_jobs_schedule', 'waybill_jobs', 'driver_schedules',
                    ['schedule_id'], ['id'],
                )

    # Drop default_payload_json from drivers
    if 'drivers' in tables:
        columns = {col['name'] for col in inspector.get_columns('drivers')}
        if 'default_payload_json' in columns:
            try:
                op.drop_column('drivers', 'default_payload_json')
            except Exception as e:
                print(f"Warning: could not drop default_payload_json: {e}")
