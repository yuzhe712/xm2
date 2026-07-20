from __future__ import annotations

import logging

from intelliticket_backend.services.notifications.base import (
    NotificationPayload,
    NotificationResult,
    Notifier,
)

logger = logging.getLogger(__name__)


class NotificationService:
    """通知服务：管理多个渠道，best-effort 发送。"""

    def __init__(self, notifiers: list[Notifier] | None = None) -> None:
        self._notifiers: list[Notifier] = notifiers or []

    def send(self, payload: NotificationPayload) -> list[NotificationResult]:
        """向所有已注册渠道发送通知，单个渠道失败不影响其他渠道。"""
        results: list[NotificationResult] = []
        for notifier in self._notifiers:
            try:
                result = notifier.send(payload)
            except Exception:
                logger.exception(
                    "通知渠道 %s 发送异常: ticket_id=%s",
                    notifier.channel,
                    payload.ticket_id,
                )
                result = NotificationResult(
                    channel=notifier.channel,
                    status="failed",
                    message="未预期的发送异常",
                )
            results.append(result)
        sent_count = sum(1 for r in results if r.status == "sent")
        logger.info(
            "通知发送完成: ticket_id=%s channels=%d sent=%d",
            payload.ticket_id,
            len(results),
            sent_count,
        )
        return results

    def build_payload(
        self,
        ticket_id: str,
        title: str,
        summary: str,
        priority: str,
        affected_service: str | None,
        recommended_actions: list[str] | None = None,
        ticket_url: str | None = None,
        is_at_all: bool = False,
    ) -> NotificationPayload:
        return NotificationPayload(
            ticket_id=ticket_id,
            title=title,
            summary=summary,
            priority=priority,
            affected_service=affected_service,
            recommended_actions=recommended_actions or [],
            ticket_url=ticket_url,
            is_at_all=is_at_all,
        )
