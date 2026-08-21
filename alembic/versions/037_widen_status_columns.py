"""Widen status columns across PostgreSQL tables to VARCHAR(50)

Revision ID: 037_widen_status_columns
Revises: 036_management_tables_and_activity_logs_fix
Create Date: 2026-08-21 17:05:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '037_widen_status_columns'
down_revision: Union[str, None] = '036_management_tables_and_activity_logs_fix'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            ALTER TABLE waybill_jobs ALTER COLUMN status TYPE VARCHAR(50);
            ALTER TABLE waybill_task_logs ALTER COLUMN status TYPE VARCHAR(50);
            IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'waybill_job_submissions') THEN
                ALTER TABLE waybill_job_submissions ALTER COLUMN status TYPE VARCHAR(50);
            END IF;
            IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'drivers') THEN
                ALTER TABLE drivers ALTER COLUMN status TYPE VARCHAR(50);
                ALTER TABLE drivers ALTER COLUMN runtime_status TYPE VARCHAR(50);
            END IF;
            IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'driver_plates') THEN
                ALTER TABLE driver_plates ALTER COLUMN status TYPE VARCHAR(50);
            END IF;
            IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'clients') THEN
                ALTER TABLE clients ALTER COLUMN status TYPE VARCHAR(50);
            END IF;
            IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'fuel_inquiries') THEN
                ALTER TABLE fuel_inquiries ALTER COLUMN status TYPE VARCHAR(50);
            END IF;
            IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'upload_batches') THEN
                ALTER TABLE upload_batches ALTER COLUMN status TYPE VARCHAR(50);
            END IF;
            IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'executions') THEN
                ALTER TABLE executions ALTER COLUMN status TYPE VARCHAR(50);
            END IF;
        END $$;
    """)


def downgrade() -> None:
    pass
