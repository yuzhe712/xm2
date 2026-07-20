from __future__ import annotations

import pytest

from intelliticket_backend.config import Settings
from intelliticket_backend.errors import AppError
from intelliticket_backend.repositories.mock_ops_data import MockOpsDataRepository
from intelliticket_backend.schemas.tickets import DataMode, DeskId
from intelliticket_backend.services.knowledge import KnowledgeService
from intelliticket_backend.services.knowledge.connectors.feishu import FeishuKnowledgeConnector

SAMPLE_TEXT = "支付服务超时告警，订单量下降"


def test_knowledge_service_uses_mock_connector_by_default() -> None:
    service = KnowledgeService(
        settings=Settings(knowledge_provider="mock"),
        repository=MockOpsDataRepository(),
    )

    sops = service.search_sops(query=SAMPLE_TEXT, service_name="payment-service")
    articles = service.search_support_articles(query="无法访问监控面板", desk_id=DeskId.SUPPORT)

    assert sops
    assert articles
    assert {item["data_mode"] for item in sops + articles} == {DataMode.MOCK.value}
    assert sops[0]["trace_uri"].startswith("mock_data/sop_docs.json")


def test_knowledge_service_fails_closed_when_feishu_is_unconfigured() -> None:
    with pytest.raises(AppError) as exc_info:
        KnowledgeService(
            settings=Settings(
                knowledge_provider="feishu",
                feishu_app_id=None,
                feishu_app_secret=None,
                feishu_drive_folder_url=None,
                feishu_drive_folder_token=None,
            ),
            repository=MockOpsDataRepository(),
        )

    assert exc_info.value.code == "FEISHU_KB_NOT_CONFIGURED"
    assert exc_info.value.details["fallback"] == "disabled"


def test_knowledge_service_builds_feishu_connector_when_drive_folder_is_configured() -> None:
    service = KnowledgeService(
        settings=Settings(
            knowledge_provider="feishu",
            feishu_app_id="cli_test",
            feishu_app_secret="secret_test",
            feishu_drive_folder_url="https://my.feishu.cn/drive/folder/fld-test",
        ),
        repository=MockOpsDataRepository(),
    )

    assert isinstance(service.connector, FeishuKnowledgeConnector)
    assert service.connector.drive_folder_token == "fld-test"
