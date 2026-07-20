from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from intelliticket_backend.schemas.tickets import DataMode, Evidence


class ServiceLookupInput(BaseModel):
    """服务目录查询工具输入。"""

    query: str = Field(..., min_length=1, max_length=2000)

    @field_validator("query")
    @classmethod
    def strip_query(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("query 不能为空")
        return stripped


class ServiceScopedInput(BaseModel):
    """服务维度运维数据查询工具输入。"""

    service_name: str = Field(..., min_length=1, max_length=200)

    @field_validator("service_name")
    @classmethod
    def strip_service_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("service_name 不能为空")
        return stripped


class McpToolError(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class OpsKnowledgeToolResult(BaseModel):
    tool_name: str
    data_mode: DataMode = DataMode.MOCK
    records: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)


class OpsKnowledgeToolPayload(BaseModel):
    result: OpsKnowledgeToolResult | None = None
    error: McpToolError | None = None
