from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import ValidationError

from intelliticket_backend.errors import AppError
from intelliticket_backend.schemas.mcp_tools import (
    McpToolError,
    ServiceLookupInput,
    ServiceScopedInput,
)
from intelliticket_backend.services.ops_knowledge import OpsKnowledgeService

McpTransport = Literal["stdio", "sse", "streamable-http"]


def create_mcp_server(service: OpsKnowledgeService | None = None) -> FastMCP:
    """创建 IntelliTicket mock 运维知识 MCP server。"""
    ops_service = service or OpsKnowledgeService()
    server = FastMCP(
        "intelliticket-mock-ops-tools",
        instructions=(
            "Mock-only IntelliTicket ops data tools. All returned records and evidence "
            "are explicitly data_mode=mock and do not represent real external systems."
        ),
        host="127.0.0.1",
        port=8765,
        streamable_http_path="/mcp",
    )

    @server.tool(
        name="lookup_service_catalog",
        description="Lookup a service in the local mock service catalog from ticket text or alias.",
    )
    def lookup_service_catalog(query: str) -> dict[str, Any]:
        payload = _validate_input(ServiceLookupInput, {"query": query})
        return _call_tool(lambda: ops_service.lookup_service_catalog(payload.query))

    @server.tool(
        name="get_metric_snapshots",
        description="Return local mock metric snapshots for a known service name.",
    )
    def get_metric_snapshots(service_name: str) -> dict[str, Any]:
        payload = _validate_input(ServiceScopedInput, {"service_name": service_name})
        return _call_tool(lambda: ops_service.get_metric_snapshots(payload.service_name))

    @server.tool(
        name="get_incident_history",
        description="Return local mock historical incidents for a known service name.",
    )
    def get_incident_history(service_name: str) -> dict[str, Any]:
        payload = _validate_input(ServiceScopedInput, {"service_name": service_name})
        return _call_tool(lambda: ops_service.get_incident_history(payload.service_name))

    @server.tool(
        name="get_sop_documents",
        description="Return local mock SOP documents for a known service name.",
    )
    def get_sop_documents(service_name: str) -> dict[str, Any]:
        payload = _validate_input(ServiceScopedInput, {"service_name": service_name})
        return _call_tool(lambda: ops_service.get_sop_documents(payload.service_name))

    return server


def run_mcp_server(transport: McpTransport = "stdio") -> None:
    """运行 MCP server。支持官方 SDK 的 stdio、sse、streamable-http 传输。"""
    create_mcp_server().run(transport=transport)


def _validate_input(
    model: type[ServiceLookupInput | ServiceScopedInput],
    data: dict[str, Any],
) -> Any:
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise ToolError(
            _tool_error_json(
                "MCP_INVALID_INPUT",
                "MCP 工具输入无效",
                {"error": str(exc)},
            )
        ) from exc


def _call_tool(call: Callable[[], Any]) -> dict[str, Any]:
    try:
        result = call()
    except AppError as exc:
        raise ToolError(_tool_error_json(exc.code, exc.message, exc.details)) from exc
    except Exception as exc:
        raise ToolError(
            _tool_error_json(
                "MCP_TOOL_ERROR",
                "MCP 工具执行失败",
                {"error": str(exc)},
            )
        ) from exc
    return result.model_dump(mode="json")


def _tool_error_json(code: str, message: str, details: dict[str, Any]) -> str:
    return json.dumps(
        McpToolError(code=code, message=message, details=details).model_dump(mode="json"),
        ensure_ascii=False,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run IntelliTicket mock ops MCP server.")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default="stdio",
        help="Official MCP SDK transport to use.",
    )
    args = parser.parse_args()
    run_mcp_server(transport=args.transport)


if __name__ == "__main__":
    main()
