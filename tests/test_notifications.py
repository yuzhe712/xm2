from __future__ import annotations

import json

import httpx
from pydantic import SecretStr

from intelliticket_backend.services.notifications import (
    DingTalkNotifier,
    NotificationPayload,
    NotificationService,
)


def _test_payload() -> NotificationPayload:
    return NotificationPayload(
        ticket_id="TCK-20260715-ABCDEF12",
        title="支付服务超时告警处理完成",
        summary="疑似根因：数据库连接池耗尽。建议分派给支付系统运维组。",
        priority="P1",
        affected_service="payment-service",
        recommended_actions=[
            "立即检查并临时扩容 payment-db 连接池",
            "查看最近部署 diff，确认是否有连接泄漏",
        ],
        ticket_url=None,
    )


# ---------------------------------------------------------------------------
# DingTalkNotifier
# ---------------------------------------------------------------------------


class FakeDingTalkTransport(httpx.BaseTransport):
    """返回钉钉 webhook 成功响应。"""

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            json={"errcode": 0, "errmsg": "ok"},
        )


class FakeDingTalkErrorTransport(httpx.BaseTransport):
    """返回钉钉 webhook 错误响应。"""

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            json={"errcode": 300001, "errmsg": "token is not exist"},
        )


def test_dingtalk_sends_markdown_on_success() -> None:
    notifier = DingTalkNotifier(
        webhook_url=SecretStr("https://oapi.dingtalk.com/robot/send?access_token=test"),
        http_client=httpx.Client(transport=FakeDingTalkTransport()),
    )
    result = notifier.send(_test_payload())
    assert result.channel == "dingtalk"
    assert result.status == "sent"


def test_dingtalk_skips_when_webhook_url_empty() -> None:
    notifier = DingTalkNotifier(webhook_url=SecretStr(""))
    result = notifier.send(_test_payload())
    assert result.channel == "dingtalk"
    assert result.status == "skipped"
    assert "未配置" in (result.message or "")


def test_dingtalk_returns_failed_on_api_error() -> None:
    notifier = DingTalkNotifier(
        webhook_url=SecretStr("https://oapi.dingtalk.com/robot/send?access_token=bad"),
        http_client=httpx.Client(transport=FakeDingTalkErrorTransport()),
    )
    result = notifier.send(_test_payload())
    assert result.channel == "dingtalk"
    assert result.status == "failed"
    assert result.message is not None
    assert "300001" in result.message


def test_dingtalk_builds_correct_markdown_body() -> None:
    captured: list[bytes] = []

    class CaptureTransport(httpx.BaseTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            captured.append(request.content)
            return httpx.Response(status_code=200, json={"errcode": 0, "errmsg": "ok"})

    notifier = DingTalkNotifier(
        webhook_url=SecretStr("https://oapi.dingtalk.com/robot/send?access_token=test"),
        http_client=httpx.Client(transport=CaptureTransport()),
    )
    notifier.send(_test_payload())

    assert len(captured) == 1
    body = json.loads(captured[0].decode("utf-8"))
    assert body["msgtype"] == "markdown"
    assert "支付服务超时告警处理完成" in body["markdown"]["title"]
    assert "疑似根因" in body["markdown"]["text"]
    assert "payment-db" in body["markdown"]["text"]


def test_dingtalk_truncates_long_messages() -> None:
    long_actions = [f"动作 {i}: " + "测试内容 " * 100 for i in range(30)]
    payload = NotificationPayload(
        ticket_id="TCK-20260715-ABCDEF12",
        title="测试",
        summary="测试",
        priority="P3",
        affected_service=None,
        recommended_actions=long_actions,
    )
    notifier = DingTalkNotifier(
        webhook_url=SecretStr("https://oapi.dingtalk.com/robot/send?access_token=test"),
        http_client=httpx.Client(transport=FakeDingTalkTransport()),
    )
    result = notifier.send(payload)
    assert result.status == "sent"


# ---------------------------------------------------------------------------
# NotificationService
# ---------------------------------------------------------------------------


def test_notification_service_sends_to_all_channels() -> None:
    notifier1 = DingTalkNotifier(
        webhook_url=SecretStr("https://oapi.dingtalk.com/robot/send?access_token=a"),
        http_client=httpx.Client(transport=FakeDingTalkTransport()),
    )
    notifier2 = DingTalkNotifier(
        webhook_url=SecretStr("https://oapi.dingtalk.com/robot/send?access_token=b"),
        http_client=httpx.Client(transport=FakeDingTalkTransport()),
    )
    service = NotificationService(notifiers=[notifier1, notifier2])
    results = service.send(_test_payload())
    assert len(results) == 2
    assert all(r.status == "sent" for r in results)


def test_notification_service_one_channel_fails_others_still_send() -> None:
    good = DingTalkNotifier(
        webhook_url=SecretStr("https://oapi.dingtalk.com/robot/send?access_token=good"),
        http_client=httpx.Client(transport=FakeDingTalkTransport()),
    )
    bad = DingTalkNotifier(
        webhook_url=SecretStr("https://oapi.dingtalk.com/robot/send?access_token=bad"),
        http_client=httpx.Client(transport=FakeDingTalkErrorTransport()),
    )
    service = NotificationService(notifiers=[good, bad])
    results = service.send(_test_payload())
    assert len(results) == 2
    assert any(r.status == "sent" for r in results)
    assert any(r.status == "failed" for r in results)


def test_notification_service_skips_all_when_no_notifiers() -> None:
    service = NotificationService()
    results = service.send(_test_payload())
    assert results == []


def test_notification_service_builds_payload() -> None:
    service = NotificationService()
    payload = service.build_payload(
        ticket_id="TCK-001",
        title="测试",
        summary="摘要",
        priority="P2",
        affected_service="payment-service",
        recommended_actions=["动作1", "动作2"],
        ticket_url="http://example.com/tickets/TCK-001",
    )
    assert payload.ticket_id == "TCK-001"
    assert payload.title == "测试"
    assert len(payload.recommended_actions) == 2
    assert payload.ticket_url == "http://example.com/tickets/TCK-001"
