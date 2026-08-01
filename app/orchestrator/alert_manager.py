"""
Alert Manager for creating, deduplicating, broadcasting, and managing admin alerts.
"""

from datetime import UTC, datetime
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.alerts import alert_manager as webhook_alert_manager
from app.models.admin import AdminAlert
from app.realtime.events import event_hub

logger = logging.getLogger(__name__)


class AlertManagerService:
    """Service for idempotent admin alert creation and notification dispatch."""

    async def create_alert(
        self,
        session: AsyncSession,
        severity: str,
        category: str,
        message: str,
        dedupe_key: str,
        tenant_id: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> AdminAlert | None:
        """
        Idempotently create an alert using dedupe_key.
        Returns the created alert object, or None if deduplicated.
        """
        stmt = select(AdminAlert).where(AdminAlert.dedupe_key == dedupe_key)
        existing = (await session.execute(stmt)).scalar_one_or_none()
        if existing:
            logger.info("Admin alert deduplicated", extra={"dedupe_key": dedupe_key})
            return existing

        now = datetime.now(UTC).replace(tzinfo=None)
        alert = AdminAlert(
            tenant_id=tenant_id,
            severity=severity.lower(),
            category=category,
            message=message,
            dedupe_key=dedupe_key,
            details=details or {},
            is_acknowledged=False,
            created_at=now,
        )

        try:
            session.add(alert)
            await session.commit()
            await session.refresh(alert)
        except IntegrityError:
            await session.rollback()
            existing = (await session.execute(stmt)).scalar_one_or_none()
            return existing
        except Exception as exc:
            await session.rollback()
            logger.error("Failed to create admin alert: %s", exc)
            raise

        # Send Webhook if high or critical severity
        if alert.severity in ("high", "critical"):
            try:
                webhook_alert_manager.emit(
                    severity=alert.severity,
                    title=f"[{category.upper()}] Admin Alert",
                    payload={
                        "alert_id": alert.id,
                        "tenant_id": alert.tenant_id,
                        "category": alert.category,
                        "message": alert.message,
                        "dedupe_key": alert.dedupe_key,
                        "details": alert.details,
                    },
                )
            except Exception as e:
                logger.warning("Failed to emit webhook alert: %s", e)

        # Broadcast event over Redis Pub/Sub for WebSockets
        try:
            await event_hub.publish(
                {
                    "event_type": "admin_alert_created",
                    "alert_id": alert.id,
                    "tenant_id": alert.tenant_id,
                    "severity": alert.severity,
                    "category": alert.category,
                    "message": alert.message,
                    "dedupe_key": alert.dedupe_key,
                    "created_at": alert.created_at.isoformat(),
                }
            )
        except Exception as e:
            logger.warning("Failed to publish admin alert websocket event: %s", e)

        return alert

    async def acknowledge_alert(
        self,
        session: AsyncSession,
        alert_id: int,
        admin_id: int | None = None,
    ) -> AdminAlert | None:
        """Mark an admin alert as acknowledged."""
        stmt = select(AdminAlert).where(AdminAlert.id == alert_id)
        alert = (await session.execute(stmt)).scalar_one_or_none()
        if not alert:
            return None

        if not alert.is_acknowledged:
            alert.is_acknowledged = True
            alert.acknowledged_at = datetime.now(UTC).replace(tzinfo=None)
            alert.acknowledged_by = admin_id
            session.add(alert)
            await session.commit()
            await session.refresh(alert)

            try:
                await event_hub.publish(
                    {
                        "event_type": "admin_alert_acknowledged",
                        "alert_id": alert.id,
                        "acknowledged_by": admin_id,
                        "acknowledged_at": alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
                    }
                )
            except Exception as e:
                logger.warning("Failed to publish alert ack event: %s", e)

        return alert

    async def check_repeated_unknown_submission(
        self,
        session: AsyncSession,
        job_id: int,
        consecutive_count: int,
        tenant_id: int | None = None,
    ) -> AdminAlert | None:
        """Create high severity alert if consecutive submission_unknown attempts reach threshold."""
        if consecutive_count < 3:
            return None

        dedupe_key = f"job_{job_id}_submission_unknown_{consecutive_count}"
        return await self.create_alert(
            session=session,
            severity="high",
            category="submission_unknown_repeated",
            message=f"Job #{job_id} encountered submission_unknown {consecutive_count} consecutive times.",
            dedupe_key=dedupe_key,
            tenant_id=tenant_id,
            details={"job_id": job_id, "consecutive_count": consecutive_count},
        )


admin_alert_service = AlertManagerService()
