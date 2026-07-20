from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True)
class NotificationPayload:
    """通知内容，与渠道无关。"""

    ticket_id: str
    title: str
    summary: str
    priority: str
    affected_service: str | None
    recommended_actions: list[str] = field(default_factory=list)
    ticket_url: str | None = None
    is_at_all: bool = False


@dataclass(frozen=True)
class NotificationResult:
    """单渠道通知发送结果。"""

    channel: str
    status: str  # "sent" | "skipped" | "failed"
    message: str | None = None


class Notifier(ABC):
    """通知渠道抽象。"""

    channel: str

    @abstractmethod
    def send(self, payload: NotificationPayload) -> NotificationResult:
        """发送通知，不抛异常——失败返回 failed 状态。"""
