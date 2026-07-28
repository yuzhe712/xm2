from __future__ import annotations

from sqlalchemy.orm import Session

from intelliticket_backend.config import Settings, get_settings
from intelliticket_backend.repositories.notifications import NotificationDeliveryRepository
from intelliticket_backend.services.notifications.base import NotificationPayload


def queue_notification(
    session: Session,
    *,
    ticket_id: str,
    target: str,
    event_type: str,
    payload: NotificationPayload,
    settings: Settings | None = None,
) -> str | None:
    configured = settings or get_settings()
    if not configured.dingtalk_enabled:
        return None
    delivery = NotificationDeliveryRepository(session).create(
        ticket_id=ticket_id,
        target=target,
        event_type=event_type,
        payload=payload,
    )
    return delivery.id
