"""add multi-level system tables

Revision ID: 007_add_multi_level_system
Revises: 006_add_performance_indexes
Create Date: 2025-05-01 20:30:00.000000

"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = '007_add_multi_level_system'
down_revision = '006_add_performance_indexes'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create super_admins table
    op.create_table(
        'super_admins',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(length=50), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('hashed_password', sa.String(length=255), nullable=False),
        sa.Column('full_name', sa.String(length=255), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.Column('last_login_at', sa.TIMESTAMP(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('username'),
        sa.UniqueConstraint('email')
    )
    op.create_index('idx_super_admins_username', 'super_admins', ['username'])
    op.create_index('idx_super_admins_email', 'super_admins', ['email'])

    # 2. Create subscription_plans table
    op.create_table(
        'subscription_plans',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('name_fa', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('price_monthly', sa.Numeric(10, 2), nullable=True),
        sa.Column('price_yearly', sa.Numeric(10, 2), nullable=True),
        sa.Column('max_drivers', sa.Integer(), nullable=False),
        sa.Column('max_concurrent_tasks', sa.Integer(), nullable=False),
        sa.Column('max_daily_tasks', sa.Integer(), nullable=False),
        sa.Column('features', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('is_public', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # 3. Add new columns to clients table
    op.add_column('clients', sa.Column('username', sa.String(length=50), nullable=True))
    op.add_column('clients', sa.Column('full_name', sa.String(length=255), nullable=True))
    op.add_column('clients', sa.Column('company_name', sa.String(length=255), nullable=True))
    op.add_column('clients', sa.Column('national_code', sa.String(length=10), nullable=True))
    op.add_column('clients', sa.Column('is_active', sa.Boolean(), server_default='true', nullable=True))
    op.add_column('clients', sa.Column('subscription_plan_id', sa.Integer(), nullable=True))
    op.add_column('clients', sa.Column('subscription_start_date', sa.TIMESTAMP(), nullable=True))
    op.add_column('clients', sa.Column('subscription_end_date', sa.TIMESTAMP(), nullable=True))
    op.add_column('clients', sa.Column('created_by_admin_id', sa.Integer(), nullable=True))

    # Update existing clients with username from client_code
    op.execute("UPDATE clients SET username = client_code WHERE username IS NULL")
    op.execute("UPDATE clients SET full_name = name WHERE full_name IS NULL")

    # Make username NOT NULL after populating
    op.alter_column('clients', 'username', nullable=False)
    op.alter_column('clients', 'full_name', nullable=False)

    # Create unique constraint and indexes
    op.create_unique_constraint('uq_clients_username', 'clients', ['username'])
    op.create_index('idx_clients_username', 'clients', ['username'])
    op.create_foreign_key('fk_clients_subscription_plan', 'clients', 'subscription_plans', ['subscription_plan_id'], ['id'])
    op.create_foreign_key('fk_clients_created_by_admin', 'clients', 'super_admins', ['created_by_admin_id'], ['id'])

    # 4. Add new columns to drivers table
    op.add_column('drivers', sa.Column('vehicle_plate', sa.String(length=20), nullable=True))
    op.add_column('drivers', sa.Column('vehicle_type', sa.String(length=50), nullable=True))
    op.add_column('drivers', sa.Column('vehicle_model', sa.String(length=100), nullable=True))
    op.add_column('drivers', sa.Column('auto_schedule_enabled', sa.Boolean(), server_default='false', nullable=True))
    op.add_column('drivers', sa.Column('schedule_config', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('drivers', sa.Column('total_waybills', sa.Integer(), server_default='0', nullable=True))
    op.add_column('drivers', sa.Column('successful_waybills', sa.Integer(), server_default='0', nullable=True))
    op.add_column('drivers', sa.Column('failed_waybills', sa.Integer(), server_default='0', nullable=True))
    op.add_column('drivers', sa.Column('last_waybill_at', sa.TIMESTAMP(), nullable=True))
    op.add_column('drivers', sa.Column('last_error_message', sa.Text(), nullable=True))

    # Create indexes
    op.create_index('idx_drivers_auto_schedule', 'drivers', ['auto_schedule_enabled'],
                    postgresql_where=sa.text('auto_schedule_enabled = true'))
    op.create_index('idx_drivers_vehicle_plate', 'drivers', ['client_id', 'vehicle_plate'])

    # 5. Create driver_schedules table
    op.create_table(
        'driver_schedules',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('driver_id', sa.Integer(), nullable=False),
        sa.Column('schedule_type', sa.String(length=20), nullable=False),
        sa.Column('schedule_time', sa.Time(), nullable=False),
        sa.Column('schedule_days', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('waybill_template', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('last_run_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('next_run_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('total_runs', sa.Integer(), server_default='0', nullable=False),
        sa.Column('successful_runs', sa.Integer(), server_default='0', nullable=False),
        sa.Column('failed_runs', sa.Integer(), server_default='0', nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['driver_id'], ['drivers.id'], ondelete='CASCADE')
    )
    op.create_index('idx_schedules_driver_id', 'driver_schedules', ['driver_id'])
    op.create_index('idx_schedules_next_run', 'driver_schedules', ['next_run_at'],
                    postgresql_where=sa.text('is_active = true'))

    # 6. Add new columns to waybill_jobs table
    op.add_column('waybill_jobs', sa.Column('scheduled_by', sa.String(length=20), server_default='manual', nullable=True))
    op.add_column('waybill_jobs', sa.Column('schedule_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_waybill_jobs_schedule', 'waybill_jobs', 'driver_schedules', ['schedule_id'], ['id'])
    op.create_index('idx_waybill_jobs_scheduled_by', 'waybill_jobs', ['scheduled_by'])

    # 7. Create activity_logs table
    op.create_table(
        'activity_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_type', sa.String(length=20), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('action', sa.String(length=50), nullable=False),
        sa.Column('entity_type', sa.String(length=50), nullable=True),
        sa.Column('entity_id', sa.Integer(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('changes', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_activity_user', 'activity_logs', ['user_type', 'user_id'])
    op.create_index('idx_activity_created', 'activity_logs', ['created_at'])
    op.create_index('idx_activity_action', 'activity_logs', ['action'])

    # 8. Insert default subscription plans
    op.execute("""
        INSERT INTO subscription_plans (name, name_fa, price_monthly, price_yearly, max_drivers, max_concurrent_tasks, max_daily_tasks, features)
        VALUES 
            ('Basic', 'پایه', 500000, 5000000, 5, 1, 50, '{"support": "email", "api_access": false}'::jsonb),
            ('Pro', 'حرفه‌ای', 1500000, 15000000, 20, 5, 200, '{"support": "priority", "api_access": true}'::jsonb),
            ('Enterprise', 'سازمانی', 5000000, 50000000, 100, 20, 1000, '{"support": "24/7", "api_access": true, "custom_features": true}'::jsonb)
    """)

    # 9. Insert default super admin (password: admin123)
    op.execute("""
        INSERT INTO super_admins (username, email, hashed_password, full_name)
        VALUES ('admin', 'admin@utcms.local', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5NU7qXqKqKqKq', 'مدیر سیستم')
    """)


def downgrade() -> None:
    # Drop in reverse order
    op.drop_table('activity_logs')
    op.drop_index('idx_waybill_jobs_scheduled_by', 'waybill_jobs')
    op.drop_constraint('fk_waybill_jobs_schedule', 'waybill_jobs', type_='foreignkey')
    op.drop_column('waybill_jobs', 'schedule_id')
    op.drop_column('waybill_jobs', 'scheduled_by')

    op.drop_table('driver_schedules')

    op.drop_index('idx_drivers_vehicle_plate', 'drivers')
    op.drop_index('idx_drivers_auto_schedule', 'drivers')
    op.drop_column('drivers', 'last_error_message')
    op.drop_column('drivers', 'last_waybill_at')
    op.drop_column('drivers', 'failed_waybills')
    op.drop_column('drivers', 'successful_waybills')
    op.drop_column('drivers', 'total_waybills')
    op.drop_column('drivers', 'schedule_config')
    op.drop_column('drivers', 'auto_schedule_enabled')
    op.drop_column('drivers', 'vehicle_model')
    op.drop_column('drivers', 'vehicle_type')
    op.drop_column('drivers', 'vehicle_plate')

    op.drop_constraint('fk_clients_created_by_admin', 'clients', type_='foreignkey')
    op.drop_constraint('fk_clients_subscription_plan', 'clients', type_='foreignkey')
    op.drop_index('idx_clients_username', 'clients')
    op.drop_constraint('uq_clients_username', 'clients', type_='unique')
    op.drop_column('clients', 'created_by_admin_id')
    op.drop_column('clients', 'subscription_end_date')
    op.drop_column('clients', 'subscription_start_date')
    op.drop_column('clients', 'subscription_plan_id')
    op.drop_column('clients', 'is_active')
    op.drop_column('clients', 'national_code')
    op.drop_column('clients', 'company_name')
    op.drop_column('clients', 'full_name')
    op.drop_column('clients', 'username')

    op.drop_table('subscription_plans')
    op.drop_table('super_admins')
