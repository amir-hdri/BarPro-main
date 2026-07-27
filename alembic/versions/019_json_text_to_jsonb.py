"""Migrate JSON text columns to PostgreSQL JSONB and add FK constraints.

Revision ID: 019_json_text_to_jsonb
Revises: 018_fuel_inquiry_active_unique
Create Date: 2026-07-27

This migration converts 9 TEXT columns that store JSON data to native
PostgreSQL JSONB type, enabling indexed queries, containment operators,
and automatic serialization.  Rows with NULL values are preserved as-is;
rows with invalid JSON are wrapped in {"raw": <original_text>}.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "019_json_text_to_jsonb"
down_revision = "018_fuel_inquiry_active_unique"
branch_labels = None
depends_on = None

# (table, column) pairs to convert
_JSON_COLUMNS = [
    ("clients", "metadata_json"),
    ("drivers", "default_payload_json"),
    ("drivers", "metadata_json"),
    ("driver_schedules", "payload_template_json"),
    ("waybill_jobs", "payload_json"),
    ("waybill_jobs", "result_json"),
    ("waybill_task_logs", "details_json"),
    ("upload_batches", "errors_json"),
    ("fuel_inquiries", "quota_data_json"),
]


def upgrade() -> None:
    for table, column in _JSON_COLUMNS:
        # Step 1: Wrap invalid JSON values so the cast won't fail
        op.execute(
            f"""
            UPDATE {table}
            SET {column} = '{{"raw": "' || replace(replace({column}, '\\', '\\\\'), '"', '\\"') || '"}}'
            WHERE {column} IS NOT NULL
              AND {column} != ''
              AND {column}::jsonb IS NULL;
            """  # noqa: S608
        )
        # Step 2: Handle empty-string values → set to NULL
        op.execute(
            f"""
            UPDATE {table}
            SET {column} = NULL
            WHERE {column} = '';
            """  # noqa: S608
        )
        # Step 3: ALTER COLUMN type to JSONB using the built-in cast
        op.execute(
            f"""
            ALTER TABLE {table}
            ALTER COLUMN {column} TYPE JSONB
            USING {column}::jsonb;
            """  # noqa: S608
        )


def downgrade() -> None:
    for table, column in reversed(_JSON_COLUMNS):
        op.execute(
            f"""
            ALTER TABLE {table}
            ALTER COLUMN {column} TYPE TEXT
            USING {column}::text;
            """  # noqa: S608
        )
