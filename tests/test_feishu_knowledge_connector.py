from __future__ import annotations

import httpx
import pytest
from pydantic import SecretStr

from intelliticket_backend.errors import AppError
from intelliticket_backend.schemas.tickets import DataMode, DeskId
from intelliticket_backend.services.knowledge.connectors.feishu import FeishuKnowledgeConnector

FOLDER_URL = "https://my.feishu.cn/drive/folder/fld-test?from=from_copylink"


def _connector(handler) -> FeishuKnowledgeConnector:
    return FeishuKnowledgeConnector(
        app_id=SecretStr("app-id"),
        app_secret=SecretStr("app-secret"),
        base_url="https://open.feishu.cn",
        wiki_space_id=None,
        drive_folder_url=FOLDER_URL,
        timeout_seconds=2.0,
        max_results=5,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def test_feishu_connector_reads_drive_folder_documents() -> None:
    requested_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        if request.url.path.endswith("/tenant_access_token/internal"):
            return httpx.Response(
                200,
                json={"code": 0, "tenant_access_token": "tenant-token", "expire": 7200},
            )
        assert request.headers["Authorization"] == "Bearer tenant-token"
        if request.url.path == "/open-apis/drive/v1/files":
            assert request.url.params["folder_token"] == "fld-test"
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "files": [
                            {
                                "token": "doc-payment-timeout",
                                "name": "支付服务超时处理 SOP",
                                "type": "docx",
                                "url": "https://example.feishu.cn/docx/doc-payment-timeout",
                                "updated_at": "2026-07-18T10:00:00+08:00",
                            }
                        ]
                    },
                },
            )
        if request.url.path == "/open-apis/docx/v1/documents/doc-payment-timeout/raw_content":
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "content": "1. 检查支付服务日志\n2. 检查数据库连接池配置",
                    },
                },
            )
        raise AssertionError(f"unexpected request path: {request.url.path}")

    docs = _connector(handler).search_sops(
        query="支付服务超时",
        service_name="payment-service",
        limit=3,
    )

    assert "/open-apis/search/v2/data/search" not in requested_paths
    assert len(docs) == 1
    doc = docs[0]
    assert doc.data_mode == DataMode.REAL
    assert doc.source_name == "Feishu Drive Folder"
    assert doc.evidence_id == "ev_feishu_doc-payment-timeout"
    assert doc.trace_uri == "https://example.feishu.cn/docx/doc-payment-timeout"
    assert doc.actions[:2] == ["1. 检查支付服务日志", "2. 检查数据库连接池配置"]


def test_feishu_connector_returns_empty_when_drive_document_does_not_match() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/tenant_access_token/internal"):
            return httpx.Response(
                200,
                json={"code": 0, "tenant_access_token": "tenant-token", "expire": 7200},
            )
        if request.url.path == "/open-apis/drive/v1/files":
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "files": [
                            {"token": "doc-vpn", "name": "VPN 连接处理", "type": "docx"}
                        ]
                    },
                },
            )
        if request.url.path == "/open-apis/docx/v1/documents/doc-vpn/raw_content":
            return httpx.Response(200, json={"code": 0, "data": {"content": "重启客户端"}})
        raise AssertionError(f"unexpected request path: {request.url.path}")

    docs = _connector(handler).search_sops(
        query="支付服务超时",
        service_name="payment-service",
        limit=3,
    )

    assert docs == []


def test_feishu_connector_maps_api_errors_without_leaking_secrets() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/tenant_access_token/internal"):
            return httpx.Response(
                200,
                json={"code": 0, "tenant_access_token": "tenant-token", "expire": 7200},
            )
        return httpx.Response(200, json={"code": 1061004, "msg": "forbidden"})

    with pytest.raises(AppError) as exc_info:
        _connector(handler).search_support_articles(
            query="无法访问监控面板",
            desk_id=DeskId.SUPPORT,
            limit=3,
        )

    assert exc_info.value.code == "FEISHU_KB_UNAVAILABLE"
    details = str(exc_info.value.details)
    assert "app-secret" not in details
    assert "tenant-token" not in details
    assert "fld-test" not in details
