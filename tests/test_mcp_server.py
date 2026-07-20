from __future__ import annotations

import json

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from intelliticket_backend.mcp_server import create_mcp_server


def _tool_error_payload(exc: ToolError) -> dict:
    message = str(exc)
    json_start = message.index("{")
    return json.loads(message[json_start:])


@pytest.mark.anyio
async def test_mcp_server_discovers_mock_ops_tools() -> None:
    server = create_mcp_server()

    tools = await server.list_tools()

    assert {tool.name for tool in tools} == {
        "lookup_service_catalog",
        "get_metric_snapshots",
        "get_incident_history",
        "get_sop_documents",
    }


@pytest.mark.anyio
async def test_mcp_server_calls_lookup_service_catalog() -> None:
    server = create_mcp_server()

    _, structured = await server.call_tool(
        "lookup_service_catalog",
        {"query": "线上支付服务"},
    )

    assert structured["tool_name"] == "lookup_service_catalog"
    assert structured["data_mode"] == "mock"
    assert structured["records"][0]["name"] == "payment-service"
    assert structured["evidence_ids"] == ["ev_service_payment_001"]


@pytest.mark.anyio
async def test_mcp_server_calls_metric_snapshots() -> None:
    server = create_mcp_server()

    _, structured = await server.call_tool(
        "get_metric_snapshots",
        {"service_name": "payment-service"},
    )

    assert structured["tool_name"] == "get_metric_snapshots"
    assert "ev_metric_db_pool_001" in structured["evidence_ids"]
    assert {item["data_mode"] for item in structured["evidence"]} == {"mock"}


@pytest.mark.anyio
async def test_mcp_server_rejects_invalid_input() -> None:
    server = create_mcp_server()

    with pytest.raises(ToolError) as exc_info:
        await server.call_tool("get_metric_snapshots", {"service_name": ""})

    error = _tool_error_payload(exc_info.value)
    assert error["code"] == "MCP_INVALID_INPUT"
    assert error["details"]


@pytest.mark.anyio
async def test_mcp_server_maps_service_not_found_error() -> None:
    server = create_mcp_server()

    with pytest.raises(ToolError) as exc_info:
        await server.call_tool("get_sop_documents", {"service_name": "unknown-service"})

    error = _tool_error_payload(exc_info.value)
    assert error["code"] == "MCP_SERVICE_NOT_FOUND"
    assert error["details"]["service_name"] == "unknown-service"
