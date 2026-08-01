"""add error_category to fuel_inquiries

Revision ID: 027_add_fuel_inquiry_error_category
Revises: 026_error_category_backfill
Create Date: 2026-08-01 01:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "027_add_fuel_inquiry_error_category"
down_revision: str | None = "026_error_category_backfill"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add column
    op.add_column(
        "fuel_inquiries",
        sa.Column("error_category", sa.String(length=50), nullable=True)
    )
    # Create index
    op.create_index(
        "idx_fuel_inquiries_error_category",
        "fuel_inquiries",
        ["error_category"],
        unique=False
    )


def downgrade() -> None:
    # Drop index
    op.drop_index("idx_fuel_inquiries_error_category", table_name="fuel_inquiries")
    # Drop column
    op.drop_column("fuel_inquiries", "error_category")
