from __future__ import annotations

import json
import logging

import httpx
from pydantic import SecretStr

from intelliticket_backend.services.notifications.base import (
    NotificationPayload,
    NotificationResult,
    Notifier,
)

logger = logging.getLogger(__name__)

_DINGTALK_MARKDOWN_LIMIT = 20000


class DingTalkNotifier(Notifier):
    """钉钉群机器人 Webhook 通知渠道。

    文档: https://open.dingtalk.com/document/orgapp/custom-bot-send-message
    """

    channel = "dingtalk"

    def __init__(
        self,
        webhook_url: SecretStr,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._webhook_url = webhook_url
        self._http_client = http_client or httpx.Client(timeout=10.0)

    def send(self, payload: NotificationPayload) -> NotificationResult:
        if not self._webhook_url.get_secret_value().strip():
            return NotificationResult(
                channel=self.channel,
                status="skipped",
                message="钉钉 webhook URL 未配置。",
            )
        try:
            body = self._build_markdown(payload)
            response = self._http_client.post(
                self._webhook_url.get_secret_value(),
                headers={"Content-Type": "application/json"},
                content=body,
                timeout=10.0,
            )
            result = response.json()
            errcode = result.get("errcode", -1)
            if errcode == 0:
                logger.info("DingTalk notification sent: ticket_id=%s", payload.ticket_id)
                return NotificationResult(channel=self.channel, status="sent")
            errmsg = result.get("errmsg", "未知错误")
            logger.warning(
                "DingTalk notification failed: ticket_id=%s errcode=%s errmsg=%s",
                payload.ticket_id,
                errcode,
                errmsg,
            )
            return NotificationResult(
                channel=self.channel,
                status="failed",
                message=f"钉钉返回错误: errcode={errcode} errmsg={errmsg}",
            )
        except Exception as exc:
            logger.exception(
                "DingTalk notification exception: ticket_id=%s", payload.ticket_id
            )
            return NotificationResult(
                channel=self.channel,
                status="failed",
                message=f"钉钉发送异常: {exc}",
            )

    def _build_markdown(self, payload: NotificationPayload) -> bytes:
        actions_block = ""
        if payload.recommended_actions:
            action_items = "\n".join(
                f"- {action}" for action in payload.recommended_actions[:5]
            )
            actions_block = f"\n\n{action_items}"

        markdown_text = (
            f"## {payload.title}\n\n"
            f"{payload.summary}"
            f"{actions_block}"
        )
        if len(markdown_text) > _DINGTALK_MARKDOWN_LIMIT:
            markdown_text = (
                markdown_text[:_DINGTALK_MARKDOWN_LIMIT - 50]
                + "\n\n... (内容过长已截断)"
            )
        body: dict = {
            "msgtype": "markdown",
            "markdown": {
                "title": payload.title[:64],
                "text": markdown_text,
            },
        }
        if payload.is_at_all:
            body["at"] = {"isAtAll": True}
        return json.dumps(body, ensure_ascii=False).encode("utf-8")
