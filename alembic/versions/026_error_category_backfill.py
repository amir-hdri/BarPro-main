"""backfill error_category in waybill_jobs table

Revision ID: 026_error_category_backfill
Revises: 025_auth_lock_coherency
Create Date: 2026-07-31 05:00:00.000000

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "026_error_category_backfill"
down_revision: str | None = "025_auth_lock_coherency"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Perform update queries to map old legacy string error categories to the new ErrorCategory values
    op.execute(
        """
        UPDATE waybill_jobs
        SET error_category = 'AUTH_FAILURE'
        WHERE error_category IN ('login_failed', 'invalid_driver', 'driver_key_mismatch', 'utcms_login_error');
        """
    )
    op.execute(
        """
        UPDATE waybill_jobs
        SET error_category = 'USER_DATA_ERROR'
        WHERE error_category IN ('incomplete_data');
        """
    )
    op.execute(
        """
        UPDATE waybill_jobs
        SET error_category = 'TARGET_SITE_TIMEOUT'
        WHERE error_category IN ('system_error', 'destination_error');
        """
    )
    op.execute(
        """
        UPDATE waybill_jobs
        SET error_category = 'CAPTCHA_EXHAUSTION'
        WHERE error_category IN ('captcha_failed');
        """
    )
    op.execute(
        """
        UPDATE waybill_jobs
        SET error_category = 'UNKNOWN_AUTOMATION_ERROR'
        WHERE error_category IN ('unknown', 'submission_unknown', 'submission_unconfirmed');
        """
    )


def downgrade() -> None:
    # Downgrade mapping (approximate fallback map)
    op.execute(
        """
        UPDATE waybill_jobs
        SET error_category = 'invalid_driver'
        WHERE error_category = 'AUTH_FAILURE';
        """
    )
    op.execute(
        """
        UPDATE waybill_jobs
        SET error_category = 'incomplete_data'
        WHERE error_category = 'USER_DATA_ERROR';
        """
    )
    op.execute(
        """
        UPDATE waybill_jobs
        SET error_category = 'system_error'
        WHERE error_category = 'TARGET_SITE_TIMEOUT';
        """
    )
    op.execute(
        """
        UPDATE waybill_jobs
        SET error_category = 'captcha_failed'
        WHERE error_category = 'CAPTCHA_EXHAUSTION';
        """
    )
    op.execute(
        """
        UPDATE waybill_jobs
        SET error_category = 'unknown'
        WHERE error_category IN ('UNKNOWN_AUTOMATION_ERROR', 'SELECTOR_CHANGED', 'BOT_DETECTED', 'TRANSIENT_INFRA_ERROR', 'WORKER_RESOURCE_ERROR');
        """
    )
