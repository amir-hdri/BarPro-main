"""normalize unconfirmed submission error categories

Revision ID: 028_submission_unconfirmed_category
Revises: 027_add_fuel_inquiry_error_category
Create Date: 2026-08-01 02:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "028_submission_unconfirmed_category"
down_revision: str | None = "027_add_fuel_inquiry_error_category"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE waybill_jobs
        SET error_category = 'submission_unconfirmed'
        WHERE error_category IN ('submission_unknown', 'SUBMISSION_UNCONFIRMED')
           OR (
               error_category = 'UNKNOWN_AUTOMATION_ERROR'
               AND status IN ('failed', 'needs_review')
               AND (
                   terminal_reason IN ('submission_unknown', 'submission_unconfirmed')
                   OR last_error ILIKE '%reconciliation%'
                   OR last_error ILIKE '%tracking code%'
                   OR result_json ->> 'error_category' IN ('submission_unknown', 'submission_unconfirmed')
                   OR result_json ->> 'reason' IN ('submission_unknown', 'submission_unconfirmed')
               )
           );
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE waybill_jobs
        SET error_category = 'UNKNOWN_AUTOMATION_ERROR'
        WHERE error_category = 'submission_unconfirmed';
        """
    )
