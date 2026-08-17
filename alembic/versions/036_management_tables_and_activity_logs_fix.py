"""Add updated_at to activity_logs and create managed tables

Revision ID: 036_management_tables_and_activity_logs_fix
Revises: 035_location_favorites
Create Date: 2026-08-17 00:48:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '036_management_tables_and_activity_logs_fix'
down_revision: Union[str, None] = '035_location_favorites'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add updated_at column to activity_logs if not present
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'activity_logs' AND column_name = 'updated_at'
            ) THEN
                ALTER TABLE activity_logs ADD COLUMN updated_at TIMESTAMP NOT NULL DEFAULT now();
            END IF;
        END $$;
    """)

    # 2. Create managed_customers table
    op.execute("""
        CREATE TABLE IF NOT EXISTS managed_customers (
            id SERIAL PRIMARY KEY,
            source_system VARCHAR(255) NOT NULL DEFAULT 'local',
            external_key VARCHAR(255) NOT NULL,
            full_name VARCHAR(255) NOT NULL,
            wallet VARCHAR(255),
            driver_limit INTEGER,
            bot_running BOOLEAN,
            bot_running_barname BOOLEAN,
            auto_stop BOOLEAN,
            two_way BOOLEAN,
            remaining_duration FLOAT,
            raw_json TEXT NOT NULL DEFAULT '{}',
            synced_at TIMESTAMP NOT NULL DEFAULT now(),
            CONSTRAINT uq_managed_customer_source_external UNIQUE (source_system, external_key)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_mc_source ON managed_customers(source_system)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_mc_ext_key ON managed_customers(external_key)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_mc_full_name ON managed_customers(full_name)")

    # 3. Create managed_routes table
    op.execute("""
        CREATE TABLE IF NOT EXISTS managed_routes (
            id SERIAL PRIMARY KEY,
            source_system VARCHAR(255) NOT NULL DEFAULT 'local',
            route_key VARCHAR(255) NOT NULL,
            name VARCHAR(255),
            origin_label VARCHAR(255),
            origin_province VARCHAR(255),
            origin_city VARCHAR(255),
            origin_address TEXT,
            origin_lat FLOAT,
            origin_lng FLOAT,
            destination_label VARCHAR(255),
            destination_province VARCHAR(255),
            destination_city VARCHAR(255),
            destination_address TEXT,
            destination_lat FLOAT,
            destination_lng FLOAT,
            distance_km FLOAT,
            duration_minutes FLOAT,
            same_province BOOLEAN,
            recommended BOOLEAN,
            enabled BOOLEAN NOT NULL DEFAULT true,
            raw_json TEXT NOT NULL DEFAULT '{}',
            synced_at TIMESTAMP NOT NULL DEFAULT now(),
            CONSTRAINT uq_managed_route_source_key UNIQUE (source_system, route_key)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_mr_source ON managed_routes(source_system)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_mr_route_key ON managed_routes(route_key)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_mr_name ON managed_routes(name)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_mr_origin_prov ON managed_routes(origin_province)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_mr_origin_city ON managed_routes(origin_city)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_mr_dest_prov ON managed_routes(destination_province)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_mr_dest_city ON managed_routes(destination_city)")

    # 4. Create managed_accounts table
    op.execute("""
        CREATE TABLE IF NOT EXISTS managed_accounts (
            id SERIAL PRIMARY KEY,
            source_system VARCHAR(255) NOT NULL DEFAULT 'local',
            external_name VARCHAR(255) NOT NULL,
            bot_owner VARCHAR(255),
            title VARCHAR(255),
            phone_number VARCHAR(255),
            national_code VARCHAR(255),
            platform VARCHAR(255),
            status VARCHAR(255),
            route_key VARCHAR(255),
            otp_needed BOOLEAN,
            has_account_is_enabled BOOLEAN,
            has_driver_data BOOLEAN,
            has_truck_data BOOLEAN,
            has_valid_location BOOLEAN,
            start_shipping BOOLEAN,
            two_way BOOLEAN,
            custom_current_submit INTEGER,
            custom_target_submit INTEGER,
            time_interval INTEGER,
            last_success VARCHAR(255),
            source_details_json TEXT,
            destination_detail_json TEXT,
            mobile_info_json TEXT,
            payment_details_json TEXT,
            flags_json TEXT NOT NULL DEFAULT '{}',
            raw_json TEXT NOT NULL DEFAULT '{}',
            synced_at TIMESTAMP NOT NULL DEFAULT now(),
            CONSTRAINT uq_managed_account_source_external UNIQUE (source_system, external_name)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_ma_source ON managed_accounts(source_system)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_ma_ext_name ON managed_accounts(external_name)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_ma_bot_owner ON managed_accounts(bot_owner)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_ma_title ON managed_accounts(title)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_ma_phone ON managed_accounts(phone_number)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_ma_nat_code ON managed_accounts(national_code)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_ma_status ON managed_accounts(status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_ma_route_key ON managed_accounts(route_key)")

    # 5. Create managed_queue_items table
    op.execute("""
        CREATE TABLE IF NOT EXISTS managed_queue_items (
            id SERIAL PRIMARY KEY,
            queue_item_id VARCHAR(255) NOT NULL,
            source_system VARCHAR(255) NOT NULL DEFAULT 'local',
            external_key VARCHAR(255) NOT NULL,
            account_external_name VARCHAR(255),
            route_key VARCHAR(255),
            bot_owner VARCHAR(255),
            status VARCHAR(255) NOT NULL DEFAULT 'queued',
            operation_mode VARCHAR(255) NOT NULL DEFAULT 'safe',
            priority INTEGER NOT NULL DEFAULT 100,
            origin VARCHAR(255) NOT NULL DEFAULT 'local',
            payload_json TEXT,
            result_json TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            last_error TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now(),
            dispatched_at TIMESTAMP,
            finished_at TIMESTAMP,
            CONSTRAINT uq_managed_queue_source_external UNIQUE (source_system, external_key)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_mqi_queue_id ON managed_queue_items(queue_item_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_mqi_source ON managed_queue_items(source_system)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_mqi_ext_key ON managed_queue_items(external_key)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_mqi_acc_name ON managed_queue_items(account_external_name)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_mqi_route_key ON managed_queue_items(route_key)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_mqi_bot_owner ON managed_queue_items(bot_owner)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_mqi_status ON managed_queue_items(status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_mqi_op_mode ON managed_queue_items(operation_mode)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_mqi_priority ON managed_queue_items(priority)")

    # 6. Create managed_sync_logs table
    op.execute("""
        CREATE TABLE IF NOT EXISTS managed_sync_logs (
            id SERIAL PRIMARY KEY,
            source_system VARCHAR(255) NOT NULL DEFAULT 'local',
            sync_type VARCHAR(255) NOT NULL DEFAULT 'audit',
            status VARCHAR(255) NOT NULL DEFAULT 'completed',
            summary_json TEXT NOT NULL DEFAULT '{}',
            error_text TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_msl_source ON managed_sync_logs(source_system)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_msl_sync_type ON managed_sync_logs(sync_type)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_msl_status ON managed_sync_logs(status)")


def downgrade() -> None:
    op.drop_table('managed_sync_logs')
    op.drop_table('managed_queue_items')
    op.drop_table('managed_accounts')
    op.drop_table('managed_routes')
    op.drop_table('managed_customers')
