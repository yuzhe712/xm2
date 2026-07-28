from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from intelliticket_backend.models import NotificationDelivery

if TYPE_CHECKING:
    from intelliticket_backend.services.notifications.base import NotificationPayload


class NotificationDeliveryRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        ticket_id: str,
        target: str,
        event_type: str,
        payload: NotificationPayload,
    ) -> NotificationDelivery:
        delivery = NotificationDelivery(
            ticket_id=ticket_id,
            channel="dingtalk",
            target=target,
            event_type=event_type,
            payload_json={
                "ticket_id": payload.ticket_id,
                "title": payload.title,
                "summary": payload.summary,
                "priority": payload.priority,
                "affected_service": payload.affected_service,
                "recommended_actions": payload.recommended_actions,
                "ticket_url": payload.ticket_url,
                "is_at_all": payload.is_at_all,
            },
        )
        self.session.add(delivery)
        self.session.flush()
        return delivery

    def get(self, delivery_id: str) -> NotificationDelivery | None:
        return self.session.get(NotificationDelivery, delivery_id)

    def mark_dispatched(self, delivery_id: str, task_id: str) -> None:
        delivery = self.get(delivery_id)
        if delivery is not None:
            delivery.celery_task_id = task_id
            delivery.updated_at = datetime.now(UTC)

    def mark_attempt(self, delivery_id: str) -> NotificationDelivery | None:
        delivery = self.get(delivery_id)
        if delivery is None or delivery.status in {"sent", "skipped"}:
            return delivery
        delivery.status = "sending"
        delivery.attempts += 1
        delivery.updated_at = datetime.now(UTC)
        self.session.flush()
        return delivery

    def mark_retry(self, delivery_id: str, message: str) -> None:
        delivery = self.get(delivery_id)
        if delivery is not None:
            delivery.status = "queued"
            delivery.last_error = message[:2000]
            delivery.updated_at = datetime.now(UTC)

    def finish(self, delivery_id: str, status: str, message: str | None = None) -> None:
        delivery = self.get(delivery_id)
        if delivery is None:
            return
        now = datetime.now(UTC)
        delivery.status = status
        delivery.last_error = message[:2000] if message else None
        delivery.sent_at = now if status == "sent" else None
        delivery.updated_at = now
