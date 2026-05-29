"""Phase 1 multi-tenant hybrid RPA backend schema.

Revision ID: 002_phase1_rpa_backend
Revises: 001_initial
Create Date: 2026-04-06 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "002_phase1_rpa_backend"
down_revision: str | None = "001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _columns(table_name: str) -> set[str]:
    return {column["name"] for column in _inspector().get_columns(table_name)}


def _indexes(table_name: str) -> set[str]:
    return {index["name"] for index in _inspector().get_indexes(table_name)}


def _create_clients_table() -> None:
    if _has_table("clients"):
        return

    op.create_table(
        "clients",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("client_code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("max_drivers", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("max_concurrent_tasks", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("max_daily_tasks", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("client_code", name="uq_clients_client_code"),
        sa.UniqueConstraint("email", name="uq_clients_email"),
    )
    op.create_index("ix_clients_client_code", "clients", ["client_code"])
    op.create_index("ix_clients_email", "clients", ["email"])
    op.create_index("idx_clients_status", "clients", ["status"])
    op.create_index("idx_clients_created_at", "clients", ["created_at"])


def _create_drivers_table() -> None:
    if _has_table("drivers"):
        return

    op.create_table(
        "drivers",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("client_id", sa.Integer(), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("driver_national_code", sa.String(length=10), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column("license_number", sa.String(length=50), nullable=True),
        sa.Column("utcms_username", sa.String(length=100), nullable=False),
        sa.Column("utcms_password_encrypted", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("runtime_status", sa.String(length=40), nullable=False, server_default="active"),
        sa.Column("last_auth_at", sa.DateTime(), nullable=True),
        sa.Column("last_session_expires_at", sa.DateTime(), nullable=True),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("client_id", "driver_national_code", name="uq_driver_client_national_code"),
    )
    op.create_index("ix_drivers_client_id", "drivers", ["client_id"])
    op.create_index("idx_drivers_client_id", "drivers", ["client_id"])
    op.create_index("ix_drivers_driver_national_code", "drivers", ["driver_national_code"])
    op.create_index("idx_drivers_national_code", "drivers", ["driver_national_code"])
    op.create_index("ix_drivers_status", "drivers", ["status"])
    op.create_index("idx_drivers_status", "drivers", ["status"])
    op.create_index("ix_drivers_runtime_status", "drivers", ["runtime_status"])
    op.create_index("ix_drivers_last_error_code", "drivers", ["last_error_code"])


def _ensure_driver_runtime_columns() -> None:
    if not _has_table("drivers"):
        return

    columns = _columns("drivers")
    indexes = _indexes("drivers")

    if "runtime_status" not in columns:
        op.add_column(
            "drivers",
            sa.Column("runtime_status", sa.String(length=40), nullable=False, server_default="active"),
        )
    if "last_auth_at" not in columns:
        op.add_column("drivers", sa.Column("last_auth_at", sa.DateTime(), nullable=True))
    if "last_session_expires_at" not in columns:
        op.add_column("drivers", sa.Column("last_session_expires_at", sa.DateTime(), nullable=True))
    if "last_error_code" not in columns:
        op.add_column("drivers", sa.Column("last_error_code", sa.String(length=64), nullable=True))

    if "ix_drivers_runtime_status" not in indexes:
        op.create_index("ix_drivers_runtime_status", "drivers", ["runtime_status"])
    if "ix_drivers_last_error_code" not in indexes:
        op.create_index("ix_drivers_last_error_code", "drivers", ["last_error_code"])


def _create_waybill_jobs_table() -> None:
    if _has_table("waybill_jobs"):
        return

    op.create_table(
        "waybill_jobs",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("job_id", sa.String(length=100), nullable=False),
        sa.Column("idempotency_key", sa.String(length=100), nullable=False),
        sa.Column("client_id", sa.Integer(), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("driver_id", sa.Integer(), sa.ForeignKey("drivers.id"), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("source", sa.String(length=20), nullable=False, server_default="manual"),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("result_json", sa.Text(), nullable=True),
        sa.Column("correlation_id", sa.String(length=128), nullable=True),
        sa.Column("business_date", sa.String(length=16), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("next_retry_at", sa.DateTime(), nullable=True),
        sa.Column("submit_after", sa.DateTime(), nullable=True),
        sa.Column("terminal_reason", sa.String(length=64), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("error_category", sa.String(length=50), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("retryable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("celery_task_id", sa.String(length=100), nullable=True),
        sa.Column("worker_id", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("job_id", name="uq_waybill_jobs_job_id"),
        sa.UniqueConstraint("idempotency_key", name="uq_waybill_jobs_idempotency_key"),
    )
    op.create_index("ix_waybill_jobs_job_id", "waybill_jobs", ["job_id"])
    op.create_index("ix_waybill_jobs_idempotency_key", "waybill_jobs", ["idempotency_key"])
    op.create_index("idx_waybill_jobs_client_id", "waybill_jobs", ["client_id"])
    op.create_index("idx_waybill_jobs_driver_id", "waybill_jobs", ["driver_id"])
    op.create_index("idx_waybill_jobs_status", "waybill_jobs", ["status"])
    op.create_index("idx_waybill_jobs_created_at", "waybill_jobs", ["created_at"])
    op.create_index("idx_waybill_jobs_celery_task_id", "waybill_jobs", ["celery_task_id"])
    op.create_index("ix_waybill_jobs_correlation_id", "waybill_jobs", ["correlation_id"])
    op.create_index("ix_waybill_jobs_business_date", "waybill_jobs", ["business_date"])
    op.create_index("ix_waybill_jobs_priority", "waybill_jobs", ["priority"])
    op.create_index("ix_waybill_jobs_terminal_reason", "waybill_jobs", ["terminal_reason"])


def _ensure_waybill_job_columns() -> None:
    if not _has_table("waybill_jobs"):
        return

    columns = _columns("waybill_jobs")
    indexes = _indexes("waybill_jobs")

    additions = [
        ("correlation_id", sa.Column("correlation_id", sa.String(length=128), nullable=True)),
        ("business_date", sa.Column("business_date", sa.String(length=16), nullable=True)),
        ("priority", sa.Column("priority", sa.Integer(), nullable=False, server_default="5")),
        ("next_retry_at", sa.Column("next_retry_at", sa.DateTime(), nullable=True)),
        ("submit_after", sa.Column("submit_after", sa.DateTime(), nullable=True)),
        ("terminal_reason", sa.Column("terminal_reason", sa.String(length=64), nullable=True)),
    ]
    for name, column in additions:
        if name not in columns:
            op.add_column("waybill_jobs", column)

    if "ix_waybill_jobs_correlation_id" not in indexes:
        op.create_index("ix_waybill_jobs_correlation_id", "waybill_jobs", ["correlation_id"])
    if "ix_waybill_jobs_business_date" not in indexes:
        op.create_index("ix_waybill_jobs_business_date", "waybill_jobs", ["business_date"])
    if "ix_waybill_jobs_priority" not in indexes:
        op.create_index("ix_waybill_jobs_priority", "waybill_jobs", ["priority"])
    if "ix_waybill_jobs_terminal_reason" not in indexes:
        op.create_index("ix_waybill_jobs_terminal_reason", "waybill_jobs", ["terminal_reason"])


def _create_waybill_task_logs_table() -> None:
    if _has_table("waybill_task_logs"):
        return

    op.create_table(
        "waybill_task_logs",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("job_id", sa.String(length=100), nullable=False),
        sa.Column("client_id", sa.Integer(), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("step", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("details_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("idx_waybill_task_logs_job_id", "waybill_task_logs", ["job_id"])
    op.create_index("idx_waybill_task_logs_created_at", "waybill_task_logs", ["created_at"])


def _create_upload_batches_table() -> None:
    if _has_table("upload_batches"):
        return

    op.create_table(
        "upload_batches",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("batch_id", sa.String(length=100), nullable=False),
        sa.Column("client_id", sa.Integer(), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("total_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("valid_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("invalid_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="processing"),
        sa.Column("errors_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("batch_id", name="uq_upload_batches_batch_id"),
    )
    op.create_index("ix_upload_batches_batch_id", "upload_batches", ["batch_id"])
    op.create_index("idx_upload_batches_client_id", "upload_batches", ["client_id"])
    op.create_index("idx_upload_batches_created_at", "upload_batches", ["created_at"])


def _create_table_if_missing(name: str, *columns, indexes: list[tuple[str, list[str]]] | None = None) -> None:
    if _has_table(name):
        return

    op.create_table(name, *columns)
    for index_name, fields in indexes or []:
        op.create_index(index_name, name, fields)


def upgrade() -> None:
    _create_clients_table()
    _create_drivers_table()
    _ensure_driver_runtime_columns()
    _create_waybill_jobs_table()
    _ensure_waybill_job_columns()
    _create_waybill_task_logs_table()
    _create_upload_batches_table()

    _create_table_if_missing(
        "driver_runtime_states",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("client_id", sa.Integer(), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("driver_id", sa.Integer(), sa.ForeignKey("drivers.id"), nullable=False),
        sa.Column("state", sa.String(length=64), nullable=False, server_default="active"),
        sa.Column("session_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_auth_at", sa.DateTime(), nullable=True),
        sa.Column("session_expires_at", sa.DateTime(), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(), nullable=True),
        sa.Column("paused_until", sa.DateTime(), nullable=True),
        sa.Column("proxy_key", sa.String(length=128), nullable=True),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column("last_error_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("driver_id", name="uq_driver_runtime_states_driver_id"),
        indexes=[
            ("idx_driver_runtime_states_client_state", ["client_id", "state"]),
            ("idx_driver_runtime_states_next_retry_at", ["next_retry_at"]),
        ],
    )

    _create_table_if_missing(
        "driver_daily_counters",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("business_date", sa.String(length=16), nullable=False),
        sa.Column("client_id", sa.Integer(), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("driver_id", sa.Integer(), sa.ForeignKey("drivers.id"), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("successes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("last_success_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "business_date",
            "client_id",
            "driver_id",
            name="uq_driver_daily_counters_scope",
        ),
        indexes=[("idx_driver_daily_counters_client_date", ["client_id", "business_date"])],
    )

    _create_table_if_missing(
        "driver_session_metadata",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("client_id", sa.Integer(), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("driver_id", sa.Integer(), sa.ForeignKey("drivers.id"), nullable=False),
        sa.Column("session_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("auth_state_path", sa.String(length=512), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("csrf_token", sa.String(length=512), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("last_auth_result", sa.String(length=64), nullable=True),
        sa.Column("last_auth_at", sa.DateTime(), nullable=True),
        sa.Column("proxy_key", sa.String(length=128), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("driver_id", name="uq_driver_session_metadata_driver_id"),
        indexes=[("idx_driver_session_metadata_client_driver", ["client_id", "driver_id"])],
    )

    _create_table_if_missing(
        "waybill_attempts",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("attempt_id", sa.String(length=64), nullable=False),
        sa.Column("job_id", sa.String(length=100), nullable=False),
        sa.Column("client_id", sa.Integer(), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("driver_id", sa.Integer(), sa.ForeignKey("drivers.id"), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("attempt_type", sa.String(length=32), nullable=False, server_default="submit"),
        sa.Column("result", sa.String(length=64), nullable=False, server_default="unknown_error"),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("reason_code", sa.String(length=64), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("session_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("proxy_key", sa.String(length=128), nullable=True),
        sa.Column("response_excerpt", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("attempt_id", name="uq_waybill_attempts_attempt_id"),
        indexes=[
            ("idx_waybill_attempts_job_id", ["job_id"]),
            ("idx_waybill_attempts_driver_id_created", ["driver_id", "created_at"]),
            ("idx_waybill_attempts_result", ["result"]),
        ],
    )

    _create_table_if_missing(
        "domain_events",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("client_id", sa.Integer(), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("driver_id", sa.Integer(), sa.ForeignKey("drivers.id"), nullable=True),
        sa.Column("job_id", sa.String(length=100), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("event_id", name="uq_domain_events_event_id"),
        indexes=[("idx_domain_events_type_created", ["event_type", "created_at"])],
    )

    _create_table_if_missing(
        "proxy_endpoints",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("client_id", sa.Integer(), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("proxy_key", sa.String(length=128), nullable=False),
        sa.Column("endpoint_url", sa.String(length=512), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_healthy", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_success_at", sa.DateTime(), nullable=True),
        sa.Column("last_failure_at", sa.DateTime(), nullable=True),
        sa.Column("cooldown_until", sa.DateTime(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("client_id", "proxy_key", name="uq_proxy_endpoints_scope"),
        indexes=[("idx_proxy_endpoints_health", ["client_id", "is_active", "is_healthy"])],
    )


def downgrade() -> None:
    op.drop_index("idx_proxy_endpoints_health", table_name="proxy_endpoints")
    op.drop_table("proxy_endpoints")
    op.drop_index("idx_domain_events_type_created", table_name="domain_events")
    op.drop_table("domain_events")
    op.drop_index("idx_waybill_attempts_result", table_name="waybill_attempts")
    op.drop_index("idx_waybill_attempts_driver_id_created", table_name="waybill_attempts")
    op.drop_index("idx_waybill_attempts_job_id", table_name="waybill_attempts")
    op.drop_table("waybill_attempts")
    op.drop_index("idx_driver_session_metadata_client_driver", table_name="driver_session_metadata")
    op.drop_table("driver_session_metadata")
    op.drop_index("idx_driver_daily_counters_client_date", table_name="driver_daily_counters")
    op.drop_table("driver_daily_counters")
    op.drop_index("idx_driver_runtime_states_next_retry_at", table_name="driver_runtime_states")
    op.drop_index("idx_driver_runtime_states_client_state", table_name="driver_runtime_states")
    op.drop_table("driver_runtime_states")
    op.drop_index("ix_waybill_jobs_terminal_reason", table_name="waybill_jobs")
    op.drop_index("ix_waybill_jobs_priority", table_name="waybill_jobs")
    op.drop_index("ix_waybill_jobs_business_date", table_name="waybill_jobs")
    op.drop_index("ix_waybill_jobs_correlation_id", table_name="waybill_jobs")
    op.drop_column("waybill_jobs", "terminal_reason")
    op.drop_column("waybill_jobs", "submit_after")
    op.drop_column("waybill_jobs", "next_retry_at")
    op.drop_column("waybill_jobs", "priority")
    op.drop_column("waybill_jobs", "business_date")
    op.drop_column("waybill_jobs", "correlation_id")
    op.drop_index("ix_drivers_last_error_code", table_name="drivers")
    op.drop_index("ix_drivers_runtime_status", table_name="drivers")
    op.drop_column("drivers", "last_error_code")
    op.drop_column("drivers", "last_session_expires_at")
    op.drop_column("drivers", "last_auth_at")
    op.drop_column("drivers", "runtime_status")
