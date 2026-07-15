"""fix runtime state and job client_id consistency

This migration fixes the data inconsistency where driver_runtime_states and
waybill_jobs rows have a client_id that does not match the actual client_id
of the driver.  This was caused by an earlier bug in _ensure_runtime_state /
_get_or_create_runtime_state that wrote the client_id from the *requesting*
Celery task argument rather than from the Driver row itself.

Revision ID: 017_fix_runtime_state_client_id
Revises: 016_add_optimization_indexes
Create Date: 2026-07-13 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import text

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "017_fix_runtime_state_client_id"
down_revision: str | None = "016_add_optimization_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()

    # 1. Fix driver_runtime_states: align client_id with the driver table
    connection.execute(text("""
        UPDATE driver_runtime_states drs
        SET client_id = d.client_id
        FROM drivers d
        WHERE drs.driver_id = d.id
          AND drs.client_id != d.client_id
    """))

    # 2. Fix driver_session_metadata: same alignment
    connection.execute(text("""
        UPDATE driver_session_metadata dsm
        SET client_id = d.client_id
        FROM drivers d
        WHERE dsm.driver_id = d.id
          AND dsm.client_id != d.client_id
    """))

    # 3. Fix waybill_jobs: align client_id with the driver table and reset stuck jobs
    connection.execute(text("""
        UPDATE waybill_jobs j
        SET client_id = d.client_id,
            status    = CASE
                            WHEN j.status IN ('waiting_auth', 'failed')
                            THEN 'pending'
                            ELSE j.status
                        END,
            celery_task_id = CASE
                                 WHEN j.status IN ('waiting_auth', 'failed')
                                 THEN NULL
                                 ELSE j.celery_task_id
                             END,
            last_error     = CASE
                                 WHEN j.status IN ('waiting_auth', 'failed')
                                 THEN NULL
                                 ELSE j.last_error
                             END,
            attempt_count  = CASE
                                 WHEN j.status IN ('waiting_auth', 'failed')
                                 THEN 0
                                 ELSE j.attempt_count
                             END
        FROM drivers d
        WHERE j.driver_id = d.id
          AND j.client_id != d.client_id
    """))


def downgrade() -> None:
    # This migration corrects bad data; rolling back would reintroduce the bug.
    pass
